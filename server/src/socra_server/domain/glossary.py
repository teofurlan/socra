"""Glossary of technical terms.

``terms.json`` maps a written term to its spoken form. The written terms prime the
recognizer so Whisper spells them right; the voice reads the text as plain English.
"""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_TERMS: dict[str, str] = {
    "README": "read me",
    "README.md": "read me dot em dee",
    "pull request": "pull request",
    "pull requests": "pull requests",
    "API": "A P I",
    "APIs": "A P Is",
    "ollama": "ollama",
    "c++": "C plus plus",
    "c#": "C sharp",
}


def load_glossary(path: Path | str | None = None) -> dict[str, str]:
    """Read the terms file; a missing file yields the built-in defaults."""
    if path is None or not Path(path).exists():
        return dict(DEFAULT_TERMS)
    target = Path(path)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Failed to read glossary from {target}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Glossary file must contain a JSON object")
    if data.get("version") != 1 or not isinstance(data.get("terms"), dict):
        raise ValueError("Glossary must have version: 1 and a 'terms' dictionary")
    terms: dict[str, str] = {}
    for term, spoken in data["terms"].items():
        if not isinstance(term, str) or not term.strip():
            raise ValueError("Glossary term must be a non-empty string")
        if not isinstance(spoken, str) or not spoken.strip():
            raise ValueError(f"Spoken text for term '{term}' must be a non-empty string")
        terms[term] = spoken
    return terms
