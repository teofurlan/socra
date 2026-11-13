"""Whisper inference failure regressions without loading real models."""
from types import SimpleNamespace

import pytest

from socra_server.adapters.whisper_stt import WhisperSTT
from tests.conftest import make_wav_bytes


def test_cuda_runtime_failure_retries_on_cpu_with_same_prompt():
    calls = []

    class Transcriber:
        def __init__(self, device="cuda", compute_type="float16", download_root="cached"):
            self.device = device
            self.download_root = download_root
            self.model = self

        def transcribe(self, audio, **kwargs):
            calls.append((self.device, kwargs))

            def segments():
                if self.device == "cuda":
                    raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
                yield SimpleNamespace(text="A process has its own memory.")

            return segments(), None

    stt = WhisperSTT(["API"])
    stt._transcriber = Transcriber()
    assert stt.transcribe_with_glossary(make_wav_bytes(), ["thread"]) == "A process has its own memory."
    assert calls == [
        ("cuda", {"language": "en", "vad_filter": True, "initial_prompt": "API, thread, Socra"}),
        ("cpu", {"language": "en", "vad_filter": True, "initial_prompt": "API, thread, Socra"}),
    ]


def test_cpu_inference_failure_is_not_returned_as_a_final_empty_answer():
    def broken(*args, **kwargs):
        raise RuntimeError("inference failed")

    stt = WhisperSTT()
    stt._transcriber = SimpleNamespace(device="cpu", model=SimpleNamespace(transcribe=broken))
    with pytest.raises(RuntimeError, match="inference failed"):
        stt.transcribe_with_glossary(make_wav_bytes())


def test_warm_up_runs_one_full_decode_without_vad_so_the_first_turn_is_not_cold():  # live S3
    calls = []

    class Model:
        def transcribe(self, audio, **kwargs):
            calls.append((len(audio), kwargs))
            return iter([SimpleNamespace(text="")]), None

    stt = WhisperSTT()
    stt._transcriber = SimpleNamespace(device="cuda", model=Model())
    stt.warm_up()

    # VAD would drop the silence and skip the decoder, leaving it cold.
    assert len(calls) == 1 and calls[0][1]["vad_filter"] is False


def test_warm_up_failure_never_raises():
    def broken(*args, **kwargs):
        raise RuntimeError("cublas missing")

    stt = WhisperSTT()
    stt._transcriber = SimpleNamespace(device="cuda", model=SimpleNamespace(transcribe=broken))
    stt.warm_up()  # the first real turn falls back to CPU as before
    WhisperSTT().warm_up()  # not loaded: nothing to warm


def test_final_and_partial_transcripts_fix_near_misses_of_known_terms():  # live S2
    class Model:
        def transcribe(self, audio, **kwargs):
            return iter([SimpleNamespace(text="Abrí socrá en dog ear con web socket")]), None

    stt = WhisperSTT(["WebSocket"])
    stt._transcriber = SimpleNamespace(device="cpu", model=Model())

    expected = "Abrí Socra en dogear con WebSocket"
    assert stt.transcribe_with_glossary(make_wav_bytes(), ["dogear"]) == expected
    assert stt.transcribe_partial(make_wav_bytes(), ["dogear"]) == expected


def test_two_decodes_failing_on_cuda_at_once_rebuild_the_cpu_model_only_once():  # review R3-cpu-fallback
    import threading
    import time

    built = []

    class Transcriber:
        def __init__(self, device="cuda", compute_type="float16", download_root="cached", model_size=None):
            if device == "cpu":
                time.sleep(0.05)  # a slow rebuild leaves room for the other decode to start
                built.append(device)
            self.device = device
            self.download_root = download_root
            self.model = self

        def transcribe(self, audio, **kwargs):
            def segments():
                if self.device == "cuda":
                    raise RuntimeError("cublas64_12.dll missing")
                yield SimpleNamespace(text="Hola.")
            return segments(), None

    stt = WhisperSTT()
    stt._transcriber = Transcriber()
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(stt.transcribe_with_glossary(make_wav_bytes())))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == ["Hola.", "Hola."]
    assert built == ["cpu"]
