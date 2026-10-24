"""Wires activation, audio, the hub and the UI together.

Inputs arrive from many threads (wake word, hotkey, RabbitMQ, audio workers);
each one is turned into a Qt signal so all state changes happen on the UI thread.
"""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from paula_agent.activation.foreground import ExclusionPolicy, WindowInfo
from paula_agent.audio.speech_queue import SpeechQueue
from paula_agent.conversation import is_farewell
from paula_agent.messaging.messages import Action, Intent, Order, Result, Source, Status
from paula_agent.ui.robot.states import RobotState
from paula_agent.ui.window import ChatWindow, StageWindow

log = logging.getLogger(__name__)

THINKING_TIMEOUT_MS = 60_000
FLASH_MS = {RobotState.SPEAKING: 2000, RobotState.ANGRY: 2500}
# Pause between the end of Paula's voice and listening again, so the tail of her own
# audio (Bluetooth adds latency) is not recorded as the user's answer.
FOLLOW_UP_DELAY_MS = 700
# Follow-ups per activation: background talk (a TV) must not keep the mic open forever.
MAX_FOLLOW_UPS = 5

# User-facing text, Spanish
NO_REPLY_TEXT = "No obtuve respuesta. ¿Está corriendo el hub?"
GOODBYE_TEXT = "¡Hasta luego!"
COMMANDS_TEXT = (
    "Puedo abrir: {apps}. También puedo revisar el estado del PC o apagarlo (te pido "
    "confirmación antes)."
)


def _normalize(text: str) -> str:
    """Collapse whitespace: the hub strips sentences, the final text keeps line breaks."""
    return " ".join(text.split())


def spawn_thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, daemon=True).start()


class AgentController(QObject):
    _wake = Signal()
    _hotkey = Signal()
    _escape = Signal()
    _heard = Signal(str, str)  # source, text ("" when nothing was heard)
    _result = Signal(object)
    _spoken = Signal()

    def __init__(
        self,
        stage: StageWindow,
        chat: ChatWindow,
        *,
        bus,
        recorder,
        transcriber,
        speaker,
        runner,
        wake_detector,
        exclusion: ExclusionPolicy,
        foreground: Callable[[], WindowInfo | None],
        quit_app: Callable[[], None],
        listen_seconds: int = 5,
        conversation_seconds: float = 8.0,
        spawn: Callable[[Callable[[], None]], None] = spawn_thread,
        threaded_speech: bool = True,
    ) -> None:
        super().__init__()
        self._stage = stage
        self._chat = chat
        self._bus = bus
        self._recorder = recorder
        self._transcriber = transcriber
        self._speaker = speaker
        self._runner = runner
        self._wake_detector = wake_detector
        self._exclusion = exclusion
        self._foreground = foreground
        self._quit_app = quit_app
        self._listen_seconds = listen_seconds
        self._conversation_seconds = conversation_seconds
        self._spawn = spawn

        self._busy = False
        self._listening = False
        self._speaking = False
        self._asleep = False
        self._question_id: str | None = None
        # Source of the voice conversation in progress (follow-ups need no wake word).
        self._conversation: Source | None = None
        self._following = False
        self._follow_ups = 0
        # Result ids that answer the order in flight; anything else is a late reply.
        self._expected: set[str] = set()
        # Sentences of the reply in flight that already arrived as partial results.
        self._streamed = ""
        self._stream_bubble = None
        self._muted = False
        self._speech = SpeechQueue(speaker, self._spoken.emit, threaded=threaded_speech)
        self._cancel = threading.Event()
        self._countdown = 0

        self._countdown_timer = QTimer(self, interval=1000, timeout=self._tick)
        self._thinking_timer = QTimer(
            self, singleShot=True, interval=THINKING_TIMEOUT_MS, timeout=self._no_reply
        )
        self._idle_timer = QTimer(self, singleShot=True, timeout=self._idle)
        self._follow_up_timer = QTimer(
            self, singleShot=True, interval=FOLLOW_UP_DELAY_MS, timeout=self._follow_up
        )

        self._wake.connect(self._on_wake)
        self._hotkey.connect(self._on_hotkey)
        self._escape.connect(self._on_escape)
        self._heard.connect(self._on_heard)
        self._result.connect(self._on_result)
        self._spoken.connect(self._on_spoken)
        stage.cloud_picked.connect(self._on_cloud)
        stage.robot.clicked.connect(self._on_robot_clicked)
        stage.robot.drag_finished.connect(self._follow_chat)
        chat.panel.message_sent.connect(self._on_chat_message)
        chat.panel.option_chosen.connect(self._on_option)

    # Thread-safe entry points

    def wake_word_heard(self) -> None:
        self._wake.emit()

    def hotkey_pressed(self) -> None:
        self._hotkey.emit()

    def escape_pressed(self) -> None:
        self._escape.emit()

    def result_received(self, result: Result) -> None:
        self._result.emit(result)

    def action_received(self, action: Action) -> None:
        """Runs on the bus thread; commands do not touch the UI."""
        self._bus.publish_event(self._runner.run(action))

    # Activation

    def _on_wake(self) -> None:
        if self._busy or self._asleep:
            return
        if self._exclusion.is_excluded(self._foreground()):
            log.info("Wake word ignored in excluded app")
            return
        self._follow_ups = 0
        self._listen(Source.VOICE)

    def _on_hotkey(self) -> None:
        if self._busy:
            return
        self._asleep = False
        self._follow_ups = 0
        self._listen(Source.HOTKEY)
        self._countdown = self._listen_seconds
        self._stage.show_listen(self._countdown)
        self._countdown_timer.start()

    def _on_escape(self) -> None:
        waiting = self._follow_up_timer.isActive()
        self._end_conversation()
        if self._listening:
            self._cancel.set()
            self._end_countdown()
        elif self._speaking:
            # Silence the rest of this reply too: later sentences only go to the chat.
            self._muted = True
            self._speech.stop()
        elif waiting:
            # Between the end of a reply and the follow-up recording.
            self._idle()

    def _tick(self) -> None:
        self._countdown -= 1
        if self._countdown <= 0:
            self._end_countdown()
        else:
            self._stage.show_listen(self._countdown)

    def _end_countdown(self) -> None:
        self._countdown_timer.stop()
        self._stage.hide_listen()

    def _listen(self, source: Source, timeout_seconds: float | None = None) -> None:
        timeout = self._listen_seconds if timeout_seconds is None else timeout_seconds
        self._busy = self._listening = True
        self._cancel.clear()
        self._wake_detector.pause()
        self._set_state(RobotState.LISTENING)

        def work() -> None:
            text = ""
            try:
                audio = self._recorder.record(start_timeout_seconds=timeout, cancel=self._cancel)
                if audio is not None and not self._cancel.is_set():
                    self._set_state_later(RobotState.THINKING)
                    text = self._transcriber.transcribe(audio)
            except Exception:
                log.exception("Listening failed")
            self._heard.emit(source.value, text)

        self._spawn(work)

    def _set_state_later(self, state: RobotState) -> None:
        # Called from worker threads: the stage is touched on the UI thread only.
        QTimer.singleShot(0, self, lambda: self._set_state(state))

    def _on_heard(self, source: str, text: str) -> None:
        self._listening = False
        following, self._following = self._following, False
        self._end_countdown()
        if self._cancel.is_set() or not text.strip():
            if following:
                self._end_conversation()  # silence after a reply ends the conversation
            # A chat order may have replaced this recording and even been answered already.
            if not self._expected and not self._speaking and not self._idle_timer.isActive():
                self._idle()
            return
        self._chat.panel.add_message("user", text)
        if following and is_farewell(text):
            self._end_conversation()
            self._say_goodbye()
            return
        if self._conversation_seconds > 0:
            self._conversation = Source(source)
        self._send(Order(source=Source(source), intent=Intent.CONVERSATION, payload={"text": text}))

    # Conversation mode

    def _follow_up(self) -> None:
        """Listen for the next thing the user says, without the wake word."""
        if self._expected or self._listening:
            return  # a new order or recording took over
        if self._conversation is None or self._asleep or self._follow_ups >= MAX_FOLLOW_UPS:
            self._idle()
            return
        if self._exclusion.is_excluded(self._foreground()):
            # In Discord or a game the mic would pick up the user talking to others.
            log.info("Conversation ended: excluded app in front")
            self._idle()
            return
        self._follow_ups += 1
        self._following = True
        # Same banner as the hotkey: the mic is open again and Esc ends it.
        self._countdown = max(1, math.ceil(self._conversation_seconds))
        self._stage.show_listen(self._countdown)
        self._countdown_timer.start()
        self._listen(self._conversation, timeout_seconds=self._conversation_seconds)

    def _end_conversation(self) -> None:
        self._conversation = None
        self._follow_up_timer.stop()

    def _say_goodbye(self) -> None:
        self._chat.panel.add_message("assistant", GOODBYE_TEXT)
        if self._speaker.enabled:
            self._speaking = True
            self._set_state(RobotState.SPEAKING)
            self._speech.say(GOODBYE_TEXT)
            self._speech.finish()
        else:
            self._idle()

    # Chat

    def _on_chat_message(self, text: str) -> None:
        self._end_conversation()  # typing switches to the chat
        if self._listening:
            # Typing wins over a recording in progress.
            self._cancel.set()
            self._end_countdown()
        self._send(Order(source=Source.CHAT, intent=Intent.CONVERSATION, payload={"text": text}))

    def _on_option(self, option: str) -> None:
        reply_to, self._question_id = self._question_id, None
        self._send(
            Order(
                source=Source.CHAT,
                intent=Intent.CONFIRM,
                payload={"text": option, "reply_to": reply_to},
            )
        )

    def _send(self, order: Order) -> None:
        self._expected = {order.id}
        if order.intent is Intent.CONFIRM:
            # The hub answers a confirmation under the id of the original order.
            self._expected.add(str(order.payload.get("reply_to")))
        elif self._question_id is not None:
            # Saying something else drops the pending question.
            self._question_id = None
            self._chat.panel.clear_options()
        self._reset_stream()
        self._busy = True
        self._idle_timer.stop()
        self._set_state(RobotState.THINKING)
        self._bus.publish_order(order)
        self._thinking_timer.start()

    # Replies from the hub

    def _on_result(self, result: Result) -> None:
        if result.id not in self._expected:
            # Late reply (timed out or superseded): show it, but leave the state alone.
            if not result.partial:
                self._chat.panel.add_message("assistant", result.response_text)
            return
        self._idle_timer.stop()
        if result.partial:
            self._on_partial(result)
            return
        self._expected = set()
        self._thinking_timer.stop()

        # Text already spoken sentence by sentence is not shown or said again. The final
        # text is the last round's reply, so it is the tail of what was streamed.
        final = _normalize(result.response_text)
        streamed = bool(final) and self._streamed.endswith(final)
        muted = self._muted
        self._reset_stream()
        if not streamed:
            self._chat.panel.add_message("assistant", result.response_text)

        if result.status is Status.QUESTION and result.options:
            self._question_id = result.id
            self._chat.panel.show_options(result.options)
            self._chat.open_next_to(self._stage)

        state = (
            RobotState.ANGRY if result.status is Status.ERROR else RobotState(result.robot_state)
        )
        if (result.speak and self._speaker.enabled and not muted) or self._speaking:
            # Keep the question or angry face while talking; otherwise the mouth moves.
            talking = state if state in (RobotState.QUESTION, RobotState.ANGRY) else None
            self._set_state(talking or RobotState.SPEAKING)
            self._speaking = True
            if result.speak and not streamed and not muted:
                self._speech.say(result.response_text)
            self._speech.finish()
        else:
            self._flash(state)

    def _on_partial(self, result: Result) -> None:
        sentence = _normalize(result.response_text)
        self._streamed = f"{self._streamed} {sentence}".strip()
        if self._stream_bubble is None:
            self._stream_bubble = self._chat.panel.add_message("assistant", sentence)
        else:
            self._stream_bubble.setText(self._streamed)
        if self._speaker.enabled and not self._muted:
            if not self._speaking:
                self._speaking = True
                self._set_state(RobotState.SPEAKING)
            self._speech.say(sentence)
        # The rest may take a while (a command running): keep watching for a hang.
        self._thinking_timer.start()

    def _on_spoken(self) -> None:
        self._speaking = False
        if self._question_id is not None:
            # Confirmations are answered with the chat buttons.
            self._end_conversation()
            self._busy = False
            self._set_state(RobotState.QUESTION)
            self._wake_detector.resume()
            return
        if self._conversation is not None and not self._asleep and not self._expected:
            self._follow_up_timer.start()
            return
        self._idle()

    def _flash(self, state: RobotState) -> None:
        self._set_state(state)
        if state is RobotState.QUESTION:
            self._busy = False
            self._wake_detector.resume()
        elif state in FLASH_MS:
            self._idle_timer.start(FLASH_MS[state])
        else:
            self._idle()

    def _no_reply(self) -> None:
        self._end_conversation()
        self._expected = set()
        self._reset_stream()
        if self._speaking:
            # Partials were spoken but the final never came: end the speech cleanly.
            self._speech.stop()
        self._chat.panel.add_message("assistant", NO_REPLY_TEXT)
        self._flash(RobotState.ANGRY)

    def _reset_stream(self) -> None:
        self._streamed, self._stream_bubble, self._muted = "", None, False

    # Clouds and robot

    def _on_cloud(self, cloud_id: str) -> None:
        if cloud_id == "chat":
            self._chat.open_next_to(self._stage)
        elif cloud_id == "commands":
            apps = ", ".join(self._runner.app_names)
            self._chat.panel.add_message("assistant", COMMANDS_TEXT.format(apps=apps))
            self._chat.open_next_to(self._stage)
        elif cloud_id == "quit":
            self._speech.stop()
            self._chat.hide()
            self._quit_app()
        elif cloud_id == "sleep":
            self._end_conversation()
            if self._listening:
                self._cancel.set()  # stop a follow-up recording too
            elif not self._expected and not self._speaking:
                # Picked between a reply and its follow-up. While Paula still speaks,
                # `_on_spoken` brings her to idle instead.
                self._busy = False
            self._asleep = True
            self._wake_detector.pause()
            self._chat.hide()
            self._set_state(RobotState.SLEEPING)

    def _follow_chat(self) -> None:
        if self._chat.isVisible():
            self._chat.open_next_to(self._stage)

    def _on_robot_clicked(self) -> None:
        if self._asleep:
            self._asleep = False
            self._wake_detector.resume()

    # State

    def _set_state(self, state: RobotState) -> None:
        self._stage.set_state(state)

    def _idle(self) -> None:
        self._end_conversation()
        self._busy = self._listening = False
        self._set_state(RobotState.QUESTION if self._question_id else RobotState.SLEEPING)
        if not self._asleep:
            self._wake_detector.resume()

    @property
    def asleep(self) -> bool:
        return self._asleep
