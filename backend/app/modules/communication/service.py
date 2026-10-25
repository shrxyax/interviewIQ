"""
Wires app.modules.communication.analysis into the interview turn-submission
path and shapes a session-level summary for the final report. See
app/modules/interview/service.py's submit_turn_answer / _finish_session.
"""

from datetime import datetime, timezone

from app.modules.communication.analysis import analyze_communication


def _aware(dt: datetime) -> datetime:
    # SQLite round-trips DateTime(timezone=True) columns as naive - the same
    # normalization applied to InterviewSession.ends_at in interview/service.py.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def build_turn_metrics(
    answer: str,
    listening_started_at: datetime | None,
    answered_at: datetime,
) -> dict:
    latency = None

    if listening_started_at is not None and answered_at is not None:
        latency = max(0.0, (_aware(answered_at) - _aware(listening_started_at)).total_seconds())

    return analyze_communication(answer, latency)


def aggregate_session_metrics(turns: list) -> dict:
    """
    Mean communication signals across every answered turn that has
    comm_metrics attached. turns is a list of InterviewTurn rows (or any
    object exposing a .comm_metrics attribute).
    """

    samples = [t.comm_metrics for t in turns if getattr(t, "comm_metrics", None)]

    if not samples:
        return {
            "sample_count": 0,
            "avg_filler_rate": None,
            "avg_hedge_count": None,
            "avg_vocabulary_diversity": None,
            "avg_response_latency_seconds": None,
        }

    def _mean(key: str) -> float | None:
        values = [s[key] for s in samples if s.get(key) is not None]
        return round(sum(values) / len(values), 4) if values else None

    return {
        "sample_count": len(samples),
        "avg_filler_rate": _mean("filler_rate"),
        "avg_hedge_count": _mean("hedge_count"),
        "avg_vocabulary_diversity": _mean("vocabulary_diversity"),
        "avg_response_latency_seconds": _mean("response_latency_seconds"),
    }
