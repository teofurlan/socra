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
        self.speakers: list[int | None] = []

    def synthesize_wav(self, text, wav_file, syn_config=None) -> None:
        self.calls.append((text, syn_config.length_scale))
        self.speakers.append(syn_config.speaker_id)
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x00\x00" * 10)


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

    tts = PiperTTS(voice_loader=load_voice, glossary_path=glossary_file)
    tts.fake_voice, tts.loaded = voice, loaded
    return tts


def test_synthesize_before_load_raises(piper):
    with pytest.raises(RuntimeError, match="load"):
        piper.synthesize("hello")


def test_default_voice_is_libritts_r_and_unknown_voices_are_refused(piper):  # S2
    assert piper.voice_id == DEFAULT_VOICE_ID == "libritts_r"
    assert piper.set_voice("nope") is False
    assert piper.set_voice(None) is False
    assert piper.voice_id == "libritts_r"
    assert piper.set_voice("libritts_r") is True


def test_a_stored_voice_that_no_longer_exists_falls_back_to_the_default(piper):  # S2
    assert piper.set_voice("daniela") is False  # the page sends its stored choice; no error
    assert piper.set_voice("ryan") is False
    piper.load()
    piper.synthesize("Hello there")
    assert piper.loaded == ["libritts_r"]
    assert piper.voice_id == "libritts_r"


def test_libritts_r_speaker_0_is_the_only_voice_in_the_catalogue():  # S2
    from socra_server.domain.voices import VOICES

    assert [v.id for v in VOICES] == ["libritts_r"]
    assert VOICES[0].model == "en/en_US/libritts_r/medium/en_US-libritts_r-medium"
    assert VOICES[0].speaker == 0
    assert VOICES[0].length_scale == 1.0


def test_glossary_terms_are_the_keys(piper):
    piper.load()
    assert piper.glossary_terms == ["hook", "API"]


def test_the_multi_speaker_model_speaks_with_speaker_0(piper):  # S2
    piper.load()
    piper.synthesize("Hello there")
    assert piper.fake_voice.speakers == [0]


def test_returns_wav_bytes(piper):
    piper.load()
    wav = piper.synthesize("hello")
    assert wav[:4] == b"RIFF"


def test_english_text_reaches_the_voice_as_plain_text(piper):  # S6
    piper.load()
    piper.synthesize("Review the hook in the API")
    text, _ = piper.fake_voice.calls[0]
    assert text == "Review the hook in the API"
    assert "[[" not in text


def test_glossary_terms_still_prime_whisper_with_socra_last():  # S6
    from socra_server.adapters.whisper_stt import WhisperSTT

    class Voice:
        def synthesize_wav(self, text, wav_file, syn_config=None) -> None:
            pass

    tts = PiperTTS(voice_loader=lambda spec: Voice(), glossary_path=None)
    tts.load()
    assert "README" in tts.glossary_terms
    prompt = WhisperSTT(tts.glossary_terms)._build_prompt(None)
    assert "README" in prompt
    assert prompt.endswith(", Socra")


def test_markdown_is_stripped_and_empty_text_is_silent(piper):
    piper.load()
    piper.synthesize("**hello** `x`")
    assert piper.fake_voice.calls[0][0] == "hello x"
    assert piper.synthesize("```\ncode\n```") == b""
    assert len(piper.fake_voice.calls) == 1


def test_length_scale_defaults_to_catalogue(piper, monkeypatch):
    monkeypatch.delenv("SOCRA_TTS_LENGTH_SCALE", raising=False)
    piper.load()
    piper.synthesize("hello")
    assert piper.fake_voice.calls[0][1] == get_voice("libritts_r").length_scale == 1.0


def test_length_scale_env_override(piper, monkeypatch):
    monkeypatch.setenv("SOCRA_TTS_LENGTH_SCALE", "1.4")
    piper.load()
    piper.synthesize("hello")
    assert piper.fake_voice.calls[0][1] == 1.4


@pytest.mark.parametrize("value", ["fast", "0", "-1", "nan"])
def test_invalid_length_scale_is_ignored(piper, monkeypatch, caplog, value):
    monkeypatch.setenv("SOCRA_TTS_LENGTH_SCALE", value)
    piper.load()
    piper.synthesize("hello")
    assert piper.fake_voice.calls[0][1] == 1.0
    assert "SOCRA_TTS_LENGTH_SCALE" in caplog.text


def test_load_fetches_the_current_voice_once(piper):
    piper.load()
    piper.synthesize("one")
    piper.synthesize("two")
    assert piper.loaded == ["libritts_r"]


class LoudPiperVoice(FakePiperVoice):
    def synthesize_wav(self, text, wav_file, syn_config=None) -> None:
        self.calls.append((text, syn_config.length_scale))
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x10\x27" * 10)  # sound from the very first sample, like ryan


def test_every_clip_starts_with_a_lead_in_of_silence(glossary_file):  # S11
    """ryan starts speaking in the first 10 ms; the page's output loses that much on wake-up."""
    from socra_server.adapters.piper_tts import LEAD_IN_MS

    tts = PiperTTS(voice_loader=lambda spec: LoudPiperVoice(), glossary_path=glossary_file)
    tts.load()
    import io

    with wave.open(io.BytesIO(tts.synthesize("Hello there")), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 22050)
        lead = round(22050 * LEAD_IN_MS / 1000)
        frames = wav.readframes(wav.getnframes())
    assert LEAD_IN_MS >= 60  # at least daniela's typical 30-75 ms, which masked the cut
    assert frames[: lead * 2] == b"\x00\x00" * lead
    assert frames[lead * 2 :] == b"\x10\x27" * 10
