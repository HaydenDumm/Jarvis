# One Jarvis conversation with Claude. A request runs on a worker thread (so
# Blender never freezes): the Claude API's tool-use loop, where each tool call
# Claude makes is handed to Blender's main thread (pump, a timer) and its result
# handed back. The system prompt and tool list never change, so the prompt
# cache holds them; each turn carries the scene as it stands. History is only
# ever appended to (a new conversation starts afresh).
import queue
import threading
import traceback

import bpy

from . import deps, library, profile, tools

SYSTEM = """You are Jarvis, a modelling assistant inside Blender. The user models live and watches every change you make in the viewport, so act at once with your tools; never ask before acting unless the request is truly ambiguous. Reply in one short sentence saying what you did (the user may be talking to you by voice).

Modelling conventions (unless the project's say otherwise): 1 Blender unit is 1 unit of the project's grid; a model's origin is the middle of its footprint on the ground; Z is up and the front is -Y. Keep forms simple and clean, a little more detail than a plain block, never overdesigned.

Work like this:
- Prefer library assets (the first message lists them; list_assets refreshes) and the building tools; stand pieces on what they belong on (on_top_of).
- When you build a new reusable component the library lacks, call propose_asset with a name in the library's style, a catalog and attachment notes; the user names and saves it.
- Use run_python only when no tool can do it; keep scripts short and print what they made.
- If a tool fails, fix the call and try again rather than giving up.
"""


def system_prompt() -> str:
	"""Jarvis's instructions with the project's (the same text every request)."""
	settings = profile.current()
	palette = ", ".join("%s (%s)" % (key, entry[0]) for key, entry in sorted(settings["materials"].items()))
	text = SYSTEM + "\nThe project: %s. A grid tile is %g units; footprints are whole tiles.\nPalette (material keys): %s\n" % (settings["name"], settings["tile"], palette)
	rules = profile.conventions()
	return text + ("\nThe project's conventions:\n" + rules + "\n" if rules else "")


MODELS_WITH_FALLBACK = ("claude-opus-5-5", "claude-sonnet-5-5")


class Session:
	def __init__(self):
		self.messages = []
		self.log = []          # (who, text) lines for the panel
		self.status = "Ready"
		self.busy = False
		self._jobs = queue.Queue()
		self._client = None
		self._assets_sent = False
		self._finished = None # the prompt just answered, for its undo step
		self._shown = 0       # log lines the panel has drawn

	# ---- the panel's side (main thread) ----

	def reset(self):
		if not self.busy:
			self.messages = []
			self._assets_sent = False
			self.log.append(("jarvis", "New conversation."))

	def send(self, prompt: str) -> None:
		prompt = prompt.strip()
		if not prompt or self.busy:
			return
		self.log.append(("you", prompt))
		if not deps.text_ready():
			self.log.append(("jarvis", "Install Jarvis's packages first (Preferences > Add-ons > Jarvis)."))
			return
		content = []
		if not self._assets_sent:
			found = library.assets()
			catalogue = "\n".join("- %s [%s/%s]: %s" % (a["name"], a["family"], a["catalog"], a["notes"]) for a in found) or "(none yet)"
			content.append({"type": "text", "text": "Asset library (%s):\n%s" % (library.folder(), catalogue)})
			self._assets_sent = True
		content.append({"type": "text", "text": tools.scene_summary()})
		content.append({"type": "text", "text": prompt})
		self.messages.append({"role": "user", "content": content})
		self.busy = True
		self.status = "Thinking..."
		self._prompt = prompt
		prefs = bpy.context.preferences.addons[__package__].preferences
		settings = {"model": prefs.model, "effort": prefs.effort, "api_key": prefs.api_key.strip(), "system": system_prompt(), "tools": tools.definitions()}
		threading.Thread(target=self._work, args=(settings,), daemon=True).start()

	def pump(self) -> float:
		"""Runs waiting tool calls on the main thread (a timer, every 50 ms)."""
		ran = False
		while True:
			try:
				job = self._jobs.get_nowait()
			except queue.Empty:
				break
			name, data, done = job
			try:
				job_result = (tools.run(name, data), False)
			except Exception as error:
				job_result = ("%s failed: %s" % (name, error), True)
			done.put(job_result)
			ran = True
		if self._finished is not None:
			# Each command is one undo step (Ctrl+Z takes it back whole)
			try:
				bpy.ops.ed.undo_push(message="Jarvis: " + self._finished[:60])
			except Exception:
				pass
			self._finished = None
			ran = True
		if ran or len(self.log) != self._shown or self.busy:
			self._shown = len(self.log)
			for window in bpy.context.window_manager.windows:
				for area in window.screen.areas:
					area.tag_redraw()
		return 0.05

	# ---- the worker's side ----

	def _call_tool(self, name: str, data: dict):
		done = queue.Queue(maxsize=1)
		self._jobs.put((name, data, done))
		return done.get()

	def _say(self, text: str) -> None:
		self.log.append(("jarvis", text))

	def _work(self, settings: dict) -> None:
		import anthropic
		try:
			if self._client is None or getattr(self, "_key", None) != settings["api_key"]:
				self._client = anthropic.Anthropic(api_key=settings["api_key"]) if settings["api_key"] else anthropic.Anthropic()
				self._key = settings["api_key"]
			extra = {}
			if settings["model"] in MODELS_WITH_FALLBACK:
				# A declined request re-runs on Anthropic's recommended fallback model
				extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
			for _ in range(25): # (tool rounds in one request, at most)
				response = self._client.beta.messages.create(
					model=settings["model"],
					max_tokens=16000,
					system=[{"type": "text", "text": settings["system"]}],
					tools=settings["tools"],
					messages=self.messages,
					output_config={"effort": settings["effort"]},
					cache_control={"type": "ephemeral"},
					**extra,
				)
				self.messages.append({"role": "assistant", "content": response.content})
				for block in response.content:
					if block.type == "text" and block.text.strip():
						self._say(block.text.strip())
				if response.stop_reason == "refusal":
					self._say("Claude declined that request.")
					break
				if response.stop_reason == "max_tokens":
					self._say("That answer ran too long and was cut off; try a smaller step.")
					break
				if response.stop_reason == "pause_turn":
					continue
				uses = [b for b in response.content if b.type == "tool_use"]
				if response.stop_reason != "tool_use" or not uses:
					break
				results = []
				for use in uses:
					self.status = "Running %s..." % use.name
					text, failed = self._call_tool(use.name, dict(use.input))
					results.append({"type": "tool_result", "tool_use_id": use.id, "content": text, "is_error": failed})
					if use.name == "run_python":
						self._say("(script) " + str(use.input.get("summary", "")))
				self.messages.append({"role": "user", "content": results})
				self.status = "Thinking..."
		except anthropic.AuthenticationError:
			self._say("The API key was refused. Set it in Preferences > Add-ons > Jarvis, or ANTHROPIC_API_KEY.")
			self._drop_unanswered()
		except anthropic.RateLimitError:
			self._say("Rate limited by the API; try again in a moment.")
			self._drop_unanswered()
		except anthropic.APIStatusError as error:
			self._say("API error %s: %s" % (error.status_code, error.message))
			self._drop_unanswered()
		except anthropic.APIConnectionError:
			self._say("Couldn't reach the Claude API (network).")
			self._drop_unanswered()
		except Exception:
			self._say("Jarvis hit an error:\n" + traceback.format_exc(limit=2))
			self._drop_unanswered()
		finally:
			self._finished = getattr(self, "_prompt", "")
			self.busy = False
			self.status = "Ready"

	def _drop_unanswered(self) -> None:
		"""After a failed request, the history ends with a turn the API never answered:
		start the next request from a fresh conversation instead of editing it."""
		self.messages = []
		self._assets_sent = False


session = Session()
