"""Shared test fixtures and helpers."""
from __future__ import annotations

import asyncio
import base64
import io
import os
import socket
import struct
import wave

import pytest
import pytest_asyncio

# The suite asserts the default language; a developer's own SOCRA_LANGUAGE must not leak in.
# This runs before the first socra_server import, which reads the variable once.
os.environ.pop("SOCRA_LANGUAGE", None)

from socra_server.app import ExamApp, ModelLoader, PageChannel
from socra_server.adapters.whisper_stt import WhisperSTT
from socra_server.domain.voices import DEFAULT_VOICE_ID, get_voice


# ---------------------------------------------------------------------------
# Minimal silent WAV builder
# ---------------------------------------------------------------------------

def free_ports(count: int) -> list[int]:
    """Distinct loopback ports, free a moment ago: all are held at once so none repeats."""
    socks = [socket.socket() for _ in range(count)]
    try:
        for sock in socks:
            sock.bind(("127.0.0.1", 0))
        return [sock.getsockname()[1] for sock in socks]
    finally:
        for sock in socks:
            sock.close()


def make_wav_bytes(num_samples: int = 160, sample_rate: int = 16000) -> bytes:
    """Return a valid silent PCM-16 WAV byte string."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * num_samples)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fake adapters (no model loading)
# ---------------------------------------------------------------------------

class FakeTTS:
    """Fake Piper TTS: returns a minimal WAV for any text."""

    def __init__(self) -> None:
        self._voice_id: str = DEFAULT_VOICE_ID

    @property
    def voice_id(self) -> str:
        return self._voice_id

    def set_voice(self, voice_id: object) -> bool:
        voice = get_voice(voice_id)
        if voice is None:
            return False
        self._voice_id = voice.id
        return True

    def synthesize(self, text: str) -> bytes:
        return make_wav_bytes()

    @property
    def glossary_terms(self) -> list[str]:
        return ["python", "API", "whisper"]


class FakeSTT:
    """Fake Whisper STT: returns a fixed transcript and records calls."""

    def __init__(self, reply: str = "fake transcript") -> None:
        self.reply = reply
        self.last_prompt: str | None = None
        self.last_extra_glossary: list[str] | None = None
        # Expose the underlying model interface used by the adapter
        self._model = self  # self acts as the fake model
        self._base_terms: list[str] = []

    # --- adapter-compatible surface ---

    def set_base_terms(self, terms: list[str]) -> None:
        self._base_terms = terms

    def transcribe_with_glossary(
        self, wav_bytes: bytes, extra_glossary: list[str] | None = None
    ) -> str:
        self.last_extra_glossary = extra_glossary
        prompt = ", ".join(self._base_terms)
        if extra_glossary:
            extras = [t for t in extra_glossary if t not in self._base_terms]
            if extras:
                prompt = (prompt + ", " + ", ".join(extras)).lstrip(", ")
        self.last_prompt = prompt
        return self.reply

    def transcribe(self, wav_bytes: bytes, prompt: str = "") -> str:
        self.last_prompt = prompt
        return self.reply

    # --- fake faster-whisper model surface (used by WhisperSTT.transcribe_with_glossary) ---
    def transcribe_model(self, audio, language="en", vad_filter=True, initial_prompt=None):
        self.last_prompt = initial_prompt
        # Return a fake segments iterator
        class Seg:
            text = self.reply if isinstance(self, FakeSTT) else "ok"
        return iter([Seg()]), None


class FakeLoader:
    """Fake ModelLoader: instantly ready, uses fake adapters."""

    def __init__(self, stt_reply: str = "fake transcript") -> None:
        self.tts = FakeTTS()
        self.stt = FakeSTT(reply=stt_reply)
        self._ready = True

    async def ready(self) -> None:
        pass  # instant

    def start(self) -> None:
        pass


# ---------------------------------------------------------------------------
# App fixture (no page connected by default)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_preferences(tmp_path_factory, monkeypatch):
    """Keep every page server off the user's real preferences file."""
    monkeypatch.setenv("SOCRA_PREFERENCES_FILE", str(tmp_path_factory.mktemp("prefs") / "preferences.json"))


@pytest.fixture
def loader():
    return FakeLoader()


@pytest.fixture
def channel():
    return PageChannel()


@pytest.fixture
def app(channel, loader, tmp_path):
    (tmp_path / "index.html").write_text("<h1>Exam</h1>")
    return ExamApp(channel=channel, loader=loader, web_dist=tmp_path)
