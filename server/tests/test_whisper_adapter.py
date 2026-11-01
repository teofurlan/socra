"""Tests for the Whisper STT adapter — fake model, no real model loading."""
from __future__ import annotations

import io
import wave
import numpy as np
import pytest

from socra_server.adapters.whisper_stt import WhisperSTT, _wav_bytes_to_array
from tests.conftest import make_wav_bytes


# ---------------------------------------------------------------------------
# Fake faster-whisper model
# ---------------------------------------------------------------------------

class _FakeSegment:
    def __init__(self, text: str):
        self.text = text


class _FakeWhisperModel:
    """Records every transcribe() call for assertion."""

    def __init__(self, reply: str = "hola mundo"):
        self.reply = reply
        self.last_call: dict = {}

    def transcribe(self, audio, language="es", vad_filter=True, initial_prompt=None, **kw):
        self.last_call = {
            "language": language,
            "vad_filter": vad_filter,
            "initial_prompt": initial_prompt,
        }
        return iter([_FakeSegment(self.reply)]), None


class _FakeTranscriber:
    """Mimics dictation.transcriber.WhisperTranscriber with a fake model."""

    def __init__(self, reply: str = "hola mundo"):
        self.model = _FakeWhisperModel(reply)


# ---------------------------------------------------------------------------
# WhisperSTT.transcribe_with_glossary passes initial_prompt (S6)
# ---------------------------------------------------------------------------

def test_whisper_passes_initial_prompt_with_glossary():
    """The adapter must build initial_prompt from base terms + glossary (S6)."""
    stt = WhisperSTT()
    stt._transcriber = _FakeTranscriber(reply="test answer")
    stt.set_base_terms(["python", "API", "whisper"])

    wav = make_wav_bytes()
    text = stt.transcribe_with_glossary(wav, extra_glossary=["MCP", "asyncio"])

    assert text == "test answer"
    model: _FakeWhisperModel = stt._transcriber.model
    prompt = model.last_call["initial_prompt"]
    assert prompt is not None
    assert "python" in prompt
    assert "MCP" in prompt
    assert "asyncio" in prompt


def test_whisper_base_terms_only_when_no_extra_glossary():
    stt = WhisperSTT()
    stt._transcriber = _FakeTranscriber(reply="respuesta")
    stt.set_base_terms(["commit", "branch"])

    wav = make_wav_bytes()
    stt.transcribe_with_glossary(wav, extra_glossary=None)

    model: _FakeWhisperModel = stt._transcriber.model
    prompt = model.last_call["initial_prompt"]
    assert "commit" in prompt
    assert "branch" in prompt


def test_whisper_language_es_and_vad_filter():
    """Adapter always passes language='es' and vad_filter=True (S4, S6)."""
    stt = WhisperSTT()
    stt._transcriber = _FakeTranscriber()
    stt.set_base_terms([])

    wav = make_wav_bytes()
    stt.transcribe_with_glossary(wav)

    model: _FakeWhisperModel = stt._transcriber.model
    assert model.last_call["language"] == "es"
    assert model.last_call["vad_filter"] is True


def test_whisper_not_loaded_raises():
    stt = WhisperSTT()
    with pytest.raises(RuntimeError, match="not loaded"):
        stt.transcribe(make_wav_bytes())


def test_wav_bytes_to_array_returns_float32_mono():
    wav = make_wav_bytes(num_samples=320, sample_rate=16000)
    arr = _wav_bytes_to_array(wav)
    assert arr.dtype == np.float32
    assert arr.ndim == 1
    assert arr.size == 320


def test_whisper_no_ollama_cleaner(monkeypatch):
    """Confirm the adapter never imports or calls dictation.cleaner (S4)."""
    import sys
    # If cleaner were called, it would appear in imported modules.
    # We verify it's not called by checking no 'cleaner' attribute is touched.
    stt = WhisperSTT()
    stt._transcriber = _FakeTranscriber()
    stt.set_base_terms([])
    wav = make_wav_bytes()
    stt.transcribe_with_glossary(wav)
    # No cleaner import should have happened during this path
    assert "dictation.cleaner" not in sys.modules


def test_prompt_ends_with_socra_so_it_survives_truncation():
    stt = WhisperSTT(["python", "API"])
    assert stt._build_prompt(None).endswith(", Socra")
    assert stt._build_prompt(["myproject"]).endswith("myproject, Socra")


def test_prompt_is_just_socra_without_any_terms():
    assert WhisperSTT()._build_prompt(None) == "Socra"


def test_prompt_does_not_duplicate_socra():
    stt = WhisperSTT(["Socra", "API"])
    prompt = stt._build_prompt(["Socra", "thread"])
    assert prompt.count("Socra") == 1
    assert prompt.endswith("Socra")
