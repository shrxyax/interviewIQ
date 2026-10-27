from sqlalchemy.orm import Session

from app.core.models import EvidenceEvent, User
from app.modules.coding.models import CodingProblem, Submission
from app.modules.coding.sandbox import run_one


class CodingError(ValueError):
    pass


def list_problems(db: Session) -> list[dict]:
    rows = db.query(CodingProblem).order_by(CodingProblem.order).all()
    return [{"id": p.id, "title": p.title, "difficulty": p.difficulty} for p in rows]


def get_problem(db: Session, problem_id: str) -> dict:
    p = db.get(CodingProblem, problem_id)
    if p is None:
        raise CodingError("Problem not found.")

    return {
        "id": p.id,
        "title": p.title,
        "difficulty": p.difficulty,
        "statement": p.statement,
        "signature": p.signature,
        "starter_code": p.starter_code,
        "sample_tests": p.sample_tests,
    }


def run_tests(code: str, tests: list[dict]) -> dict:
    results = []

    for t in tests:
        r = run_one(code, t["args"], t.get("expected"))
        results.append({"status": r.status, "output": r.output, "error": r.error, "runtime_ms": round(r.runtime_ms, 1)})

        if r.status == "unsafe":
            break  # no point running more; the whole submission is rejected

    passed = sum(1 for r in results if r["status"] == "ok")
    return {"results": results, "passed": passed, "total": len(tests)}


def run_samples(db: Session, problem_id: str, code: str) -> dict:
    p = db.get(CodingProblem, problem_id)
    if p is None:
        raise CodingError("Problem not found.")

    return run_tests(code, p.sample_tests)


_VERDICT_PRIORITY = ["unsafe", "timeout", "runtime_error", "wrong_answer", "ok"]


def overall_verdict(results: list[dict]) -> str:
    statuses = {r["status"] for r in results}
    for status in _VERDICT_PRIORITY:
        if status in statuses:
            worst = status
            break
    else:
        worst = "ok"

    return {
        "unsafe": "UNSAFE", "timeout": "TLE", "runtime_error": "RE",
        "wrong_answer": "WA", "ok": "AC",
    }[worst]


def submit(db: Session, user: User, problem_id: str, code: str) -> dict:
    p = db.get(CodingProblem, problem_id)
    if p is None:
        raise CodingError("Problem not found.")

    all_tests = p.sample_tests + p.hidden_tests
    run = run_tests(code, all_tests)
    verdict = overall_verdict(run["results"])
    runtime = max((r["runtime_ms"] for r in run["results"]), default=0.0)

    submission = Submission(
        user_id=user.id, problem_id=problem_id, code=code,
        verdict=verdict, passed=run["passed"], total=run["total"], runtime_ms=runtime,
    )
    db.add(submission)

    db.add(
        EvidenceEvent(
            user_id=user.id,
            domain="coding",
            source="coding",
            signal="submission",
            value={"problem_id": problem_id, "verdict": verdict, "passed": run["passed"], "total": run["total"]},
        )
    )
    db.commit()

    return {
        "submission_id": submission.id,
        "verdict": verdict,
        "passed": run["passed"],
        "total": run["total"],
        # Only reveal per-test detail for the sample tests (first N), not the hidden suite,
        # matching a real judge's behaviour.
        "visible_results": run["results"][: len(p.sample_tests)],
    }


def list_submissions(db: Session, user: User, problem_id: str) -> list[dict]:
    rows = (
        db.query(Submission)
        .filter_by(user_id=user.id, problem_id=problem_id)
        .order_by(Submission.created_at.desc())
        .all()
    )
    return [
        {"id": s.id, "verdict": s.verdict, "passed": s.passed, "total": s.total, "runtime_ms": s.runtime_ms, "created_at": s.created_at.isoformat()}
        for s in rows
    ]
