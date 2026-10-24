"""Runs whitelisted commands. Anything not listed here is refused.

The hub has its own copy of the whitelist (paula_hub/domain/commands.py);
a command only works when both sides know it.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import unicodedata
from collections.abc import Callable
from pathlib import Path

import psutil

from paula_agent.messaging.messages import Action, Event, Status

log = logging.getLogger(__name__)

DEFAULT_APPS_FILE = Path(__file__).resolve().parents[1] / "config" / "default_apps.json"
SHUTDOWN_GRACE_SECONDS = 60


class CommandError(Exception):
    pass


def normalize(name: str) -> str:
    """Lowercase and strip accents, so "Configuración" matches "configuracion"."""
    decomposed = unicodedata.normalize("NFKD", name.strip().casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def load_apps(path: Path | None = None) -> dict[str, str]:
    data = json.loads((path or DEFAULT_APPS_FILE).read_text(encoding="utf-8"))
    return {normalize(name): target for name, target in data.items()}


class CommandRunner:
    def __init__(
        self,
        apps: dict[str, str],
        *,
        opener: Callable[[str], None] = os.startfile,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._apps = apps
        self._opener = opener
        self._run = run
        self._clock = clock
        self._commands: dict[str, Callable[[Action], str]] = {
            "open_app": self._open_app,
            "system_status": self._system_status,
            "shutdown_pc": self._shutdown_pc,
        }

    @property
    def app_names(self) -> list[str]:
        return sorted(self._apps)

    def run(self, action: Action) -> Event:
        started = self._clock()
        command = self._commands.get(action.command)
        try:
            if command is None:
                raise CommandError(f"Command '{action.command}' is not on the whitelist.")
            output, status = command(action), Status.OK
        except CommandError as exc:
            output, status = str(exc), Status.ERROR
        except OSError as exc:
            log.exception("Command %s failed", action.command)
            output, status = f"The PC could not run it: {exc}", Status.ERROR
        return Event(
            action_id=action.id,
            status=status,
            output=output,
            duration_seconds=round(self._clock() - started, 3),
        )

    def _open_app(self, action: Action) -> str:
        name = normalize(str(action.args.get("app", "")))
        target = self._apps.get(name)
        if target is None:
            available = ", ".join(self.app_names)
            raise CommandError(f"'{name}' is not in the app list. Available: {available}.")
        self._opener(target)
        return f"Opened {name}."

    def _system_status(self, action: Action) -> str:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
        uptime_hours = (time.time() - psutil.boot_time()) / 3600
        parts = [
            f"CPU {psutil.cpu_percent(interval=0.5):.0f}%",
            f"memory {memory.percent:.0f}% used of {memory.total / 2**30:.1f} GB",
            f"disk {disk.percent:.0f}% used, {disk.free / 2**30:.0f} GB free",
            f"uptime {uptime_hours:.1f} h",
        ]
        battery = psutil.sensors_battery()
        if battery is not None:
            plugged = "charging" if battery.power_plugged else "on battery"
            parts.append(f"battery {battery.percent:.0f}% ({plugged})")
        return "; ".join(parts) + "."

    def _shutdown_pc(self, action: Action) -> str:
        # Second line of defense: the hub only sends this after the user confirms.
        if not action.confirmed:
            raise CommandError("Shutdown needs the user's confirmation.")
        self._run(["shutdown", "/s", "/t", str(SHUTDOWN_GRACE_SECONDS)], check=True)
        return (
            f"Shutdown scheduled in {SHUTDOWN_GRACE_SECONDS} seconds. "
            "It can be cancelled with 'shutdown /a'."
        )
