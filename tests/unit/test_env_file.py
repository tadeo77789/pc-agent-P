import pytest

from paula_agent.config.env_file import update_env


def test_updates_values_and_keeps_everything_else(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# Paula\nELEVENLABS_API_KEY=secret\nMIC_DEVICE=\nLOG_LEVEL=INFO\n", encoding="utf-8"
    )

    update_env(env, {"MIC_DEVICE": "Micrófono (USB)", "CONVERSATION_SECONDS": "10"})

    assert env.read_text(encoding="utf-8") == (
        "# Paula\nELEVENLABS_API_KEY=secret\nMIC_DEVICE=Micrófono (USB)\nLOG_LEVEL=INFO\n"
        "CONVERSATION_SECONDS=10\n"
    )


def test_rejects_line_breaks(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")

    with pytest.raises(ValueError):
        update_env(env, {"MIC_DEVICE": "x\nAGENT_SHARED_SECRET=hack"})

    assert env.read_text(encoding="utf-8") == "A=1\n"


def test_rejects_bad_names(tmp_path):
    with pytest.raises(ValueError):
        update_env(tmp_path / ".env", {"bad name": "1"})
