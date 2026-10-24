"""Speech to text with Faster-Whisper, running locally (GPU when available)."""

from __future__ import annotations

import importlib
import logging
import os
import threading
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

# pip wheels that ship the CUDA DLLs CTranslate2 needs (`pip install -e ".[gpu]"`).
CUDA_WHEELS = ("nvidia.cublas", "nvidia.cudnn")


def register_cuda_dlls() -> list[Path]:
    """Make the DLLs from the nvidia-* wheels loadable on Windows."""
    found = []
    for name in CUDA_WHEELS:
        try:
            package = importlib.import_module(name)
        except ImportError:
            continue
        for base in package.__path__:
            bin_dir = Path(base) / "bin"
            if bin_dir.is_dir():
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
                found.append(bin_dir)
    return found


class Transcriber:
    def __init__(self, model_size: str = "small", language: str = "es", device: str = "auto"):
        self._model_size = model_size
        self._language = language
        self._device = device
        self._model = None
        self.device_used: str | None = None
        self._lock = threading.Lock()

    def load(self) -> None:
        """Load the model up front (downloads it the first time)."""
        with self._lock:
            if self._model is not None:
                return
            if self._device in ("auto", "cuda"):
                try:
                    self._model = self._create("cuda", "float16")
                    self.device_used = "cuda"
                except Exception as exc:
                    if self._device == "cuda":
                        raise
                    log.warning("Whisper on GPU unavailable (%s); using CPU", exc)
            if self._model is None:
                self._model = self._create("cpu", "int8")
                self.device_used = "cpu"
            log.info("Whisper '%s' ready on %s", self._model_size, self.device_used)

    def _create(self, device: str, compute_type: str):
        from faster_whisper import WhisperModel

        if device == "cuda":
            register_cuda_dlls()
        model = WhisperModel(self._model_size, device=device, compute_type=compute_type)
        # Missing CUDA libraries only show up on the first real run, so warm up now.
        segments, _ = model.transcribe(np.zeros(8000, dtype=np.float32), language=self._language)
        list(segments)
        return model

    def transcribe(self, audio: np.ndarray) -> str:
        self.load()
        try:
            return self._run(audio)
        except Exception:
            if self.device_used != "cuda" or self._device == "cuda":
                raise
            # GPU out of memory (a game, Qwen) or a driver reset: carry on with the CPU.
            log.exception("Whisper failed on the GPU; switching to CPU")
            with self._lock:
                self._model = self._create("cpu", "int8")
                self.device_used = "cpu"
            return self._run(audio)

    def _run(self, audio: np.ndarray) -> str:
        segments, _ = self._model.transcribe(
            audio, language=self._language, beam_size=1, vad_filter=True
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
