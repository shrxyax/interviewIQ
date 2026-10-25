"""
End-to-end tests for the persisted interview state machine: legal
transitions happen, illegal ones are rejected, the session is resumable
from a GET, and both the question-count limit and the server clock can
end the interview.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.interview.service import FinalReport, InterviewDeps, TurnEvaluation, get_interview_deps


def _fake_generate_first_question(context):
    return f"Tell me about your experience as a {context.target_role}."


def _fake_evaluate_answer(context, history, question, answer):
    return TurnEvaluation(score=7, evaluation="Solid answer.", next_question=f"Follow-up #{len(history) + 1}?")


def _fake_generate_report(context, history):
    return FinalReport(
        overall_score=75,
        communication=70,
        technical_knowledge=80,
        answer_relevance=75,
        clarity=72,
        problem_solving=78,
        strengths=["Clear communication"],
        areas_for_improvement=["More depth on trade-offs"],
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


CONTEXT_BODY = {
    "target_role": "Backend Engineer",
    "company": "Acme",
    "experience_level": "junior",
    "interview_type": "technical",
    "duration_minutes": 30,
    "num_questions": 2,
}


def _create_context(client, headers, **overrides):
    body = {**CONTEXT_BODY, **overrides}
    r = client.post("/interview/context", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["context_id"]


def test_full_happy_path_ends_on_question_count(client):
    headers = _register(client, "session_user_1")
    context_id = _create_context(client, headers)

    r = client.post("/interview/sessions", json={"context_id": context_id}, headers=headers)
    assert r.status_code == 200, r.text
    session = r.json()
    assert session["state"] == "AI_SPEAKING"
    assert session["question_number"] == 1
    assert session["total_questions"] == 2
    session_id = session["session_id"]

    # AI_SPEAKING -> LISTENING
    r = client.post(f"/interview/sessions/{session_id}/listening", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "LISTENING"

    # LISTENING -> PROCESSING -> AI_SPEAKING (question 1 of 2 answered)
    r = client.post(f"/interview/sessions/{session_id}/answer", json={"answer": "My first answer."}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "AI_SPEAKING"
    assert body["question_number"] == 2
    assert body["report"] is None

    r = client.post(f"/interview/sessions/{session_id}/listening", headers=headers)
    assert r.status_code == 200

    # Second (final) answer ends the interview via the question-count limit.
    r = client.post(f"/interview/sessions/{session_id}/answer", json={"answer": "My second answer."}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "REPORT"
    assert body["report"]["overall_score"] == 75
    assert len(body["report"]["question_feedback"]) == 2
    assert body["report"]["question_feedback"][0]["answer"] == "My first answer."


def test_illegal_transitions_are_rejected(client):
    headers = _register(client, "session_user_2")
    context_id = _create_context(client, headers)

    session = client.post("/interview/sessions", json={"context_id": context_id}, headers=headers).json()
    session_id = session["session_id"]

    # Still AI_SPEAKING: answering before listening is illegal.
    r = client.post(f"/interview/sessions/{session_id}/answer", json={"answer": "too soon"}, headers=headers)
    assert r.status_code == 400

    r = client.post(f"/interview/sessions/{session_id}/listening", headers=headers)
    assert r.status_code == 200

    # Already LISTENING: a second "listening" call is illegal.
    r = client.post(f"/interview/sessions/{session_id}/listening", headers=headers)
    assert r.status_code == 400

    # Empty answers are rejected without changing state.
    r = client.post(f"/interview/sessions/{session_id}/answer", json={"answer": "   "}, headers=headers)
    assert r.status_code == 400

    r = client.get(f"/interview/sessions/{session_id}", headers=headers)
    assert r.json()["state"] == "LISTENING"


def test_session_is_resumable(client):
    headers = _register(client, "session_user_3")
    context_id = _create_context(client, headers)

    started = client.post("/interview/sessions", json={"context_id": context_id}, headers=headers).json()
    session_id = started["session_id"]

    # Simulates a page refresh mid-interview: a fresh GET restores state.
    resumed = client.get(f"/interview/sessions/{session_id}", headers=headers)
    assert resumed.status_code == 200
    body = resumed.json()
    assert body["state"] == "AI_SPEAKING"
    assert body["question"] == started["question"]
    assert body["question_number"] == 1


def test_sessions_are_private(client):
    owner_headers = _register(client, "session_owner")
    context_id = _create_context(client, owner_headers)
    session_id = client.post("/interview/sessions", json={"context_id": context_id}, headers=owner_headers).json()["session_id"]

    other_headers = _register(client, "session_stranger")
    r = client.get(f"/interview/sessions/{session_id}", headers=other_headers)
    assert r.status_code == 404


def test_proctoring_events_are_recorded_and_summarized_in_report(client):
    headers = _register(client, "session_user_5")
    context_id = _create_context(client, headers, num_questions=1)
    session_id = client.post("/interview/sessions", json={"context_id": context_id}, headers=headers).json()["session_id"]

    for event_type in ["tab_hidden", "tab_visible", "face_lost", "tab_hidden", "face_regained"]:
        r = client.post(
            f"/interview/sessions/{session_id}/proctoring-event",
            json={"event_type": event_type},
            headers=headers,
        )
        assert r.status_code == 200, r.text

    summary = r.json()
    assert summary["tab_switch_count"] == 2
    assert summary["face_lost_count"] == 1

    r = client.post(f"/interview/sessions/{session_id}/listening", headers=headers)
    assert r.status_code == 200

    r = client.post(f"/interview/sessions/{session_id}/answer", json={"answer": "Final answer."}, headers=headers)
    assert r.status_code == 200, r.text
    report = r.json()["report"]
    assert report["proctoring_summary"] == {"tab_switch_count": 2, "face_lost_count": 1}


def test_proctoring_event_rejects_unknown_type(client):
    headers = _register(client, "session_user_6")
    context_id = _create_context(client, headers)
    session_id = client.post("/interview/sessions", json={"context_id": context_id}, headers=headers).json()["session_id"]

    r = client.post(
        f"/interview/sessions/{session_id}/proctoring-event",
        json={"event_type": "not_a_real_event"},
        headers=headers,
    )
    assert r.status_code == 422


def test_time_expiry_ends_interview_even_without_question_limit(client):
    headers = _register(client, "session_user_4")
    context_id = _create_context(client, headers, num_questions=None, duration_minutes=5)
    session_id = client.post("/interview/sessions", json={"context_id": context_id}, headers=headers).json()["session_id"]

    from app.core.db import SessionLocal
    from app.modules.interview.models import InterviewSession
    from datetime import datetime, timezone, timedelta

    with SessionLocal() as db:
        session = db.get(InterviewSession, session_id)
        session.ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    r = client.get(f"/interview/sessions/{session_id}", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "REPORT"
    assert body["report"]["question_feedback"] == []
