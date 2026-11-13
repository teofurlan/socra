"""Spoken slash commands: 'barra X ...' / 'slash X ...' become '/x ...' for known commands only."""
import pytest

from socra_server.domain.commands import spoken_command

NAMES = ["tdd", "code-review", "context", "skill:grilling", "init"]


@pytest.mark.parametrize("heard, expected", [
    ("barra tdd arregla el login", "/tdd arregla el login"),
    ("Slash TDD fix the login", "/tdd fix the login"),
    ("Barra, tdd. Arregla esto", "/tdd Arregla esto"),
    ("barra tdd", "/tdd"),
    ("Bárra context", "/context"),
    ("slash code review the diff", "/code-review the diff"),
    ("barra skill grilling mi plan", "/skill:grilling mi plan"),
    ("barra t d d arregla", "/tdd arregla"),
])
def test_a_known_command_after_barra_or_slash_becomes_a_slash_command(heard, expected):
    assert spoken_command(heard, NAMES) == expected


@pytest.mark.parametrize("heard", [
    "barra desconocido haz algo",
    "slash",
    "barra",
    "arregla el slash tdd del login",
    "la barra tdd no está en el inicio",
    "tdd arregla el login",
    "barracuda tdd",
    "",
])
def test_anything_else_is_left_exactly_as_heard(heard):
    assert spoken_command(heard, NAMES) == heard


def test_without_known_commands_nothing_changes():
    assert spoken_command("barra tdd arregla", []) == "barra tdd arregla"


def test_accents_in_the_argument_are_kept():
    assert spoken_command("Bárra tdd revisa esta función", NAMES) == "/tdd revisa esta función"
