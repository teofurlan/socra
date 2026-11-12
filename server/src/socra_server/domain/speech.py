"""The one language Socra listens and speaks in, and every value that depends on it.

Whisper transcribes in it, the agent is told to reply in it, Piper speaks it with one voice,
and Whisper's known silence hallucinations are listed in it. A transcript that comes out in
another language reads as a recognition error, not as the user switching language.

Languages are rows of ``LANGUAGES``; the server uses the one named by ``SOCRA_LANGUAGE`` when
it starts (default ``en``). Nothing else under ``server/src`` may hardcode a language code or
name; it imports from here (``tests/test_language_single_source.py`` enforces this). To add a
language, add a row to this file.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

LANGUAGE_ENV = "SOCRA_LANGUAGE"
DEFAULT_LANGUAGE = "en"

# The language whose phonemes read glossary terms (technical English words) inside a text
# spoken in another language. ``espeak`` knows it by this code.
TERM_PHONEME_LANGUAGE = "en-us"


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    # The Piper voice: id, picker label, model path in the Hugging Face repo, and the speaker
    # inside that model (None for a single-speaker model).
    voice_id: str
    voice_label: str
    voice_model: str
    voice_speaker: int | None
    voice_length_scale: float
    # Phrases Whisper invents from silence or noise (lowercase; matched as substrings).
    silence_hallucinations: tuple[str, ...]
    # Spoken-command phrases and polite words this language adds to the English ones.
    command_phrases: tuple[tuple[str, tuple[str, ...]], ...] = ()
    polite_words: tuple[str, ...] = ()
    # Abbreviations whose period does not end a sentence, on top of the English ones.
    abbreviations: tuple[str, ...] = ()
    # Whether glossary terms in the text are spoken with English phonemes (the voice itself is
    # not English).
    english_terms: bool = False


LANGUAGES: dict[str, Language] = {
    # libritts_r is multi-speaker (CC BY 4.0); speaker 0 won a blind test on 2026-11-01 against
    # ryan (CC BY-NC-SA 4.0, which forbids commercial use). A bare "thank you" is deliberately
    # absent from the hallucinations: it is also a real answer.
    "en": Language(
        code="en",
        name="English",
        voice_id="libritts_r",
        voice_label="LibriTTS-R speaker 0 (US English)",
        voice_model="en/en_US/libritts_r/medium/en_US-libritts_r-medium",
        voice_speaker=0,
        voice_length_scale=1.0,
        silence_hallucinations=(
            "thanks for watching",
            "subtitles by",
            "amara.org",
            "please subscribe",
        ),
    ),
    "es": Language(
        code="es",
        name="Spanish",
        voice_id="daniela",
        voice_label="Daniela (Argentina)",
        voice_model="es/es_AR/daniela/high/es_AR-daniela-high",
        voice_speaker=None,
        voice_length_scale=1.2,
        silence_hallucinations=(
            "subtítulos realizados por",
            "amara.org",
            "gracias por ver",
            "suscríbete",
        ),
        command_phrases=(
            ("pause", ("pausa", "espera", "un momento")),
            ("repeat", ("repite", "repetir", "otra vez", "de nuevo", "repitelo")),
            ("back", ("atras", "anterior", "vuelve", "volver", "paso anterior")),
            ("next", ("siguiente", "adelante", "salta", "paso siguiente")),
            ("resume", ("continua", "continuar", "sigue", "seguir", "reanuda")),
            ("stop", ("para", "parar", "detente", "basta", "ya basta")),
        ),
        polite_words=("por", "favor"),
        abbreviations=("sr", "sra", "srta", "dra", "pág", "pag", "núm", "ej"),
        english_terms=True,
    ),
}


def resolve_language(code: str | None) -> Language:
    """The language row for ``code``; an empty or unknown value gives the default."""
    wanted = (code or "").strip().lower()
    if not wanted:
        return LANGUAGES[DEFAULT_LANGUAGE]
    language = LANGUAGES.get(wanted)
    if language is None:
        logging.getLogger(__name__).warning(
            "Ignoring unknown %s=%r; using %s (known: %s)",
            LANGUAGE_ENV, code, DEFAULT_LANGUAGE, ", ".join(LANGUAGES),
        )
        return LANGUAGES[DEFAULT_LANGUAGE]
    return language


LANGUAGE = resolve_language(os.environ.get(LANGUAGE_ENV))

SPEECH_LANGUAGE = LANGUAGE.code
SPEECH_LANGUAGE_NAME = LANGUAGE.name

SPEECH_VOICE_ID = LANGUAGE.voice_id
SPEECH_VOICE_LABEL = LANGUAGE.voice_label
SPEECH_VOICE_MODEL = LANGUAGE.voice_model
SPEECH_VOICE_SPEAKER = LANGUAGE.voice_speaker
SPEECH_VOICE_LENGTH_SCALE = LANGUAGE.voice_length_scale

SILENCE_HALLUCINATIONS: tuple[str, ...] = LANGUAGE.silence_hallucinations
SPEECH_COMMAND_PHRASES = LANGUAGE.command_phrases
SPEECH_POLITE_WORDS = LANGUAGE.polite_words
SPEECH_ABBREVIATIONS = LANGUAGE.abbreviations
SPEECH_ENGLISH_TERMS = LANGUAGE.english_terms
