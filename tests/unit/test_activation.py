import sys

import pytest

from paula_agent.activation.foreground import ExclusionPolicy, WindowInfo, foreground_window
from paula_agent.activation.hotkey import to_pynput
from paula_agent.activation.wake_word import matches

WAKE = ["paula", "paula port"]


def window(process="chrome.exe", fullscreen=False, window_class="Chrome_WidgetWin_1"):
    return WindowInfo(process=process, window_class=window_class, fullscreen=fullscreen)


def test_listed_apps_are_excluded():
    policy = ExclusionPolicy()

    assert policy.is_excluded(window("Discord.exe"))
    assert policy.is_excluded(window("ms-teams.exe"))
    assert policy.is_excluded(window("PioneerGame.exe"))  # Arc Raiders
    assert not policy.is_excluded(window("chrome.exe"))


def test_fullscreen_counts_as_game_but_not_desktop():
    policy = ExclusionPolicy()

    assert policy.is_excluded(window("eldenring.exe", fullscreen=True))
    assert not policy.is_excluded(window("explorer.exe", fullscreen=True, window_class="WorkerW"))


def test_policy_from_names_overrides_defaults():
    policy = ExclusionPolicy.from_names("obs64.exe, Zoom.exe")

    assert policy.is_excluded(window("zoom.exe"))
    assert not policy.is_excluded(window("discord.exe"))


def test_no_window_is_not_excluded():
    assert not ExclusionPolicy().is_excluded(None)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_foreground_window_runs_on_windows():
    info = foreground_window()

    assert info is None or isinstance(info.process, str)


def test_hotkey_format():
    assert to_pynput("ctrl+shift+p") == "<ctrl>+<shift>+p"
    assert to_pynput("<ctrl>+<shift>+p") == "<ctrl>+<shift>+p"


def result(text, *confs):
    return {"text": text, "result": [{"word": w, "conf": c} for w, c in zip(text.split(), confs)]}


def test_wake_word_needs_exact_phrase_and_confidence():
    assert matches(result("paula", 0.95), WAKE, 0.85)
    assert matches(result("paula port", 0.9, 0.9), WAKE, 0.85)
    assert not matches(result("paula", 0.6), WAKE, 0.85)
    assert not matches(result("[unk] paula", 0.9, 0.9), WAKE, 0.85)
    assert not matches({"text": ""}, WAKE, 0.85)
