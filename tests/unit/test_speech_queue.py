import threading

from paula_agent.audio.speech_queue import SpeechQueue


class RecordingSpeaker:
    def __init__(self):
        self.spoken = []
        self.stopped = 0

    def speak(self, text):
        if text == "boom":
            raise RuntimeError("device gone")
        self.spoken.append(text)

    def stop(self):
        self.stopped += 1


def test_threaded_queue_speaks_in_order_then_reports_done():
    speaker = RecordingSpeaker()
    done = threading.Event()
    speech = SpeechQueue(speaker, done.set)

    for sentence in ("uno", "boom", "dos"):
        speech.say(sentence)
    speech.finish()

    assert done.wait(2)
    assert speaker.spoken == ["uno", "dos"]


def test_stop_cuts_and_reports_done():
    speaker = RecordingSpeaker()
    done = []
    speech = SpeechQueue(speaker, lambda: done.append(True), threaded=False)

    speech.stop()

    assert speaker.stopped == 1
    assert done == [True]


def test_sentence_taken_before_stop_is_not_spoken():
    speaker = RecordingSpeaker()
    speech = SpeechQueue(speaker, lambda: None, threaded=False)
    stale = ("say", "vieja", speech._generation)

    speech.stop()
    speech._handle(*stale)

    assert speaker.spoken == []
