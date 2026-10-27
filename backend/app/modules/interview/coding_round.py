"""
Live coding round inside an interview.

DSA, technical and mixed interviews include one coding turn around the
middle (InterviewTurn.source == "coding"): a problem from the Coding IDE's
bank, solved in an editor during the interview. "Run" checks the visible
test cases; submitting runs every test in the coding sandbox and scores the
turn by how many pass. Per-round state lives in InterviewCodingRound.
"""

import random
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.modules.coding.models import CodingProblem
from app.modules.coding.service import overall_verdict, run_tests
from app.modules.interview.models import InterviewCodingRound, InterviewContext, InterviewSession, InterviewTurn

CODING_INTERVIEW_TYPES = {"dsa", "technical", "mixed"}

# Interviews without a question limit get their practical round at this turn.
DEFAULT_PRACTICAL_SEQ = 4

# Test cases shown to the candidate (the rest stay hidden until submit).
VISIBLE_TESTS = 3

_EASY_LEVELS = {"intern", "junior"}

VERDICT_LABELS = {
    "AC": "Accepted",
    "WA": "Wrong answer",
    "RE": "Runtime error",
    "TLE": "Time limit exceeded",
    "UNSAFE": "Blocked (unsafe code)",
}


def coding_seq(context: InterviewContext, num_questions: int | None, is_mkt_seq: Callable[[int], bool]) -> int | None:
    """The turn number of this interview's coding round, or None if it has none."""

    if context.interview_type not in CODING_INTERVIEW_TYPES:
        return None

    return middle_seq(num_questions, is_mkt_seq)


def middle_seq(num_questions: int | None, is_mkt_seq: Callable[[int], bool]) -> int | None:
    """
    The turn in the middle of an interview for a practical round (coding,
    design lab), stepping past a turn MKT has scheduled; None if the
    interview is too short for one.
    """

    if num_questions is None:
        return DEFAULT_PRACTICAL_SEQ

    if num_questions < 2:
        return None

    seq = num_questions // 2 + 1

    # Leave MKT's scheduled turns to MKT where there's room to.
    if is_mkt_seq(seq) and seq + 1 <= num_questions:
        seq += 1

    return seq


def pick_problem(db: Session, user_id: int, experience_level: str) -> CodingProblem | None:
    """A problem suited to the level that this candidate hasn't had in an interview yet."""

    used = {
        problem_id
        for (problem_id,) in db.query(InterviewCodingRound.problem_id)
        .join(InterviewTurn, InterviewTurn.id == InterviewCodingRound.turn_id)
        .join(InterviewSession, InterviewSession.id == InterviewTurn.session_id)
        .filter(InterviewSession.user_id == user_id)
    }

    problems = db.query(CodingProblem).order_by(CodingProblem.order).all()
    if not problems:
        return None

    if experience_level in _EASY_LEVELS:
        suited = [p for p in problems if p.difficulty == "Easy"]
    else:
        suited = [p for p in problems if p.difficulty != "Easy"] + [p for p in problems if p.difficulty == "Easy"]

    fresh = [p for p in suited if p.id not in used] or [p for p in problems if p.id not in used] or problems

    # Prefer the harder pool for experienced candidates, but still vary.
    pool = fresh[: max(3, len(fresh) // 2)] if experience_level not in _EASY_LEVELS else fresh
    return random.choice(pool)


def split_tests(problem: CodingProblem) -> tuple[list[dict], list[dict]]:
    """(visible, hidden) test cases; at least one test always stays hidden."""

    tests = list(problem.sample_tests) + list(problem.hidden_tests)
    n_visible = min(VISIBLE_TESTS, max(1, len(tests) - 1))
    return tests[:n_visible], tests[n_visible:]


def intro_question(problem: CodingProblem) -> str:
    """What the interviewer says; the problem itself is shown on screen."""

    return (
        f"Let's move to a coding round. Please solve {problem.title}. The problem and its test cases are on "
        "your screen. Write your solution in Python in the editor, run the tests, and submit when you're ready."
    )


def start_round(db: Session, turn: InterviewTurn, problem: CodingProblem) -> InterviewCodingRound:
    coding_round = InterviewCodingRound(turn_id=turn.id, problem_id=problem.id, code=problem.starter_code, run_count=0)
    db.add(coding_round)
    return coding_round


def public_payload(db: Session, turn: InterviewTurn) -> dict | None:
    coding_round = db.get(InterviewCodingRound, turn.id)
    if coding_round is None:
        return None

    problem = db.get(CodingProblem, coding_round.problem_id)
    visible, hidden = split_tests(problem)

    return {
        "language": "python",
        "problem": {
            "id": problem.id,
            "title": problem.title,
            "difficulty": problem.difficulty,
            "statement": problem.statement,
            "signature": problem.signature,
            "starter_code": problem.starter_code,
            "tests": [{"args": t["args"], "expected": t.get("expected")} for t in visible],
            "hidden_test_count": len(hidden),
        },
        "code": coding_round.code if coding_round.code is not None else problem.starter_code,
    }


def _detailed(results: list[dict], tests: list[dict]) -> list[dict]:
    return [{**r, "args": t["args"], "expected": t.get("expected")} for r, t in zip(results, tests)]


def run_visible(db: Session, coding_round: InterviewCodingRound, code: str) -> dict:
    """Runs the visible tests and remembers the code as the latest draft."""

    problem = db.get(CodingProblem, coding_round.problem_id)
    visible, _ = split_tests(problem)

    coding_round.code = code
    coding_round.run_count = (coding_round.run_count or 0) + 1

    run = run_tests(code, visible)
    return {"results": _detailed(run["results"], visible), "passed": run["passed"], "total": run["total"]}


def grade(db: Session, coding_round: InterviewCodingRound, code: str) -> tuple[int, str, str]:
    """
    Runs every test, stores the result, and returns (score 1-10, feedback
    shown in the report, one-line summary for the LLM's code review).
    """

    problem = db.get(CodingProblem, coding_round.problem_id)
    visible, hidden = split_tests(problem)

    coding_round.code = code

    if code.strip() == (problem.starter_code or "").strip():
        coding_round.verdict, coding_round.passed, coding_round.total = "WA", 0, len(visible) + len(hidden)
        coding_round.results = []
        return 1, "No solution was written; the starter code was submitted unchanged.", "no solution written"

    run = run_tests(code, visible + hidden)
    results = run["results"]
    verdict = overall_verdict(results)

    visible_results = _detailed(results[: len(visible)], visible)
    visible_passed = sum(r["status"] == "ok" for r in visible_results)
    hidden_passed = run["passed"] - visible_passed

    coding_round.verdict = verdict
    coding_round.passed = run["passed"]
    coding_round.total = run["total"]
    coding_round.results = visible_results

    summary = (
        f"{VERDICT_LABELS[verdict]}: passed {run['passed']}/{run['total']} tests "
        f"({visible_passed}/{len(visible)} visible, {hidden_passed}/{len(hidden)} hidden)"
    )

    lines = [summary + "."]
    if results and results[0]["status"] == "unsafe":
        lines.append(results[0]["error"])
    else:
        failed = next((r for r in visible_results if r["status"] != "ok"), None)
        if failed is not None:
            if failed["error"]:
                lines.append(f"Failed on input {failed['args']}: {failed['error']}")
            else:
                lines.append(f"Failed on input {failed['args']}: expected {failed['expected']!r}, got {failed['output']!r}.")
        elif hidden_passed < len(hidden):
            lines.append("All visible tests pass but some hidden ones fail; check edge cases (empty input, duplicates, negatives, large values).")

    total = run["total"] or 1
    score = 10 if verdict == "AC" else max(1, round(1 + 8 * run["passed"] / total))

    return score, "\n".join(lines), summary
