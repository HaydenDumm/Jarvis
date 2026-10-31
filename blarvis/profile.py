# The project profile: what you're modelling for. A JSON file (chosen in the
# add-on's preferences; see profiles/example.json) gives the project's name, the
# conventions Claude should follow, its grid and dimensions, its palette of
# materials, where its asset libraries are and a model to show for scale. Any
# field it leaves out comes from DEFAULT, so Blarvis works with no profile at all.
import json
from pathlib import Path

import bpy

DEFAULT = {
	"name": "Generic",
	# Rules for Claude, one per line (units, footprints, style, what to avoid)
	"conventions": [],
	# The grid: a tile's size in Blender units, and a footprint's default size in tiles
	"tile": 1.0,
	"footprint": [2, 2],
	# Optional: the height roads and platforms meet a model at (0: none shown)
	"road_height": 0.0,
	# Optional: models stay inside |x| + |y| <= (width + depth) / 2 - corner_inset
	"corner_inset": None,
	# Optional: a lane this wide in the test scene (0: none)
	"lane_width": 0.0,
	# Palette: key -> [material name, sRGB hex]; Claude picks materials by key
	"materials": {
		"white": ["white", "f2f2f2"],
		"grey": ["grey", "9a9a9a"],
		"dark": ["dark", "2b2b2b"],
		"window": ["window", "1c3350"],
		"red": ["red", "d4554a"],
		"orange": ["orange", "e8913a"],
		"yellow": ["yellow", "e8cf4a"],
		"green": ["green", "5a9e6e"],
		"blue": ["blue", "4a7fc9"],
		"purple": ["purple", "8a62b8"],
		"pink": ["pink", "dd88ad"],
		"brown": ["brown", "8a6446"],
	},
	# The asset libraries' folder, relative to this file (empty: Blarvis's own folder)
	"asset_folder": "",
	# Optional: {"file": a .blend relative to this file, "object": its name} shown
	# in the test scene for scale
	"scale_model": None,
}

_cache = {"key": None, "profile": None}


def path() -> str:
	prefs = bpy.context.preferences.addons[__package__].preferences
	return bpy.path.abspath(prefs.profile) if prefs.profile else ""


def current() -> dict:
	"""The profile in use (re-read when its file changes)."""
	file = path()
	stamp = Path(file).stat().st_mtime if file and Path(file).is_file() else 0
	key = (file, stamp)
	if _cache["key"] != key:
		profile = dict(DEFAULT)
		profile["materials"] = dict(DEFAULT["materials"])
		profile["_dir"] = ""
		if file and Path(file).is_file():
			loaded = json.loads(Path(file).read_text(encoding="utf-8"))
			for field, value in loaded.items():
				profile[field] = value
			profile["_dir"] = str(Path(file).resolve().parent)
		_cache["key"], _cache["profile"] = key, profile
	return _cache["profile"]


def resolve(relative: str) -> Path:
	"""A path from the profile, relative to the profile file."""
	base = current()["_dir"]
	return (Path(base) / relative).resolve() if base else Path(relative).resolve()


def conventions() -> str:
	lines = current()["conventions"]
	return "\n".join("- " + line for line in lines) if isinstance(lines, list) else str(lines)
