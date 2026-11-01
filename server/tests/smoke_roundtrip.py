"""Manual real-model round trip; intentionally excluded from pytest collection.

Run from the repository root:
    uv run --project server python server/tests/smoke_roundtrip.py
"""
from time import perf_counter
import io
import wave

from socra_server.adapters.piper_tts import PiperTTS
from socra_server.adapters.whisper_stt import WhisperSTT

TEXT = "A process has its own memory; a thread shares the memory of its process."


def main() -> None:
    start = perf_counter()
    tts = PiperTTS()
    tts.load()
    tts_loaded = perf_counter()
    stt = WhisperSTT(tts.glossary_terms)
    stt.load()
    stt_loaded = perf_counter()
    wav = tts.synthesize(TEXT)
    synthesized = perf_counter()
    with wave.open(io.BytesIO(wav), "rb") as audio:
        duration = audio.getnframes() / audio.getframerate()
    transcript = stt.transcribe_with_glossary(wav)
    finished = perf_counter()
    print(f"Input: {TEXT}")
    print(f"Transcript: {transcript}")
    print(f"TTS load: {tts_loaded - start:.3f}s")
    print(f"STT load: {stt_loaded - tts_loaded:.3f}s")
    print(f"Synthesis: {synthesized - stt_loaded:.3f}s")
    print(f"Transcription: {finished - synthesized:.3f}s")
    print(f"WAV: {len(wav)} bytes, {duration:.3f}s")
    print(f"Total: {finished - start:.3f}s")
    if not transcript.strip():
        raise RuntimeError("Real Whisper returned an empty transcript")


if __name__ == "__main__":
    main()
