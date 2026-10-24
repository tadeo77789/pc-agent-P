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
    "chao",
    "chau",
    "gracias paula",
    "muchas gracias",
    "eso es todo",
    "eso seria todo",
    "nada mas",
    "ya esta",
    "listo gracias",
    "ok gracias",
    "vale gracias",
)
# Said on its own, these also end the conversation.
FAREWELL_WORDS = ("gracias", "listo", "nada")
FILLER_WORDS = frozenset(
    [
        "gracias",
        "muchas",
        "paula",
        "port",
        "ok",
        "vale",
        "bueno",
        "si",
        "listo",
        "pues",
        "entonces",
        "ya",
        "por",
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
