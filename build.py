"""Builds Blarvis's installable zip into dist/ (Python's standard library only).

  python build.py [--blender PATH]

Upload dist/blarvis-<version>.zip to a GitHub release; people install it in
Blender with Edit > Preferences > Get Extensions > Install from Disk.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def find_blender(explicit: str = "") -> str:
	if explicit:
		return explicit
	if os.environ.get("BLENDER_EXE"):
		return os.environ["BLENDER_EXE"]
	if shutil.which("blender"):
		return shutil.which("blender")
	for root in (Path("C:/Program Files/Blender Foundation"), Path("/Applications")):
		found = sorted(root.glob("Blender */blender.exe")) + sorted(root.glob("Blender.app/Contents/MacOS/Blender"))
		if found:
			return str(found[-1])
	sys.exit("Blender not found: pass --blender PATH or set BLENDER_EXE.")


def build(blender: str, out_dir: Path) -> Path:
	out_dir.mkdir(parents=True, exist_ok=True)
	subprocess.run([blender, "--command", "extension", "validate", str(ROOT / "blarvis")], check=True)
	subprocess.run([blender, "--command", "extension", "build", "--source-dir", str(ROOT / "blarvis"), "--output-dir", str(out_dir)], check=True)
	version = next(line.split('"')[1] for line in (ROOT / "blarvis" / "blender_manifest.toml").read_text().splitlines() if line.startswith("version"))
	return out_dir / ("blarvis-%s.zip" % version)


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument("--blender", default="")
	options = parser.parse_args()
	print("Built", build(find_blender(options.blender), ROOT / "dist"))
