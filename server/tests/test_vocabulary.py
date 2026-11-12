"""Known words fix near misses in a transcript (live S2)."""
from __future__ import annotations

import pytest

from socra_server.domain.vocabulary import correct_terms

TERMS = ["Socra", "github", "WebSocket", "pipecat", "python", "PR", "dogear", "pull request"]


@pytest.mark.parametrize(
    ("heard", "expected"),
    [
        ("Le pregunté a socrá", "Le pregunté a Socra"),  # accent and case
        ("Abrí Zocra en la terminal", "Abrí Socra en la terminal"),  # z sounds like s
        ("¿Qué es sokra?", "¿Qué es Socra?"),  # punctuation stays
        ("abrí so cra ahora", "abrí Socra ahora"),  # one word heard as two
        ("lo subí a git hub", "lo subí a github"),
        ("usa un web socket", "usa un WebSocket"),
        ("pipe cat y Socra", "pipecat y Socra"),
        ("la carpeta dog ear", "la carpeta dogear"),
        ("hablale a cloud code", "hablale a Claude Code"),  # known mishearing
    ],
)
def test_near_misses_become_the_known_term(heard, expected):
    assert correct_terms(heard, TERMS) == expected


@pytest.mark.parametrize(
    "heard",
    [
        "eso sobra",  # a real word one sound away is never replaced
        "uso git todos los días",  # part of a term alone stays
        "Python es lindo",  # a case-only difference with a lowercase term stays
        "abrí un pull request",  # already right
        "so, cra",  # words are not joined across punctuation
        "pe erre",  # terms shorter than four sounds are left to Whisper
        "",
    ],
)
def test_text_without_a_near_miss_is_unchanged(heard):
    assert correct_terms(heard, TERMS) == heard


def test_the_longest_match_wins():
    assert correct_terms("el web socket server", ["web", "WebSocket"]) == "el WebSocket server"


def test_no_terms_means_no_change():
    assert correct_terms("socrá", []) == "socrá"
