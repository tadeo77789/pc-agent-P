"""Speech to text with Faster-Whisper, running locally."""

from __future__ import annotations

import logging
import threading

import numpy as np

log = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, model_size: str = "small", language: str = "es") -> None:
        self._model_size = model_size
        self._language = language
        self._model = None
        self._lock = threading.Lock()

    def load(self) -> None:
        """Load the model up front (a few seconds; downloads it the first time)."""
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                log.info("Loading Whisper model '%s'", self._model_size)
                self._model = WhisperModel(self._model_size, device="auto", compute_type="int8")

    def transcribe(self, audio: np.ndarray) -> str:
        self.load()
        segments, _ = self._model.transcribe(
            audio, language=self._language, beam_size=1, vad_filter=True
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
