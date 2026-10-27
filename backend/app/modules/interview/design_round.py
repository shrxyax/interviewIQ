"""
System-design lab round inside an interview.

System-design interviews include one turn around the middle
(InterviewTurn.source == "design") where the candidate edits an
architecture in the executable whiteboard instead of only talking about it.
"Analyze" runs the whiteboard's queueing/graph analysis on the current
draft; submitting grades the design by whether it meets the prompt's SLOs,
how many injected failures it survives, and whether it has single points of
failure or growth headroom. Per-round state lives in InterviewDesignRound.
"""

import json
import random

from sqlalchemy.orm import Session

from app.modules.interview.coding_round import middle_seq
from app.modules.interview.models import InterviewContext, InterviewDesignRound, InterviewSession, InterviewTurn
from app.modules.whiteboard.catalog import catalog_public
from app.modules.whiteboard.findings import NO_HEADROOM, SPOF
from app.modules.whiteboard.models import DesignPrompt
from app.modules.whiteboard.service import BLOCKING_TYPES, WhiteboardError, analyze_graph, resilience_suite

DESIGN_INTERVIEW_TYPES = {"system_design"}

_LEVEL_DIFFICULTIES = {
    "intern": ("Easy", "Medium"),
    "junior": ("Easy", "Medium"),
    "mid": ("Medium", "Hard"),
    "senior": ("Hard", "Medium"),
}


def design_seq(context: InterviewContext, num_questions: int | None, is_mkt_seq) -> int | None:
    """The turn number of this interview's design-lab round, or None if it has none."""

    if context.interview_type not in DESIGN_INTERVIEW_TYPES:
        return None

    return middle_seq(num_questions, is_mkt_seq)


def pick_prompt(db: Session, user_id: int, experience_level: str) -> DesignPrompt | None:
    """An executable prompt suited to the level that this candidate hasn't had in an interview yet."""

    used = {
        prompt_id
        for (prompt_id,) in db.query(InterviewDesignRound.prompt_id)
        .join(InterviewTurn, InterviewTurn.id == InterviewDesignRound.turn_id)
        .join(InterviewSession, InterviewSession.id == InterviewTurn.session_id)
        .filter(InterviewSession.user_id == user_id)
    }

    prompts = db.query(DesignPrompt).filter(DesignPrompt.simulatable.is_(True)).order_by(DesignPrompt.id).all()
    if not prompts:
        return None

    wanted = _LEVEL_DIFFICULTIES.get(experience_level, ("Medium",))
    suited = [p for p in prompts if p.difficulty in wanted]
    fresh = [p for p in suited if p.id not in used] or [p for p in prompts if p.id not in used] or prompts

    return random.choice(fresh)


def intro_question(prompt: DesignPrompt) -> str:
    """What the interviewer says; the requirements and the editor are on screen."""

    return (
        f"Let's do a hands-on design exercise. {prompt.title}. The requirements and a starting architecture are "
        "on your screen. Change the design so it meets the requirements, use Analyze to check it, and submit "
        "with a short explanation of your choices."
    )


def start_round(db: Session, turn: InterviewTurn, prompt: DesignPrompt) -> InterviewDesignRound:
    design_round = InterviewDesignRound(turn_id=turn.id, prompt_id=prompt.id, graph=prompt.starter_graph, analyze_count=0)
    db.add(design_round)
    return design_round


def public_payload(db: Session, turn: InterviewTurn) -> dict | None:
    design_round = db.get(InterviewDesignRound, turn.id)
    if design_round is None:
        return None

    prompt = db.get(DesignPrompt, design_round.prompt_id)

    return {
        "prompt": {
            "id": prompt.id,
            "title": prompt.title,
            "scenario": prompt.scenario,
            "difficulty": prompt.difficulty,
            "subtopic": prompt.subtopic_name,
            "requirements": prompt.requirements,
        },
        "catalog": catalog_public(),
        "graph": design_round.graph or prompt.starter_graph,
    }


def _analysis_public(result: dict) -> dict:
    return {
        "summary": result["summary"],
        "node_metrics": result["node_metrics"],
        "findings": [f.to_dict() for f in result["findings"]],
    }


def analyze(db: Session, design_round: InterviewDesignRound, graph: dict) -> dict:
    """Analyses the draft and remembers it. Raises WhiteboardError for an invalid design."""

    prompt = db.get(DesignPrompt, design_round.prompt_id)

    design_round.graph = graph
    design_round.analyze_count = (design_round.analyze_count or 0) + 1

    return _analysis_public(analyze_graph(graph, prompt.requirements))


def parse_answer(answer: str) -> tuple[dict | None, str]:
    """
    A design answer is JSON {"graph": ..., "explanation": "..."}; anything
    else is taken as just an explanation (the saved draft graph is graded).
    """

    try:
        data = json.loads(answer)
    except (TypeError, ValueError):
        return None, answer.strip()

    if not isinstance(data, dict):
        return None, answer.strip()

    graph = data.get("graph") if isinstance(data.get("graph"), dict) else None
    return graph, str(data.get("explanation") or "").strip()


def _components(graph: dict) -> str:
    parts = [
        f"{n.get('label') or n['type']} x{(n.get('params') or {}).get('replicas', 1)}"
        for n in graph.get("nodes", [])
        if n.get("type") != "client"
    ]
    return ", ".join(parts)


def grade(db: Session, design_round: InterviewDesignRound, graph: dict | None, explanation: str) -> tuple[int, str, str]:
    """
    Grades the design and stores the verdict. Returns (score 1-10, feedback
    shown in the report, summary for the LLM's design review).
    """

    prompt = db.get(DesignPrompt, design_round.prompt_id)
    reqs = prompt.requirements
    graph = graph or design_round.graph or prompt.starter_graph

    design_round.graph = graph
    design_round.explanation = explanation or None

    try:
        result = analyze_graph(graph, reqs)
        resilience = resilience_suite(graph, reqs)
    except WhiteboardError as exc:
        design_round.slo_satisfied = False
        design_round.resilience_pct = 0.0
        design_round.summary, design_round.findings = None, []
        return 1, f"The design could not be analysed: {exc}", f"invalid design ({exc})"

    findings = result["findings"]
    blocking = [f for f in findings if f.type in BLOCKING_TYPES]
    spofs = [f for f in findings if f.type == SPOF]
    no_headroom = [f for f in findings if f.type == NO_HEADROOM]
    slo_ok = not blocking
    resilience_pct = resilience["resilience_pct"] or 0.0

    design_round.slo_satisfied = slo_ok
    design_round.resilience_pct = resilience_pct
    design_round.summary = result["summary"]
    design_round.findings = [f.to_dict() for f in findings]

    # Meeting the SLOs matters most; then surviving failures; then the
    # structural/growth checks.
    points = 1 + (4 if slo_ok else 0) + 3 * resilience_pct / 100 + (1 if not spofs else 0) + (1 if not no_headroom else 0)
    score = max(1, min(10, round(points)))

    summary = result["summary"]
    p99 = summary["end_to_end_latency_p99_ms"]
    p99_text = f"{p99:.0f} ms" if p99 is not None else "unbounded (overloaded)"

    lines = [
        ("Meets its requirements." if slo_ok else "Does not meet its requirements.")
        + f" p99 latency {p99_text} against a {reqs['p99_slo_ms']} ms target;"
        + f" handles up to {summary['max_sustainable_rps'] or 0:,.0f} requests/s against a peak of {reqs['peak_rps']:,}.",
        f"Resilience: survived {resilience['scenarios_survived']} of {resilience['scenarios_run']} failure scenarios ({resilience_pct:.0f}%).",
    ]

    for f in (blocking + spofs + no_headroom)[:3]:
        lines.append(f"Issue: {f.message}")

    failed = [r["scenario"] for r in resilience["results"] if not r["survived"]]
    if failed:
        names = ", ".join(
            s["type"].replace("_", " ") + (f" ({s['node_id']})" if s.get("node_id") else "") for s in failed[:4]
        )
        lines.append(f"Failed under: {names}.")

    if graph == prompt.starter_graph:
        lines.append("The starting design was submitted unchanged.")

    llm_summary = (
        f"Components: {_components(graph)}. "
        f"{'Meets' if slo_ok else 'Misses'} SLOs (p99 {p99_text} vs {reqs['p99_slo_ms']} ms), "
        f"resilience {resilience_pct:.0f}%, "
        f"issues: {'; '.join(f.message for f in findings[:3]) or 'none'}"
    )

    return score, "\n".join(lines), llm_summary


def history_summary(db: Session, turn: InterviewTurn) -> dict | None:
    design_round = db.get(InterviewDesignRound, turn.id)
    if design_round is None:
        return None

    prompt = db.get(DesignPrompt, design_round.prompt_id)
    summary = design_round.summary or {}

    return {
        "prompt_title": prompt.title if prompt else design_round.prompt_id,
        "slo_satisfied": design_round.slo_satisfied,
        "resilience_pct": design_round.resilience_pct,
        "p99_ms": summary.get("end_to_end_latency_p99_ms"),
        "max_rps": summary.get("max_sustainable_rps"),
        "components": _components(design_round.graph or {}),
    }
