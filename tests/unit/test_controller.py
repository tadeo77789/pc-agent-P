import numpy as np
import pytest

from paula_agent.activation.foreground import ExclusionPolicy, WindowInfo
from paula_agent.controller import NO_REPLY_TEXT, AgentController
from paula_agent.messaging.messages import (
    Action,
    Channel,
    Event,
    Intent,
    Result,
    RobotState,
    Source,
    Status,
)
from paula_agent.ui.window import ChatWindow, StageWindow


class FakeBus:
    def __init__(self):
        self.orders = []
        self.events = []

    def publish_order(self, order):
        self.orders.append(order)

    def publish_event(self, event):
        self.events.append(event)


SPEECH = np.ones(10, dtype=np.float32)


class FakeRecorder:
    def __init__(self, audio=SPEECH):
        self.audio = audio

    def record(self, start_timeout_seconds, cancel):
        return self.audio


class FakeTranscriber:
    def __init__(self, text="abre el navegador"):
        self.text = text

    def transcribe(self, audio):
        return self.text


class FakeSpeaker:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)
        return True

    def stop(self):
        pass


class FakeRunner:
    def __init__(self):
        self.app_names = ["navegador", "spotify"]

    def run(self, action):
        return Event(action_id=action.id, status=Status.OK, output="done")


class FakeWake:
    def __init__(self):
        self.paused = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False


@pytest.fixture
def parts(qapp):
    return {
        "stage": StageWindow(),
        "chat": ChatWindow(),
        "bus": FakeBus(),
        "recorder": FakeRecorder(),
        "transcriber": FakeTranscriber(),
        "speaker": FakeSpeaker(),
        "runner": FakeRunner(),
        "wake_detector": FakeWake(),
        "window": None,
        "opened": [],
    }


def make(parts):
    return AgentController(
        parts["stage"],
        parts["chat"],
        bus=parts["bus"],
        recorder=parts["recorder"],
        transcriber=parts["transcriber"],
        speaker=parts["speaker"],
        runner=parts["runner"],
        wake_detector=parts["wake_detector"],
        exclusion=ExclusionPolicy(),
        foreground=lambda: parts["window"],
        open_settings=lambda: parts["opened"].append(True),
        spawn=lambda work: work(),
        threaded_speech=False,
    )


def state(parts):
    return parts["stage"].robot.state


def reply(order, text="Listo", **kwargs):
    defaults = {
        "id": order.id,
        "status": Status.OK,
        "response_text": text,
        "speak": True,
        "channel": Channel.PC,
        "robot_state": RobotState.SPEAKING,
    }
    defaults.update(kwargs)
    return Result(**defaults)


def test_wake_word_records_and_sends_voice_order(parts):
    controller = make(parts)

    controller.wake_word_heard()

    [order] = parts["bus"].orders
    assert order.source is Source.VOICE
    assert order.text == "abre el navegador"
    assert state(parts) is RobotState.THINKING
    assert parts["wake_detector"].paused


def test_wake_word_ignored_in_excluded_app(parts):
    parts["window"] = WindowInfo("Discord.exe", "Chrome_WidgetWin_1", False)
    controller = make(parts)

    controller.wake_word_heard()

    assert parts["bus"].orders == []


def test_hotkey_works_in_excluded_app_and_marks_source(parts):
    parts["window"] = WindowInfo("Discord.exe", "Chrome_WidgetWin_1", False)
    controller = make(parts)

    controller.hotkey_pressed()

    [order] = parts["bus"].orders
    assert order.source is Source.HOTKEY


def test_silence_goes_back_to_sleep(parts):
    parts["recorder"] = FakeRecorder(audio=None)
    controller = make(parts)

    controller.hotkey_pressed()

    assert parts["bus"].orders == []
    assert state(parts) is RobotState.SLEEPING
    assert not parts["wake_detector"].paused


def test_spoken_result_plays_voice_then_sleeps(parts):
    controller = make(parts)
    controller.wake_word_heard()
    order = parts["bus"].orders[0]

    controller.result_received(reply(order, "Abrí el navegador."))

    assert parts["speaker"].spoken == ["Abrí el navegador."]
    assert state(parts) is RobotState.SLEEPING
    assert parts["chat"].panel.bubbles()[-1].text() == "Abrí el navegador."


def test_question_shows_options_and_confirm_replies_to_it(parts):
    controller = make(parts)
    controller.wake_word_heard()
    order = parts["bus"].orders[0]

    controller.result_received(
        reply(
            order,
            "¿Confirmas?",
            status=Status.QUESTION,
            robot_state=RobotState.QUESTION,
            options=["Sí, confirmo", "No"],
        )
    )
    assert state(parts) is RobotState.QUESTION
    assert parts["chat"].isVisible()

    parts["chat"].panel.option_chosen.emit("Sí, confirmo")

    confirm = parts["bus"].orders[-1]
    assert confirm.intent is Intent.CONFIRM
    assert confirm.payload == {"text": "Sí, confirmo", "reply_to": order.id}


def test_chat_message_sends_chat_order(parts):
    controller = make(parts)  # noqa: F841 (keep it alive: Qt drops its connections)

    parts["chat"].panel.message_sent.emit("hola")

    [order] = parts["bus"].orders
    assert order.source is Source.CHAT
    assert state(parts) is RobotState.THINKING


def test_error_result_without_voice_flashes_angry(parts):
    parts["speaker"] = FakeSpeaker(enabled=False)
    controller = make(parts)
    parts["chat"].panel.message_sent.emit("hola")
    order = parts["bus"].orders[0]

    controller.result_received(
        reply(order, "Falló", status=Status.ERROR, speak=False, robot_state=RobotState.ANGRY)
    )

    assert state(parts) is RobotState.ANGRY


def test_action_runs_and_publishes_event(parts):
    controller = make(parts)

    controller.action_received(Action(order_id="o1", command="system_status", args={}))

    [event] = parts["bus"].events
    assert event.output == "done"


def test_sleep_cloud_pauses_wake_word_until_robot_clicked(parts):
    controller = make(parts)

    parts["stage"].cloud_picked.emit("sleep")
    assert controller.asleep and parts["wake_detector"].paused
    controller.wake_word_heard()
    assert parts["bus"].orders == []

    parts["stage"].robot.clicked.emit()
    assert not controller.asleep and not parts["wake_detector"].paused


def test_commands_cloud_lists_apps(parts):
    controller = make(parts)  # noqa: F841 (keep it alive: Qt drops its connections)

    parts["stage"].cloud_picked.emit("commands")

    assert "navegador, spotify" in parts["chat"].panel.bubbles()[-1].text()


def test_settings_cloud_opens_settings(parts):
    controller = make(parts)  # noqa: F841 (keep it alive: Qt drops its connections)

    parts["stage"].cloud_picked.emit("settings")

    assert parts["opened"] == [True]


def test_no_reply_turns_angry(parts):
    controller = make(parts)
    parts["chat"].panel.message_sent.emit("hola")

    controller._no_reply()

    assert parts["chat"].panel.bubbles()[-1].text() == NO_REPLY_TEXT
    assert state(parts) is RobotState.ANGRY


def test_typing_drops_pending_question(parts):
    controller = make(parts)
    controller.wake_word_heard()
    order = parts["bus"].orders[0]
    controller.result_received(
        reply(
            order,
            "¿Confirmas?",
            status=Status.QUESTION,
            robot_state=RobotState.QUESTION,
            options=["Sí, confirmo", "No"],
        )
    )

    parts["chat"].panel.message_sent.emit("olvídalo")
    new_order = parts["bus"].orders[-1]
    controller.result_received(reply(new_order, "Vale."))

    assert new_order.intent is Intent.CONVERSATION
    assert state(parts) is RobotState.SLEEPING
    assert parts["chat"].panel._options_box.isHidden()


def test_confirm_reply_uses_original_order_id(parts):
    controller = make(parts)
    controller.wake_word_heard()
    order = parts["bus"].orders[0]
    controller.result_received(
        reply(
            order,
            "¿Confirmas?",
            status=Status.QUESTION,
            robot_state=RobotState.QUESTION,
            options=["Sí, confirmo", "No"],
        )
    )
    parts["chat"].panel.option_chosen.emit("Sí, confirmo")

    controller.result_received(reply(order, "Apagando."))

    assert parts["speaker"].spoken[-1] == "Apagando."
    assert state(parts) is RobotState.SLEEPING


def test_late_reply_is_shown_but_does_not_change_state(parts):
    controller = make(parts)
    parts["chat"].panel.message_sent.emit("hola")
    order = parts["bus"].orders[0]
    controller._no_reply()

    controller.result_received(reply(order, "Llegué tarde"))

    assert parts["speaker"].spoken == []
    assert parts["chat"].panel.bubbles()[-1].text() == "Llegué tarde"
    assert state(parts) is RobotState.ANGRY


def test_speaker_exception_returns_to_idle(parts):
    class BrokenSpeaker(FakeSpeaker):
        def speak(self, text):
            raise RuntimeError("audio device gone")

    parts["speaker"] = BrokenSpeaker()
    controller = make(parts)
    controller.wake_word_heard()

    controller.result_received(reply(parts["bus"].orders[0]))

    assert state(parts) is RobotState.SLEEPING
    assert not parts["wake_detector"].paused


def test_chat_reply_while_transcribing_is_accepted(parts):
    controller = make(parts)

    class ChattyTranscriber:
        def transcribe(self, audio):
            # The user types while Whisper works, and the hub answers right away.
            parts["chat"].panel.message_sent.emit("mejor por chat")
            controller.result_received(reply(parts["bus"].orders[-1], "Hecho."))
            return "texto de voz"

    controller._transcriber = ChattyTranscriber()
    controller.wake_word_heard()

    assert [o.source for o in parts["bus"].orders] == [Source.CHAT]
    assert parts["speaker"].spoken == ["Hecho."]
    assert state(parts) is RobotState.SLEEPING
    assert not controller._thinking_timer.isActive()


def test_partials_are_spoken_as_they_arrive_and_not_repeated(parts):
    controller = make(parts)
    controller.wake_word_heard()
    order = parts["bus"].orders[0]

    controller.result_received(reply(order, "Hola, Ola.", status=Status.PENDING, partial=True))
    assert state(parts) is RobotState.SPEAKING
    assert parts["speaker"].spoken == ["Hola, Ola."]
    controller.result_received(reply(order, "Todo va bien.", status=Status.PENDING, partial=True))
    controller.result_received(reply(order, "Hola, Ola. Todo va bien."))

    assert parts["speaker"].spoken == ["Hola, Ola.", "Todo va bien."]
    assert state(parts) is RobotState.SLEEPING
    assistant_bubbles = [b.text() for b in parts["chat"].panel.bubbles() if b.role == "assistant"]
    assert assistant_bubbles[-1] == "Hola, Ola. Todo va bien."
    assert assistant_bubbles.count("Hola, Ola. Todo va bien.") == 1


def test_final_error_after_partials_is_spoken(parts):
    controller = make(parts)
    controller.wake_word_heard()
    order = parts["bus"].orders[0]

    controller.result_received(reply(order, "Claro, lo abro.", status=Status.PENDING, partial=True))
    controller.result_received(
        reply(order, "No pude abrirlo.", status=Status.ERROR, robot_state=RobotState.ANGRY)
    )

    assert parts["speaker"].spoken == ["Claro, lo abro.", "No pude abrirlo."]


def test_late_partials_are_ignored(parts):
    controller = make(parts)
    parts["chat"].panel.message_sent.emit("hola")
    order = parts["bus"].orders[0]
    controller._no_reply()
    bubbles = len(parts["chat"].panel.bubbles())

    controller.result_received(reply(order, "Tarde.", status=Status.PENDING, partial=True))

    assert len(parts["chat"].panel.bubbles()) == bubbles
    assert parts["speaker"].spoken == []
