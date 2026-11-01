"""Tests for PiperTTS with a fake voice and phonemizer: no model is downloaded."""
from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from socra_server.adapters.piper_tts import PiperTTS
from socra_server.domain.voices import DEFAULT_VOICE_ID, get_voice


class FakePiperVoice:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    def synthesize_wav(self, text, wav_file, syn_config=None) -> None:
        self.calls.append((text, syn_config.length_scale))
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x00\x00" * 10)


class FakePhonemizer:
    def phonemize(self, language: str, text: str) -> list[list[str]]:
        assert language == "en-us"
        return [list(text.upper())]


@pytest.fixture
def glossary_file(tmp_path):
    path = tmp_path / "terms.json"
    path.write_text(json.dumps({"version": 1, "terms": {"hook": "hook", "API": "A P I"}}), encoding="utf-8")
    return path


@pytest.fixture
def piper(glossary_file):
    loaded: list[str] = []
    voice = FakePiperVoice()

    def load_voice(spec):
        loaded.append(spec.id)
        return voice

    tts = PiperTTS(voice_loader=load_voice, phonemizer=FakePhonemizer(), glossary_path=glossary_file)
    tts.fake_voice, tts.loaded = voice, loaded
    return tts


def test_synthesize_before_load_raises(piper):
    with pytest.raises(RuntimeError, match="load"):
        piper.synthesize("hola")


def test_default_voice_and_unknown_voice(piper):
    assert piper.voice_id == DEFAULT_VOICE_ID == "daniela"
    assert piper.set_voice("nope") is False
    assert piper.set_voice(None) is False
    assert piper.voice_id == "daniela"
    assert piper.set_voice("daniela") is True


def test_glossary_terms_are_the_keys(piper):
    piper.load()
    assert piper.glossary_terms == ["hook", "API"]


def test_returns_wav_bytes(piper):
    piper.load()
    wav = piper.synthesize("hola")
    assert wav[:4] == b"RIFF"


def test_english_terms_are_inlined_as_phonemes(piper):
    piper.load()
    piper.synthesize("Revisá el hook de la API")
    text, _ = piper.fake_voice.calls[0]
    assert text == "Revisá el [[ HOOK ]] de la [[ A P I ]]"


def test_claude_code_is_phonemized_with_its_english_spelling():
    """The shipped terms.json must hand espeak the real word, not a respelling."""
    from socra_server.adapters.piper_tts import PiperTTS as RealPiperTTS

    seen: list[str] = []

    class RecordingPhonemizer:
        def phonemize(self, language: str, text: str) -> list[list[str]]:
            assert language == "en-us"
            seen.append(text)
            return [list(text)]

    shipped = Path(__file__).resolve().parents[2] / "voice" / "pi_voice" / "terms.json"
    tts = RealPiperTTS(
        voice_loader=lambda spec: FakePiperVoice(), phonemizer=RecordingPhonemizer(), glossary_path=shipped
    )
    tts.load()
    tts.synthesize("Abrí Claude Code ahora")
    assert seen == ["claude code"]


def test_markdown_is_stripped_and_empty_text_is_silent(piper):
    piper.load()
    piper.synthesize("**hola** `x`")
    assert piper.fake_voice.calls[0][0] == "hola x"
    assert piper.synthesize("```\ncode\n```") == b""
    assert len(piper.fake_voice.calls) == 1


def test_length_scale_defaults_to_catalogue(piper, monkeypatch):
    monkeypatch.delenv("SOCRA_TTS_LENGTH_SCALE", raising=False)
    piper.load()
    piper.synthesize("hola")
    assert piper.fake_voice.calls[0][1] == get_voice("daniela").length_scale == 1.2


def test_length_scale_env_override(piper, monkeypatch):
    monkeypatch.setenv("SOCRA_TTS_LENGTH_SCALE", "1.4")
    piper.load()
    piper.synthesize("hola")
    assert piper.fake_voice.calls[0][1] == 1.4


@pytest.mark.parametrize("value", ["fast", "0", "-1", "nan"])
def test_invalid_length_scale_is_ignored(piper, monkeypatch, caplog, value):
    monkeypatch.setenv("SOCRA_TTS_LENGTH_SCALE", value)
    piper.load()
    piper.synthesize("hola")
    assert piper.fake_voice.calls[0][1] == 1.2
    assert "SOCRA_TTS_LENGTH_SCALE" in caplog.text


def test_load_fetches_the_current_voice_once(piper):
    piper.load()
    piper.synthesize("uno")
    piper.synthesize("dos")
    assert piper.loaded == ["daniela"]
