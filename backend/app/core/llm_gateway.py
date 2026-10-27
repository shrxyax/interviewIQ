"""
The single place in the backend that talks to an LLM.

Every call is:
- schema-validated (structured output via Pydantic),
- cached by prompt hash (reproducible evaluation runs),
- logged (prompt, response, latency) for auditing.

Algorithmic modules (belief updates, selection, simulation) must never
import this file. That separation is deliberate.
"""

import hashlib
import json
import time
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.models import LLMCall


T = TypeVar("T", bound=BaseModel)

_client = None


class LLMUnavailable(RuntimeError):
    pass


def _get_client():
    global _client

    if _client is None:
        if not settings.gemini_api_key:
            raise LLMUnavailable("GEMINI_API_KEY is not set.")

        from google import genai

        _client = genai.Client(api_key=settings.gemini_api_key)

    return _client


def _cache_key(task: str, prompt: str, schema_name: str) -> str:
    raw = f"{settings.gemini_model}|{task}|{schema_name}|{prompt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> str | None:
    with SessionLocal() as db:
        row = db.query(LLMCall).filter_by(cache_key=key).first()
        return row.response if row else None


def _cache_put(key: str, task: str, prompt: str, response: str, latency_ms: int, model: str):
    with SessionLocal() as db:
        db.add(
            LLMCall(
                cache_key=key,
                model=model,
                task=task,
                prompt=prompt,
                response=response,
                latency_ms=latency_ms,
            )
        )

        try:
            db.commit()
        except Exception:
            # A concurrent request cached the same prompt first.
            db.rollback()


class QuotaExhausted(LLMUnavailable):
    pass


# Per model: monotonic time until which it isn't tried (after a quota error).
# Free-tier quotas are daily, so retrying a spent model only adds latency;
# requests go to the next model in settings.gemini_models instead, and once
# every model is spent callers fall back to their non-LLM paths.
_paused_until: dict[str, float] = {}
_QUOTA_COOLDOWN_S = 10 * 60


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc)
    return "RESOURCE_EXHAUSTED" in text or text.startswith("429")


def _call_with_retry(fn, attempts: int = 3):
    delay = 1.0

    for attempt in range(attempts):
        try:
            return fn()
        except LLMUnavailable:
            raise
        except Exception as exc:
            if _is_quota_error(exc):
                raise QuotaExhausted(f"LLM quota exhausted: {str(exc)[:200]}") from exc

            if attempt == attempts - 1:
                raise

            time.sleep(delay)
            delay *= 2


def _generate(contents: str, config) -> tuple[object, str]:
    """
    generate_content on the first model in settings.gemini_models that still
    has quota. Returns (response, model used).
    """

    for model in settings.gemini_models:
        if time.monotonic() < _paused_until.get(model, 0.0):
            continue

        try:
            response = _call_with_retry(
                lambda: _get_client().models.generate_content(model=model, contents=contents, config=config)
            )
            return response, model
        except QuotaExhausted:
            _paused_until[model] = time.monotonic() + _QUOTA_COOLDOWN_S
            print(f"Gemini model {model} is out of quota; trying the next model.")

    raise LLMUnavailable("Every Gemini model is out of quota; paused until it resets.")


def generate_text(prompt: str, task: str = "text", temperature: float = 0.7, use_cache: bool = False) -> str:
    """
    Free-form text generation (question phrasing, feedback prose).
    Not cached by default because variety is desirable here.
    """

    from google.genai import types

    key = _cache_key(task, prompt, "text")

    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            return cached

    start = time.perf_counter()

    response, model = _generate(prompt, types.GenerateContentConfig(temperature=temperature))

    text = (response.text or "").strip()

    if use_cache:
        _cache_put(key, task, prompt, text, int((time.perf_counter() - start) * 1000), model)

    return text


def generate_structured(prompt: str, schema: type[T], task: str) -> T:
    """
    Structured generation at temperature 0, validated against `schema`
    and cached by prompt hash.
    """

    from google.genai import types

    key = _cache_key(task, prompt, schema.__name__)

    cached = _cache_get(key)

    if cached is not None:
        try:
            return schema.model_validate_json(cached)
        except ValidationError:
            pass  # Schema changed since caching; regenerate.

    start = time.perf_counter()

    response, model = _generate(
        prompt,
        types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )

    parsed = response.parsed

    if isinstance(parsed, schema):
        result = parsed
    else:
        result = schema.model_validate(json.loads(response.text))

    _cache_put(
        key,
        task,
        prompt,
        result.model_dump_json(),
        int((time.perf_counter() - start) * 1000),
        model,
    )

    return result

