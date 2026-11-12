"""Glossary of technical terms.

``terms.json`` maps a written term to its spoken form. The written terms prime the
recognizer so Whisper spells them right. In a language whose voice is not English, the
segmentation below also splits a text into its own stretches and glossary matches, so an
adapter can give each match English pronunciation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from socra_server.domain.speech import SPEECH_LANGUAGE, TERM_PHONEME_LANGUAGE

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


def speech_segments(text: str, terms: dict[str, str]) -> list[dict[str, str]]:
    """Split text into stretches in the speech language and glossary matches (longest term first)."""
    if not text:
        return []
    if not terms:
        return [{"text": text, "language": SPEECH_LANGUAGE}]

    ordered = sorted(terms, key=len, reverse=True)
    alternatives = []
    for term in ordered:
        # Word boundaries only where the term starts or ends with a word character
        # (terms such as "c++" or "README.md" end in punctuation).
        prefix = r"(?<!\w)" if term[0].isalnum() or term[0] == "_" else ""
        suffix = r"(?!\w)" if term[-1].isalnum() or term[-1] == "_" else ""
        alternatives.append(f"{prefix}{re.escape(term)}{suffix}")
    pattern = re.compile("|".join(f"({alt})" for alt in alternatives), flags=re.IGNORECASE)
    spoken_by_lower: dict[str, str] = {}
    for term in ordered:
        spoken_by_lower.setdefault(term.lower(), terms[term])

    segments: list[dict[str, str]] = []
    last_end = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if start > last_end:
            segments.append({"text": text[last_end:start], "language": SPEECH_LANGUAGE})
        written = match.group(0)
        segments.append({
            "text": written,
            "spoken": spoken_by_lower.get(written.lower(), written),
            "language": TERM_PHONEME_LANGUAGE,
        })
        last_end = end
    if last_end < len(text):
        segments.append({"text": text[last_end:], "language": SPEECH_LANGUAGE})
    return segments
