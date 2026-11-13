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

    def __init__(self, reply: str = "hello world"):
        self.reply = reply
        self.last_call: dict = {}

    def transcribe(self, audio, language="en", vad_filter=True, initial_prompt=None, beam_size=None, **kw):
        self.last_call = {
            "language": language,
            "vad_filter": vad_filter,
            "initial_prompt": initial_prompt,
            "beam_size": beam_size,
        }
        return iter([_FakeSegment(self.reply)]), None


class _FakeTranscriber:
    """Mimics dictation.transcriber.WhisperTranscriber with a fake model."""

    def __init__(self, reply: str = "hello world"):
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
    stt._transcriber = _FakeTranscriber(reply="answer")
    stt.set_base_terms(["commit", "branch"])

    wav = make_wav_bytes()
    stt.transcribe_with_glossary(wav, extra_glossary=None)

    model: _FakeWhisperModel = stt._transcriber.model
    prompt = model.last_call["initial_prompt"]
    assert "commit" in prompt
    assert "branch" in prompt


def test_whisper_language_en_and_vad_filter():
    """Whisper is called with the profile language (English) and vad_filter=True (S1)."""
    stt = WhisperSTT()
    stt._transcriber = _FakeTranscriber()
    stt.set_base_terms([])

    wav = make_wav_bytes()
    stt.transcribe_with_glossary(wav)

    model: _FakeWhisperModel = stt._transcriber.model
    assert model.last_call["language"] == "en"
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


def test_partial_transcription_decodes_cheaply_with_a_greedy_beam():
    stt = WhisperSTT()
    stt._transcriber = _FakeTranscriber(reply="so far")

    text = stt.transcribe_partial(make_wav_bytes(), extra_glossary=["socra"])

    assert text == "so far"
    assert stt._transcriber.model.last_call["beam_size"] == 1
    assert stt._transcriber.model.last_call["vad_filter"] is True


def test_a_final_decode_keeps_the_default_beam():
    stt = WhisperSTT()
    stt._transcriber = _FakeTranscriber()

    stt.transcribe_with_glossary(make_wav_bytes())

    assert stt._transcriber.model.last_call["beam_size"] is None


def test_a_partial_and_a_final_never_run_on_the_model_at_the_same_time():
    import threading
    import time

    stt = WhisperSTT()
    active = {"now": 0, "max": 0}
    guard = threading.Lock()

    class _Model(_FakeWhisperModel):
        def transcribe(self, audio, **kw):
            with guard:
                active["now"] += 1
                active["max"] = max(active["max"], active["now"])
            time.sleep(0.05)
            with guard:
                active["now"] -= 1
            return super().transcribe(audio, **kw)

    class _T:
        model = _Model()

    stt._transcriber = _T()
    threads = [
        threading.Thread(target=stt.transcribe_partial, args=(make_wav_bytes(), None)),
        threading.Thread(target=stt.transcribe_with_glossary, args=(make_wav_bytes(), None)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert active["max"] == 1
