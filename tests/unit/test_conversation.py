import pytest

from paula_agent.conversation import is_farewell, normalize


def test_normalize_drops_accents_and_punctuation():
    assert normalize("¡Adiós, Paula!") == "adios paula"


@pytest.mark.parametrize(
    "text",
    [
        "Gracias, Paula.",
        "adiós",
        "Eso es todo",
        "nada más, gracias",
        "Listo.",
        "hasta luego",
        "No, nada más",
        "No, gracias",
        "Sí, gracias",
        "Gracias por la ayuda",
        "Muchas gracias por todo",
        "Hasta mañana",
        "Buenas noches",
    ],
)
def test_farewells(text):
    assert is_farewell(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "¿qué hora es?",
        "abre Spotify y nada más",  # a request that happens to end in a farewell word
        "gracias, ahora abre la calculadora y dime cómo está el PC",
        "listos para jugar",
    ],
)
def test_not_farewells(text):
    assert not is_farewell(text)
