"""Blarvis's MCP server for Claude Code (Python's standard library only).

Claude Code runs this; it forwards Claude's tool calls to Blarvis in Blender
over the bridge Blarvis opens on this computer (Blarvis panel > Connect Claude
Code), so you can model with Claude Code on your Claude plan, no API key needed.
Register it once:

  claude mcp add --transport stdio --scope user blarvis -- python C:\\path\\to\\Blarvis\\bridge\\blarvis_mcp.py

It speaks MCP's JSON-RPC over stdin/stdout. The bridge's address and token are
in ~/.blarvis/bridge.json, written by Blarvis when it connects.
"""
import json
import os
import socket
import sys
from pathlib import Path

HOME = Path(os.environ.get("BLARVIS_HOME") or Path.home() / ".blarvis") # (BLARVIS_HOME: for tests)
INFO_FILE = HOME / "bridge.json"
CACHE_FILE = HOME / "tools_cache.json"
VERSION = "0.1.0"

INSTRUCTIONS = """Blarvis lets you model in the user's open Blender scene, live: they watch every change in the viewport.
Call blarvis_context first: it gives Blarvis's modelling rules, the project's conventions and palette, the asset library and the scene.
Build with the tools (prefer library assets and the building tools; run_python only when nothing fits), act at once, and put anything with more than one piece in one batch call.
Use viewport_image only when the user asks to look or a result is uncertain.
When you make a new reusable component, call propose_asset so the user can name and save it.
If a call says Blender isn't connected, ask the user to open Blender's Blarvis tab and click Connect Claude Code."""

NOT_CONNECTED = "Blender isn't connected. In Blender, open the Blarvis tab (N panel) and click Connect Claude Code, then try again."

STATUS_TOOL = {"name": "blarvis_context", "description": "Blarvis's rules, the project's conventions, the asset library and the scene (Blender must be connected).",
	"inputSchema": {"type": "object", "properties": {}, "required": []}}


def _ask(request: dict, timeout: float = 320.0) -> dict:
	"""One request to Blarvis in Blender, or None when it isn't connected."""
	try:
		info = json.loads(INFO_FILE.read_text(encoding="utf-8"))
	except (OSError, ValueError):
		return None
	request = dict(request, token=info.get("token", ""))
	try:
		with socket.create_connection(("127.0.0.1", int(info["port"])), timeout=timeout) as connection:
			connection.sendall((json.dumps(request) + "\n").encode("utf-8"))
			reply = b""
			while not reply.endswith(b"\n"):
				chunk = connection.recv(1 << 20)
				if not chunk:
					break
				reply += chunk
		return json.loads(reply.decode("utf-8"))
	except (OSError, ValueError, KeyError):
		return None


def _tools() -> list:
	reply = _ask({"method": "info"}, timeout=40.0)
	if reply and reply.get("ok"):
		tools = reply["result"]["tools"]
		try:
			HOME.mkdir(parents=True, exist_ok=True)
			CACHE_FILE.write_text(json.dumps(tools), encoding="utf-8")
		except OSError:
			pass
		return tools
	try:
		return json.loads(CACHE_FILE.read_text(encoding="utf-8")) # (the last list Blender gave)
	except (OSError, ValueError):
		return [STATUS_TOOL]


def _call(name: str, arguments: dict) -> dict:
	reply = _ask({"method": "call", "tool": name, "input": arguments or {}})
	if reply is None:
		return {"content": [{"type": "text", "text": NOT_CONNECTED}], "isError": True}
	result = reply.get("result")
	if isinstance(result, dict) and result.get("type") == "image":
		content = [{"type": "image", "data": result["data"], "mimeType": result.get("media_type", "image/png")},
			{"type": "text", "text": result.get("note", "")}]
	else:
		content = [{"type": "text", "text": str(result)}]
	return {"content": content, "isError": not reply.get("ok", False)}


def _send(message: dict) -> None:
	sys.stdout.buffer.write((json.dumps(message) + "\n").encode("utf-8"))
	sys.stdout.buffer.flush()


def main() -> None:
	for line in sys.stdin.buffer:
		try:
			message = json.loads(line)
		except ValueError:
			continue
		method, ident = message.get("method"), message.get("id")
		if ident is None: # (a notification: nothing to answer)
			continue
		params = message.get("params") or {}
		try:
			if method == "initialize":
				result = {"protocolVersion": params.get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}},
					"serverInfo": {"name": "blarvis", "version": VERSION}, "instructions": INSTRUCTIONS}
			elif method == "tools/list":
				result = {"tools": _tools()}
			elif method == "tools/call":
				result = _call(params.get("name", ""), params.get("arguments") or {})
			elif method == "ping":
				result = {}
			else:
				_send({"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "Method not found: %s" % method}})
				continue
			_send({"jsonrpc": "2.0", "id": ident, "result": result})
		except Exception as error: # (one bad request must not stop the server)
			_send({"jsonrpc": "2.0", "id": ident, "error": {"code": -32603, "message": str(error)}})


if __name__ == "__main__":
	main()
