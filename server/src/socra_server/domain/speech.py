"""The one language Socra listens and speaks in, and every value that depends on it.

Whisper transcribes in it, the agent is told to reply in it, Piper speaks it with one voice,
and Whisper's known silence hallucinations are listed in it. A transcript that comes out in
another language reads as a recognition error, not as the user switching language.

Nothing else under ``server/src`` may hardcode a language code or name; it imports from here
(``tests/test_language_single_source.py`` enforces this). To change language, change this file.
"""
from __future__ import annotations

SPEECH_LANGUAGE = "en"
SPEECH_LANGUAGE_NAME = "English"

# The Piper voice for the language: id, picker label, model path in the Hugging Face repo.
SPEECH_VOICE_ID = "ryan"
SPEECH_VOICE_LABEL = "Ryan (US English)"
SPEECH_VOICE_MODEL = "en/en_US/ryan/high/en_US-ryan-high"
SPEECH_VOICE_LENGTH_SCALE = 1.0

# Phrases Whisper invents from silence or noise (lowercase; matched as substrings).
# A bare "thank you" is deliberately absent: it is also a real answer.
SILENCE_HALLUCINATIONS: tuple[str, ...] = (
    "thanks for watching",
    "subtitles by",
    "amara.org",
    "please subscribe",
)
