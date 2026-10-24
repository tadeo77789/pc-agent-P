from types import SimpleNamespace

import pytest

from paula_agent.audio import devices

INFOS = [
    {
        "name": "Asignador de sonido Microsoft - Input",
        "hostapi": 0,
        "max_input_channels": 2,
        "max_output_channels": 0,
    },
    {
        "name": "Micrófono (Realtek)",
        "hostapi": 0,
        "max_input_channels": 2,
        "max_output_channels": 0,
    },
    {"name": "Auriculares (TWS)", "hostapi": 0, "max_input_channels": 0, "max_output_channels": 2},
    {"name": "Micrófono (TWS)", "hostapi": 0, "max_input_channels": 1, "max_output_channels": 0},
    {
        "name": "Micrófono (Realtek)",
        "hostapi": 2,
        "max_input_channels": 2,
        "max_output_channels": 0,
    },
]


class FakeSd:
    PortAudioError = RuntimeError
    default = SimpleNamespace(device=(1, 2))

    @staticmethod
    def query_devices(index=None):
        return INFOS if index is None else INFOS[index]


@pytest.fixture(autouse=True)
def fake_sd(monkeypatch):
    monkeypatch.setattr(devices, "_query", lambda: FakeSd)


def test_lists_only_the_default_api_and_marks_the_default():
    mics = devices.list_devices("input")

    assert [(d.index, d.name, d.is_default) for d in mics] == [
        (1, "Micrófono (Realtek)", True),
        (3, "Micrófono (TWS)", False),
    ]
    assert [d.name for d in devices.list_devices("output")] == ["Auriculares (TWS)"]


def test_resolve_by_name_and_fall_back_to_default():
    assert devices.resolve("Micrófono (TWS)", "input") == 3
    assert devices.resolve("", "input") is None
    assert devices.resolve("Unplugged headset", "input") is None
