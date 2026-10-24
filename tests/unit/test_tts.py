import threading

import pytest

from paula_agent.audio.tts import (
    LEAD_IN_SECONDS,
    PREBUFFER_SECONDS,
    WAKE_AFTER_SECONDS,
    SoundDevicePlayer,
    Speaker,
    buffered,
)

RATE = 1000  # small rate keeps the byte counts readable


def test_audio_is_held_until_the_prebuffer_fills():
    prebuffer = int(RATE * PREBUFFER_SECONDS) * 2
    chunks = [b"\x01" * 100] * 10

    blocks = list(buffered(chunks, b"", RATE, threading.Event()))

    assert len(blocks[0]) >= prebuffer
    assert b"".join(blocks) == b"".join(chunks)


def test_short_reply_is_still_played_whole():
    blocks = list(buffered([b"\x01\x02\x03"], b"", RATE, threading.Event()))

    assert blocks == [b"\x01\x02"]  # whole int16 samples only


def test_lead_in_comes_first():
    blocks = list(buffered([b"\x01" * 1000], b"\x00" * 4, RATE, threading.Event()))

    assert b"".join(blocks).startswith(b"\x00" * 4 + b"\x01")


def test_stop_ends_playback():
    stop = threading.Event()
    stop.set()

    assert list(buffered([b"\x01" * 1000], b"", RATE, stop)) == []


class FakeStream:
    def __init__(self, fail=False):
        self.written = b""
        self.calls = []
        self.fail = fail

    def start(self):
        self.calls.append("start")

    def write(self, block):
        if self.fail:
            raise OSError("device gone")
        self.written += block

    def stop(self):
        self.calls.append("stop")

    def abort(self):
        self.calls.append("abort")

    def close(self):
        self.calls.append("close")


def make_player(stream, now):
    return SoundDevicePlayer(rate=RATE, clock=lambda: now[0], open_stream=lambda rate: stream)


def test_lead_in_only_after_silence():
    now = [100.0]
    stream = FakeStream()
    player = make_player(stream, now)
    silence = b"\x00\x00" * int(RATE * LEAD_IN_SECONDS)

    player([b"\x01" * 1000], threading.Event())

    assert stream.written.startswith(silence + b"\x01")  # nothing played before
    now[0] += WAKE_AFTER_SECONDS / 2
    assert player.lead_in() == b""  # next sentence of the same reply
    now[0] += WAKE_AFTER_SECONDS
    assert player.lead_in() == silence


def test_normal_end_drains_and_stop_aborts():
    stream = FakeStream()
    make_player(stream, [0.0])([b"\x01" * 1000], threading.Event())
    assert stream.calls == ["start", "stop", "close"]

    stream, stop = FakeStream(), threading.Event()
    stop.set()
    make_player(stream, [0.0])([b"\x01" * 1000], stop)
    assert stream.calls == ["start", "abort", "close"]


def test_failed_playback_still_marks_the_end():
    player = make_player(FakeStream(fail=True), [50.0])

    with pytest.raises(OSError):
        player([b"\x01" * 1000], threading.Event())

    assert player.lead_in() == b""


class FakeResponse:
    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        return iter([b"\x00\x00"])


class FakeSession:
    def __init__(self):
        self.bodies = []

    def post(self, url, **kwargs):
        self.bodies.append(kwargs["json"])
        return FakeResponse()


def speak_with(speed):
    session = FakeSession()
    speaker = Speaker("key", "voice", speed=speed, session=session, player=lambda c, s: list(c))
    assert speaker.speak("Hola.")
    return session.bodies[0]


def test_default_speed_keeps_the_voice_settings():
    assert "voice_settings" not in speak_with(1.0)


def test_custom_speed_is_sent():
    assert speak_with(0.9)["voice_settings"] == {"speed": 0.9}
