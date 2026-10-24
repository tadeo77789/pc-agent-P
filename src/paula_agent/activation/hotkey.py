"""System-wide Ctrl+Shift+P to start listening, and Esc to cancel."""

from __future__ import annotations

import logging
from collections.abc import Callable

from pynput import keyboard

log = logging.getLogger(__name__)

DEFAULT_HOTKEY = "<ctrl>+<shift>+p"


def to_pynput(hotkey: str) -> str:
    """Turn "ctrl+shift+p" into pynput's "<ctrl>+<shift>+p"."""
    parts = []
    for part in hotkey.casefold().replace(" ", "").split("+"):
        parts.append(part if len(part) == 1 or part.startswith("<") else f"<{part}>")
    return "+".join(parts)


class HotkeyListener:
    def __init__(
        self,
        on_activate: Callable[[], None],
        on_cancel: Callable[[], None],
        hotkey: str = DEFAULT_HOTKEY,
    ) -> None:
        self._on_cancel = on_cancel
        self._hotkeys = keyboard.GlobalHotKeys({to_pynput(hotkey): on_activate})
        self._escape = keyboard.Listener(on_press=self._on_press)

    def start(self) -> None:
        self._hotkeys.start()
        self._escape.start()

    def stop(self) -> None:
        self._hotkeys.stop()
        self._escape.stop()

    def _on_press(self, key) -> None:
        if key == keyboard.Key.esc:
            self._on_cancel()
