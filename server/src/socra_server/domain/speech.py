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

# The Piper voice for the language: id, picker label, model path in the Hugging Face repo, and
# the speaker inside that model. libritts_r is multi-speaker (CC BY 4.0); speaker 0 won a blind
# test on 2026-11-01 against ryan (CC BY-NC-SA 4.0, which forbids commercial use).
SPEECH_VOICE_ID = "libritts_r"
SPEECH_VOICE_LABEL = "LibriTTS-R speaker 0 (US English)"
SPEECH_VOICE_MODEL = "en/en_US/libritts_r/medium/en_US-libritts_r-medium"
SPEECH_VOICE_SPEAKER = 0
SPEECH_VOICE_LENGTH_SCALE = 1.0

# Phrases Whisper invents from silence or noise (lowercase; matched as substrings).
# A bare "thank you" is deliberately absent: it is also a real answer.
SILENCE_HALLUCINATIONS: tuple[str, ...] = (
    "thanks for watching",
    "subtitles by",
    "amara.org",
    "please subscribe",
)
