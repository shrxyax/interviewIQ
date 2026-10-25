"""
Phase 9: communication/soft-skill analysis unit tests plus an end-to-end
check that the final report's communication_summary is populated from a
real (short) interview session, without any LLM/audio call involved.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.communication.analysis import analyze_communication
from app.modules.communication.service import aggregate_session_metrics, build_turn_metrics
from app.modules.interview.service import FinalReport, InterviewDeps, TurnEvaluation, get_interview_deps


def test_filler_and_hedge_counts_on_known_text():
    answer = "Um, so, like, I think this is basically the right approach, you know."

    metrics = analyze_communication(answer)

    assert metrics["filler_count"] == 4  # um, like, basically, you know
    assert metrics["hedge_count"] == 1  # "i think"
    assert metrics["word_count"] > 0


def test_vocabulary_diversity_distinguishes_repetitive_from_varied_text():
    repetitive = analyze_communication("test test test test test")
    varied = analyze_communication("test design implement verify ship")

    assert repetitive["vocabulary_diversity"] < varied["vocabulary_diversity"]
    assert varied["vocabulary_diversity"] == 1.0


def test_empty_answer_does_not_raise():
    metrics = analyze_communication("")

    assert metrics["word_count"] == 0
    assert metrics["filler_rate"] == 0.0
    assert metrics["vocabulary_diversity"] == 0.0


def test_build_turn_metrics_computes_latency_from_timestamps():
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(seconds=12)

    metrics = build_turn_metrics("A clear answer.", start, end)

    assert metrics["response_latency_seconds"] == 12.0


def test_build_turn_metrics_handles_missing_listening_timestamp():
    from datetime import datetime, timezone

    metrics = build_turn_metrics("An answer.", None, datetime.now(timezone.utc))

    assert metrics["response_latency_seconds"] is None


class _FakeTurn:
    def __init__(self, comm_metrics):
        self.comm_metrics = comm_metrics


def test_aggregate_session_metrics_averages_across_turns():
    turns = [
        _FakeTurn({"filler_rate": 0.1, "hedge_count": 1, "vocabulary_diversity": 0.8, "response_latency_seconds": 10.0}),
        _FakeTurn({"filler_rate": 0.3, "hedge_count": 3, "vocabulary_diversity": 0.6, "response_latency_seconds": 20.0}),
        _FakeTurn(None),  # no answer recorded for this turn
    ]

    summary = aggregate_session_metrics(turns)

    assert summary["sample_count"] == 2
    assert summary["avg_filler_rate"] == pytest.approx(0.2)
    assert summary["avg_response_latency_seconds"] == pytest.approx(15.0)


def test_aggregate_session_metrics_empty():
    assert aggregate_session_metrics([])["sample_count"] == 0


# --------------------------------------------------------------------------
# End-to-end: communication_summary lands in the final report.
# --------------------------------------------------------------------------

def _fake_generate_first_question(context):
    return f"Tell me about your experience as a {context.target_role}."


def _fake_evaluate_answer(context, history, question, answer):
    return TurnEvaluation(score=7, evaluation="Solid answer.", next_question=f"Follow-up #{len(history) + 1}?")


def _fake_generate_report(context, history):
    return FinalReport(
        overall_score=75, communication=70, technical_knowledge=80, answer_relevance=75,
        clarity=72, problem_solving=78, strengths=[], areas_for_improvement=[],
        final_feedback="Good overall performance.",
    )


FAKE_DEPS = InterviewDeps(
    generate_first_question=_fake_generate_first_question,
    evaluate_answer=_fake_evaluate_answer,
    generate_report=_fake_generate_report,
)


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_interview_deps] = lambda: FAKE_DEPS

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def _register(client, username):
    r = client.post("/auth/register", json={"username": username, "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_communication_summary_in_final_report(client):
    headers = _register(client, "comms_user_1")

    context = client.post(
        "/interview/context",
        json={
            "target_role": "Backend Engineer", "experience_level": "junior",
            "interview_type": "technical", "duration_minutes": 30, "num_questions": 1,
        },
        headers=headers,
    ).json()

    session_id = client.post(
        "/interview/sessions", json={"context_id": context["context_id"]}, headers=headers,
    ).json()["session_id"]

    client.post(f"/interview/sessions/{session_id}/listening", headers=headers)

    r = client.post(
        f"/interview/sessions/{session_id}/answer",
        json={"answer": "Um, I think this is, like, basically my answer."},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    report = r.json()["report"]
    summary = report["communication_summary"]

    assert summary["sample_count"] == 1
    assert summary["avg_filler_rate"] > 0
