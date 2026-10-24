"""Speaks sentences one after another as they arrive from the hub."""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)

_SAY, _DONE = "say", "done"


class SpeechQueue:
    """`say()` queues a sentence; `finish()` calls `on_done` once everything queued is spoken.

    With `threaded=False` everything runs inline (for tests).
    """

    def __init__(self, speaker, on_done: Callable[[], None], *, threaded: bool = True) -> None:
        self._speaker = speaker
        self._on_done = on_done
        self._threaded = threaded
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._thread: threading.Thread | None = None

    def say(self, text: str) -> None:
        self._put(_SAY, text)

    def finish(self) -> None:
        self._put(_DONE, "")

    def stop(self) -> None:
        """Cut the current sentence, drop the rest, and report done."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._speaker.stop()
        self.finish()

    def _put(self, kind: str, text: str) -> None:
        if not self._threaded:
            self._handle(kind, text)
            return
        self._queue.put((kind, text))
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="speech", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while True:
            self._handle(*self._queue.get())

    def _handle(self, kind: str, text: str) -> None:
        if kind == _DONE:
            self._on_done()
            return
        try:
            self._speaker.speak(text)
        except Exception:
            log.exception("Speaking failed")
