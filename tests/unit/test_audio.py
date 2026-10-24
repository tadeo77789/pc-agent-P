import threading

import requests

from paula_agent.audio.recorder import Endpointer
from paula_agent.audio.tts import Speaker


def run(endpointer, levels):
    for i, level in enumerate(levels):
        if endpointer.push(level):
            return i
    return None


def test_endpointer_stops_after_silence_following_speech():
    endpointer = Endpointer(threshold=0.1, silence_seconds=0.3, frame_seconds=0.1)

    stop_at = run(endpointer, [0.0, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0])

    assert stop_at == 5
    assert endpointer.speech_started


def test_endpointer_gives_up_without_speech():
    endpointer = Endpointer(threshold=0.1, start_timeout_seconds=0.5, frame_seconds=0.1)

    stop_at = run(endpointer, [0.0] * 10)

    assert stop_at == 4
    assert not endpointer.speech_started


def test_endpointer_caps_long_speech():
    endpointer = Endpointer(threshold=0.1, max_seconds=1.0, frame_seconds=0.1)

    assert run(endpointer, [0.5] * 20) == 9


class FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(str(self.status))

    def iter_content(self, chunk_size):
        yield b"\x01\x00\x02"
        yield b"\x00"


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.response


def test_speaker_streams_pcm_to_player():
    session = FakeSession(FakeResponse())
    played = []

    def player(chunks, stop):
        played.extend(chunks)

    speaker = Speaker("key", "voice123", session=session, player=player)

    assert speaker.speak("Hola") is True
    url, kwargs = session.requests[0]
    assert "voice123" in url
    assert kwargs["json"] == {"text": "Hola", "model_id": "eleven_flash_v2_5"}
    assert kwargs["params"] == {"output_format": "pcm_22050"}
    assert kwargs["headers"]["xi-api-key"] == "key"
    assert b"".join(played) == b"\x01\x00\x02\x00"


def test_speaker_reports_http_errors():
    speaker = Speaker("key", "v", session=FakeSession(FakeResponse(401)), player=lambda c, s: None)

    assert speaker.speak("Hola") is False


def test_speaker_without_key_is_disabled():
    session = FakeSession(FakeResponse())
    speaker = Speaker("", "v", session=session, player=lambda c, s: None)

    assert speaker.speak("Hola") is False
    assert session.requests == []


def test_stop_interrupts_player():
    seen = threading.Event()

    def player(chunks, stop):
        if stop.is_set():
            seen.set()

    speaker = Speaker("key", "v", session=FakeSession(FakeResponse()), player=player)
    speaker.stop()
    speaker.speak("Hola")

    assert not seen.is_set()  # speak() clears the previous stop request
