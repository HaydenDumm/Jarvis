# Jarvis: model by text or voice with Claude, live in the viewport (README.md).
# The sidebar's Jarvis tab (N panel) takes a request typed or spoken (Alt+J to
# talk, Alt+Shift+J to type in a popup); Claude answers by building in the scene
# with Jarvis's tools (tools.py), from your asset libraries (library.py), in the
# conventions of your project profile (profile.py). New components it makes
# come up in the panel to be named and saved. A few commands run at once,
# without the API: "create a test scene", "undo", "new conversation".
import re

import bpy
from bpy.props import EnumProperty, StringProperty

from . import agent, deps, library, profile, reference, tools, voice

MODEL_ITEMS = [
	("claude-opus-5-5", "Claude Opus 5.5", "The most capable; the default"),
	("claude-sonnet-5-5", "Claude Sonnet 5.5", "Faster replies"),
	("claude-haiku-5-5", "Claude Haiku 5.5", "Fastest and cheapest, for simple placing"),
]
EFFORT_ITEMS = [
	("low", "Low", "Quickest replies (the default)"),
	("medium", "Medium", "More careful"),
	("high", "High", "Most careful, slowest"),
]
WHISPER_ITEMS = [
	("base.en", "Base (English)", "Quick and accurate enough for commands (about 140 MB)"),
	("small.en", "Small (English)", "More accurate, slower (about 460 MB)"),
	("tiny.en", "Tiny (English)", "Fastest (about 75 MB)"),
]

_keymaps = []


class JarvisPreferences(bpy.types.AddonPreferences):
	bl_idname = __package__

	api_key: StringProperty(name="Anthropic API key", subtype="PASSWORD",
		description="Your Claude API key (console.anthropic.com). Empty: uses ANTHROPIC_API_KEY or an `ant auth login` profile")
	model: EnumProperty(name="Model", items=MODEL_ITEMS, default="claude-opus-5-5")
	effort: EnumProperty(name="Effort", items=EFFORT_ITEMS, default="low")
	whisper_model: EnumProperty(name="Voice model", items=WHISPER_ITEMS, default="base.en")
	profile: StringProperty(name="Project profile", subtype="FILE_PATH",
		description="A JSON file with your project's conventions, grid, palette and asset folder (see profiles/example.json). Empty: generic defaults")
	asset_folder: StringProperty(name="Asset folder", subtype="DIR_PATH",
		description="Where the asset libraries live. Empty: the profile's, else Jarvis's own folder")

	def draw(self, context):
		layout = self.layout
		box = layout.box()
		box.label(text="Packages", icon="PACKAGE")
		row = box.row()
		row.label(text="Claude SDK: " + ("installed" if deps.text_ready() else "not installed"))
		row.operator("jarvis.install", text="Install").kind = "text"
		row = box.row()
		row.label(text="Voice (offline): " + ("installed" if deps.voice_ready() else "not installed"))
		row.operator("jarvis.install", text="Install").kind = "voice"
		for line in deps.log()[-8:]:
			box.label(text=line[:120])
		layout.prop(self, "api_key")
		row = layout.row()
		row.prop(self, "model")
		row.prop(self, "effort")
		layout.prop(self, "whisper_model")
		layout.prop(self, "profile")
		try:
			layout.label(text="Project: %s" % profile.current()["name"])
		except Exception as error:
			layout.label(text="The profile couldn't be read: %s" % error, icon="ERROR")
		layout.prop(self, "asset_folder")
		layout.label(text="Assets: %s" % library.folder())


def _prefs(context) -> JarvisPreferences:
	return context.preferences.addons[__package__].preferences


# ---- requests ----

LOCAL = [
	(re.compile(r"\b(create|make|set up|show|build)\b.*\btest scene\b|^test scene$"), "test_scene"),
	(re.compile(r"^(undo|undo that|take that back)$"), "undo"),
	(re.compile(r"^(new conversation|start over|reset)$"), "reset"),
]


def handle(prompt: str) -> None:
	"""A request, typed or spoken: run it here if it's a quick one, else ask Claude."""
	text = prompt.strip()
	plain = text.lower().strip(" .!?")
	for pattern, command in LOCAL:
		if pattern.search(plain):
			agent.session.log.append(("you", text))
			if command == "test_scene":
				footprint = re.search(r"(\d+)\s*x\s*(\d+)", plain)
				size = (int(footprint.group(1)), int(footprint.group(2))) if footprint else (0, 0) # (0: the profile's)
				agent.session.log.append(("jarvis", reference.build(6, size[0], size[1])))
				bpy.ops.ed.undo_push(message="Jarvis: test scene")
			elif command == "undo":
				bpy.ops.ed.undo()
				agent.session.log.append(("jarvis", "Undone."))
			else:
				agent.session.reset()
			return
	agent.session.send(text)


class JARVIS_OT_send(bpy.types.Operator):
	bl_idname = "jarvis.send"
	bl_label = "Send to Jarvis"
	bl_description = "Send the request to Jarvis"

	def execute(self, context):
		wm = context.window_manager
		handle(wm.jarvis_prompt)
		wm.jarvis_prompt = ""
		return {"FINISHED"}


class JARVIS_OT_prompt(bpy.types.Operator):
	bl_idname = "jarvis.prompt"
	bl_label = "Jarvis"
	bl_description = "Type a request to Jarvis (Enter sends it)"

	text: StringProperty(name="", default="")

	def invoke(self, context, event):
		self.text = ""
		return context.window_manager.invoke_props_dialog(self, width=520, confirm_text="Send")

	def draw(self, context):
		self.layout.prop(self, "text", text="")

	def execute(self, context):
		handle(self.text)
		return {"FINISHED"}


class JARVIS_OT_talk(bpy.types.Operator):
	bl_idname = "jarvis.talk"
	bl_label = "Talk to Jarvis"
	bl_description = "Start recording a voice command; press again to stop and send it"

	def execute(self, context):
		if voice.recording():
			model = _prefs(context).whisper_model

			def heard(text):
				if text:
					handle(text)
				elif voice.last_error:
					agent.session.log.append(("jarvis", voice.last_error))
				else:
					agent.session.log.append(("jarvis", "I didn't catch that."))
			voice.stop(model, heard)
		else:
			voice.start()
			if voice.last_error:
				self.report({"WARNING"}, voice.last_error)
		return {"FINISHED"}


class JARVIS_OT_test_scene(bpy.types.Operator):
	bl_idname = "jarvis.test_scene"
	bl_label = "Test scene"
	bl_description = "Reference tiles and the footprint (with the corner cut, road height, a lane and a scale model where your profile has them)"
	bl_options = {"REGISTER", "UNDO"}

	def execute(self, context):
		agent.session.log.append(("jarvis", reference.build()))
		return {"FINISHED"}


class JARVIS_OT_new_chat(bpy.types.Operator):
	bl_idname = "jarvis.new_chat"
	bl_label = "New conversation"
	bl_description = "Forget this conversation (the scene stays)"

	def execute(self, context):
		agent.session.reset()
		return {"FINISHED"}


class JARVIS_OT_install(bpy.types.Operator):
	bl_idname = "jarvis.install"
	bl_label = "Install Jarvis packages"
	bl_description = "Install Jarvis's Python packages into its own folder"

	kind: StringProperty(default="text")

	def execute(self, context):
		deps.install(deps.TEXT_PACKAGES if self.kind == "text" else deps.VOICE_PACKAGES, done=lambda: None)
		return {"FINISHED"}


# ---- saving new components ----

def propose(objects, name, catalog, family, notes, origin):
	wm = bpy.context.window_manager
	wm.jarvis_save_objects = ",".join(objects)
	family = family or library.default_family()
	wm.jarvis_save_name = name
	wm.jarvis_save_catalog = catalog
	wm.jarvis_save_family = family
	wm.jarvis_save_notes = notes
	wm.jarvis_save_origin = origin


class JARVIS_OT_save_asset(bpy.types.Operator):
	bl_idname = "jarvis.save_asset"
	bl_label = "Save component"
	bl_description = "Save it into the asset library under this name"

	def execute(self, context):
		wm = context.window_manager
		objects = [bpy.data.objects.get(n) for n in wm.jarvis_save_objects.split(",") if n]
		try:
			where = library.save(objects, wm.jarvis_save_name.strip(), wm.jarvis_save_catalog.strip(), wm.jarvis_save_family.strip(),
				wm.jarvis_save_notes.strip(), wm.jarvis_save_origin)
		except Exception as error:
			self.report({"ERROR"}, str(error)[:300])
			return {"CANCELLED"}
		agent.session.log.append(("jarvis", "Saved " + where))
		wm.jarvis_save_objects = ""
		return {"FINISHED"}


class JARVIS_OT_skip_asset(bpy.types.Operator):
	bl_idname = "jarvis.skip_asset"
	bl_label = "Skip"
	bl_description = "Don't save it"

	def execute(self, context):
		context.window_manager.jarvis_save_objects = ""
		return {"FINISHED"}


# ---- the panel ----

class JARVIS_PT_panel(bpy.types.Panel):
	bl_space_type = "VIEW_3D"
	bl_region_type = "UI"
	bl_category = "Jarvis"
	bl_label = "Jarvis"

	def draw(self, context):
		layout = self.layout
		wm = context.window_manager
		session = agent.session
		if not deps.text_ready():
			box = layout.box()
			box.label(text="Install Jarvis's packages first:", icon="INFO")
			box.operator("jarvis.install", text="Install Claude SDK").kind = "text"
			for line in deps.log()[-4:]:
				box.label(text=line[:60])
		row = layout.row(align=True)
		row.prop(wm, "jarvis_prompt", text="")
		row.operator("jarvis.send", text="", icon="PLAY")
		row = layout.row(align=True)
		talking = voice.state
		row.operator("jarvis.talk", text={"recording": "Stop and send", "transcribing": "Listening...", "loading": "Loading voice..."}.get(talking, "Talk  (Alt+J)"),
			icon="REC" if talking == "recording" else "SPEAKER", depress=talking == "recording")
		row.enabled = talking in ("idle", "recording")
		row = layout.row(align=True)
		row.operator("jarvis.test_scene", icon="GRID")
		row.operator("jarvis.new_chat", text="", icon="FILE_NEW")
		status = layout.row()
		status.label(text=("%s  (%s)" % (session.status, _prefs(context).model.replace("claude-", ""))), icon="TIME" if session.busy else "CHECKMARK")
		if wm.jarvis_save_objects:
			box = layout.box()
			box.label(text="Save this new component?", icon="ASSET_MANAGER")
			box.prop(wm, "jarvis_save_name", text="Name")
			box.prop(wm, "jarvis_save_catalog", text="Catalog")
			box.prop(wm, "jarvis_save_family", text="Family")
			box.prop(wm, "jarvis_save_notes", text="Notes")
			box.prop(wm, "jarvis_save_origin", text="Origin")
			row = box.row()
			row.operator("jarvis.save_asset", icon="CHECKMARK")
			row.operator("jarvis.skip_asset", icon="X")
		log = layout.box()
		for who, text in session.log[-12:]:
			first = True
			for chunk in _wrap(text, 44):
				log.label(text=chunk, icon=("USER" if who == "you" else "LIGHT") if first else "BLANK1")
				first = False


def _wrap(text: str, width: int) -> list:
	lines = []
	for paragraph in text.splitlines() or [""]:
		while len(paragraph) > width:
			cut = paragraph.rfind(" ", 0, width)
			cut = cut if cut > 0 else width
			lines.append(paragraph[:cut])
			paragraph = paragraph[cut:].lstrip()
		lines.append(paragraph)
	return lines[:12]


def _pump():
	return agent.session.pump()


CLASSES = (JarvisPreferences, JARVIS_OT_send, JARVIS_OT_prompt, JARVIS_OT_talk, JARVIS_OT_test_scene, JARVIS_OT_new_chat,
	JARVIS_OT_install, JARVIS_OT_save_asset, JARVIS_OT_skip_asset, JARVIS_PT_panel)


def register():
	deps.enable()
	for cls in CLASSES:
		bpy.utils.register_class(cls)
	wm = bpy.types.WindowManager
	wm.jarvis_prompt = StringProperty(name="Request", description="What should Jarvis do? (Send, or Alt+Shift+J for a popup)")
	wm.jarvis_save_objects = StringProperty()
	wm.jarvis_save_name = StringProperty(name="Name")
	wm.jarvis_save_catalog = StringProperty(name="Catalog")
	wm.jarvis_save_family = StringProperty(name="Family")
	wm.jarvis_save_notes = StringProperty(name="Notes")
	wm.jarvis_save_origin = EnumProperty(name="Origin", items=[("bottom_center", "Bottom middle", ""), ("world_origin", "World origin", ""), ("cursor", "3D cursor", "")])
	tools.propose_hook = propose
	bpy.app.timers.register(_pump, persistent=True)
	config = bpy.context.window_manager.keyconfigs.addon
	if config is not None:
		keymap = config.keymaps.new(name="3D View", space_type="VIEW_3D")
		_keymaps.append((keymap, keymap.keymap_items.new("jarvis.talk", "J", "PRESS", alt=True)))
		_keymaps.append((keymap, keymap.keymap_items.new("jarvis.prompt", "J", "PRESS", alt=True, shift=True)))


def unregister():
	for keymap, item in _keymaps:
		keymap.keymap_items.remove(item)
	_keymaps.clear()
	if bpy.app.timers.is_registered(_pump):
		bpy.app.timers.unregister(_pump)
	tools.propose_hook = None
	wm = bpy.types.WindowManager
	for prop in ("jarvis_prompt", "jarvis_save_objects", "jarvis_save_name", "jarvis_save_catalog", "jarvis_save_family", "jarvis_save_notes", "jarvis_save_origin"):
		if hasattr(wm, prop):
			delattr(wm, prop)
	for cls in reversed(CLASSES):
		bpy.utils.unregister_class(cls)
