from datetime import timezone

from sqlalchemy.orm import Session

from app.core.models import EvidenceEvent, User, utcnow
from app.modules.aptitude.models import AptitudeAttempt, AptitudeQuestion

TIME_LIMIT_SECONDS = 20 * 60  # ~1 minute per question, matching typical tech-interview aptitude rounds
CATEGORIES = ["quantitative", "logical", "verbal"]


class AptitudeError(ValueError):
    pass


def _as_utc(dt):
    """
    SQLite drops tzinfo on round-trip, so a value written as UTC comes back
    naive. Every datetime this module stores is UTC (via utcnow()), so a
    naive one read back is re-tagged as UTC rather than left ambiguous --
    otherwise isoformat() produces a string JS parses as local time.
    """

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _all_questions(db: Session) -> list[AptitudeQuestion]:
    return db.query(AptitudeQuestion).order_by(AptitudeQuestion.order).all()


def _sanitize_question(q: AptitudeQuestion) -> dict:
    return {
        "id": q.id,
        "category": q.category,
        "difficulty": q.difficulty,
        "question": q.question,
        "options": q.options,
    }


def start_attempt(db: Session, user: User) -> dict:
    questions = _all_questions(db)
    if not questions:
        raise AptitudeError("No aptitude questions available.")

    attempt = AptitudeAttempt(
        user_id=user.id,
        question_ids=[q.id for q in questions],
        time_limit_seconds=TIME_LIMIT_SECONDS,
        status="in_progress",
        total=len(questions),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    return {
        "attempt_id": attempt.id,
        "time_limit_seconds": attempt.time_limit_seconds,
        "started_at": _as_utc(attempt.started_at).isoformat(),
        "questions": [_sanitize_question(q) for q in questions],
    }


def _get_owned_attempt(db: Session, user: User, attempt_id: int) -> AptitudeAttempt:
    attempt = db.get(AptitudeAttempt, attempt_id)
    if attempt is None or attempt.user_id != user.id:
        raise AptitudeError("Attempt not found.")
    return attempt


def get_attempt(db: Session, user: User, attempt_id: int) -> dict:
    attempt = _get_owned_attempt(db, user, attempt_id)
    questions = {q.id: q for q in _all_questions(db) if q.id in attempt.question_ids}
    ordered = [questions[qid] for qid in attempt.question_ids if qid in questions]

    if attempt.status == "submitted":
        return _result_payload(attempt, ordered)

    return {
        "attempt_id": attempt.id,
        "status": attempt.status,
        "time_limit_seconds": attempt.time_limit_seconds,
        "started_at": _as_utc(attempt.started_at).isoformat(),
        "questions": [_sanitize_question(q) for q in ordered],
    }


def _result_payload(attempt: AptitudeAttempt, ordered: list[AptitudeQuestion]) -> dict:
    return {
        "attempt_id": attempt.id,
        "status": attempt.status,
        "score": attempt.score,
        "total": attempt.total,
        "category_breakdown": attempt.category_breakdown,
        "expired": attempt.category_breakdown.get("_expired", False),
        "started_at": _as_utc(attempt.started_at).isoformat(),
        "submitted_at": _as_utc(attempt.submitted_at).isoformat() if attempt.submitted_at else None,
        "questions": [
            {
                **_sanitize_question(q),
                "correct_index": q.correct_index,
                "explanation": q.explanation,
                "selected_index": attempt.answers.get(q.id),
            }
            for q in ordered
        ],
    }


def submit_attempt(db: Session, user: User, attempt_id: int, answers: dict[str, int]) -> dict:
    attempt = _get_owned_attempt(db, user, attempt_id)
    if attempt.status == "submitted":
        raise AptitudeError("Attempt already submitted.")

    questions = {q.id: q for q in _all_questions(db) if q.id in attempt.question_ids}
    ordered = [questions[qid] for qid in attempt.question_ids if qid in questions]

    elapsed = (utcnow() - _as_utc(attempt.started_at)).total_seconds()
    expired = elapsed > attempt.time_limit_seconds

    score = 0
    breakdown = {c: {"correct": 0, "total": 0} for c in CATEGORIES}
    for q in ordered:
        breakdown[q.category]["total"] += 1
        selected = answers.get(q.id)
        if selected is not None and selected == q.correct_index:
            score += 1
            breakdown[q.category]["correct"] += 1
    breakdown["_expired"] = expired

    attempt.answers = {qid: v for qid, v in answers.items() if qid in questions}
    attempt.score = score
    attempt.status = "submitted"
    attempt.category_breakdown = breakdown
    attempt.submitted_at = utcnow()
    db.add(attempt)

    db.add(
        EvidenceEvent(
            user_id=user.id,
            domain="aptitude",
            source="aptitude",
            signal="attempt_submitted",
            value={"attempt_id": attempt.id, "score": score, "total": attempt.total, "expired": expired},
        )
    )
    db.commit()
    db.refresh(attempt)

    return _result_payload(attempt, ordered)


def list_attempts(db: Session, user: User) -> list[dict]:
    rows = (
        db.query(AptitudeAttempt)
        .filter_by(user_id=user.id)
        .order_by(AptitudeAttempt.started_at.desc())
        .all()
    )
    return [
        {
            "attempt_id": a.id,
            "status": a.status,
            "score": a.score,
            "total": a.total,
            "started_at": _as_utc(a.started_at).isoformat(),
            "submitted_at": _as_utc(a.submitted_at).isoformat() if a.submitted_at else None,
        }
        for a in rows
    ]
