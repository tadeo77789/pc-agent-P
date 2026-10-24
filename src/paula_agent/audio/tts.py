"""Paula's voice: ElevenLabs text to speech, streamed straight to the speakers."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable

import requests

log = logging.getLogger(__name__)

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
PCM_RATE = 22050


def sounddevice_player(chunks: Iterable[bytes], stop: threading.Event) -> None:
    import sounddevice as sd

    with sd.RawOutputStream(samplerate=PCM_RATE, channels=1, dtype="int16") as stream:
        pending = b""
        for chunk in chunks:
            if stop.is_set():
                return
            pending += chunk
            usable = len(pending) - len(pending) % 2  # whole int16 samples only
            stream.write(pending[:usable])
            pending = pending[usable:]


class Speaker:
    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model_id: str = "eleven_flash_v2_5",
        *,
        session: requests.Session | None = None,
        player: Callable[[Iterable[bytes], threading.Event], None] = sounddevice_player,
    ) -> None:
        self._api_key = api_key
        self._voice_id = voice_id
        self._model_id = model_id
        self._session = session or requests.Session()
        self._player = player
        self._stop = threading.Event()

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def speak(self, text: str) -> bool:
        """Block until the text is spoken. Return False if it could not be spoken."""
        if not self.enabled or not text.strip():
            return False
        self._stop.clear()
        try:
            response = self._session.post(
                API_URL.format(voice_id=self._voice_id),
                params={"output_format": f"pcm_{PCM_RATE}"},
                headers={"xi-api-key": self._api_key, "Accept": "audio/pcm"},
                json={"text": text, "model_id": self._model_id},
                stream=True,
                timeout=(5, 30),
            )
            response.raise_for_status()
            self._player(response.iter_content(chunk_size=4096), self._stop)
            return True
        except requests.RequestException as exc:
            log.warning("ElevenLabs failed: %s", exc)
            return False

    def stop(self) -> None:
        self._stop.set()
