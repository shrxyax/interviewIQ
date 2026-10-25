from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.models import User
from app.modules.content.models import (
    Company,
    CompanyWeight,
    CoreCSNote,
    SheetProblem,
    SheetTopic,
    UserProblemStatus,
)
from app.modules.mkt import belief as B
from app.modules.mkt.models import ConceptBelief
from app.modules.whiteboard.models import DesignPrompt, DesignSession


class ContentError(ValueError):
    pass


# --------------------------------------------------------------------------
# DSA / Core CS sheets
# --------------------------------------------------------------------------

def _status_map(db: Session, user: User, problem_ids: list[str]) -> dict[str, UserProblemStatus]:
    rows = db.query(UserProblemStatus).filter(
        UserProblemStatus.user_id == user.id,
        UserProblemStatus.problem_id.in_(problem_ids),
    )
    return {r.problem_id: r for r in rows}


def get_dsa_sheet(db: Session, user: User) -> dict:
    topics = db.query(SheetTopic).filter_by(sheet="dsa").order_by(SheetTopic.order).all()
    problems = db.query(SheetProblem).filter(SheetProblem.topic_id.in_([t.id for t in topics])).order_by(SheetProblem.order).all()
    statuses = _status_map(db, user, [p.id for p in problems])

    by_topic: dict[str, list] = {t.id: [] for t in topics}
    for p in problems:
        by_topic[p.topic_id].append(p)

    total, solved = len(problems), sum(1 for s in statuses.values() if s.status == "solved")

    topics_out = []
    for t in topics:
        plist = by_topic[t.id]
        t_solved = sum(1 for p in plist if statuses.get(p.id) and statuses[p.id].status == "solved")
        topics_out.append(
            {
                "id": t.id,
                "name": t.name,
                "solved": t_solved,
                "total": len(plist),
                "problems": [
                    {
                        "id": p.id,
                        "title": p.title,
                        "difficulty": p.difficulty,
                        "pattern": p.pattern,
                        "leetcode_url": p.leetcode_url,
                        "concept_id": p.concept_id,
                        "status": statuses[p.id].status if p.id in statuses else "unsolved",
                    }
                    for p in plist
                ],
            }
        )

    return {"solved": solved, "total": total, "topics": topics_out}


def set_problem_status(db: Session, user: User, problem_id: str, status: str) -> dict:
    if status not in ("unsolved", "solved", "revisit"):
        raise ContentError("status must be 'unsolved', 'solved', or 'revisit'.")

    if db.get(SheetProblem, problem_id) is None:
        raise ContentError("Problem not found.")

    row = db.query(UserProblemStatus).filter_by(user_id=user.id, problem_id=problem_id).first()
    if row is None:
        row = UserProblemStatus(user_id=user.id, problem_id=problem_id)
        db.add(row)

    row.status = status
    row.updated_at = datetime.now(timezone.utc)
    if status == "solved":
        row.solved_at = datetime.now(timezone.utc)

    db.commit()
    return {"problem_id": problem_id, "status": status}


def get_core_cs(db: Session) -> dict:
    topics = db.query(SheetTopic).filter_by(sheet="core_cs").order_by(SheetTopic.order).all()
    notes = db.query(CoreCSNote).order_by(CoreCSNote.order).all()

    by_topic: dict[str, list] = {t.id: [] for t in topics}
    for n in notes:
        by_topic.setdefault(n.topic_id, []).append(n)

    return {
        "topics": [
            {
                "id": t.id,
                "name": t.name,
                "notes": [{"id": n.id, "title": n.title, "body_markdown": n.body_markdown} for n in by_topic.get(t.id, [])],
            }
            for t in topics
        ]
    }


# --------------------------------------------------------------------------
# Companies & readiness
# --------------------------------------------------------------------------

def list_companies(db: Session) -> list[dict]:
    return [
        {"id": c.id, "name": c.name, "tier": c.tier, "rounds": c.rounds}
        for c in db.query(Company).order_by(Company.tier.desc(), Company.name).all()
    ]


def _topic_mastery(db: Session, user: User, topic: SheetTopic) -> float:
    problems = db.query(SheetProblem).filter_by(topic_id=topic.id).all()
    if not problems:
        return 0.0

    statuses = _status_map(db, user, [p.id for p in problems])
    concept_ids = [p.concept_id for p in problems if p.concept_id]
    beliefs = {
        row.concept_id: B.mastery(row.probs)
        for row in db.query(ConceptBelief).filter(
            ConceptBelief.user_id == user.id, ConceptBelief.concept_id.in_(concept_ids)
        )
    } if concept_ids else {}

    scores = []
    for p in problems:
        if p.concept_id in beliefs:
            # Blend sheet-solved status with the deeper MKT signal when we have it.
            solved = 1.0 if statuses.get(p.id) and statuses[p.id].status == "solved" else 0.0
            scores.append(0.5 * solved + 0.5 * beliefs[p.concept_id])
        else:
            scores.append(1.0 if statuses.get(p.id) and statuses[p.id].status == "solved" else 0.0)

    return sum(scores) / len(scores)


def _subtopic_mastery(db: Session, user: User, subtopic_id: str) -> float:
    prompt_ids = [p.id for p in db.query(DesignPrompt.id).filter_by(subtopic_id=subtopic_id, simulatable=True)]
    if not prompt_ids:
        return 0.0

    sessions = db.query(DesignSession).filter(
        DesignSession.user_id == user.id,
        DesignSession.prompt_id.in_(prompt_ids),
        DesignSession.status == "completed",
    ).all()

    if not sessions:
        return 0.0

    # Credit for attempting; more for ending with the current design satisfying its SLOs
    # (we don't re-run analysis here, so this is a coarse "attempted" signal; the full
    # report's `slo_satisfied` is available via /design/sessions/{id}/report).
    return min(1.0, 0.4 + 0.2 * len(sessions))


def company_readiness(db: Session, user: User, company_id: str) -> dict:
    company = db.get(Company, company_id)
    if company is None:
        raise ContentError("Company not found.")

    weights = db.query(CompanyWeight).filter_by(company_id=company_id).all()
    topic_weights = {w.ref_id: w.weight for w in weights if w.ref_type == "topic"}
    subtopic_weights = {w.ref_id: w.weight for w in weights if w.ref_type == "subtopic"}

    dsa_topics = db.query(SheetTopic).filter_by(sheet="dsa").all()
    design_subtopics = {p.subtopic_id for p in db.query(DesignPrompt.subtopic_id).distinct()}

    breakdown = []
    weighted_sum, weight_total = 0.0, 0.0

    for t in dsa_topics:
        w = topic_weights.get(t.id, 1.0)
        m = _topic_mastery(db, user, t)
        breakdown.append({"type": "dsa_topic", "id": t.id, "name": t.name, "weight": w, "mastery": round(m, 3)})
        weighted_sum += w * m
        weight_total += w

    for sid in sorted(design_subtopics):
        w = subtopic_weights.get(sid, 1.0)
        m = _subtopic_mastery(db, user, sid)
        breakdown.append({"type": "design_subtopic", "id": sid, "name": sid.replace("_", " ").title(), "weight": w, "mastery": round(m, 3)})
        weighted_sum += w * m
        weight_total += w

    readiness = weighted_sum / weight_total if weight_total else 0.0
    breakdown.sort(key=lambda b: b["weight"] * (1 - b["mastery"]), reverse=True)

    return {
        "company": {"id": company.id, "name": company.name, "tier": company.tier, "rounds": company.rounds},
        "readiness_pct": round(readiness * 100, 1),
        "weakest_areas": breakdown[:5],
        "breakdown": breakdown,
    }


def recommended_plan(db: Session, user: User, company_id: str, limit: int = 8) -> list[dict]:
    """
    Greedy plan: rank (weight * (1 - mastery)) and recommend the top-k,
    each with a concrete next action and the reason it was picked.
    """

    report = company_readiness(db, user, company_id)
    plan = []

    for item in report["breakdown"][:limit]:
        if item["mastery"] >= 0.85:
            continue

        if item["type"] == "dsa_topic":
            action = f"Practice problems in '{item['name']}', then test robustness with Metamorphic Probing"
        else:
            action = f"Attempt a simulatable system-design prompt under '{item['name']}'"

        plan.append(
            {
                "focus": item["name"],
                "type": item["type"],
                "ref_id": item["id"],
                "mastery": item["mastery"],
                "reason": f"Weight {item['weight']:.1f} for {report['company']['name']}, current mastery {item['mastery'] * 100:.0f}%.",
                "action": action,
            }
        )

    return plan
