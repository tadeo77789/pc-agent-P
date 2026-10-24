"""Conversation mode: after Paula answers by voice she listens again, without the wake
word, until the user stays silent or says goodbye."""

from __future__ import annotations

import re
import unicodedata

# User-facing phrases, Spanish. An utterance is a goodbye only if, once these phrases
# are removed, nothing but filler words is left: "abre Spotify y nada más" is a request.
FAREWELL_PHRASES = (
    "adios",
    "hasta luego",
    "hasta pronto",
    "hasta manana",
    "buenas noches",
    "chao",
    "chau",
    "gracias",
    "gracias por todo",
    "gracias por la ayuda",
    "gracias por tu ayuda",
    "eso es todo",
    "eso seria todo",
    "nada mas",
    "ya esta",
)
# Said on its own, these also end the conversation.
FAREWELL_WORDS = ("listo", "nada")
# Not "si", "vale" or "bueno": "sí, gracias" usually accepts an offer from Paula.
FILLER_WORDS = frozenset(
    [
        "muchas",
        "paula",
        "port",
        "ok",
        "no",
        "listo",
        "pues",
        "entonces",
        "ya",
        "ahora",
    ]
)


def normalize(text: str) -> str:
    """Lowercase, without accents or punctuation: "¡Gracias, Paula!" -> "gracias paula"."""
    plain = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", plain).split())


def is_farewell(text: str) -> bool:
    words = normalize(text)
    if words in FAREWELL_WORDS:
        return True
    padded = f" {words} "
    found = False
    for phrase in sorted(FAREWELL_PHRASES, key=len, reverse=True):
        if f" {phrase} " in padded:
            padded = padded.replace(f" {phrase} ", " ")
            found = True
    return found and all(word in FILLER_WORDS for word in padded.split())
