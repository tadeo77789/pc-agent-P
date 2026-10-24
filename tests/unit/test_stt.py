import pytest

from paula_agent.audio import stt
from paula_agent.audio.stt import Transcriber


class FakeModel:
    def transcribe(self, audio, **kwargs):
        return iter([]), None


def test_auto_falls_back_to_cpu_when_gpu_fails(monkeypatch):
    def create(self, device, compute_type):
        if device == "cuda":
            raise RuntimeError("cudnn64_9.dll not found")
        return FakeModel()

    monkeypatch.setattr(Transcriber, "_create", create)
    transcriber = Transcriber(device="auto")

    transcriber.load()

    assert transcriber.device_used == "cpu"


def test_auto_prefers_gpu(monkeypatch):
    monkeypatch.setattr(Transcriber, "_create", lambda self, device, ct: FakeModel())
    transcriber = Transcriber(device="auto")

    transcriber.load()

    assert transcriber.device_used == "cuda"


def test_forced_cuda_raises(monkeypatch):
    def create(self, device, compute_type):
        raise RuntimeError("no gpu")

    monkeypatch.setattr(Transcriber, "_create", create)

    with pytest.raises(RuntimeError):
        Transcriber(device="cuda").load()


def test_forced_cpu_skips_gpu(monkeypatch):
    devices = []

    def create(self, device, compute_type):
        devices.append(device)
        return FakeModel()

    monkeypatch.setattr(Transcriber, "_create", create)

    Transcriber(device="cpu").load()

    assert devices == ["cpu"]


def test_register_cuda_dlls_without_wheels(monkeypatch):
    def missing(name):
        raise ImportError(name)

    monkeypatch.setattr(stt.importlib, "import_module", missing)

    assert stt.register_cuda_dlls() == []


def test_gpu_failure_at_transcription_switches_to_cpu(monkeypatch):
    class OutOfMemoryModel:
        def transcribe(self, audio, **kwargs):
            raise RuntimeError("CUDA failed with error out of memory")

    class Segment:
        text = " hola "

    class CpuModel:
        def transcribe(self, audio, **kwargs):
            return iter([Segment()]), None

    monkeypatch.setattr(
        Transcriber,
        "_create",
        lambda self, device, ct: OutOfMemoryModel() if device == "cuda" else CpuModel(),
    )
    transcriber = Transcriber(device="auto")

    assert transcriber.transcribe(None) == "hola"
    assert transcriber.device_used == "cpu"
