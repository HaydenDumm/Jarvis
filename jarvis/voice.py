# Voice commands, offline: the talk button (or Alt+J) starts recording from the
# default microphone, pressing it again stops, and faster-whisper turns the
# speech into text on this PC (its model downloads once, then stays loaded).
# The text then goes to Jarvis as if typed.
import threading

import bpy

from . import deps

SAMPLE_RATE = 16000

_stream = None
_chunks = []
_model = None
_model_name = ""
state = "idle"  # idle, recording, transcribing, loading
last_error = ""


def recording() -> bool:
	return state == "recording"


def start() -> None:
	global _stream, state, last_error
	if state != "idle":
		return
	if not deps.voice_ready():
		last_error = "Install the voice packages first (Preferences > Add-ons > Jarvis)."
		return
	import sounddevice
	_chunks.clear()
	last_error = ""

	def collect(indata, frames, time, status):
		_chunks.append(indata.copy())

	try:
		_stream = sounddevice.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=collect)
		_stream.start()
		state = "recording"
	except Exception as error:
		last_error = "No microphone: %s" % error
		_stream = None


def stop(model_name: str, done) -> None:
	"""Stops recording and transcribes in the background; done(text) runs on the main thread."""
	global _stream, state
	if state != "recording":
		return
	_stream.stop()
	_stream.close()
	_stream = None
	state = "transcribing"
	chunks = list(_chunks)
	threading.Thread(target=_transcribe, args=(chunks, model_name, done), daemon=True).start()


def _transcribe(chunks, model_name, done) -> None:
	global _model, _model_name, state, last_error
	text = ""
	try:
		import numpy
		from faster_whisper import WhisperModel
		if _model is None or _model_name != model_name:
			state = "loading"
			_model = WhisperModel(model_name, device="cpu", compute_type="int8")
			_model_name = model_name
			state = "transcribing"
		if chunks:
			audio = numpy.concatenate(chunks)[:, 0]
			segments, _ = _model.transcribe(audio, language="en", beam_size=1, vad_filter=True)
			text = " ".join(segment.text.strip() for segment in segments).strip()
	except Exception as error:
		last_error = "Transcribing failed: %s" % error
	finally:
		state = "idle"
		bpy.app.timers.register(lambda: (done(text), None)[1], first_interval=0.0)
