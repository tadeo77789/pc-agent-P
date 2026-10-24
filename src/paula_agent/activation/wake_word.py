"""Local wake word ("Paula" / "Paula Port") with Vosk and a closed grammar.

The recognizer only knows the wake words, so other speech maps to "[unk]".
Audio never leaves this process and nothing is stored: this stream only
decides whether to start an actual recording.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import threading
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

MODEL_NAME = "vosk-model-small-es-0.42"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
SAMPLE_RATE = 16000
RETRY_SECONDS = 2.0


def matches(result: dict, wake_words: list[str], min_confidence: float) -> bool:
    """True when a Vosk result is one of the wake words, confidently heard."""
    text = result.get("text", "").strip()
    if text not in wake_words:
        return False
    words = result.get("result") or []
    return bool(words) and min(w.get("conf", 0.0) for w in words) >= min_confidence


def ensure_model(models_dir: Path) -> Path:
    """Download the small Spanish model the first time (about 40 MB)."""
    target = models_dir / MODEL_NAME
    if target.exists():
        return target
    models_dir.mkdir(parents=True, exist_ok=True)
    log.info("Downloading Vosk model %s", MODEL_NAME)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "model.zip"
        with urllib.request.urlopen(MODEL_URL) as response, archive.open("wb") as out:
            shutil.copyfileobj(response, out)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(tmp)
        shutil.move(str(Path(tmp) / MODEL_NAME), target)
    return target


class WakeWordDetector:
    def __init__(
        self,
        model_path: Path,
        on_wake: Callable[[], None],
        *,
        wake_words: list[str] | None = None,
        min_confidence: float = 0.85,
        device: int | str | None = None,
    ) -> None:
        self._model_path = model_path
        self._on_wake = on_wake
        self._wake_words = [w.strip().casefold() for w in (wake_words or ["paula", "paula port"])]
        self._min_confidence = min_confidence
        self._device = device
        self._paused = threading.Event()
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run, name="wake-word", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._thread.join(timeout=3)

    def pause(self) -> None:
        """Ignore the wake word (while recording, speaking or asleep)."""
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def _run(self) -> None:
        import sounddevice as sd
        import vosk

        vosk.SetLogLevel(-1)
        model = vosk.Model(str(self._model_path))
        grammar = json.dumps([*self._wake_words, "[unk]"])
        recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE, grammar)
        recognizer.SetWords(True)

        while not self._stopping.is_set():
            if self._paused.is_set():
                # The mic stays closed while paused or asleep.
                self._stopping.wait(0.2)
                continue
            recognizer.Reset()
            try:
                self._listen(sd, recognizer)
            except Exception:
                # Headset unplugged, device busy...: keep retrying instead of dying.
                log.exception("Wake-word microphone failed; retrying in %ss", RETRY_SECONDS)
                self._stopping.wait(RETRY_SECONDS)

    def _listen(self, sd, recognizer) -> None:
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=4000,
            device=self._device,
        ) as stream:
            while not self._stopping.is_set() and not self._paused.is_set():
                data, _ = stream.read(4000)
                if recognizer.AcceptWaveform(bytes(data)):
                    result = json.loads(recognizer.Result())
                    if matches(result, self._wake_words, self._min_confidence):
                        log.info("Wake word heard")
                        self._on_wake()
