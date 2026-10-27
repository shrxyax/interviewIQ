"""
Phase 7: MKT integrated into the live conversational interview.

Covers:
- an eligible interview session routes a fixed turn through MKT's belief
  engine instead of the plain LLM path, and that turn's answer updates
  belief state (ConceptBelief) the same way the standalone MKT session does;
- mr_transfer's outcome derivation distinguishes a robust candidate from a
  memoriser, the same signature as the existing metamorphic relations;
- resume-grounded probe generation is validated before use and rejected
  when the LLM's output doesn't ground in the resume or target the concept.

No test here hits the real Gemini API: resume retrieval is monkeypatched to
return no context (so the interview flow never attempts LLM-based probe
generation), and the resume-grounded generation unit tests monkeypatch the
LLM gateway directly.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.main import app
from app.modules.interview import service as interview_service
from app.modules.interview.models import InterviewSession, InterviewTurn
from app.modules.interview.service import FinalReport, InterviewDeps, TurnEvaluation, get_interview_deps
from app.modules.mkt.consistency import AnswerAssessment, relation_outcome
from app.modules.mkt.models import Concept, ConceptBelief, ProbeTemplate
from app.modules.mkt.resume_probe import GeneratedProbe, generate_resume_grounded_probe
from app.modules.mkt.service import MKTDeps, get_mkt_deps
from app.modules.mkt.states import CONSISTENT_CORRECT, CONSISTENT_WRONG, INCONSISTENT, MR_TRANSFER
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
    # Keeps the interview flow from ever calling the real retriever/LLM for
    # resume-grounded probe generation; only the seeded-template path runs.
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


def _answer_turn(client, headers, session_id, answer):
    r = client.post(f"/interview/sessions/{session_id}/listening", headers=headers)
    assert r.status_code == 200, r.text

    r = client.post(f"/interview/sessions/{session_id}/answer", json={"answer": answer}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_fixed_turn_routes_through_mkt_and_updates_belief(client):
    headers = _register(client, "mkt_interview_user")
    context_id = _create_context(client, headers)

    session = client.post("/interview/sessions", json={"context_id": context_id}, headers=headers).json()
    session_id = session["session_id"]

    # Turns 1 and 2: plain LLM-driven turns.
    body = _answer_turn(client, headers, session_id, "My first plain answer.")
    assert body["question_number"] == 2
    body = _answer_turn(client, headers, session_id, "My second plain answer.")
    assert body["question_number"] == 3

    with SessionLocal() as db:
        turn3 = db.query(InterviewTurn).filter_by(session_id=session_id, seq=3).one()
        assert turn3.source == "mkt"
        assert turn3.mkt_concept_id is not None
        assert turn3.mkt_probe_type is not None
        assert turn3.question == body["question"]

        template = db.get(ProbeTemplate, turn3.mkt_template_id)
        concept_id = turn3.mkt_concept_id
        correct_answer = ". ".join(template.relation_spec.get("must_entail", []))

    # A correct, on-concept answer to the MKT-driven turn.
    body = _answer_turn(client, headers, session_id, correct_answer)
    assert body["question_number"] == 4

    with SessionLocal() as db:
        turn3 = db.query(InterviewTurn).filter_by(session_id=session_id, seq=3).one()
        assert turn3.mkt_outcome in (CONSISTENT_CORRECT, "partial")
        assert turn3.mkt_belief_after is not None
        assert turn3.score is not None and turn3.evaluation is not None

        belief = db.get(ConceptBelief, (_user_id(db, headers), concept_id))
        assert belief is not None
        assert belief.n_obs >= 1

        session_row = db.get(InterviewSession, session_id)
        assert session_row.mkt_state is not None
        assert session_row.mkt_state["last_concept"] == concept_id


def test_final_report_includes_concept_belief_summary_for_mkt_turns(client):
    headers = _register(client, "mkt_report_user")
    context_id = _create_context(client, headers)

    session = client.post("/interview/sessions", json={"context_id": context_id}, headers=headers).json()
    session_id = session["session_id"]

    _answer_turn(client, headers, session_id, "My first plain answer.")
    _answer_turn(client, headers, session_id, "My second plain answer.")

    with SessionLocal() as db:
        template = db.get(ProbeTemplate, db.query(InterviewTurn).filter_by(session_id=session_id, seq=3).one().mkt_template_id)
        correct_answer = ". ".join(template.relation_spec.get("must_entail", []))

    _answer_turn(client, headers, session_id, correct_answer)
    body = _answer_turn(client, headers, session_id, "My final plain answer.")

    report = body["report"]
    assert report is not None

    summary = report["concept_belief_summary"]
    assert summary["sample_count"] == 1
    assert len(summary["concepts"]) == 1

    concept_summary = summary["concepts"][0]
    assert concept_summary["probe_count"] == 1
    assert concept_summary["classification"] in ("absent", "memorised", "misconceived", "robust")
    assert 0.0 <= concept_summary["mastery"] <= 1.0


def test_final_report_concept_belief_summary_absent_for_non_mkt_session(client):
    headers = _register(client, "mkt_report_hr_user")
    context_id = _create_context(client, headers, interview_type="hr", num_questions=2)
    session_id = client.post("/interview/sessions", json={"context_id": context_id}, headers=headers).json()["session_id"]

    _answer_turn(client, headers, session_id, "An HR-style answer.")
    body = _answer_turn(client, headers, session_id, "Another HR-style answer.")

    report = body["report"]
    assert report is not None
    assert report["concept_belief_summary"] == {"sample_count": 0, "concepts": []}


def _user_id(db, headers):
    import jwt

    from app.core.config import settings

    token = headers["Authorization"].split(" ")[1]
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return int(payload["sub"])


def test_mkt_disabled_for_non_eligible_interview_types(client):
    headers = _register(client, "mkt_hr_user")
    context_id = _create_context(client, headers, interview_type="hr", num_questions=4)
    session_id = client.post("/interview/sessions", json={"context_id": context_id}, headers=headers).json()["session_id"]

    for _ in range(3):
        _answer_turn(client, headers, session_id, "An HR-style answer.")

    with SessionLocal() as db:
        turns = db.query(InterviewTurn).filter_by(session_id=session_id).all()
        assert all(t.source == "llm" for t in turns)


def test_mr_transfer_outcome_matches_robust_vs_memoriser_signature():
    # A robust candidate: correct on the base question and on the transfer
    # probe (understanding generalises to the new context).
    robust_transfer = AnswerAssessment(answer_class="correct", coverage=1.0, propositions=[], verdicts={})
    outcome, _ = relation_outcome(MR_TRANSFER, "correct", robust_transfer)
    assert outcome == CONSISTENT_CORRECT

    # A memoriser: correct on the base (canned) question, but wrong on the
    # transfer probe because the understanding doesn't actually generalise.
    memoriser_transfer = AnswerAssessment(answer_class="wrong", coverage=0.0, propositions=[], verdicts={})
    outcome, _ = relation_outcome(MR_TRANSFER, "correct", memoriser_transfer)
    assert outcome == INCONSISTENT

    # A candidate with no understanding at all: wrong on both.
    consistently_wrong = AnswerAssessment(answer_class="wrong", coverage=0.0, propositions=[], verdicts={})
    outcome, _ = relation_outcome(MR_TRANSFER, "wrong", consistently_wrong)
    assert outcome == CONSISTENT_WRONG


class _FakeStructuredLLM:
    """Monkeypatches app.core.llm_gateway.generate_structured for one call."""

    def __init__(self, result):
        self.result = result

    def __call__(self, prompt, schema, task=""):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_resume_grounded_probe_is_accepted_when_grounded_and_on_concept(monkeypatch):
    concept = Concept(
        id="dsa.search.binary_search", domain="dsa", name="Binary Search",
        key_facts=["Binary search runs in O(log n) time", "Binary search requires sorted input"],
        misconceptions=[],
    )
    resume_text = "Built a product search feature using binary search over a sorted price index for fast lookups."

    good = GeneratedProbe(
        question="In your product search feature, you used binary search over a sorted price index - why does that give O(log n) lookups?",
        must_entail=["Binary search runs in O(log n) time because it halves the search range each step"],
        must_not_entail=[],
        grounding_reference="binary search over a sorted price index",
    )

    monkeypatch.setattr("app.core.llm_gateway.generate_structured", _FakeStructuredLLM(good))

    result = generate_resume_grounded_probe(concept, "base", resume_text)
    assert result is not None
    assert result.question == good.question


def test_resume_grounded_probe_is_rejected_when_not_actually_grounded(monkeypatch):
    concept = Concept(
        id="dsa.search.binary_search", domain="dsa", name="Binary Search",
        key_facts=["Binary search runs in O(log n) time", "Binary search requires sorted input"],
        misconceptions=[],
    )
    resume_text = "Built a product search feature using binary search over a sorted price index for fast lookups."

    # grounding_reference is fabricated - not present anywhere in the resume text.
    fabricated = GeneratedProbe(
        question="You mention leading a team of 50 engineers - how does binary search relate to team scaling?",
        must_entail=["Binary search runs in O(log n) time"],
        must_not_entail=[],
        grounding_reference="leading a team of 50 engineers",
    )

    monkeypatch.setattr("app.core.llm_gateway.generate_structured", _FakeStructuredLLM(fabricated))
    assert generate_resume_grounded_probe(concept, "base", resume_text) is None


def test_resume_grounded_probe_is_rejected_when_off_concept(monkeypatch):
    concept = Concept(
        id="dsa.search.binary_search", domain="dsa", name="Binary Search",
        key_facts=["Binary search runs in O(log n) time", "Binary search requires sorted input"],
        misconceptions=[],
    )
    resume_text = "Built a product search feature using binary search over a sorted price index for fast lookups."

    # Grounded in the resume (the quote is real), but the claims don't
    # actually target the "Binary Search" concept at all.
    off_concept = GeneratedProbe(
        question="Your price index component - what color scheme did its dashboard use?",
        must_entail=["The dashboard used a blue and white color scheme"],
        must_not_entail=[],
        grounding_reference="price index",
    )

    monkeypatch.setattr("app.core.llm_gateway.generate_structured", _FakeStructuredLLM(off_concept))
    assert generate_resume_grounded_probe(concept, "base", resume_text) is None


def test_resume_grounded_probe_generation_falls_back_silently_on_llm_error(monkeypatch):
    concept = Concept(id="dsa.search.binary_search", domain="dsa", name="Binary Search", key_facts=[], misconceptions=[])

    monkeypatch.setattr("app.core.llm_gateway.generate_structured", _FakeStructuredLLM(RuntimeError("quota exhausted")))
    assert generate_resume_grounded_probe(concept, "base", "some resume text") is None


# --------------------------------------------------------------------------
# MKT as the fallback question source when the LLM is unavailable
# --------------------------------------------------------------------------

def _llm_down_evaluate_answer(context, history, question, answer):
    # What _default_evaluate_answer returns when the LLM call fails.
    return TurnEvaluation(score=5, evaluation="Detailed evaluation was unavailable.", next_question="")


LLM_DOWN_INTERVIEW_DEPS = InterviewDeps(
    generate_first_question=_fake_generate_first_question,
    evaluate_answer=_llm_down_evaluate_answer,
    generate_report=_fake_generate_report,
)


@pytest.fixture
def llm_down_client(client):
    app.dependency_overrides[get_interview_deps] = lambda: LLM_DOWN_INTERVIEW_DEPS
    yield client
    app.dependency_overrides[get_interview_deps] = lambda: FAKE_INTERVIEW_DEPS


def _questions_for(client, headers, interview_type, turns):
    context_id = _create_context(client, headers, interview_type=interview_type, num_questions=turns + 1)
    session = client.post("/interview/sessions", json={"context_id": context_id}, headers=headers).json()

    for i in range(turns):
        _answer_turn(client, headers, session["session_id"], f"Answer number {i}.")

    with SessionLocal() as db:
        return db.query(InterviewTurn).filter_by(session_id=session["session_id"]).order_by(InterviewTurn.seq).all()


@pytest.mark.parametrize("interview_type", ["custom", "mixed", "technical"])
def test_without_the_llm_every_later_turn_is_a_distinct_mkt_probe(llm_down_client, interview_type):
    headers = _register(llm_down_client, f"llm_down_{interview_type}")
    turns = _questions_for(llm_down_client, headers, interview_type, turns=5)

    # Technical and mixed interviews also have one coding round.
    expected_coding = 1 if interview_type in ("mixed", "technical") else 0
    assert sum(t.source == "coding" for t in turns) == expected_coding

    later = [t for t in turns[1:] if t.source != "coding"]
    assert [t.source for t in later] == ["mkt"] * (5 - expected_coding)
    assert len({t.question for t in later}) == len(later)
    assert all(t.mkt_concept_id and t.mkt_probe_type for t in later)


def test_without_the_llm_hr_questions_come_from_the_bank_without_repeats(llm_down_client):
    headers = _register(llm_down_client, "llm_down_hr")
    turns = _questions_for(llm_down_client, headers, "hr", turns=5)

    later = turns[1:]
    assert [t.source for t in later] == ["llm"] * 5
    assert len({t.question for t in later}) == 5
