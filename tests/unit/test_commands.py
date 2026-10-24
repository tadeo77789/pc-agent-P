import subprocess

import pytest

from paula_agent.commands.runner import CommandRunner, load_apps, normalize
from paula_agent.messaging.messages import Action, Status


class Recorder:
    def __init__(self):
        self.opened = []
        self.ran = []

    def opener(self, target):
        self.opened.append(target)

    def run(self, args, check):
        self.ran.append(args)
        return subprocess.CompletedProcess(args, 0)


@pytest.fixture
def recorder():
    return Recorder()


@pytest.fixture
def runner(recorder):
    apps = {"navegador": "https://www.google.com", "configuracion": "ms-settings:"}
    return CommandRunner(apps, opener=recorder.opener, run=recorder.run)


def action(command, confirmed=False, **args):
    return Action(order_id="o1", command=command, args=args, confirmed=confirmed)


def test_normalize_strips_case_and_accents():
    assert normalize("  Configuración ") == "configuracion"


def test_default_apps_load():
    apps = load_apps()

    assert "navegador" in apps
    assert "bloc de notas" in apps


def test_open_known_app(runner, recorder):
    event = runner.run(action("open_app", app="Navegador"))

    assert event.status is Status.OK
    assert recorder.opened == ["https://www.google.com"]


def test_open_unknown_app_lists_available(runner, recorder):
    event = runner.run(action("open_app", app="photoshop"))

    assert event.status is Status.ERROR
    assert "navegador" in event.output
    assert recorder.opened == []


def test_command_outside_whitelist_is_refused(runner, recorder):
    event = runner.run(action("format_disk"))

    assert event.status is Status.ERROR
    assert "whitelist" in event.output
    assert recorder.ran == [] and recorder.opened == []


def test_shutdown_requires_confirmation(runner, recorder):
    event = runner.run(action("shutdown_pc"))

    assert event.status is Status.ERROR
    assert recorder.ran == []


def test_confirmed_shutdown_schedules_with_grace(runner, recorder):
    event = runner.run(action("shutdown_pc", confirmed=True))

    assert event.status is Status.OK
    assert recorder.ran == [["shutdown", "/s", "/t", "60"]]


def test_system_status_reports_metrics(runner):
    event = runner.run(action("system_status"))

    assert event.status is Status.OK
    assert "CPU" in event.output and "memory" in event.output


def test_os_error_becomes_error_event(recorder):
    def broken(target):
        raise OSError("not found")

    runner = CommandRunner({"x": "missing.exe"}, opener=broken, run=recorder.run)

    event = runner.run(action("open_app", app="x"))

    assert event.status is Status.ERROR
    assert "not found" in event.output
