"""Microphone capture of one utterance, ending on silence.

Audio is only captured between `record()` being called and the utterance
ending; nothing is kept or sent anywhere else.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
FRAME_SECONDS = 0.03


@dataclass
class Endpointer:
    """Decides when an utterance starts and ends from per-frame loudness."""

    threshold: float = 0.015
    silence_seconds: float = 0.9
    start_timeout_seconds: float = 5.0
    max_seconds: float = 20.0
    frame_seconds: float = FRAME_SECONDS

    def __post_init__(self) -> None:
        self.speech_started = False
        self._frames = 0
        self._silent_frames = 0

    def _reached(self, frames: int, seconds: float) -> bool:
        # Count frames instead of summing floats, which drift below the limit.
        return frames * self.frame_seconds >= seconds - 1e-9

    def push(self, rms: float) -> bool:
        """Feed one frame; return True when recording should stop."""
        self._frames += 1
        if rms >= self.threshold:
            self.speech_started = True
            self._silent_frames = 0
        elif self.speech_started:
            self._silent_frames += 1
        if not self.speech_started:
            return self._reached(self._frames, self.start_timeout_seconds)
        return self._reached(self._silent_frames, self.silence_seconds) or self._reached(
            self._frames, self.max_seconds
        )


class Recorder:
    def __init__(self, *, device: int | str | None = None, threshold: float = 0.015) -> None:
        self._device = device
        self._threshold = threshold

    def record(
        self, *, start_timeout_seconds: float = 5.0, cancel: threading.Event | None = None
    ) -> np.ndarray | None:
        """Return mono float32 audio at 16 kHz, or None if nobody spoke or it was cancelled."""
        endpointer = Endpointer(
            threshold=self._threshold, start_timeout_seconds=start_timeout_seconds
        )
        frames: queue.Queue[np.ndarray] = queue.Queue()
        chunks: list[np.ndarray] = []
        blocksize = int(SAMPLE_RATE * FRAME_SECONDS)

        def callback(indata, frame_count, time_info, status) -> None:
            frames.put(indata[:, 0].copy())

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=blocksize,
            device=self._device,
            callback=callback,
        ):
            while True:
                if cancel is not None and cancel.is_set():
                    return None
                try:
                    frame = frames.get(timeout=1.0)
                except queue.Empty:
                    continue
                chunks.append(frame)
                if endpointer.push(float(np.sqrt(np.mean(frame**2)))):
                    break

        if not endpointer.speech_started:
            return None
        return np.concatenate(chunks)
