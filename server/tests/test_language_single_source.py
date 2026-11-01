"""Structural guard: the language lives in ``domain/speech.py`` and nowhere else (S4).

Rule: parse every ``.py`` file under ``server/src`` except ``domain/speech.py`` and look at its
string literals (docstrings and comments are prose, so they are skipped). A literal fails the
test when it is

* a language code (``"en"``, ``"es"``, ``"en-us"``, ``"es_AR"``...),
* a language name (``"Spanish"``, ``"English"``...) or a sentence naming one, such as
  ``"Always reply in English"``, or
* a Piper voice path that starts with a language folder (``"en/en_US/..."``).

Use the values exported by ``speech.py`` instead (``SPEECH_LANGUAGE``,
``SPEECH_LANGUAGE_NAME``, ``SPEECH_VOICE_MODEL``...). The test also checks the files are found,
so it cannot pass by scanning nothing.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "socra_server"
ALLOWED = SRC / "domain" / "speech.py"

_CODE = re.compile(r"^(en|es)([-_][a-z]{2})?$", re.IGNORECASE)
_NAME = re.compile(r"\b(spanish|english|espa[nñ]ol|ingl[eé]s)\b", re.IGNORECASE)
_VOICE_PATH = re.compile(r"^(en|es)/(en|es)_[A-Z]{2}/")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def _offences(source: str) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in docstrings:
            continue
        value = node.value.strip()
        if _CODE.match(value) or _NAME.search(value) or _VOICE_PATH.match(value):
            found.append((node.lineno, value))
    return sorted(found)


def test_only_speech_py_hardcodes_a_language():
    files = [p for p in SRC.rglob("*.py") if p != ALLOWED]
    assert len(files) > 10, "the scan found no source files"
    offences = [
        f"{path.relative_to(SRC)}:{line}: {value!r}"
        for path in files
        for line, value in _offences(path.read_text(encoding="utf-8"))
    ]
    assert offences == [], "language hardcoded outside domain/speech.py:" + chr(10) + chr(10).join(offences)


def test_the_scan_catches_a_hardcoded_language():
    sample = chr(10).join([
        '"""A docstring that mentions English is fine."""',
        'a = dict(language="es")',
        'b = "Always reply in Spanish"',
        'c = "en-us"',
        'd = "es/es_AR/daniela/high/es_AR-daniela-high"',
    ])
    assert [value for _, value in _offences(sample)] == [
        "es", "Always reply in Spanish", "en-us", "es/es_AR/daniela/high/es_AR-daniela-high",
    ]
