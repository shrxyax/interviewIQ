"""
Phase 12: the in-app evidence timeline for a completed/in-progress interview
session (GET /interview/sessions/{id}/evidence).

Covers: a session mixing MKT-driven and plain-LLM turns (with communication
metrics attached to every answered turn) returns a correctly ordered
timeline; a session with no MKT turns still returns a valid, shorter
timeline; and cross-user access is rejected the same way the session GET
endpoint already is (Phase 11's ownership pattern).
"""

import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.main import app
from app.modules.interview import service as interview_service
from app.modules.interview.models import InterviewTurn
from app.modules.interview.service import FinalReport, InterviewDeps, TurnEvaluation, get_interview_deps
from app.modules.mkt.models import ProbeTemplate
from app.modules.mkt.service import MKTDeps, get_mkt_deps
from tests.fakes import SubstringVerifier, fake_embed


def _fake_generate_first_question(context):
    return f"Tell me about your experience as a {context.target_role}."


def _fake_evaluate_answer(context, history, question, answer):
    return TurnEvaluation(score=7, evaluation="Solid answer.", next_question=f"Plain follow-up #{len(history) + 1}?")


def _fake_generate_report(context, history):
    return FinalReport(
        overall_score=75, communication=70, technical_knowledge=80, answer_relevance=75,
        clarity=72, problem_solving=78, strengths=["Clear"], areas_for_improvement=["Depth"],
        final_feedback="Good.",
    )


FAKE_INTERVIEW_DEPS = InterviewDeps(
    generate_first_question=_fake_generate_first_question,
    evaluate_answer=_fake_evaluate_answer,
    generate_report=_fake_generate_report,
)
FAKE_MKT_DEPS = MKTDeps(verifier=SubstringVerifier(), embed=fake_embed)


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_interview_deps] = lambda: FAKE_INTERVIEW_DEPS
    app.dependency_overrides[get_mkt_deps] = lambda: FAKE_MKT_DEPS

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _no_resume_context(monkeypatch):
    monkeypatch.setattr(interview_service, "_resume_context_text", lambda context: "")


def _register(client, username):
    r = client.post("/auth/register", json={"username": username, "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _create_context(client, headers, **overrides):
    body = {
        "target_role": "Backend Engineer",
        "experience_level": "junior",
        "interview_type": "technical",
        "duration_minutes": 30,
        "num_questions": 4,
        **overrides,
    }
    r = client.post("/interview/context", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["context_id"]


def _answer_turn(client, headers, session_id, answer, emotion_signal=None):
    r = client.post(f"/interview/sessions/{session_id}/listening", headers=headers)
    assert r.status_code == 200, r.text

    body = {"answer": answer}
    if emotion_signal is not None:
        body["emotion_signal"] = emotion_signal

    r = client.post(f"/interview/sessions/{session_id}/answer", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_evidence_timeline_mixes_mkt_and_comms_in_order(client):
    headers = _register(client, "evidence_user_mkt")
    context_id = _create_context(client, headers)

    session_id = client.post("/interview/sessions", json={"context_id": context_id}, headers=headers).json()["session_id"]

    # Turns 1-2: plain LLM-driven turns, each with an emotion signal attached.
    _answer_turn(client, headers, session_id, "My first plain answer.", emotion_signal={"valence": 0.5})
    _answer_turn(client, headers, session_id, "My second plain answer.", emotion_signal={"valence": 0.4})

    with SessionLocal() as db:
        turn3 = db.query(InterviewTurn).filter_by(session_id=session_id, seq=3).one()
        assert turn3.source == "mkt"
        template = db.get(ProbeTemplate, turn3.mkt_template_id)
        correct_answer = ". ".join(template.relation_spec.get("must_entail", []))

    # Turn 3: MKT-driven, turn 4: plain again.
    _answer_turn(client, headers, session_id, correct_answer)
    _answer_turn(client, headers, session_id, "My final plain answer.")

    r = client.get(f"/interview/sessions/{session_id}/evidence", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["session_id"] == session_id
    items = body["items"]
    assert body["item_count"] == len(items)

    # Every answered turn contributes an "interview"-or-"mkt" item plus a
    # "comms" communication_analysis item; turns 1-2 also get an emotion item.
    assert [i["seq"] for i in items[:3]] == [1, 1, 1]
    assert items[0]["source"] == "interview"
    assert items[1]["source"] == "comms" and items[1]["signal"] == "communication_analysis"
    assert items[2]["source"] == "comms" and items[2]["signal"] == "emotion_snapshot"

    mkt_items = [i for i in items if i["source"] == "mkt"]
    assert len(mkt_items) == 1
    mkt_item = mkt_items[0]
    assert mkt_item["seq"] == 3
    assert mkt_item["concept_id"] is not None
    assert mkt_item["belief_before"] is not None
    assert mkt_item["belief_after"] is not None
    assert mkt_item["outcome"] is not None
    assert "probe on" in mkt_item["description"]

    # Ordering is chronological by turn seq.
    seqs = [i["seq"] for i in items]
    assert seqs == sorted(seqs)


def test_evidence_timeline_valid_and_shorter_without_mkt_turns(client):
    headers = _register(client, "evidence_user_hr")
    context_id = _create_context(client, headers, interview_type="hr", num_questions=2)
    session_id = client.post("/interview/sessions", json={"context_id": context_id}, headers=headers).json()["session_id"]

    _answer_turn(client, headers, session_id, "An HR-style answer.")
    _answer_turn(client, headers, session_id, "Another HR-style answer.")

    r = client.get(f"/interview/sessions/{session_id}/evidence", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["item_count"] > 0
    assert all(i["source"] != "mkt" for i in body["items"])
    assert all(i["signal"] != "emotion_snapshot" for i in body["items"])


def test_evidence_timeline_rejects_cross_user_access(client):
    owner_headers = _register(client, "evidence_owner")
    context_id = _create_context(client, owner_headers)
    session_id = client.post("/interview/sessions", json={"context_id": context_id}, headers=owner_headers).json()["session_id"]

    stranger_headers = _register(client, "evidence_stranger")
    r = client.get(f"/interview/sessions/{session_id}/evidence", headers=stranger_headers)
    assert r.status_code == 404
