"""
Phase 9: communication/soft-skill analysis of an interview answer.

Scoped to what's measurable from the transcript the app already has (Web
Speech API output) plus timing already tracked on InterviewTurn - no new
audio-processing stack, no LLM call. Pure functions so they're trivially unit
tested and never block/slow down answer submission.
"""

import re

FILLER_WORDS = (
    "um", "umm", "uh", "uhh", "like", "you know", "i mean",
    "sort of", "kind of", "basically", "actually", "literally",
)

HEDGES = (
    "i think", "i guess", "maybe", "probably", "possibly",
    "i'm not sure", "not sure", "i believe", "sort of feel",
)

_WORD_RE = re.compile(r"[a-zA-Z']+")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")


def _count_phrases(text_lower: str, phrases: tuple[str, ...]) -> int:
    total = 0

    for phrase in phrases:
        pattern = r"\b" + re.escape(phrase) + r"\b"
        total += len(re.findall(pattern, text_lower))

    return total


def analyze_communication(answer: str, response_latency_seconds: float | None = None) -> dict:
    """
    Returns a small JSON-serializable dict of communication signals for one
    answer. Never raises on empty/degenerate input.
    """

    text = (answer or "").strip()
    text_lower = text.lower()

    words = _WORD_RE.findall(text_lower)
    word_count = len(words)

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    sentence_count = len(sentences) or (1 if word_count else 0)

    filler_count = _count_phrases(text_lower, FILLER_WORDS)
    hedge_count = _count_phrases(text_lower, HEDGES)

    vocabulary_diversity = round(len(set(words)) / word_count, 4) if word_count else 0.0
    avg_sentence_length = round(word_count / sentence_count, 2) if sentence_count else 0.0
    filler_rate = round(filler_count / word_count, 4) if word_count else 0.0

    return {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "filler_count": filler_count,
        "filler_rate": filler_rate,
        "hedge_count": hedge_count,
        "avg_sentence_length": avg_sentence_length,
        "vocabulary_diversity": vocabulary_diversity,
        "response_latency_seconds": (
            round(response_latency_seconds, 2) if response_latency_seconds is not None else None
        ),
    }
