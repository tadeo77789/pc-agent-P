import pytest
from dotenv import dotenv_values

from paula_agent.config.env_file import update_env


def test_updates_values_and_keeps_everything_else(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# Paula\nELEVENLABS_API_KEY=secret\nMIC_DEVICE=\nLOG_LEVEL=INFO\n", encoding="utf-8"
    )

    update_env(env, {"MIC_DEVICE": "Micrófono (USB)", "CONVERSATION_SECONDS": "10"})

    assert env.read_text(encoding="utf-8") == (
        "# Paula\nELEVENLABS_API_KEY=secret\nMIC_DEVICE='Micrófono (USB)'\nLOG_LEVEL=INFO\n"
        "CONVERSATION_SECONDS='10'\n"
    )


@pytest.mark.parametrize(
    "value",
    [
        "Mic (Realtek #2)",
        "a=b",
        "it's",
        'say "hi"',
        "cost $5",
        "C:\\Audio\\mic",
        "",
    ],
)
def test_values_read_back_exactly(tmp_path, value):
    env = tmp_path / ".env"

    update_env(env, {"MIC_DEVICE": value})

    assert dotenv_values(env)["MIC_DEVICE"] == value


@pytest.mark.parametrize("value", ["x\nAGENT_SHARED_SECRET=hack", "x\rY=1", "x\u2028Y=1", "x\x1cY"])
def test_rejects_line_breaks(tmp_path, value):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")

    with pytest.raises(ValueError):
        update_env(env, {"MIC_DEVICE": value})

    assert env.read_text(encoding="utf-8") == "A=1\n"


def test_rejects_bad_names(tmp_path):
    with pytest.raises(ValueError):
        update_env(tmp_path / ".env", {"bad name": "1"})
