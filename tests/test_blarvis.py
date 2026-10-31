r"""Headless test of Blarvis, without calling the Claude API.

Run by tests/run_tests.py (which installs Blarvis into an isolated Blender profile
first, so your own Blender settings are untouched):

  python tests/run_tests.py [--blender PATH] [--profile some_profile.json]

It builds the test scene with the generic defaults and with a full profile,
builds with every tool (and a batch), saves a new component into a fresh asset
library and appends it back, then opens the Claude Code bridge and drives it
through the real MCP server (bridge/blarvis_mcp.py), as Claude Code does. With --profile, it also builds that profile's test scene and
lists its assets. Prints BLARVIS_TEST OK when every check passes.
"""
import json
import shutil
import sys
import time
import types
from importlib import import_module
from pathlib import Path

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
WORK = Path(args[0])
EXTRA_PROFILE = args[1] if len(args) > 1 and args[1] else ""
pkg = next(n for n in bpy.context.preferences.addons.keys() if n.endswith("blarvis"))
tools = import_module(pkg + ".tools")
kit = import_module(pkg + ".kit")
library = import_module(pkg + ".library")
bridge = import_module(pkg + ".bridge")
session = import_module(pkg + ".session").session
reference = import_module(pkg + ".reference")
profile = import_module(pkg + ".profile")
prefs = bpy.context.preferences.addons[pkg].preferences
failures = []


def check(ok, what):
	print(("PASS " if ok else "FAIL ") + what)
	if not ok:
		failures.append(what)


# With no profile: generic defaults, assets in Blarvis's own folder
prefs.profile = ""
prefs.asset_folder = ""
print(reference.build())
check(bpy.data.objects.get("tile_0_0") is not None and bpy.data.objects.get("corner_cut_1_1") is None, "generic test scene: tiles, no corner cut")
check(library.folder().is_dir(), "generic asset folder exists (%s)" % library.folder())

# A full profile, with its own asset folder
assets = WORK / "assets"
shutil.rmtree(assets, ignore_errors=True)
test_profile = WORK / "profile.json"
test_profile.write_text(json.dumps({
	"name": "Test project", "conventions": ["Keep it simple."], "tile": 2.0, "footprint": [2, 2], "road_height": 0.14,
	"corner_inset": 0.82, "lane_width": 1.0, "default_family": "testing", "asset_folder": "assets",
	"materials": {"ivory": ["test_ivory", "ede8db"], "purple": ["test_purple", "945cc7"], "window": ["window", "1c3350"]},
}), encoding="utf-8")
prefs.profile = str(test_profile)
check(profile.current()["name"] == "Test project" and library.folder() == assets.resolve(), "the profile is read, with its asset folder")
print(reference.build())
check(bpy.data.objects.get("corner_cut_1_1") is not None and bpy.data.objects.get("lane") is not None, "profile test scene: corner cut and lane")
print(tools.run("make_box", {"name": "plinth", "size": [3.5, 3.5, 0.14], "material": "ivory", "chamfer": 0.3}))
check(bpy.data.objects["plinth"].data.materials[0].name == "test_ivory", "palette keys make the profile's materials")
print(tools.run("make_drum", {"name": "drum", "sides": 16, "radius": 1.3, "height": 0.62, "material": "ivory", "on_top_of": "plinth"}))
low, high = kit.world_bounds(bpy.data.objects["drum"])
check(abs(low.z - 0.14) < 1e-4 and abs(high.z - 0.76) < 1e-4, "the drum stands on the plinth (%.3f..%.3f)" % (low.z, high.z))
print(tools.run("add_windows", {"target": "drum", "per_face": 1, "width": 0.2, "height": 0.18, "bottom": 0.24}))
check(len(bpy.data.objects["drum_windows"].data.polygons) == 16 * 6, "a pane on each of the 16 faces")
print(tools.run("make_ring", {"name": "parapet", "sides": 16, "outer_radius": 1.34, "width": 0.1, "height": 0.12, "material": "purple", "on_top_of": "drum"}))
print(tools.run("make_dome", {"name": "dome", "sides": 12, "rings": 3, "radius": 0.7, "rise": 0.5, "material": "purple", "on_top_of": "drum"}))
print(tools.run("make_box", {"name": "pier", "size": [0.1, 0.1, 0.6], "material": "ivory", "location": [1.5, 0, 0.14]}))
print(tools.run("duplicate", {"object": "pier", "count": 4, "mode": "radial", "center": [0, 0, 0]}))
check(sum(1 for o in bpy.data.objects if o.name.startswith("pier")) == 4, "radial duplicate makes four in all")
print(tools.run("join", {"objects": ["drum", "parapet"], "name": "drum_set"}))
check(len(bpy.data.objects["drum_set"].data.materials) == 2, "join keeps both materials")
print(tools.run("run_python", {"code": "print(len(bpy.data.objects))", "summary": "count"}))
try:
	tools.run("make_box", {"name": "x", "size": [1, 1, 1], "material": "ivory", "on_top_of": "nope"})
	check(False, "a bad object name raises")
except ValueError as error:
	check("nope" in str(error), "a bad object name raises a clear error")
batched = tools.run("batch", {"steps": [
	{"tool": "make_box", "input": {"name": "b_plinth", "size": [2, 2, 0.14], "material": "ivory", "location": [8, 0, 0]}},
	{"tool": "make_drum", "input": {"name": "b_drum", "sides": 12, "radius": 0.8, "height": 0.5, "material": "ivory", "on_top_of": "b_plinth"}},
	{"tool": "add_windows", "input": {"target": "b_drum", "width": 0.15, "height": 0.15, "bottom": 0.2}}]})
print(batched)
low, high = kit.world_bounds(bpy.data.objects["b_drum"])
check(batched.startswith("1.") and "3. Made b_drum_windows" in batched and abs(low.z - 0.14) < 1e-4, "batch builds three pieces in one call, later steps standing on earlier ones")
stopped = tools.run("batch", {"steps": [{"tool": "make_box", "input": {"name": "b2", "size": [1, 1, 1], "material": "ivory", "on_top_of": "nope"}},
	{"tool": "make_box", "input": {"name": "b3", "size": [1, 1, 1], "material": "ivory"}}]})
check("failed" in stopped and "Stopped" in stopped and bpy.data.objects.get("b3") is None, "a failed step stops the batch, and says so")
definitions = tools.definitions()
check(any("ivory" in json.dumps(t) for t in definitions) and definitions is tools.definitions(), "tool schemas list the profile's palette, the same list each request")
check("Test project" in bridge.rules() and "Keep it simple." in bridge.rules(), "Blarvis's rules carry the profile's conventions")

# Saving a new component, then using it
print(library.save([bpy.data.objects["drum_set"]], "Test Drum Set", "Drums", "", "A drum and its parapet. Origin: its foot."))
saved = library.assets(refresh=True)
check(any(a["name"] == "Test Drum Set" and a["family"] == "testing_kit" for a in saved), "saved into the default family's library and listed")
check("Testing/Drums" in (assets / "blender_assets.cats.txt").read_text(), "its catalog joins the catalog file")
check(library.append("Test Drum Set").asset_data is None, "it appends back as a plain part")
print(tools.run("add_asset", {"name": "Test Drum Set", "on_top_of": "plinth", "location": [6, 0, 0]}))

# A real project's profile, if given
if EXTRA_PROFILE:
	prefs.profile = EXTRA_PROFILE
	print(reference.build())
	print("%d assets in %s" % (len(library.assets(refresh=True)), library.folder()))
	check(profile.current()["name"] != "Generic", "the given profile (%s) loads" % profile.current()["name"])
	prefs.profile = str(test_profile)

# The Claude Code bridge: Blender's side, and the MCP server Claude Code runs
import os
import subprocess
import threading
bridge.start()
check(bridge.running() and bridge.INFO_FILE.is_file() and str(bridge.INFO_FILE).startswith(os.environ.get("BLARVIS_HOME", "?")), "the bridge opens and says where (in BLARVIS_HOME)")
server = subprocess.Popen(["python", str(Path(os.environ["BLARVIS_REPO"]) / "bridge" / "blarvis_mcp.py")],
	stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=dict(os.environ))
replies = {}

def talk():
	requests = [
		{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}},
		{"jsonrpc": "2.0", "method": "notifications/initialized"},
		{"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
		{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "make_box", "arguments": {"name": "bridge_box", "size": [1, 1, 1], "material": "purple"}}},
		{"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "blarvis_context", "arguments": {}}},
		{"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "make_box", "arguments": {"name": "x", "size": [1, 1, 1], "material": "ivory", "on_top_of": "nope"}}},
	]
	for request in requests:
		server.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
		server.stdin.flush()
		if "id" in request:
			replies[request["id"]] = json.loads(server.stdout.readline())

talker = threading.Thread(target=talk, daemon=True)
talker.start()
deadline = time.time() + 60
while talker.is_alive() and time.time() < deadline:
	session.pump()
	time.sleep(0.02)
server.stdin.close()
server.wait(timeout=10)
check(replies.get(1, {}).get("result", {}).get("serverInfo", {}).get("name") == "blarvis", "MCP initialize answers as blarvis")
names = [t["name"] for t in replies.get(2, {}).get("result", {}).get("tools", [])]
check("make_drum" in names and "viewport_image" in names and "blarvis_context" in names, "MCP lists Blarvis's tools from Blender (%d)" % len(names))
check(bpy.data.objects.get("bridge_box") is not None and replies.get(3, {}).get("result", {}).get("isError") is False, "a Claude Code tool call builds in the scene")
context_text = replies.get(4, {}).get("result", {}).get("content", [{}])[0].get("text", "")
check("Test project" in context_text and "Asset library" in context_text and "bridge_box" in context_text, "blarvis_context gives the rules, library and scene")
check(replies.get(5, {}).get("result", {}).get("isError") is True and "nope" in replies[5]["result"]["content"][0]["text"], "a failed call comes back as an error, with its reason")
check(any(who == "claude code" for who, _ in session.log), "Claude Code's calls show in the Blarvis panel")
bridge.stop()
check(not bridge.running() and not bridge.INFO_FILE.exists(), "the bridge closes and removes its address")
print("BLARVIS_TEST", "OK" if not failures else "FAILED: %s" % failures)
