"""
Text-to-speech for reading interview questions aloud.

Browser speech is unreliable on some systems (it can report "speaking" while
producing no sound), so the backend renders real audio. Providers are tried
in order:

1. Gemini TTS models (best voice quality). The free tier allows only a
   handful of requests per model per day, so after a quota error Gemini is
   skipped for a cool-down period instead of being retried on every question.
2. The operating system's own synthesizer (`say` on macOS, `espeak-ng` /
   `espeak` on Linux): free, offline and unlimited.

Rendered audio is cached in memory, and concurrent requests for the same text
share one render (React's dev double-mount fetches the same question twice).
"""

import hashlib
import io
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from collections import OrderedDict

from app.core.config import settings

log = logging.getLogger(__name__)

_CACHE: OrderedDict[str, tuple[bytes, str]] = OrderedDict()
_CACHE_SIZE = 128
_cache_lock = threading.Lock()
_key_locks: dict[str, threading.Lock] = {}

# Monotonic time until which Gemini is not attempted (after quota errors).
_gemini_paused_until = 0.0
_GEMINI_COOLDOWN_S = 15 * 60

# Upper bound on a local render; normal questions take ~1s.
_LOCAL_TIMEOUT_S = 30


class SpeechUnavailable(RuntimeError):
    pass


def synthesize(text: str) -> tuple[bytes, str]:
    """`text` read aloud, as (WAV bytes, "audio/wav")."""

    key = hashlib.sha256(text.encode("utf-8")).hexdigest()

    with _cache_lock:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
        key_lock = _key_locks.setdefault(key, threading.Lock())

    with key_lock:
        # Another request may have rendered it while we waited.
        with _cache_lock:
            if key in _CACHE:
                return _CACHE[key]

        audio = _render(text)

        with _cache_lock:
            _CACHE[key] = audio
            while len(_CACHE) > _CACHE_SIZE:
                _CACHE.popitem(last=False)
            _key_locks.pop(key, None)

        return audio


def _render(text: str) -> tuple[bytes, str]:
    errors = []

    if settings.gemini_api_key and time.monotonic() >= _gemini_paused_until:
        for model in settings.gemini_tts_models:
            try:
                return _render_gemini(text, model)
            except Exception as exc:  # noqa: BLE001 - any failure falls through to the next provider
                errors.append(f"{model}: {exc}")
                if "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc):
                    continue
                break
        else:
            _pause_gemini()

    try:
        return _render_local(text)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"local: {exc}")

    log.warning("Question audio unavailable: %s", " | ".join(str(e)[:200] for e in errors))
    raise SpeechUnavailable("No speech provider could render the question.")


def _pause_gemini():
    global _gemini_paused_until
    _gemini_paused_until = time.monotonic() + _GEMINI_COOLDOWN_S
    log.info("Gemini TTS quota exhausted; using local speech for %d minutes.", _GEMINI_COOLDOWN_S // 60)


def _pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    buf = io.BytesIO()

    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)

    return buf.getvalue()


def _render_gemini(text: str, model: str) -> tuple[bytes, str]:
    from google.genai import types

    from app.core.llm_gateway import _get_client

    response = _get_client().models.generate_content(
        model=model,
        # Only the question itself: TTS models read any instruction in the
        # prompt aloud. The calm delivery comes from the chosen voice.
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=settings.gemini_tts_voice)
                )
            ),
        ),
    )

    blob = response.candidates[0].content.parts[0].inline_data
    mime = (blob.mime_type or "").lower()

    if "wav" in mime:
        return blob.data, "audio/wav"

    # Raw 16-bit PCM, e.g. "audio/L16;codec=pcm;rate=24000".
    rate = 24000
    for part in mime.split(";"):
        if part.strip().startswith("rate="):
            rate = int(part.split("=", 1)[1])

    return _pcm_to_wav(blob.data, rate), "audio/wav"


def _render_local(text: str) -> tuple[bytes, str]:
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "speech.wav")

        if shutil.which("say"):
            cmd = ["say", "-o", out, "--data-format=LEI16@22050"]
            if settings.local_tts_voice:
                cmd += ["-v", settings.local_tts_voice]
            cmd.append(text)
        elif shutil.which("espeak-ng") or shutil.which("espeak"):
            cmd = [shutil.which("espeak-ng") or shutil.which("espeak"), "-w", out, text]
        else:
            raise SpeechUnavailable("No local speech synthesizer (say / espeak) is installed.")

        subprocess.run(cmd, check=True, timeout=_LOCAL_TIMEOUT_S, capture_output=True)

        with open(out, "rb") as f:
            return f.read(), "audio/wav"
