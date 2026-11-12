"""Socra in Spanish: SOCRA_LANGUAGE=es switches every language-dependent value (S1-S6).

The language is read once, when ``domain/speech.py`` is imported, so each check runs in a fresh
interpreter with the variable set, which is the same path a real server start takes.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest


def _run_in(language: str | None, code: str):
    env = {k: v for k, v in os.environ.items() if k != "SOCRA_LANGUAGE"}
    if language is not None:
        env["SOCRA_LANGUAGE"] = language
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_spanish_profile_sets_language_name_and_daniela_voice():  # S1, S2
    out = _run_in("es", """
        import json
        from socra_server.domain import speech
        from socra_server.domain.voices import DEFAULT_VOICE_ID, VOICES, get_voice
        print(json.dumps([speech.SPEECH_LANGUAGE, speech.SPEECH_LANGUAGE_NAME, DEFAULT_VOICE_ID,
                          [v.id for v in VOICES], get_voice("daniela").model, get_voice("daniela").length_scale,
                          get_voice("libritts_r")]))
    """)
    assert out == ["es", "Spanish", "daniela", ["daniela"], "es/es_AR/daniela/high/es_AR-daniela-high", 1.2, None]


@pytest.mark.parametrize("value", [None, "", "en", "fr"])
def test_english_stays_the_default_and_an_unknown_value_falls_back(value):  # S1
    out = _run_in(value, """
        import json
        from socra_server.domain import speech
        print(json.dumps([speech.SPEECH_LANGUAGE, speech.SPEECH_VOICE_ID]))
    """)
    assert out == ["en", "libritts_r"]


def test_the_agent_is_told_to_reply_in_spanish():  # S3
    out = _run_in("es", """
        import json
        from socra_server.domain.modes import MODES
        print(json.dumps(["Always reply in Spanish" in MODES["mentor"].instructions,
                          "English" in MODES["mentor"].instructions]))
    """)
    assert out == [True, False]


def test_spanish_silence_hallucinations_are_filtered_and_real_answers_are_not():  # S3
    out = _run_in("es", """
        import json
        from socra_server.adapters.whisper_stt import is_valid_answer
        print(json.dumps([is_valid_answer("Subtítulos realizados por la comunidad de Amara.org"),
                          is_valid_answer("Gracias por ver el vídeo"),
                          is_valid_answer("Gracias, entendí el bucle"),
                          is_valid_answer("Thanks for watching")]))
    """)
    assert out == [False, False, True, True]


def test_spanish_walkthrough_commands_and_polite_words_work_and_english_ones_still_do():  # S4
    out = _run_in("es", """
        import json
        from socra_server.domain.walkthrough import parse_command
        print(json.dumps([parse_command(t) for t in
            ["pausa", "un momento", "repite", "otra vez", "atrás", "siguiente por favor", "continúa",
             "para", "detente", "por favor", "next", "stop", "por next"]]))
    """)
    assert out == ["pause", "pause", "repeat", "repeat", "back", "next", "resume",
                   "stop", "stop", None, "next", "stop", "next"]


def test_english_walkthrough_stays_english_only():  # S4 (the #85 behaviour)
    out = _run_in("en", """
        import json
        from socra_server.domain.walkthrough import parse_command
        print(json.dumps([parse_command(t) for t in ["pausa", "siguiente", "por next", "next"]]))
    """)
    assert out == [None, None, None, "next"]


def test_spanish_abbreviations_do_not_end_a_sentence():  # S5
    out = _run_in("es", """
        import json
        from socra_server.domain.sentences import SentenceSplitter
        s = SentenceSplitter()
        pieces = s.feed("Hablá con la Sra. García sobre el ej. del bucle. Después seguimos. ") + s.flush()
        print(json.dumps([p.strip() for p in pieces]))
    """)
    assert out == ["Hablá con la Sra. García sobre el ej. del bucle.", "Después seguimos."]


def test_spanish_glossary_terms_are_spoken_with_english_phonemes_and_english_text_is_untouched():  # S6
    code = """
        import json, tempfile, pathlib
        from socra_server.adapters.piper_tts import PiperTTS

        class Voice:
            def __init__(self): self.texts = []
            def synthesize_wav(self, text, wav_file, syn_config=None):
                self.texts.append(text)
                wav_file.setnchannels(1); wav_file.setsampwidth(2); wav_file.setframerate(22050)
                wav_file.writeframes(b"\\x00\\x00" * 10)

        class Phonemizer:
            def phonemize(self, lang, text): return [list("fon" + text.replace(" ", "_"))]

        glossary = pathlib.Path(tempfile.mkdtemp()) / "terms.json"
        glossary.write_text(json.dumps({"version": 1, "terms": {"README": "read me"}}), encoding="utf-8")
        voice = Voice()
        tts = PiperTTS(voice_loader=lambda spec: voice, phonemizer=Phonemizer(), glossary_path=glossary)
        tts.load()
        tts.synthesize("Abrí el README ahora")
        print(json.dumps(voice.texts))
    """
    assert _run_in("es", code) == ["Abrí el [[ fonread_me ]] ahora"]


def test_spanish_speakable_text_still_speaks_paths_by_file_name_and_drops_breadcrumb_folders():  # S7
    out = _run_in("es", """
        import json
        from socra_server.domain.speakable import speakable_text as s
        print(json.dumps([s("Abrí `src/components/App.tsx` ahora"),
                          s("Mirá src > components > App.tsx y listo"),
                          s("En Home › src › App.tsx está"),
                          s("Entrá a Ajustes > Voz y probá"),
                          s("si x > 3 > y entonces")]))
    """)
    assert out == ["Abrí App ahora", "Mirá App y listo", "En App está", "Entrá a Ajustes > Voz y probá",
                   "si x > 3 > y entonces"]


def test_ya_esta_and_termina_are_answers_not_stop_commands():  # review finding 2
    out = _run_in("es", """
        import json
        from socra_server.domain.walkthrough import parse_command
        print(json.dumps([parse_command(t) for t in ["ya está", "termina", "basta", "ya basta", "detente"]]))
    """)
    assert out == [None, None, "stop", "stop", "stop"]


def _piper_texts(reply: str, phonemes) -> list[str]:
    return _run_in("es", f"""
        import json, tempfile, pathlib
        from socra_server.adapters.piper_tts import PiperTTS

        class Voice:
            def __init__(self): self.texts = []
            def synthesize_wav(self, text, wav_file, syn_config=None):
                self.texts.append(text)
                wav_file.setnchannels(1); wav_file.setsampwidth(2); wav_file.setframerate(22050)
                wav_file.writeframes(b"\\x00\\x00" * 10)

        class Phonemizer:
            def phonemize(self, lang, text): return {phonemes!r}

        glossary = pathlib.Path(tempfile.mkdtemp()) / "terms.json"
        glossary.write_text(json.dumps({{"version": 1, "terms": {{"README": "read me"}}}}), encoding="utf-8")
        voice = Voice()
        tts = PiperTTS(voice_loader=lambda spec: voice, phonemizer=Phonemizer(), glossary_path=glossary)
        tts.load()
        tts.synthesize({reply!r})
        print(json.dumps(voice.texts))
    """)


def test_raw_phoneme_brackets_in_a_reply_never_reach_the_voice():  # review finding 3
    (text,) = _piper_texts("mira [[ k æ t ]] aquí", [list("x")])
    assert "[[" not in text and "aquí" in text


def test_a_phonemizer_that_returns_nothing_falls_back_to_the_written_term():  # review finding 4
    assert _piper_texts("Abrí el README ahora", None) == ["Abrí el README ahora"]
