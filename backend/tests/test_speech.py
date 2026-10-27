"""
Question audio must keep working when Gemini's tiny free-tier TTS quota runs
out: it falls back to the local synthesizer, stops retrying Gemini for a
while, and renders each question once even under concurrent requests.
No test here calls Gemini or a real synthesizer.
"""

import threading
import time

import pytest

from app.core import speech


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    speech._CACHE.clear()
    speech._key_locks.clear()
    monkeypatch.setattr(speech, "_gemini_paused_until", 0.0)
    monkeypatch.setattr(speech.settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(speech.settings, "gemini_tts_models", ["tts-a", "tts-b"])


def test_falls_back_to_local_speech_when_every_gemini_model_is_out_of_quota(monkeypatch):
    tried = []

    def quota_exhausted(text, model):
        tried.append(model)
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(speech, "_render_gemini", quota_exhausted)
    monkeypatch.setattr(speech, "_render_local", lambda text: (b"LOCAL", "audio/wav"))

    assert speech.synthesize("Question one?") == (b"LOCAL", "audio/wav")
    assert tried == ["tts-a", "tts-b"]

    # Gemini is now cooling down: the next question goes straight to local.
    tried.clear()
    assert speech.synthesize("Question two?") == (b"LOCAL", "audio/wav")
    assert tried == []


def test_uses_the_next_gemini_model_when_the_first_is_out_of_quota(monkeypatch):
    def first_exhausted(text, model):
        if model == "tts-a":
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return b"GEMINI-B", "audio/wav"

    monkeypatch.setattr(speech, "_render_gemini", first_exhausted)
    monkeypatch.setattr(speech, "_render_local", lambda text: pytest.fail("local should not be needed"))

    assert speech.synthesize("Question?") == (b"GEMINI-B", "audio/wav")


def test_concurrent_requests_for_the_same_question_render_once(monkeypatch):
    renders = []

    def slow_render(text):
        renders.append(text)
        time.sleep(0.2)
        return b"AUDIO", "audio/wav"

    monkeypatch.setattr(speech, "_render", slow_render)

    results = []
    threads = [threading.Thread(target=lambda: results.append(speech.synthesize("Same question?"))) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert renders == ["Same question?"]
    assert results == [(b"AUDIO", "audio/wav")] * 4


def test_reports_unavailable_when_no_provider_works(monkeypatch):
    def broken(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(speech, "_render_gemini", broken)
    monkeypatch.setattr(speech, "_render_local", broken)

    with pytest.raises(speech.SpeechUnavailable):
        speech.synthesize("Question?")
