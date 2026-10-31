# Blender's side of a Claude Code session: the work queue that runs Claude
# Code's tool calls (from the bridge's threads) on Blender's main thread, where
# bpy may be used, and the log the Blarvis panel shows. A timer pumps the queue.
import queue

import bpy


class Session:
	def __init__(self):
		self.log = []     # (who, text) lines for the panel
		self._jobs = queue.Queue()
		self._shown = 0   # log lines the panel has drawn

	def on_main_thread(self, name: str, work, timeout: float = None):
		"""Runs work() on Blender's main thread and waits: (result, failed)."""
		done = queue.Queue(maxsize=1)
		self._jobs.put((name, work, done))
		try:
			return done.get(timeout=timeout)
		except queue.Empty:
			return ("%s timed out (is Blender busy?)" % name, True)

	def pump(self) -> float:
		"""Runs the waiting calls (a timer, every 50 ms)."""
		ran = False
		while True:
			try:
				name, work, done = self._jobs.get_nowait()
			except queue.Empty:
				break
			try:
				done.put((work(), False))
			except Exception as error:
				done.put(("%s failed: %s" % (name, error), True))
			ran = True
		if ran or len(self.log) != self._shown:
			self._shown = len(self.log)
			for window in bpy.context.window_manager.windows:
				for area in window.screen.areas:
					area.tag_redraw()
		return 0.05


session = Session()
