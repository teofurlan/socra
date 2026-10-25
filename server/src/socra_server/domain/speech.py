"""The one language Socra listens and speaks in.

Whisper transcribes in it and the agent is told to reply in it, so a transcript that comes
out in another language reads as a recognition error, not as the user switching language.
"""
from __future__ import annotations

SPEECH_LANGUAGE = "es"
SPEECH_LANGUAGE_NAME = "Spanish"
