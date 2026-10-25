"""
Interview orchestration: a persisted conversational state machine on top
of an InterviewContext. Glue between the database, resume retrieval and
the LLM gateway - mirrors app/modules/mkt/service.py's shape (a
dependency-injected `deps` object so tests can fake the LLM calls).
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

import numpy as np
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.llm_gateway import generate_structured
from app.core.models import EvidenceEvent, Resume, User, utcnow
from app.modules.communication import service as communication_service
from app.modules.emotion import aggregate as emotion_aggregate
from app.modules.interview.models import (
    PROCTORING_LOG_LIMIT,
    InterviewContext,
    InterviewSession,
    InterviewTurn,
)
from app.modules.mkt import belief as MB
from app.modules.mkt.consistency import BASE_OUTCOME, CONTRADICTED, assess_answer, relation_outcome
from app.modules.mkt.emissions import DEFAULT_THETA
from app.modules.mkt.models import Concept, ProbeTemplate
from app.modules.mkt.resume_probe import generate_resume_grounded_probe, persist_generated_probe
from app.modules.mkt.selection import select_next
from app.modules.mkt.service import (
    MKTDeps,
    _descendant_counts,
    _initial_beliefs,
    _load_graph,
    _save_belief,
    _templates_by_concept,
)
from app.modules.mkt.states import BASE as MKT_BASE
from app.modules.mkt.states import MR_CONSTRAINT, MR_PARAPHRASE, STATES
from app.services.retriever import retrieve


# --------------------------------------------------------------------------
# MKT integration
# --------------------------------------------------------------------------
#
# Integration design (Phase 7): rather than a separate "MKT mode", a fixed
# subset of turns within an eligible interview route through MKT's belief
# engine and EIG-based probe selection instead of the plain LLM next-question
# path. Specifically: every MKT_TURN_INTERVAL-th turn (3, 6, 9, ...), capped
# at MKT_MAX_TURNS per session, is MKT-driven - for "technical" and "dsa"
# interviews only, where the seeded DSA concept bank is relevant. The
# candidate sees no difference: MKT-driven turns render through the exact
# same question/answer UI as plain turns (see InterviewTurn.source and the
# mkt_* columns, which are recorded silently for the Phase 10 report).
#
# Per-session MKT state (beliefs, asked templates, base-answered concepts,
# EIG continuity) lives in InterviewSession.mkt_state, built lazily on the
# first MKT-driven turn. It reuses belief.py's update/propagate logic and
# selection.py's EIG selection unchanged - this module only decides *when*
# a turn is MKT-driven and glues the result into the interview's turn/answer
# cycle. The standalone MKT experience (app/modules/mkt/service.py, the
# /mkt page) is untouched by any of this.

MKT_DOMAIN = "dsa"
MKT_ELIGIBLE_INTERVIEW_TYPES = {"technical", "dsa"}
MKT_TURN_INTERVAL = 3
MKT_MAX_TURNS = 3

# A conventional 1-10 score for history/report compatibility, derived from
# the MKT outcome rather than the plain LLM rubric.
_MKT_OUTCOME_SCORE = {
    "consistent_correct": 9,
    "partial": 6,
    "inconsistent": 3,
    "consistent_wrong": 2,
    "empty": 1,
    "capitulated": 1,
}


class InterviewContextError(ValueError):
    pass


class InterviewSessionError(ValueError):
    pass


# --------------------------------------------------------------------------
# InterviewContext (setup) - unchanged from the previous phase.
# --------------------------------------------------------------------------

def create_context(
    db: Session,
    user: User,
    *,
    target_role: str,
    interview_type: str,
    experience_level: str,
    duration_minutes: int,
    company: str | None = None,
    resume_id: int | None = None,
    num_questions: int | None = None,
) -> InterviewContext:
    if resume_id is not None:
        resume = db.get(Resume, resume_id)

        if resume is None or resume.user_id != user.id:
            raise InterviewContextError("Resume not found.")

    context = InterviewContext(
        id=str(uuid.uuid4()),
        user_id=user.id,
        resume_id=resume_id,
        target_role=target_role.strip(),
        company=company.strip() if company else None,
        experience_level=experience_level,
        interview_type=interview_type,
        duration_minutes=duration_minutes,
        num_questions=num_questions,
        status="active",
    )

    db.add(context)
    db.commit()

    return context


def get_context(db: Session, user: User, context_id: str) -> InterviewContext:
    context = db.get(InterviewContext, context_id)

    if context is None or context.user_id != user.id:
        raise InterviewContextError("Interview context not found.")

    return context


def public_context(context: InterviewContext) -> dict:
    return {
        "context_id": context.id,
        "target_role": context.target_role,
        "company": context.company,
        "experience_level": context.experience_level,
        "interview_type": context.interview_type,
        "duration_minutes": context.duration_minutes,
        "num_questions": context.num_questions,
        "resume_id": context.resume_id,
        "status": context.status,
    }


# --------------------------------------------------------------------------
# State machine
# --------------------------------------------------------------------------

READY = "READY"
AI_SPEAKING = "AI_SPEAKING"
LISTENING = "LISTENING"
PROCESSING = "PROCESSING"
TIME_EXPIRED = "TIME_EXPIRED"
GENERATING_REPORT = "GENERATING_REPORT"
REPORT = "REPORT"

# Legal transitions, keyed by the state being left. TIME_EXPIRED is not
# listed as a target here: the server clock can interrupt any live state
# (READY..PROCESSING) into TIME_EXPIRED, enforced separately in
# _apply_time_expiry rather than via this map.
TRANSITIONS: dict[str, set[str]] = {
    READY: {AI_SPEAKING},
    AI_SPEAKING: {LISTENING},
    LISTENING: {PROCESSING},
    PROCESSING: {AI_SPEAKING, GENERATING_REPORT},
    TIME_EXPIRED: {GENERATING_REPORT},
    GENERATING_REPORT: {REPORT},
    REPORT: set(),
}

LIVE_STATES = {READY, AI_SPEAKING, LISTENING, PROCESSING}


def _transition(session: InterviewSession, to_state: str) -> None:
    allowed = TRANSITIONS.get(session.state, set())

    if to_state not in allowed:
        raise InterviewSessionError(f"Cannot move from {session.state} to {to_state}.")

    session.state = to_state


def _apply_time_expiry(session: InterviewSession) -> bool:
    """
    Returns True (and forces TIME_EXPIRED) if the server-side clock has
    run out and the session hasn't already been wrapped up.
    """

    if session.state not in LIVE_STATES:
        return False

    ends_at = session.ends_at if session.ends_at.tzinfo else session.ends_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) >= ends_at:
        session.state = TIME_EXPIRED
        return True

    return False


def _get_owned_session(db: Session, user: User, session_id: str) -> InterviewSession:
    session = db.get(InterviewSession, session_id)

    if session is None or session.user_id != user.id:
        raise InterviewSessionError("Interview session not found.")

    return session


# --------------------------------------------------------------------------
# LLM-facing schemas and default dependencies
# --------------------------------------------------------------------------

class FirstQuestion(BaseModel):
    question: str


class TurnEvaluation(BaseModel):
    score: int = Field(ge=1, le=10)
    evaluation: str
    next_question: str


class FinalReport(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    communication: int = Field(ge=0, le=100)
    technical_knowledge: int = Field(ge=0, le=100)
    answer_relevance: int = Field(ge=0, le=100)
    clarity: int = Field(ge=0, le=100)
    problem_solving: int = Field(ge=0, le=100)
    strengths: list[str]
    areas_for_improvement: list[str]
    final_feedback: str


@dataclass
class InterviewDeps:
    generate_first_question: Callable[[InterviewContext], str]
    evaluate_answer: Callable[[InterviewContext, list[dict], str, str], TurnEvaluation]
    generate_report: Callable[[InterviewContext, list[dict]], FinalReport]


_FOCUS_BY_TYPE = {
    "hr": "Evaluate communication, relevance and the realism of behavioural examples. Ask natural behavioural follow-ups.",
    "technical": "Evaluate technical correctness, depth of understanding and use of technologies mentioned in the resume.",
    "dsa": "Evaluate algorithmic correctness, complexity analysis and edge-case reasoning.",
    "core_cs": "Evaluate correctness of core computer science fundamentals (OS, DBMS, networks, architecture).",
    "system_design": "Evaluate architectural trade-offs, scalability reasoning and failure handling.",
    "mixed": "Evaluate a blend of technical depth, problem solving and communication.",
    "custom": "Evaluate relevance to the candidate's resume and stated target role.",
}


def _clean_question(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^(question|next question)\s*:\s*", "", text, flags=re.IGNORECASE)

    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].strip()

    return text


def _context_brief(context: InterviewContext) -> str:
    parts = [
        f"Target role: {context.target_role}",
        f"Experience level: {context.experience_level}",
        f"Interview type: {context.interview_type}",
    ]

    if context.company:
        parts.append(f"Company: {context.company}")

    return "\n".join(parts)


def _resume_context_text(context: InterviewContext) -> str:
    query = (
        f"candidate background relevant to {context.target_role} {context.interview_type} "
        "skills projects experience education achievements"
    )

    try:
        chunks = retrieve(query, k=8)
    except Exception as exc:
        print(f"Resume retrieval failed: {exc}")
        return ""

    return "\n\n".join(f"[Page {c['page']}]\n{c['text']}" for c in chunks)


def _history_text(history: list[dict]) -> str:
    return "\n\n".join(
        f"Question: {h['question']}\nCandidate Answer: {h['answer']}\n"
        f"Evaluation: {h['evaluation']}\nScore: {h['score']}/10"
        for h in history
    )


def _default_generate_first_question(context: InterviewContext) -> str:
    resume_text = _resume_context_text(context)

    prompt = f"""
You are a professional interviewer conducting a placement interview.

{_context_brief(context)}

RESUME CONTEXT:
{resume_text or "No resume context available."}

{_FOCUS_BY_TYPE.get(context.interview_type, "Evaluate the quality and relevance of the answer.")}

Rules:
- Ask exactly ONE opening question appropriate for a {context.experience_level} {context.target_role} candidate.
- Keep it concise and natural, like a real interviewer speaking.
- Personalize it using the resume whenever useful; never invent resume facts.
- Do not introduce yourself, number the question, or provide feedback.
"""

    try:
        result = generate_structured(prompt, FirstQuestion, task="interview_first_question")
        question = _clean_question(result.question)

        if question:
            return question
    except Exception as exc:
        print(f"First question generation failed: {exc}")

    return f"Could you introduce yourself and walk me through your background relevant to {context.target_role}?"


def _default_evaluate_answer(
    context: InterviewContext,
    history: list[dict],
    question: str,
    answer: str,
) -> TurnEvaluation:
    resume_text = _resume_context_text(context)

    prompt = f"""
You are conducting a professional {context.interview_type} placement interview.

{_context_brief(context)}

RESUME CONTEXT:
{resume_text or "No resume context available."}

PREVIOUS INTERVIEW HISTORY:
{_history_text(history) or "No previous questions."}

CURRENT QUESTION:
{question}

CANDIDATE'S ANSWER:
{answer}

{_FOCUS_BY_TYPE.get(context.interview_type, "Evaluate the quality and relevance of the answer.")}

Evaluate the candidate's current answer (score 1-10), then generate exactly ONE next
interview question that logically follows from the answer whenever possible. Do not
repeat previous questions, invent resume facts, or reveal the score to the candidate.
"""

    try:
        result = generate_structured(prompt, TurnEvaluation, task="interview_turn_evaluation")
        result.next_question = _clean_question(result.next_question)
        return result
    except Exception as exc:
        print(f"Answer evaluation failed: {exc}")
        return TurnEvaluation(
            score=5,
            evaluation="The answer was reviewed, but detailed evaluation was unavailable.",
            next_question="",
        )


def _default_generate_report(context: InterviewContext, history: list[dict]) -> FinalReport:
    prompt = f"""
You are a professional placement interview evaluator.

The candidate completed a {context.interview_type} interview for the role of
{context.target_role} ({context.experience_level} level).

Interview history:

{_history_text(history) or "No answers were recorded."}

Score the dimensions below from 0 to 100: communication, technical knowledge
(for an HR interview this can represent job-related knowledge demonstrated
during the interview), answer relevance, clarity, and problem solving. Also
give an overall score, 2-4 strengths, 2-4 areas for improvement, and a short
final feedback paragraph.
"""

    try:
        return generate_structured(prompt, FinalReport, task="interview_final_report")
    except Exception as exc:
        print(f"Final report generation failed: {exc}")

        scores = [h["score"] for h in history if h["score"] is not None]
        overall = round((sum(scores) / len(scores)) * 10) if scores else 0

        return FinalReport(
            overall_score=overall,
            communication=overall,
            technical_knowledge=overall,
            answer_relevance=overall,
            clarity=overall,
            problem_solving=overall,
            strengths=[],
            areas_for_improvement=[],
            final_feedback="Detailed feedback was unavailable.",
        )


_deps: InterviewDeps | None = None


def get_interview_deps() -> InterviewDeps:
    """
    FastAPI dependency. Tests override it with fakes so no network calls
    are made.
    """

    global _deps

    if _deps is None:
        _deps = InterviewDeps(
            generate_first_question=_default_generate_first_question,
            evaluate_answer=_default_evaluate_answer,
            generate_report=_default_generate_report,
        )

    return _deps


# --------------------------------------------------------------------------
# MKT-driven turns
# --------------------------------------------------------------------------

def _mkt_eligible(context: InterviewContext) -> bool:
    return context.interview_type in MKT_ELIGIBLE_INTERVIEW_TYPES


def _is_mkt_turn_seq(seq: int) -> bool:
    return seq % MKT_TURN_INTERVAL == 0 and (seq // MKT_TURN_INTERVAL) <= MKT_MAX_TURNS


def _init_mkt_state(db: Session, user: User) -> dict:
    concepts = db.query(Concept).filter(Concept.domain == MKT_DOMAIN).order_by(Concept.difficulty, Concept.id).all()
    scope = [c.id for c in concepts]
    parents, children = _load_graph(db, scope)
    beliefs, _observed = _initial_beliefs(db, user, scope, parents)

    return {
        "beliefs": {c: b.tolist() for c, b in beliefs.items()},
        "templates": _templates_by_concept(db, scope),
        "parents": parents,
        "descendants": _descendant_counts(children),
        "asked": [],
        "base_answered": {},  # concept_id -> InterviewTurn.id of its base turn
        "last_concept": None,
        "last_probe_type": None,
    }


def _select_mkt_turn(db: Session, mkt_state: dict, resume_text: str) -> dict | None:
    """
    Picks the next (concept, probe_type, template) by EIG, same as the
    standalone MKT engine, then - for BASE/MR_PARAPHRASE only - tries to
    replace the seeded question with a resume-grounded one.
    """

    beliefs = {c: np.asarray(p, dtype=float) for c, p in mkt_state["beliefs"].items()}

    action = select_next(
        beliefs,
        mkt_state["templates"],
        set(mkt_state["asked"]),
        set(mkt_state["base_answered"]),
        DEFAULT_THETA,
        descendants=mkt_state["descendants"],
        last_concept=mkt_state["last_concept"],
        last_probe_type=mkt_state["last_probe_type"],
        force=True,
    )

    if action is None:
        return None

    concept = db.get(Concept, action.concept_id)
    template = db.get(ProbeTemplate, action.template_id)
    question, template_id = template.question, template.id

    if resume_text:
        generated = generate_resume_grounded_probe(concept, action.probe_type, resume_text)

        if generated is not None:
            new_template = persist_generated_probe(db, concept, action.probe_type, generated)
            question, template_id = new_template.question, new_template.id

    return {
        "concept_id": action.concept_id,
        "probe_type": action.probe_type,
        "template_id": template_id,
        "question": question,
        "belief_before": beliefs[action.concept_id].tolist(),
    }


def _evaluate_mkt_turn(db: Session, user: User, mkt_state: dict, turn: InterviewTurn, answer: str, mkt_deps: MKTDeps) -> tuple[dict, int, str]:
    """
    Runs the MKT assessment/outcome pipeline for one MKT-driven turn's
    answer and updates belief state (persisted via ConceptBelief, same as
    the standalone MKT session). Returns (new_mkt_state, score,
    evaluation_text); new_mkt_state is a NEW dict (never a mutation of the
    one passed in) so SQLAlchemy's JSON column change-tracking picks up
    the assignment - see MKTSession.state's docstring in
    app/modules/mkt/models.py for the same constraint.
    """

    template = db.get(ProbeTemplate, turn.mkt_template_id)
    concept = db.get(Concept, turn.mkt_concept_id)
    spec = template.relation_spec
    probe_type = turn.mkt_probe_type

    if probe_type == MKT_BASE:
        assessment, _ = assess_answer(turn.question, answer, spec, concept.misconceptions, mkt_deps.verifier)
        outcome = BASE_OUTCOME[assessment.answer_class]
        reasons = [f"answer {assessment.answer_class} (coverage {assessment.coverage:.0%})"]
    else:
        base_turn = db.get(InterviewTurn, mkt_state["base_answered"][turn.mkt_concept_id])
        base_class = base_turn.mkt_assessment["answer_class"]

        prior_claims = []
        if probe_type == MR_PARAPHRASE:
            prior_claims = base_turn.mkt_assessment.get("propositions", [])[:6]

        assessment, _ = assess_answer(
            turn.question, answer, spec, concept.misconceptions, mkt_deps.verifier, extra_statements=prior_claims,
        )

        contradicted = sum(
            1 for claim in prior_claims
            if assessment.verdicts.get(claim, {}).get("label") == CONTRADICTED
        )

        similarity = None
        if probe_type == MR_CONSTRAINT and base_turn.answer and answer:
            vecs = np.asarray(mkt_deps.embed([base_turn.answer, answer]))
            similarity = float(vecs[0] @ vecs[1])

        outcome, reasons = relation_outcome(
            probe_type, base_class, assessment, prior_claims_contradicted=contradicted, answer_similarity=similarity,
        )

    beliefs = {c: np.asarray(p, dtype=float) for c, p in mkt_state["beliefs"].items()}
    theta = DEFAULT_THETA[probe_type]
    before = beliefs[turn.mkt_concept_id]
    after = MB.update(before, theta, outcome)
    beliefs[turn.mkt_concept_id] = after

    for parent in mkt_state["parents"].get(turn.mkt_concept_id, []):
        beliefs[parent] = MB.propagate_to_parent(beliefs[parent], theta, outcome)
        _save_belief(db, user, parent, beliefs[parent], add_obs=0)

    _save_belief(db, user, turn.mkt_concept_id, after, add_obs=1)

    turn.mkt_outcome = outcome
    turn.mkt_assessment = {
        "answer_class": assessment.answer_class,
        "coverage": assessment.coverage,
        "propositions": assessment.propositions,
        "verdicts": assessment.verdicts,
        "misconceptions_hit": assessment.misconceptions_hit,
        "false_claim": assessment.false_claim,
    }
    turn.mkt_belief_after = [round(float(p), 4) for p in after]

    base_answered = dict(mkt_state["base_answered"])
    if probe_type == MKT_BASE:
        base_answered[turn.mkt_concept_id] = turn.id

    new_mkt_state = {
        **mkt_state,
        "beliefs": {c: b.tolist() for c, b in beliefs.items()},
        "asked": mkt_state["asked"] + [turn.mkt_template_id],
        "base_answered": base_answered,
        "last_concept": turn.mkt_concept_id,
        "last_probe_type": probe_type,
    }

    db.add(
        EvidenceEvent(
            user_id=user.id,
            concept_id=turn.mkt_concept_id,
            domain=MKT_DOMAIN,
            source="interview_mkt",
            signal=probe_type,
            value={"outcome": outcome, "belief": turn.mkt_belief_after, "session_id": turn.session_id},
        )
    )

    evaluation_text = f"({', '.join(reasons)})"
    return new_mkt_state, _MKT_OUTCOME_SCORE[outcome], evaluation_text


# --------------------------------------------------------------------------
# Session lifecycle
# --------------------------------------------------------------------------

def _answered_turns(db: Session, session: InterviewSession) -> list[InterviewTurn]:
    return (
        db.query(InterviewTurn)
        .filter(InterviewTurn.session_id == session.id, InterviewTurn.answer.isnot(None))
        .order_by(InterviewTurn.seq)
        .all()
    )


def _history_for_prompt(db: Session, session: InterviewSession, turns: list[InterviewTurn] | None = None) -> list[dict]:
    if turns is None:
        turns = _answered_turns(db, session)

    return [
        {
            "question": t.question,
            "answer": t.answer,
            "evaluation": t.evaluation,
            "score": t.score,
            "source": t.source,
            "mkt_probe_type": t.mkt_probe_type,
        }
        for t in turns
    ]


def _proctoring_summary(session: InterviewSession) -> dict:
    events = session.proctoring_events or []

    return {
        "tab_switch_count": sum(1 for e in events if e.get("type") == "tab_hidden"),
        "face_lost_count": sum(1 for e in events if e.get("type") == "face_lost"),
    }


def _concept_belief_summary(db: Session, turns: list[InterviewTurn]) -> dict:
    """
    Per-concept knowledge-depth readout for turns that went through MKT
    (Phase 7). Reuses belief.py's own scalars (mastery, robustness_index)
    against each concept's *last* recorded belief in this session, rather
    than recomputing belief updates here.
    """

    by_concept: dict[str, list[InterviewTurn]] = {}
    for t in turns:
        if t.source == "mkt" and t.mkt_concept_id and t.mkt_belief_after:
            by_concept.setdefault(t.mkt_concept_id, []).append(t)

    concepts = []
    for concept_id, concept_turns in by_concept.items():
        concept = db.get(Concept, concept_id)
        final_belief = np.asarray(concept_turns[-1].mkt_belief_after)

        concepts.append(
            {
                "concept_id": concept_id,
                "concept_name": concept.name if concept else concept_id,
                "probe_count": len(concept_turns),
                "mastery": MB.mastery(final_belief),
                "robustness_index": MB.robustness_index(final_belief),
                "classification": STATES[int(np.argmax(final_belief))],
                "misconceptions_hit": any((t.mkt_assessment or {}).get("misconceptions_hit") for t in concept_turns),
            }
        )

    concepts.sort(key=lambda c: c["concept_name"])

    return {
        "sample_count": sum(len(v) for v in by_concept.values()),
        "concepts": concepts,
    }


def get_session_evidence(db: Session, user: User, session_id: str) -> dict:
    """
    Phase 12: the raw evidence trail behind this session's report, one item
    per signal recorded while it ran (same facts as the EvidenceEvent rows
    written in submit_turn_answer/_evaluate_mkt_turn, read here off
    InterviewTurn directly since it already carries the joined question/
    answer/belief context those events only reference by id).
    """

    session = _get_owned_session(db, user, session_id)
    turns = _answered_turns(db, session)

    items: list[dict] = []
    for t in turns:
        if t.source == "mkt" and t.mkt_concept_id:
            concept = db.get(Concept, t.mkt_concept_id)
            concept_name = concept.name if concept else t.mkt_concept_id

            before = np.asarray(t.mkt_belief_before) if t.mkt_belief_before else None
            after = np.asarray(t.mkt_belief_after) if t.mkt_belief_after else None
            before_label = STATES[int(np.argmax(before))] if before is not None else None
            after_label = STATES[int(np.argmax(after))] if after is not None else None

            items.append(
                {
                    "seq": t.seq,
                    "source": "mkt",
                    "signal": t.mkt_probe_type,
                    "concept_id": t.mkt_concept_id,
                    "concept_name": concept_name,
                    "outcome": t.mkt_outcome,
                    "belief_before": t.mkt_belief_before,
                    "belief_after": t.mkt_belief_after,
                    "classification_before": before_label,
                    "classification_after": after_label,
                    "description": (
                        f"Turn {t.seq}: {t.mkt_probe_type} probe on {concept_name} "
                        f"→ outcome={t.mkt_outcome} "
                        f"→ belief updated from {t.mkt_belief_before} to {t.mkt_belief_after}"
                    ),
                    "question": t.question,
                    "answer": t.answer,
                }
            )
        else:
            items.append(
                {
                    "seq": t.seq,
                    "source": "interview",
                    "signal": "turn_answered",
                    "description": f"Turn {t.seq}: answered — scored {t.score}/10",
                    "question": t.question,
                    "answer": t.answer,
                    "score": t.score,
                    "evaluation": t.evaluation,
                }
            )

        if t.comm_metrics:
            items.append(
                {
                    "seq": t.seq,
                    "source": "comms",
                    "signal": "communication_analysis",
                    "description": f"Turn {t.seq}: communication metrics recorded",
                    "metrics": t.comm_metrics,
                }
            )

        if t.emotion_metrics:
            items.append(
                {
                    "seq": t.seq,
                    "source": "comms",
                    "signal": "emotion_snapshot",
                    "description": f"Turn {t.seq}: emotion snapshot recorded",
                    "metrics": t.emotion_metrics,
                }
            )

    return {
        "session_id": session.id,
        "item_count": len(items),
        "items": items,
    }


def record_proctoring_event(db: Session, user: User, session_id: str, event_type: str) -> dict:
    session = _get_owned_session(db, user, session_id)

    events = list(session.proctoring_events or [])
    events.append({"type": event_type, "at": utcnow().isoformat()})
    session.proctoring_events = events[-PROCTORING_LOG_LIMIT:]

    db.commit()
    return _proctoring_summary(session)


def _finish_session(db: Session, session: InterviewSession, deps: InterviewDeps) -> None:
    _transition(session, GENERATING_REPORT)

    context = db.get(InterviewContext, session.context_id)
    turns = _answered_turns(db, session)
    history = _history_for_prompt(db, session, turns)
    report = deps.generate_report(context, history)

    report_dict = report.model_dump()
    report_dict["question_feedback"] = history
    report_dict["proctoring_summary"] = _proctoring_summary(session)
    report_dict["communication_summary"] = communication_service.aggregate_session_metrics(turns)
    report_dict["emotion_summary"] = emotion_aggregate.aggregate_session_emotion(turns)
    report_dict["concept_belief_summary"] = _concept_belief_summary(db, turns)

    session.report = report_dict
    session.ended_at = utcnow()
    context.status = "completed"

    _transition(session, REPORT)


def start_session(db: Session, user: User, context_id: str, deps: InterviewDeps) -> dict:
    context = get_context(db, user, context_id)

    if context.status != "active":
        raise InterviewSessionError("This interview context has already been used.")

    now = utcnow()

    session = InterviewSession(
        id=str(uuid.uuid4()),
        context_id=context.id,
        user_id=user.id,
        state=READY,
        num_questions=context.num_questions,
        turns_asked=0,
        started_at=now,
        ends_at=now + timedelta(minutes=context.duration_minutes),
    )

    db.add(session)
    db.flush()

    question = deps.generate_first_question(context)

    turn = InterviewTurn(session_id=session.id, seq=1, question=question, state_at_ask=AI_SPEAKING)
    db.add(turn)

    session.turns_asked = 1
    session.current_turn_seq = 1
    _transition(session, AI_SPEAKING)

    db.commit()

    return public_session(db, session)


def advance_to_listening(db: Session, user: User, session_id: str, deps: InterviewDeps) -> dict:
    session = _get_owned_session(db, user, session_id)

    if _apply_time_expiry(session):
        _finish_session(db, session, deps)
    else:
        _transition(session, LISTENING)

        turn = (
            db.query(InterviewTurn)
            .filter_by(session_id=session.id, seq=session.current_turn_seq)
            .one_or_none()
        )

        if turn is not None and turn.listening_started_at is None:
            turn.listening_started_at = utcnow()

    db.commit()
    return public_session(db, session)


def submit_turn_answer(
    db: Session,
    user: User,
    session_id: str,
    answer: str,
    deps: InterviewDeps,
    mkt_deps: MKTDeps | None = None,
    emotion_signal: dict | None = None,
) -> dict:
    session = _get_owned_session(db, user, session_id)

    if _apply_time_expiry(session):
        _finish_session(db, session, deps)
        db.commit()
        return public_session(db, session)

    if session.state != LISTENING:
        raise InterviewSessionError(f"Cannot submit an answer while the session is {session.state}.")

    answer = answer.strip()

    if not answer:
        raise InterviewSessionError("Answer cannot be empty.")

    _transition(session, PROCESSING)

    turn = (
        db.query(InterviewTurn)
        .filter_by(session_id=session.id, seq=session.current_turn_seq)
        .one()
    )
    context = db.get(InterviewContext, session.context_id)
    history = _history_for_prompt(db, session)

    # Always ask the plain LLM path for a candidate next_question, even for
    # an MKT-driven turn: it keeps the interview's conversational thread
    # coherent whenever the *next* turn isn't itself MKT-driven. Its score
    # is discarded for MKT turns in favour of the MKT-derived one below.
    evaluation = deps.evaluate_answer(context, history, turn.question, answer)

    turn.answer = answer
    turn.answered_at = utcnow()
    turn.comm_metrics = communication_service.build_turn_metrics(answer, turn.listening_started_at, turn.answered_at)
    turn.emotion_metrics = emotion_signal

    if turn.source == "mkt" and mkt_deps is not None:
        new_mkt_state, score, evaluation_text = _evaluate_mkt_turn(db, user, session.mkt_state, turn, answer, mkt_deps)
        turn.score = score
        turn.evaluation = evaluation_text
        session.mkt_state = new_mkt_state
        concept_id = turn.mkt_concept_id
    else:
        turn.score = evaluation.score
        turn.evaluation = evaluation.evaluation
        concept_id = None

    db.add(
        EvidenceEvent(
            user_id=user.id,
            concept_id=concept_id,
            domain=context.interview_type,
            source="interview",
            signal="turn_answered",
            value={"session_id": session.id, "seq": turn.seq, "score": turn.score},
        )
    )

    db.add(
        EvidenceEvent(
            user_id=user.id,
            concept_id=concept_id,
            domain=context.interview_type,
            source="comms",
            signal="communication_analysis",
            value={"session_id": session.id, "seq": turn.seq, **turn.comm_metrics},
        )
    )

    if emotion_signal is not None:
        db.add(
            EvidenceEvent(
                user_id=user.id,
                concept_id=concept_id,
                domain=context.interview_type,
                source="comms",
                signal="emotion_snapshot",
                value={"session_id": session.id, "seq": turn.seq, **emotion_signal},
            )
        )

    # The session's autoflush is off; _finish_session re-queries
    # InterviewTurn for the history, so this turn's answer must be
    # flushed before that happens.
    db.flush()

    question_limit_reached = (
        session.num_questions is not None and session.turns_asked >= session.num_questions
    )
    time_expired = _apply_time_expiry(session)

    if time_expired or question_limit_reached:
        _finish_session(db, session, deps)
        db.commit()
        return public_session(db, session)

    next_seq = turn.seq + 1
    next_turn = None

    if mkt_deps is not None and _mkt_eligible(context) and _is_mkt_turn_seq(next_seq):
        mkt_state = session.mkt_state or _init_mkt_state(db, user)
        resume_text = _resume_context_text(context)
        mkt_turn_data = _select_mkt_turn(db, mkt_state, resume_text)

        if mkt_turn_data is not None:
            next_turn = InterviewTurn(
                session_id=session.id,
                seq=next_seq,
                question=mkt_turn_data["question"],
                state_at_ask=AI_SPEAKING,
                source="mkt",
                mkt_concept_id=mkt_turn_data["concept_id"],
                mkt_probe_type=mkt_turn_data["probe_type"],
                mkt_template_id=mkt_turn_data["template_id"],
                mkt_belief_before=[round(float(p), 4) for p in mkt_turn_data["belief_before"]],
            )
            session.mkt_state = mkt_state

    if next_turn is None:
        next_question = evaluation.next_question.strip() or _fallback_next_question(context)
        next_turn = InterviewTurn(session_id=session.id, seq=next_seq, question=next_question, state_at_ask=AI_SPEAKING)

    db.add(next_turn)

    session.turns_asked = next_seq
    session.current_turn_seq = next_seq
    _transition(session, AI_SPEAKING)

    db.commit()
    return public_session(db, session)


def _fallback_next_question(context: InterviewContext) -> str:
    if context.interview_type in ("technical", "dsa", "system_design", "core_cs"):
        return "Can you explain another technical aspect of your experience in more detail?"

    return "Can you describe a situation where you had to solve a difficult problem?"


def get_session(db: Session, user: User, session_id: str, deps: InterviewDeps) -> dict:
    session = _get_owned_session(db, user, session_id)

    if _apply_time_expiry(session):
        _finish_session(db, session, deps)
        db.commit()

    return public_session(db, session)


def public_session(db: Session, session: InterviewSession) -> dict:
    question = None

    if session.state in (AI_SPEAKING, LISTENING, PROCESSING) and session.current_turn_seq is not None:
        turn = (
            db.query(InterviewTurn)
            .filter_by(session_id=session.id, seq=session.current_turn_seq)
            .one_or_none()
        )

        if turn is not None:
            question = turn.question

    ends_at = session.ends_at if session.ends_at.tzinfo else session.ends_at.replace(tzinfo=timezone.utc)
    time_remaining = max(0, int((ends_at - datetime.now(timezone.utc)).total_seconds()))

    return {
        "session_id": session.id,
        "context_id": session.context_id,
        "state": session.state,
        "question": question,
        "question_number": session.current_turn_seq,
        "questions_asked": session.turns_asked,
        "total_questions": session.num_questions,
        "time_remaining_seconds": time_remaining,
        "report": session.report,
    }
