"""
When a Gemini model's daily quota is used up, requests move on to the next
model in settings.gemini_models instead of failing, and a spent model is
skipped (not retried) for a while. No test here calls Gemini.
"""

from types import SimpleNamespace

import pytest

from app.core import llm_gateway


@pytest.fixture(autouse=True)
def _models(monkeypatch):
    monkeypatch.setattr(llm_gateway, "_paused_until", {})
    monkeypatch.setattr(llm_gateway.settings, "gemini_models", ["main", "lite"])


def _client(handler):
    models = SimpleNamespace(generate_content=lambda model, contents, config: handler(model))
    return lambda: SimpleNamespace(models=models)


def test_a_spent_model_falls_through_to_the_next_and_is_then_skipped(monkeypatch):
    calls = []

    def handler(model):
        calls.append(model)
        if model == "main":
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return SimpleNamespace(text=f"answer from {model}")

    monkeypatch.setattr(llm_gateway, "_get_client", _client(handler))
    monkeypatch.setattr(llm_gateway.time, "sleep", lambda s: pytest.fail("quota errors must not be retried"))

    assert llm_gateway.generate_text("hi") == "answer from lite"
    assert llm_gateway.generate_text("hi again") == "answer from lite"
    assert calls == ["main", "lite", "lite"]


def test_unavailable_once_every_model_is_spent(monkeypatch):
    def handler(model):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(llm_gateway, "_get_client", _client(handler))

    with pytest.raises(llm_gateway.LLMUnavailable):
        llm_gateway.generate_text("hi")

    assert set(llm_gateway._paused_until) == {"main", "lite"}


def test_other_errors_are_still_retried(monkeypatch):
    monkeypatch.setattr(llm_gateway.time, "sleep", lambda s: None)
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("503 UNAVAILABLE")
        return "ok"

    assert llm_gateway._call_with_retry(flaky) == "ok"
    assert len(attempts) == 3
