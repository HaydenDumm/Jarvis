r"""Headless test of Jarvis, without calling the Claude API.

Run by tests/run_tests.py (which installs Jarvis into an isolated Blender profile
first, so your own Blender settings are untouched):

  python tests/run_tests.py [--blender PATH] [--profile some_profile.json]

It builds the test scene with the generic defaults and with a full profile,
builds with every tool, saves a new component into a fresh asset library and
appends it back, installs the Claude SDK, and runs the Claude tool loop against
a stand-in client. With --profile, it also builds that profile's test scene and
lists its assets. Prints JARVIS_TEST OK when every check passes.
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
pkg = next(n for n in bpy.context.preferences.addons.keys() if n.endswith("jarvis"))
tools = import_module(pkg + ".tools")
kit = import_module(pkg + ".kit")
library = import_module(pkg + ".library")
agent = import_module(pkg + ".agent")
reference = import_module(pkg + ".reference")
deps = import_module(pkg + ".deps")
profile = import_module(pkg + ".profile")
prefs = bpy.context.preferences.addons[pkg].preferences
failures = []


def check(ok, what):
	print(("PASS " if ok else "FAIL ") + what)
	if not ok:
		failures.append(what)


# With no profile: generic defaults, assets in Jarvis's own folder
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
definitions = tools.definitions()
check(any("ivory" in json.dumps(t) for t in definitions) and definitions is tools.definitions(), "tool schemas list the profile's palette, the same list each request")
check("Test project" in agent.system_prompt() and "Keep it simple." in agent.system_prompt(), "the system prompt carries the profile's conventions")

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

# The Claude loop, with a stand-in client
if not deps.text_ready():
	deps.install(deps.TEXT_PACKAGES)
	while deps.installing():
		time.sleep(0.5)
	print("\n".join(deps.log()[-3:]))
check(deps.text_ready(), "the Claude SDK installs into Jarvis's folder")
calls = []
script = [
	types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="Putting a box there."),
		types.SimpleNamespace(type="tool_use", id="tool_1", name="make_box", input={"name": "agent_box", "size": [1, 1, 1], "material": "purple"})], stop_reason="tool_use"),
	types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="Done: a purple box.")], stop_reason="end_turn"),
]


def create(**kwargs):
	calls.append(kwargs)
	return script[len(calls) - 1]


session = agent.session
session._client = types.SimpleNamespace(beta=types.SimpleNamespace(messages=types.SimpleNamespace(create=create)))
session._key = ""
session.send("Put a purple box at the origin")
deadline = time.time() + 20
while (session.busy or not session._jobs.empty()) and time.time() < deadline:
	session.pump()
	time.sleep(0.02)
session.pump()
check(bpy.data.objects.get("agent_box") is not None, "a tool call from Claude builds in the scene on the main thread")
results = [m for m in session.messages if m["role"] == "user" and isinstance(m["content"], list) and m["content"]
	and isinstance(m["content"][0], dict) and m["content"][0].get("type") == "tool_result"]
check(len(calls) == 2 and len(results) == 1 and results[0]["content"][0]["tool_use_id"] == "tool_1" and not results[0]["content"][0]["is_error"], "the tool result goes back to Claude")
check(calls[0]["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in calls[0]["betas"], "Opus requests carry the default refusal fallback")
check(calls[0]["output_config"] == {"effort": "low"} and calls[0]["model"] == "claude-opus-5-5", "Opus 5.5 at low effort by default")
check("Asset library" in calls[0]["messages"][0]["content"][0]["text"] and "Test Drum Set" in calls[0]["messages"][0]["content"][0]["text"], "the first message lists the asset library")
check(any("Done: a purple box." in t for _, t in session.log), "Claude's reply shows in the panel log")
print("JARVIS_TEST", "OK" if not failures else "FAILED: %s" % failures)
