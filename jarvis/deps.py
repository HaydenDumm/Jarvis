# Jarvis's Python packages: installed with Blender's own Python into the
# extension's user folder (Blender's install folder is read-only), and put on
# sys.path when the add-on loads. Text commands need only `anthropic`; voice
# also needs `faster-whisper` (offline speech to text) and `sounddevice`.
import importlib
import importlib.util
import os
import subprocess
import sys
import threading

import bpy

TEXT_PACKAGES = ["anthropic"]
VOICE_PACKAGES = ["faster-whisper", "sounddevice"]

_install_log = []
_installing = False


def site_dir() -> str:
	return bpy.utils.extension_path_user(__package__, path="site-packages", create=True)


def enable() -> None:
	path = site_dir()
	if path not in sys.path:
		sys.path.insert(0, path)


def has(module: str) -> bool:
	enable()
	return importlib.util.find_spec(module) is not None


def text_ready() -> bool:
	return has("anthropic")


def voice_ready() -> bool:
	return has("faster_whisper") and has("sounddevice")


def installing() -> bool:
	return _installing


def log() -> list:
	return _install_log


def install(packages: list, done=None) -> None:
	"""Installs `packages` in the background (pip into the user folder)."""
	global _installing
	if _installing:
		return
	_installing = True
	_install_log.clear()

	def run():
		global _installing
		try:
			command = [sys.executable, "-m", "pip", "install", "--upgrade", "--target", site_dir(), *packages]
			_install_log.append("Installing " + ", ".join(packages) + " ...")
			process = subprocess.run(command, capture_output=True, text=True, env={**os.environ, "PYTHONNOUSERSITE": "1"})
			lines = (process.stdout + process.stderr).strip().splitlines()
			_install_log.extend(lines[-6:])
			_install_log.append("Done." if process.returncode == 0 else "Install failed (code %d)." % process.returncode)
			importlib.invalidate_caches()
		except Exception as error:  # (shown in the panel)
			_install_log.append("Install failed: %s" % error)
		finally:
			_installing = False
			if done is not None:
				bpy.app.timers.register(lambda: (done(), None)[1], first_interval=0.1)

	threading.Thread(target=run, daemon=True).start()
