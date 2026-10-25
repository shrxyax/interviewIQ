"""
MKT session orchestration: glue between the database, the language
layer (verifier) and the algorithmic core (belief, selection).
"""

import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.models import EvidenceEvent, User
from app.modules.mkt import belief as B
from app.modules.mkt.consistency import (
    BASE_OUTCOME,
    CONTRADICTED,
    FallbackVerifier,
    LLMVerifier,
    LocalVerifier,
    Verifier,
    assess_answer,
    relation_outcome,
)
from app.modules.mkt.emissions import DEFAULT_THETA
from app.modules.mkt.models import Concept, ConceptBelief, ConceptEdge, MKTSession, MKTTurn, ProbeTemplate
from app.modules.mkt.selection import select_next
from app.modules.mkt.states import BASE, MR_CONSTRAINT, MR_PARAPHRASE, STATES


class MKTError(ValueError):
    pass


@dataclass
class MKTDeps:
    verifier: Verifier
    embed: Callable  # list[str] -> np.ndarray of L2-normalised vectors


_deps: MKTDeps | None = None


def get_mkt_deps() -> MKTDeps:
    """
    FastAPI dependency. Tests override it with fakes.
    """

    global _deps

    if _deps is None:
        from app.services.embeddings import generate_embeddings

        local = LocalVerifier(embed=generate_embeddings)
        verifier = FallbackVerifier(LLMVerifier(), local) if settings.gemini_api_key else local
        _deps = MKTDeps(verifier=verifier, embed=generate_embeddings)

    return _deps


# --------------------------------------------------------------------------
# Graph helpers
# --------------------------------------------------------------------------

def _load_graph(db: Session, concept_ids: list[str]):
    edges = db.query(ConceptEdge).filter(ConceptEdge.kind == "prereq").all()
    scope = set(concept_ids)

    parents = {c: [] for c in concept_ids}
    children = {c: [] for c in concept_ids}

    for e in edges:
        if e.src in scope and e.dst in scope:
            parents[e.dst].append(e.src)
            children[e.src].append(e.dst)

    return parents, children


def _descendant_counts(children: dict[str, list[str]]) -> dict[str, int]:
    counts = {}

    for start in children:
        seen, queue = set(), deque(children[start])

        while queue:
            node = queue.popleft()
            if node not in seen:
                seen.add(node)
                queue.extend(children.get(node, []))

        counts[start] = len(seen)

    return counts


def _topological_order(concept_ids: list[str], parents: dict[str, list[str]]) -> list[str]:
    """
    Kahn's algorithm, so a concept's prior is computed after its parents'.
    """

    indegree = {c: len(parents[c]) for c in concept_ids}
    children = {c: [] for c in concept_ids}

    for c in concept_ids:
        for p in parents[c]:
            children[p].append(c)

    queue = deque(c for c in concept_ids if indegree[c] == 0)
    order = []

    while queue:
        node = queue.popleft()
        order.append(node)

        for child in children[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(order) != len(concept_ids):
        raise MKTError("Concept graph contains a cycle.")

    return order


def _initial_beliefs(db: Session, user: User, concept_ids: list[str], parents) -> tuple[dict, set[str]]:
    """
    Stored beliefs (decayed for elapsed time) where they exist; otherwise
    a prior derived from observed prerequisites.
    """

    stored = {
        row.concept_id: row
        for row in db.query(ConceptBelief).filter(
            ConceptBelief.user_id == user.id,
            ConceptBelief.concept_id.in_(concept_ids),
        )
    }

    now = datetime.now(timezone.utc)
    beliefs, observed = {}, set()

    for c in _topological_order(concept_ids, parents):
        row = stored.get(c)

        if row is not None and row.n_obs > 0:
            updated = row.updated_at if row.updated_at.tzinfo else row.updated_at.replace(tzinfo=timezone.utc)
            days = (now - updated).total_seconds() / 86400
            beliefs[c] = B.decay(np.asarray(row.probs, dtype=float), days)
            observed.add(c)
        else:
            beliefs[c] = B.prior_from_parents([beliefs[p] for p in parents[c] if p in observed])

    return beliefs, observed


def _save_belief(db: Session, user: User, concept_id: str, probs: np.ndarray, add_obs: int):
    row = db.get(ConceptBelief, (user.id, concept_id))

    if row is None:
        row = ConceptBelief(user_id=user.id, concept_id=concept_id, probs=probs.tolist(), n_obs=0)
        db.add(row)

    row.probs = [round(float(p), 6) for p in probs]
    row.n_obs = (row.n_obs or 0) + add_obs
    row.updated_at = datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Session lifecycle
# --------------------------------------------------------------------------

def _templates_by_concept(db: Session, concept_ids: list[str]) -> dict[str, dict[str, list[int]]]:
    rows = (
        db.query(ProbeTemplate)
        .filter(ProbeTemplate.concept_id.in_(concept_ids), ProbeTemplate.validated.is_(True))
        .order_by(ProbeTemplate.id)
        .all()
    )

    templates = {c: {} for c in concept_ids}

    for t in rows:
        templates[t.concept_id].setdefault(t.probe_type, []).append(t.id)

    return templates


def _beliefs_from_state(state: dict) -> dict[str, np.ndarray]:
    return {c: np.asarray(p, dtype=float) for c, p in state["beliefs"].items()}


def _state_with(state: dict, **changes) -> dict:
    new = {**state, **changes}
    return new


def _create_next_turn(db: Session, session: MKTSession, state: dict, force: bool = False) -> MKTTurn | None:
    beliefs = _beliefs_from_state(state)

    action = select_next(
        beliefs,
        state["templates"],
        set(state["asked"]),
        set(state["base_answered"]),
        DEFAULT_THETA,
        descendants=state["descendants"],
        last_concept=state.get("last_concept"),
        last_probe_type=state.get("last_probe_type"),
        force=force,
    )

    if action is None:
        return None

    template = db.get(ProbeTemplate, action.template_id)

    turn = MKTTurn(
        session_id=session.id,
        seq=state["turns_done"] + 1,
        concept_id=action.concept_id,
        probe_type=action.probe_type,
        template_id=template.id,
        question=template.question,
        eig=round(action.eig, 4),
        belief_before=[round(float(p), 4) for p in beliefs[action.concept_id]],
    )

    db.add(turn)
    db.flush()
    return turn


def start_session(db: Session, user: User, domain: str = "dsa", concept_ids: list[str] | None = None, budget: int = 10) -> dict:
    query = db.query(Concept).filter(Concept.domain == domain)

    if concept_ids:
        query = query.filter(Concept.id.in_(concept_ids))

    concepts = query.order_by(Concept.difficulty, Concept.id).all()

    if not concepts:
        raise MKTError(f"No concepts found for domain '{domain}'.")

    scope = [c.id for c in concepts]
    parents, children = _load_graph(db, scope)
    beliefs, _observed = _initial_beliefs(db, user, scope, parents)

    session = MKTSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        domain=domain,
        config={"budget": budget, "concept_ids": scope},
    )

    state = {
        "beliefs": {c: b.tolist() for c, b in beliefs.items()},
        "templates": _templates_by_concept(db, scope),
        "parents": parents,
        "descendants": _descendant_counts(children),
        "asked": [],
        "base_answered": {},
        "last_concept": None,
        "last_probe_type": None,
        "turns_done": 0,
        "budget": budget,
        "pending_turn_id": None,
    }

    db.add(session)
    db.flush()

    turn = _create_next_turn(db, session, state, force=True)

    if turn is None:
        raise MKTError("No probes available for the selected concepts.")

    session.state = _state_with(state, pending_turn_id=turn.id)
    db.commit()

    return {"session_id": session.id, "budget": budget, "turn": _turn_public(turn, db)}


def submit_answer(db: Session, user: User, session_id: str, turn_id: int, answer: str, latency_ms: int | None, deps: MKTDeps) -> dict:
    session = db.get(MKTSession, session_id)

    if session is None or session.user_id != user.id:
        raise MKTError("Session not found.")

    if session.status != "active":
        raise MKTError("Session is already completed.")

    state = session.state

    if state["pending_turn_id"] != turn_id:
        raise MKTError("This is not the current question.")

    turn = db.get(MKTTurn, turn_id)
    template = db.get(ProbeTemplate, turn.template_id)
    concept = db.get(Concept, turn.concept_id)
    spec = template.relation_spec
    answer = answer.strip()

    if turn.probe_type == BASE:
        assessment, _ = assess_answer(turn.question, answer, spec, concept.misconceptions, deps.verifier)
        outcome = BASE_OUTCOME[assessment.answer_class]
        reasons = [f"answer {assessment.answer_class} (coverage {assessment.coverage:.0%})"]
    else:
        base_turn = db.get(MKTTurn, state["base_answered"][turn.concept_id])
        base_class = base_turn.assessment["answer_class"]

        prior_claims = []
        if turn.probe_type == MR_PARAPHRASE:
            prior_claims = base_turn.assessment.get("propositions", [])[:6]

        assessment, _ = assess_answer(
            turn.question,
            answer,
            spec,
            concept.misconceptions,
            deps.verifier,
            extra_statements=prior_claims,
        )

        contradicted = sum(
            1 for claim in prior_claims
            if assessment.verdicts.get(claim, {}).get("label") == CONTRADICTED
        )

        similarity = None
        if turn.probe_type == MR_CONSTRAINT and base_turn.answer and answer:
            vecs = np.asarray(deps.embed([base_turn.answer, answer]))
            similarity = float(vecs[0] @ vecs[1])

        outcome, reasons = relation_outcome(
            turn.probe_type,
            base_class,
            assessment,
            prior_claims_contradicted=contradicted,
            answer_similarity=similarity,
        )

    # Bayesian update for the probed concept.
    beliefs = _beliefs_from_state(state)
    theta = DEFAULT_THETA[turn.probe_type]
    before = beliefs[turn.concept_id]
    after = B.update(before, theta, outcome)
    beliefs[turn.concept_id] = after

    # Tempered evidence to prerequisites in scope.
    for parent in state["parents"].get(turn.concept_id, []):
        beliefs[parent] = B.propagate_to_parent(beliefs[parent], theta, outcome)
        _save_belief(db, user, parent, beliefs[parent], add_obs=0)

    _save_belief(db, user, turn.concept_id, after, add_obs=1)

    turn.answer = answer
    turn.latency_ms = latency_ms
    turn.verifier = deps.verifier.name
    turn.assessment = {
        "answer_class": assessment.answer_class,
        "coverage": assessment.coverage,
        "propositions": assessment.propositions,
        "verdicts": assessment.verdicts,
        "misconceptions_hit": assessment.misconceptions_hit,
        "false_claim": assessment.false_claim,
    }
    turn.outcome = outcome
    turn.reasons = reasons
    turn.belief_after = [round(float(p), 4) for p in after]
    turn.answered_at = datetime.now(timezone.utc)

    db.add(
        EvidenceEvent(
            user_id=user.id,
            concept_id=turn.concept_id,
            domain=session.domain,
            source="mkt",
            signal=turn.probe_type,
            value={"outcome": outcome, "belief": turn.belief_after, "session_id": session.id},
        )
    )

    base_answered = dict(state["base_answered"])
    if turn.probe_type == BASE:
        base_answered[turn.concept_id] = turn.id

    state = _state_with(
        state,
        beliefs={c: b.tolist() for c, b in beliefs.items()},
        asked=state["asked"] + [turn.template_id],
        base_answered=base_answered,
        last_concept=turn.concept_id,
        last_probe_type=turn.probe_type,
        turns_done=state["turns_done"] + 1,
        pending_turn_id=None,
    )

    result = {
        "turn_result": {
            "turn_id": turn.id,
            "concept_id": turn.concept_id,
            "probe_type": turn.probe_type,
            "outcome": outcome,
            "reasons": reasons,
            "answer_class": assessment.answer_class,
            "belief_before": turn.belief_before,
            "belief_after": turn.belief_after,
        }
    }

    next_turn = None
    if state["turns_done"] < state["budget"]:
        next_turn = _create_next_turn(db, session, state)

    if next_turn is None:
        session.status = "completed"
        session.ended_at = datetime.now(timezone.utc)
        session.state = state
        db.commit()
        result["completed"] = True
        result["report"] = build_report(db, session)
        return result

    session.state = _state_with(state, pending_turn_id=next_turn.id)
    db.commit()

    result["completed"] = False
    result["turn"] = _turn_public(next_turn, db)
    return result


# --------------------------------------------------------------------------
# Read models
# --------------------------------------------------------------------------

def _turn_public(turn: MKTTurn, db: Session) -> dict:
    concept = db.get(Concept, turn.concept_id)

    return {
        "turn_id": turn.id,
        "seq": turn.seq,
        "concept_id": turn.concept_id,
        "concept_name": concept.name,
        "probe_type": turn.probe_type,
        "question": turn.question,
        "eig": turn.eig,
        "belief": turn.belief_before,
    }


def concept_summary(probs) -> dict:
    b = np.asarray(probs, dtype=float)
    ri = B.robustness_index(b)

    return {
        "belief": dict(zip(STATES, [round(float(p), 4) for p in b])),
        "most_likely": STATES[int(np.argmax(b))],
        "confidence": round(float(b.max()), 4),
        "entropy": round(B.entropy(b), 4),
        "mastery": round(B.mastery(b), 4),
        "robustness_index": None if ri is None else round(ri, 4),
    }


def build_report(db: Session, session: MKTSession) -> dict:
    turns = db.query(MKTTurn).filter_by(session_id=session.id).order_by(MKTTurn.seq).all()
    answered = [t for t in turns if t.outcome is not None]
    concepts = {c.id: c for c in db.query(Concept).filter(Concept.id.in_(session.config["concept_ids"]))}
    state = session.state

    probed = {t.concept_id for t in answered}
    per_concept = []

    for cid in session.config["concept_ids"]:
        summary = concept_summary(state["beliefs"][cid])
        summary.update({"concept_id": cid, "name": concepts[cid].name, "probed": cid in probed})
        per_concept.append(summary)

    # The conventional single-answer score, for comparison: base answers only.
    credit = {"correct": 1.0, "partial": 0.5}
    base_turns = [t for t in answered if t.probe_type == BASE]
    conventional = (
        sum(credit.get(t.assessment["answer_class"], 0.0) for t in base_turns) / len(base_turns)
        if base_turns else None
    )

    probed_summaries = [c for c in per_concept if c["probed"]]
    ris = [c["robustness_index"] for c in probed_summaries if c["robustness_index"] is not None]

    return {
        "session_id": session.id,
        "status": session.status,
        "turns": len(answered),
        "conventional_score": None if conventional is None else round(conventional, 3),
        "mean_robustness_index": round(float(np.mean(ris)), 3) if ris else None,
        "capitulations": sum(1 for t in answered if t.outcome == "capitulated"),
        "misconceptions": sorted({m for t in answered for m in t.assessment.get("misconceptions_hit", [])}),
        "concepts": per_concept,
    }


def get_trace(db: Session, user: User, session_id: str) -> dict:
    session = db.get(MKTSession, session_id)

    if session is None or session.user_id != user.id:
        raise MKTError("Session not found.")

    turns = db.query(MKTTurn).filter_by(session_id=session.id).order_by(MKTTurn.seq).all()

    return {
        "session_id": session.id,
        "status": session.status,
        "turns": [
            {
                "turn_id": t.id,
                "seq": t.seq,
                "concept_id": t.concept_id,
                "probe_type": t.probe_type,
                "question": t.question,
                "answer": t.answer,
                "eig": t.eig,
                "verifier": t.verifier,
                "assessment": t.assessment,
                "outcome": t.outcome,
                "reasons": t.reasons,
                "belief_before": t.belief_before,
                "belief_after": t.belief_after,
                "latency_ms": t.latency_ms,
            }
            for t in turns
        ],
    }


def get_report(db: Session, user: User, session_id: str) -> dict:
    session = db.get(MKTSession, session_id)

    if session is None or session.user_id != user.id:
        raise MKTError("Session not found.")

    return build_report(db, session)


def concept_graph(db: Session, user: User, domain: str) -> dict:
    concepts = db.query(Concept).filter(Concept.domain == domain).order_by(Concept.difficulty, Concept.id).all()
    ids = [c.id for c in concepts]
    parents, _children = _load_graph(db, ids)

    stored = {
        row.concept_id: row
        for row in db.query(ConceptBelief).filter(ConceptBelief.user_id == user.id, ConceptBelief.concept_id.in_(ids))
    }

    nodes = []

    for c in concepts:
        row = stored.get(c.id)
        node = {"id": c.id, "name": c.name, "difficulty": c.difficulty, "observations": row.n_obs if row else 0}
        node.update(concept_summary(row.probs if row else B.UNIFORM_PRIOR))
        nodes.append(node)

    edges = [{"source": p, "target": c} for c in ids for p in parents[c]]

    return {"domain": domain, "nodes": nodes, "edges": edges}
