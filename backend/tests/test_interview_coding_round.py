"""
The live coding round inside DSA, technical and mixed interviews: a turn in
the middle of the interview is a coding problem, "Run" checks the visible
tests, and submitting grades the code by running every test in the sandbox.
No LLM is called (interview deps are faked) and the problem is pinned to
Two Sum so solutions can be written here.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.main import app
from app.modules.coding.models import CodingProblem
from app.modules.interview import coding_round
from app.modules.interview import service as interview_service
from app.modules.interview.models import InterviewCodingRound, InterviewContext, InterviewTurn
from app.modules.interview.service import FinalReport, InterviewDeps, TurnEvaluation, get_interview_deps
from app.modules.mkt.service import MKTDeps, get_mkt_deps
from tests.fakes import SubstringVerifier, fake_embed

TWO_SUM = """
def solve(nums, target):
    seen = {}
    for i, n in enumerate(nums):
        if target - n in seen:
            return [seen[target - n], i]
        seen[n] = i
"""

# Always returns [0, 1]: right on the visible tests where that is the answer
# (the 1st and 3rd), wrong on the other two.
WRONG = "def solve(nums, target):\n    return [0, 1]\n"

reviews = []


def _evaluate(context, history, question, answer):
    reviews.append((question, answer))
    return TurnEvaluation(score=7, evaluation="Clean hash-map solution.", next_question=f"Follow-up #{len(history) + 1}?")


def _report(context, history):
    return FinalReport(
        overall_score=70, communication=70, technical_knowledge=70, answer_relevance=70, clarity=70,
        problem_solving=70, strengths=["x"], areas_for_improvement=["y"], final_feedback="ok",
    )


DEPS = InterviewDeps(
    generate_first_question=lambda context: "Tell me about yourself.",
    evaluate_answer=_evaluate,
    generate_report=_report,
)


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_interview_deps] = lambda: DEPS
    app.dependency_overrides[get_mkt_deps] = lambda: MKTDeps(verifier=SubstringVerifier(), embed=fake_embed)

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _pinned_problem(monkeypatch):
    monkeypatch.setattr(interview_service, "_resume_context_text", lambda context: "")
    monkeypatch.setattr(
        coding_round, "pick_problem", lambda db, user_id, level: db.get(CodingProblem, "code.two_sum")
    )
    reviews.clear()


def _register(client, username):
    r = client.post("/auth/register", json={"username": username, "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _start(client, headers, interview_type="dsa", num_questions=3):
    body = {
        "target_role": "Backend Engineer", "experience_level": "junior", "interview_type": interview_type,
        "duration_minutes": 30, "num_questions": num_questions,
    }
    context_id = client.post("/interview/context", json=body, headers=headers).json()["context_id"]
    return client.post("/interview/sessions", json={"context_id": context_id}, headers=headers).json()


def _answer(client, headers, session_id, answer):
    client.post(f"/interview/sessions/{session_id}/listening", headers=headers)
    r = client.post(f"/interview/sessions/{session_id}/answer", json={"answer": answer}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _reach_coding_round(client, username):
    headers = _register(client, username)
    session = _start(client, headers)
    assert session["coding"] is None

    session = _answer(client, headers, session["session_id"], "I build backend services in Python.")
    client.post(f"/interview/sessions/{session['session_id']}/listening", headers=headers)
    return headers, session


def test_the_middle_turn_is_a_coding_question_with_visible_tests(client):
    _, session = _reach_coding_round(client, "coding_round_shape")

    assert session["question_number"] == 2
    assert "coding round" in session["question"].lower()

    problem = session["coding"]["problem"]
    assert problem["title"] == "Two Sum"
    assert len(problem["tests"]) == 3 and problem["hidden_test_count"] == 1
    assert session["coding"]["code"] == problem["starter_code"]


def test_run_reports_each_visible_test_and_saves_the_draft(client):
    headers, session = _reach_coding_round(client, "coding_round_run")
    sid = session["session_id"]

    r = client.post(f"/interview/sessions/{sid}/code/run", json={"code": WRONG}, headers=headers)
    assert r.status_code == 200, r.text
    run = r.json()
    assert (run["passed"], run["total"]) == (2, 3)
    assert [t["status"] for t in run["results"]] == ["ok", "wrong_answer", "ok"]
    assert run["results"][1]["args"] == [[3, 2, 4], 6]
    assert run["results"][1]["expected"] == [1, 2] and run["results"][1]["output"] == [0, 1]

    # The draft survives a page refresh.
    again = client.get(f"/interview/sessions/{sid}", headers=headers).json()
    assert again["coding"]["code"] == WRONG

    errors = client.post(f"/interview/sessions/{sid}/code/run", json={"code": "def solve(nums, target):\n    return 1/0\n"}, headers=headers).json()
    assert errors["results"][0]["status"] == "runtime_error" and "division by zero" in errors["results"][0]["error"]


def test_submitting_a_correct_solution_scores_full_marks(client):
    headers, session = _reach_coding_round(client, "coding_round_ac")
    sid = session["session_id"]

    body = _answer(client, headers, sid, TWO_SUM)
    assert body["question_number"] == 3 and body["coding"] is None

    with SessionLocal() as db:
        turn = db.query(InterviewTurn).filter_by(session_id=sid, seq=2).one()
        graded = db.get(InterviewCodingRound, turn.id)
        assert (graded.verdict, graded.passed, graded.total) == ("AC", 4, 4)
        assert turn.score == 10
        assert turn.evaluation.startswith("Accepted: passed 4/4 tests")
        assert "Code review: Clean hash-map solution." in turn.evaluation
        assert turn.comm_metrics is None

    # The LLM reviewed the problem and code, not the spoken intro.
    question, answer = reviews[-1]
    assert question.startswith("Coding problem: Two Sum") and "```python" in answer and "Accepted" in answer


def test_a_wrong_solution_explains_the_first_failing_case_and_shows_in_the_report(client):
    headers, session = _reach_coding_round(client, "coding_round_wa")
    sid = session["session_id"]

    _answer(client, headers, sid, WRONG)
    report = _answer(client, headers, sid, "My final answer.")["report"]

    coding = report["question_feedback"][1]
    assert coding["source"] == "coding"
    assert coding["coding"] == {"problem_title": "Two Sum", "difficulty": "Easy", "verdict": "WA", "passed": 2, "total": 4}
    assert "Failed on input [[3, 2, 4], 6]: expected [1, 2], got [0, 1]." in coding["evaluation"]
    assert coding["score"] == 5  # half the tests pass


def test_submitting_the_starter_code_scores_the_minimum(client):
    headers, session = _reach_coding_round(client, "coding_round_empty")

    _answer(client, headers, session["session_id"], session["coding"]["problem"]["starter_code"])

    with SessionLocal() as db:
        turn = db.query(InterviewTurn).filter_by(session_id=session["session_id"], seq=2).one()
        assert turn.score == 1 and "No solution was written" in turn.evaluation


def test_run_is_rejected_outside_a_coding_question(client):
    headers = _register(client, "coding_round_not_coding")
    session = _start(client, headers)
    client.post(f"/interview/sessions/{session['session_id']}/listening", headers=headers)

    r = client.post(f"/interview/sessions/{session['session_id']}/code/run", json={"code": TWO_SUM}, headers=headers)
    assert r.status_code == 400


def test_hr_interviews_have_no_coding_round(client):
    headers = _register(client, "coding_round_hr")
    session = _start(client, headers, interview_type="hr")

    body = _answer(client, headers, session["session_id"], "Answer one.")
    assert body["coding"] is None


@pytest.mark.parametrize(
    "interview_type, num_questions, expected",
    [
        ("dsa", 3, 2),
        ("dsa", 4, 4),  # turn 3 belongs to MKT
        ("technical", 6, 4),
        ("mixed", 5, 4),
        ("dsa", None, 4),
        ("dsa", 1, None),
        ("hr", 5, None),
        ("core_cs", 5, None),
    ],
)
def test_coding_round_position(interview_type, num_questions, expected):
    context = InterviewContext(interview_type=interview_type)
    is_mkt_seq = lambda seq: interview_type in interview_service.MKT_ELIGIBLE_INTERVIEW_TYPES and interview_service._is_mkt_turn_seq(seq)  # noqa: E731

    assert coding_round.coding_seq(context, num_questions, is_mkt_seq) == expected
