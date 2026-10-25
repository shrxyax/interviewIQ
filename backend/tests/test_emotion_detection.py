"""
Phase 9b: emotion/affect aggregation unit tests plus a boundary check that
client-supplied MediaPipe blendshape-derived signals (emotion_signal in the
/answer request body) are persisted and flow into the final report. No real
MediaPipe model runs here - detection is 100% client-side; this only tests
the backend boundary where that structured JSON enters the system.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.emotion.aggregate import aggregate_session_emotion
from app.modules.interview.service import FinalReport, InterviewDeps, TurnEvaluation, get_interview_deps


class _FakeTurn:
    def __init__(self, emotion_metrics):
        self.emotion_metrics = emotion_metrics


def test_aggregate_session_emotion_averages_across_turns():
    turns = [
        _FakeTurn({"engagement": 0.8, "stress_proxy": 0.2, "positive_expression_proxy": 0.6}),
        _FakeTurn({"engagement": 0.6, "stress_proxy": 0.4, "positive_expression_proxy": 0.4}),
        _FakeTurn(None),  # camera unavailable for this turn
    ]

    summary = aggregate_session_emotion(turns)

    assert summary["sample_count"] == 2
    assert summary["avg_engagement"] == pytest.approx(0.7)
    assert summary["avg_stress_proxy"] == pytest.approx(0.3)
    assert summary["avg_positive_expression_proxy"] == pytest.approx(0.5)


def test_aggregate_session_emotion_empty_when_camera_never_available():
    summary = aggregate_session_emotion([_FakeTurn(None), _FakeTurn(None)])

    assert summary["sample_count"] == 0
    assert summary["avg_engagement"] is None


# --------------------------------------------------------------------------
# API boundary: emotion_signal in the request body persists onto the turn
# and into the session's final report.
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


def _start_one_question_session(client, headers):
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
    return session_id


def test_emotion_signal_persists_into_report(client):
    headers = _register(client, "emotion_user_1")
    session_id = _start_one_question_session(client, headers)

    emotion_signal = {"engagement": 0.9, "stress_proxy": 0.1, "positive_expression_proxy": 0.7}

    r = client.post(
        f"/interview/sessions/{session_id}/answer",
        json={"answer": "A confident answer.", "emotion_signal": emotion_signal},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    report = r.json()["report"]
    summary = report["emotion_summary"]

    assert summary["sample_count"] == 1
    assert summary["avg_engagement"] == pytest.approx(0.9)


def test_missing_emotion_signal_still_finishes_session_cleanly(client):
    headers = _register(client, "emotion_user_2")
    session_id = _start_one_question_session(client, headers)

    r = client.post(
        f"/interview/sessions/{session_id}/answer",
        json={"answer": "No camera for this one."},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    summary = r.json()["report"]["emotion_summary"]
    assert summary == {
        "sample_count": 0,
        "avg_engagement": None,
        "avg_stress_proxy": None,
        "avg_positive_expression_proxy": None,
    }
