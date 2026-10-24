"""Which app is in front, and whether Paula must ignore her name while it is."""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from dataclasses import dataclass

import psutil

log = logging.getLogger(__name__)

DEFAULT_EXCLUDED = (
    "discord.exe",
    "zoom.exe",
    "ms-teams.exe",
    "teams.exe",
    "pioneergame.exe",  # Arc Raiders, also excluded when windowed
)
# Desktop and shell windows cover the whole screen but are not games.
SHELL_CLASSES = ("Progman", "WorkerW", "Shell_TrayWnd")
GWL_STYLE = -16
WS_CAPTION = 0x00C00000


@dataclass(frozen=True)
class WindowInfo:
    process: str
    window_class: str
    fullscreen: bool


@dataclass(frozen=True)
class ExclusionPolicy:
    """In excluded apps only Ctrl+Shift+P activates Paula. Fullscreen apps count as games."""

    processes: frozenset[str] = frozenset(DEFAULT_EXCLUDED)
    fullscreen_is_game: bool = True

    @classmethod
    def from_names(cls, names: str | None) -> ExclusionPolicy:
        if not names:
            return cls()
        return cls(frozenset(n.strip().casefold() for n in names.split(",") if n.strip()))

    def is_excluded(self, window: WindowInfo | None) -> bool:
        if window is None:
            return False
        if window.process.casefold() in self.processes:
            return True
        return (
            self.fullscreen_is_game
            and window.fullscreen
            and window.window_class not in SHELL_CLASSES
        )


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def foreground_window() -> WindowInfo | None:
    """Describe the foreground window (Windows only)."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        process = psutil.Process(pid.value).name()
    except psutil.Error:
        process = ""

    class_name = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_name, 256)

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    info = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
    monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    screen = info.rcMonitor
    covers_screen = (
        rect.left <= screen.left
        and rect.top <= screen.top
        and rect.right >= screen.right
        and rect.bottom >= screen.bottom
    )
    # A maximized normal window can also cover the monitor (auto-hide taskbar):
    # games in fullscreen have no title bar and are not "zoomed".
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    has_caption = style & WS_CAPTION == WS_CAPTION
    fullscreen = covers_screen and not has_caption and not user32.IsZoomed(hwnd)
    return WindowInfo(process=process, window_class=class_name.value, fullscreen=fullscreen)
