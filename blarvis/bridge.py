# The Claude Code bridge: how Claude Code drives Blarvis's tools in this Blender.
# Connect starts a small server on this computer only (127.0.0.1, a free port,
# a random token) and writes where it is to ~/.blarvis/bridge.json. The MCP
# server Claude Code runs (bridge/blarvis_mcp.py in the Blarvis repository) reads
# that file and forwards each tool call here, one JSON line each way. Every call
# runs on Blender's main thread through the session's queue, as one undo step,
# and shows in the Blarvis panel.
import json
import os
import secrets
import socketserver
import threading
from pathlib import Path

import bpy

from . import library, profile, tools
from .session import session

INFO_FILE = Path(os.environ.get("BLARVIS_HOME") or Path.home() / ".blarvis") / "bridge.json" # (BLARVIS_HOME: for tests)

RULES = """You are modelling in the user's open Blender scene through Blarvis; they watch every change in the viewport, so act at once with the tools and reply in one short sentence.
Modelling conventions (unless the project's say otherwise): 1 Blender unit is 1 unit of the project's grid; a model's origin is the middle of its footprint on the ground; Z is up and the front is -Y. Keep forms simple and clean, a little more detail than a plain block, never overdesigned.
- Prefer library assets and the building tools; stand pieces on what they belong on (on_top_of).
- Build anything with more than one piece in a single batch call, steps in order from the bottom up.
- When you build a new reusable component the library lacks, call propose_asset with a name in the library's style, a catalog and attachment notes; the user names and saves it in Blender.
- Use run_python only when no tool can do it; keep scripts short and print what they made.
- Use viewport_image only when the user asks to look or a result is uncertain."""

_server = None
_token = ""


def running() -> bool:
	return _server is not None


def port() -> int:
	return _server.server_address[1] if _server is not None else 0


def rules() -> str:
	"""Blarvis's rules with the project's (name, grid, palette, conventions)."""
	settings = profile.current()
	palette = ", ".join("%s (%s)" % (key, entry[0]) for key, entry in sorted(settings["materials"].items()))
	text = RULES + "\n\nThe project: %s. A grid tile is %g units; footprints are whole tiles.\nPalette (material keys): %s\n" % (settings["name"], settings["tile"], palette)
	conventions = profile.conventions()
	return text + ("\nThe project's conventions:\n" + conventions + "\n" if conventions else "")


def _context() -> str:
	found = library.assets()
	catalogue = "\n".join("- %s [%s/%s]: %s" % (a["name"], a["family"], a["catalog"], a["notes"]) for a in found) or "(none yet)"
	return "%s\nAsset library (%s):\n%s\n\n%s" % (rules(), library.folder(), catalogue, tools.scene_summary())


def _info() -> dict:
	defs = [{"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]} for t in tools.definitions()]
	defs.append({"name": "blarvis_context", "description": "Blarvis's modelling rules, the project's conventions and palette, the asset library and the scene as it stands. Read it first, once per conversation.",
		"inputSchema": {"type": "object", "properties": {}, "required": []}})
	return {"tools": defs}


def _run(name: str, data: dict):
	if name == "blarvis_context":
		return _context()
	result = tools.run(name, data)
	session.log.append(("claude code", "%s: %s" % (name, result.get("note", "picture") if isinstance(result, dict) else str(result).splitlines()[0][:120])))
	try:
		bpy.ops.ed.undo_push(message="Blarvis: " + name)
	except Exception:
		pass
	return result


class _Handler(socketserver.StreamRequestHandler):
	def handle(self):
		for line in self.rfile:
			try:
				request = json.loads(line)
			except ValueError:
				break
			if request.get("token") != _token:
				reply = {"ok": False, "result": "Wrong bridge token: reconnect Blarvis in Blender."}
			elif request.get("method") == "info":
				result, failed = session.on_main_thread("info", _info, timeout=30)
				reply = {"ok": not failed, "result": result}
			else:
				name, data = request.get("tool", ""), request.get("input") or {}
				result, failed = session.on_main_thread(name, lambda: _run(name, data), timeout=300)
				reply = {"ok": not failed, "result": result}
			self.wfile.write((json.dumps(reply) + "\n").encode("utf-8"))
			self.wfile.flush()


class _Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
	daemon_threads = True
	allow_reuse_address = True


def start() -> int:
	global _server, _token
	if _server is not None:
		return port()
	_token = secrets.token_hex(16)
	_server = _Server(("127.0.0.1", 0), _Handler)
	threading.Thread(target=_server.serve_forever, daemon=True).start()
	INFO_FILE.parent.mkdir(parents=True, exist_ok=True)
	INFO_FILE.write_text(json.dumps({"port": port(), "token": _token}), encoding="utf-8")
	session.log.append(("blarvis", "Connected for Claude Code (port %d). Ask Claude Code to use Blarvis." % port()))
	return port()


def stop() -> None:
	global _server
	if _server is None:
		return
	_server.shutdown()
	_server.server_close()
	_server = None
	try:
		INFO_FILE.unlink()
	except OSError:
		pass
	session.log.append(("blarvis", "Disconnected from Claude Code."))
