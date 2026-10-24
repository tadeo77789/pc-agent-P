"""Paula's voice: ElevenLabs text to speech, streamed straight to the speakers."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable, Iterator

import requests

log = logging.getLogger(__name__)

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
PCM_RATE = 22050


# Collect this much audio before playing, so a slow network chunk does not cut the voice.
# Later sentences of the same reply wait less: the pause between them should stay short.
PREBUFFER_SECONDS = 0.25
NEXT_SENTENCE_PREBUFFER_SECONDS = 0.1
# Bluetooth headsets wake up on the first samples and drop them; lead with silence
# when nothing has played for a while.
LEAD_IN_SECONDS = 0.3
WAKE_AFTER_SECONDS = 2.0


def sounddevice_stream(rate: int, device: int | None = None):
    import sounddevice as sd

    return sd.RawOutputStream(
        samplerate=rate, channels=1, dtype="int16", latency="high", device=device
    )


class SoundDevicePlayer:
    def __init__(
        self,
        rate: int = PCM_RATE,
        clock: Callable[[], float] = time.monotonic,
        open_stream: Callable[..., object] = sounddevice_stream,
        device: int | None = None,
    ):
        self._rate = rate
        self._clock = clock
        self._open_stream = open_stream
        self._device = device
        self._last_end: float | None = None

    def lead_in(self) -> bytes:
        idle = self._last_end is None or self._clock() - self._last_end > WAKE_AFTER_SECONDS
        return b"\x00\x00" * int(self._rate * LEAD_IN_SECONDS) if idle else b""

    def __call__(self, chunks: Iterable[bytes], stop: threading.Event) -> None:
        lead_in = self.lead_in()
        prebuffer = PREBUFFER_SECONDS if lead_in else NEXT_SENTENCE_PREBUFFER_SECONDS
        stream = self._open_stream(self._rate, self._device)
        stream.start()
        try:
            for block in buffered(chunks, lead_in, self._rate, stop, prebuffer):
                stream.write(block)
        finally:
            # Esc must cut the voice now, not after the (large) output buffer drains.
            if stop.is_set():
                stream.abort()
            else:
                stream.stop()
            stream.close()
            self._last_end = self._clock()


def buffered(
    chunks: Iterable[bytes],
    lead_in: bytes,
    rate: int,
    stop: threading.Event,
    prebuffer_seconds: float = PREBUFFER_SECONDS,
) -> Iterator[bytes]:
    """Yield whole int16 samples, holding back the first prebuffer_seconds of audio."""
    prebuffer = len(lead_in) + int(rate * prebuffer_seconds) * 2
    pending = lead_in
    started = False
    for chunk in chunks:
        if stop.is_set():
            return
        pending += chunk
        if not started and len(pending) < prebuffer:
            continue
        started = True
        usable = len(pending) - len(pending) % 2
        if usable:
            yield pending[:usable]
            pending = pending[usable:]
    usable = len(pending) - len(pending) % 2
    if usable and not stop.is_set():
        yield pending[:usable]


class Speaker:
    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model_id: str = "eleven_flash_v2_5",
        *,
        speed: float = 1.0,
        session: requests.Session | None = None,
        player: Callable[[Iterable[bytes], threading.Event], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._voice_id = voice_id
        self._model_id = model_id
        self._session = session or requests.Session()
        self._speed = speed
        self._player = player or SoundDevicePlayer()
        self._stop = threading.Event()

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def speak(self, text: str) -> bool:
        """Block until the text is spoken. Return False if it could not be spoken."""
        if not self.enabled or not text.strip():
            return False
        self._stop.clear()
        body: dict = {"text": text, "model_id": self._model_id}
        if self._speed != 1.0:
            # Only sent when changed: the default request never overrides the voice settings.
            body["voice_settings"] = {"speed": self._speed}
        try:
            response = self._session.post(
                API_URL.format(voice_id=self._voice_id),
                params={"output_format": f"pcm_{PCM_RATE}"},
                headers={"xi-api-key": self._api_key, "Accept": "audio/pcm"},
                json=body,
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
