"""
The system-design lab round inside system-design interviews: a turn in the
middle of the interview is an executable whiteboard exercise; "Analyze"
runs the engine on the draft and submitting grades the design by SLOs,
resilience, SPOFs and headroom. No LLM is called (interview deps are faked)
and the prompt is pinned to the URL shortener.
"""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.main import app
from app.modules.interview import design_round
from app.modules.interview import service as interview_service
from app.modules.interview.models import InterviewContext, InterviewDesignRound, InterviewTurn
from app.modules.interview.service import FinalReport, InterviewDeps, TurnEvaluation, get_interview_deps
from app.modules.whiteboard.models import DesignPrompt

reviews = []


def _evaluate(context, history, question, answer):
    reviews.append((question, answer))
    return TurnEvaluation(score=7, evaluation="Good use of replicas.", next_question=f"Follow-up #{len(history) + 1}?")


def _report(context, history):
    return FinalReport(
        overall_score=70, communication=70, technical_knowledge=70, answer_relevance=70, clarity=70,
        problem_solving=70, strengths=["x"], areas_for_improvement=["y"], final_feedback="ok",
    )


DEPS = InterviewDeps(
    generate_first_question=lambda context: "Tell me about a system you designed.",
    evaluate_answer=_evaluate,
    generate_report=_report,
)


def _url_shortener(db):
    return next(p for p in db.query(DesignPrompt).filter_by(simulatable=True) if p.title == "Design a URL Shortener")


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_interview_deps] = lambda: DEPS
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _pinned_prompt(monkeypatch):
    monkeypatch.setattr(interview_service, "_resume_context_text", lambda context: "")
    monkeypatch.setattr(design_round, "pick_prompt", lambda db, user_id, level: _url_shortener(db))
    reviews.clear()


def _scaled(graph, replicas):
    graph = copy.deepcopy(graph)
    for node in graph["nodes"]:
        if node["id"] in replicas:
            node["params"]["replicas"] = replicas[node["id"]]
    return graph


# 60 API servers for 20k rps (800 each), everything else doubled/tripled.
GOOD = {"lb": 2, "api": 60, "cache": 2, "db": 3}


def _register(client, username):
    r = client.post("/auth/register", json={"username": username, "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _start(client, headers, interview_type="system_design", num_questions=3):
    body = {
        "target_role": "Backend Engineer", "experience_level": "mid", "interview_type": interview_type,
        "duration_minutes": 30, "num_questions": num_questions,
    }
    context_id = client.post("/interview/context", json=body, headers=headers).json()["context_id"]
    return client.post("/interview/sessions", json={"context_id": context_id}, headers=headers).json()


def _answer(client, headers, session_id, answer):
    client.post(f"/interview/sessions/{session_id}/listening", headers=headers)
    r = client.post(f"/interview/sessions/{session_id}/answer", json={"answer": answer}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _reach_design_round(client, username):
    headers = _register(client, username)
    session = _start(client, headers)
    assert session["design"] is None

    session = _answer(client, headers, session["session_id"], "I designed a booking backend.")
    client.post(f"/interview/sessions/{session['session_id']}/listening", headers=headers)
    return headers, session


def test_the_middle_turn_is_a_design_lab_exercise(client):
    _, session = _reach_design_round(client, "design_round_shape")

    assert session["question_number"] == 2
    assert "design exercise" in session["question"].lower()
    design = session["design"]
    assert design["prompt"]["title"] == "Design a URL Shortener"
    assert design["prompt"]["requirements"]["peak_rps"] == 20000
    assert {c["id"] for c in design["catalog"]} >= {"api_service", "cache", "sql_primary"}
    assert {n["id"] for n in design["graph"]["nodes"]} == {"client", "lb", "api", "cache", "db"}


def test_analyze_measures_the_draft_and_saves_it(client):
    headers, session = _reach_design_round(client, "design_round_analyze")
    sid, starter = session["session_id"], session["design"]["graph"]

    r = client.post(f"/interview/sessions/{sid}/design/analyze", json={"graph": starter}, headers=headers)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["node_metrics"]["api"]["saturated"] is True
    assert result["summary"]["max_sustainable_rps"] == 1600
    assert any(f["type"] == "saturation" and f["node_id"] == "api" for f in result["findings"])

    better = _scaled(starter, GOOD)
    client.post(f"/interview/sessions/{sid}/design/analyze", json={"graph": better}, headers=headers)
    again = client.get(f"/interview/sessions/{sid}", headers=headers).json()
    assert again["design"]["graph"] == better  # the draft survives a refresh


def test_an_invalid_design_is_reported_not_crashed(client):
    headers, session = _reach_design_round(client, "design_round_invalid")
    graph = {"nodes": [{"id": "api", "type": "api_service", "params": {"replicas": 1}}], "edges": []}

    r = client.post(f"/interview/sessions/{session['session_id']}/design/analyze", json={"graph": graph}, headers=headers)
    assert r.status_code == 400
    assert "client" in r.json()["detail"]


def test_a_good_design_scores_high_and_reaches_the_llm_with_its_measurements(client):
    headers, session = _reach_design_round(client, "design_round_good")
    sid = session["session_id"]
    answer = json.dumps({"graph": _scaled(session["design"]["graph"], GOOD), "explanation": "Scaled the API tier to 60."})

    body = _answer(client, headers, sid, answer)
    assert body["question_number"] == 3 and body["design"] is None

    with SessionLocal() as db:
        turn = db.query(InterviewTurn).filter_by(session_id=sid, seq=2).one()
        graded = db.get(InterviewDesignRound, turn.id)
        assert graded.slo_satisfied is True
        assert graded.resilience_pct == 50.0
        assert turn.answer == "Scaled the API tier to 60."
        assert turn.evaluation.startswith("Meets its requirements.")
        assert "Design review: Good use of replicas." in turn.evaluation
        assert turn.score == 8  # 1 + 4 (SLOs) + 1.5 (resilience) + 1 (no SPOF) + 1 (headroom)

    question, llm_answer = reviews[-1]
    assert question.startswith("System design exercise: Design a URL Shortener")
    assert "Meets SLOs" in llm_answer and "Scaled the API tier to 60." in llm_answer


def test_the_unchanged_starter_design_scores_low_and_shows_in_the_report(client):
    headers, session = _reach_design_round(client, "design_round_starter")
    sid = session["session_id"]

    _answer(client, headers, sid, json.dumps({"graph": session["design"]["graph"], "explanation": ""}))
    report = _answer(client, headers, sid, "Final answer.")["report"]

    entry = report["question_feedback"][1]
    assert entry["source"] == "design"
    assert entry["design"]["prompt_title"] == "Design a URL Shortener"
    assert entry["design"]["slo_satisfied"] is False and entry["design"]["resilience_pct"] == 0.0
    assert entry["score"] <= 2
    assert "Does not meet its requirements." in entry["evaluation"]
    assert "The starting design was submitted unchanged." in entry["evaluation"]


def test_analyze_is_rejected_outside_a_design_question(client):
    headers = _register(client, "design_round_not_design")
    session = _start(client, headers)
    client.post(f"/interview/sessions/{session['session_id']}/listening", headers=headers)

    r = client.post(f"/interview/sessions/{session['session_id']}/design/analyze", json={"graph": {}}, headers=headers)
    assert r.status_code == 400


def test_only_system_design_interviews_have_a_design_round():
    for interview_type, expected in [("system_design", 2), ("dsa", None), ("hr", None), ("mixed", None)]:
        context = InterviewContext(interview_type=interview_type)
        assert design_round.design_seq(context, 3, lambda seq: False) == expected


def test_parse_answer_accepts_json_or_plain_text():
    graph = {"nodes": [], "edges": []}
    assert design_round.parse_answer(json.dumps({"graph": graph, "explanation": " Why "})) == (graph, "Why")
    assert design_round.parse_answer("Just words") == (None, "Just words")
