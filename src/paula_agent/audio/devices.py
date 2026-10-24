"""Microphones and speakers by name.

Windows lists every device once per audio API (MME, DirectSound, WASAPI...). Paula
uses the default API, so only its devices are offered, and they are saved by name:
indexes change when a headset is plugged in.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

# The MME "sound mapper" is an alias of the Windows default, not a device.
MAPPER_NAMES = ("Microsoft Sound Mapper", "Asignador de sonido Microsoft")


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    is_default: bool


def _query():
    import sounddevice as sd

    return sd


def list_devices(kind: str) -> list[AudioDevice]:
    """`kind` is "input" (microphones) or "output" (speakers and headphones)."""
    sd = _query()
    channels = f"max_{kind}_channels"
    default_index = sd.default.device[0 if kind == "input" else 1]
    try:
        hostapi = sd.query_devices(default_index)["hostapi"]
    except (sd.PortAudioError, ValueError, TypeError):
        hostapi = None
    devices = []
    for index, info in enumerate(sd.query_devices()):
        if info["name"].startswith(MAPPER_NAMES):
            continue
        if info[channels] > 0 and (hostapi is None or info["hostapi"] == hostapi):
            devices.append(AudioDevice(index, info["name"], index == default_index))
    return devices


def resolve(name: str, kind: str) -> int | None:
    """Index of the device called `name`, or None for the Windows default.

    An unplugged device falls back to the default instead of failing.
    """
    if not name:
        return None
    for device in list_devices(kind):
        if device.name == name:
            return device.index
    log.warning("Audio %s '%s' not found; using the Windows default", kind, name)
    return None
