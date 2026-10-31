"""Builds Blarvis, installs it into a throwaway Blender profile and runs tests/test_blarvis.py.

  python tests/run_tests.py [--blender PATH] [--profile some_profile.json]

Your own Blender settings and add-ons are never touched, nor your ~/.blarvis
folder (the bridge's address goes to a temporary BLARVIS_HOME). Needs Python 3
on PATH for the MCP server.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build import build, find_blender  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--blender", default="")
parser.add_argument("--profile", default="", help="also test with this project profile")
options = parser.parse_args()
blender = find_blender(options.blender)
# A short folder: Windows limits paths to 260 characters, and the SDK's are long
work = Path(tempfile.mkdtemp(prefix="jv"))
try:
	package = build(blender, work / "build")
	env = dict(os.environ, BLENDER_USER_RESOURCES=str(work / "user"), BLARVIS_HOME=str(work / "blarvis_home"), BLARVIS_REPO=str(ROOT))
	subprocess.run([blender, "--command", "extension", "install-file", "-r", "user_default", "--enable", str(package)], check=True, env=env)
	result = subprocess.run([blender, "-b", "--python", str(ROOT / "tests" / "test_blarvis.py"), "--", str(work),
		str(Path(options.profile).resolve()) if options.profile else ""], env=env, capture_output=True, text=True)
	lines = [line for line in (result.stdout + result.stderr).splitlines() if line.startswith(("PASS", "FAIL", "BLARVIS_TEST", "Traceback", "  File", "Error"))]
	print("\n".join(lines))
	sys.exit(0 if "BLARVIS_TEST OK" in result.stdout else 1)
finally:
	shutil.rmtree(work, ignore_errors=True)
