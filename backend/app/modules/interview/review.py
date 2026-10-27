"""
Built-in answer review and final report, used whenever the LLM can't be
reached (e.g. its daily quota is used up) so a finished interview still gets
real, specific feedback instead of a "feedback unavailable" placeholder.

Everything here is local: relevance comes from embedding similarity between
question and answer (the same bge model the resume retriever uses, injected
as `embed`), the rest from transcript signals - length, examples, reasoning,
STAR structure for behavioural questions, fillers and hedges (see
app/modules/communication/analysis.py). MKT-driven turns already have a
verified assessment; mkt_feedback() turns it into readable feedback.
"""

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from app.modules.communication.analysis import FILLER_WORDS, HEDGES, analyze_communication

# Questions that call for a story, so STAR structure applies.
_STORY_QUESTION = re.compile(
    r"\b(a time|situation|when you (had|faced|were|made|disagreed)|conflict|disagree|mistake|failure|"
    r"challenge you|proud of|deadline|under pressure)\b",
    re.I,
)

_STOPWORDS = set(
    """
    a an the and or but if of to in on at for with from by as is are was were be been being do does did
    you your yours i me my we our it its this that these those there their they them what which who whom
    how why when where can could would should will shall may might must have has had about into over
    under more most other some such than too very just also any each few both all not no nor only own
    same so then once here again further while tell me explain describe walk through give example
    difference between please let us one two use used using like
    """.split()
)

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z+#'-]*")
_DONT_KNOW = re.compile(r"\b(i\s*don'?t\s*know|no\s*idea|not\s*sure|can'?t\s*remember|skip)\b", re.I)
_EXAMPLE = re.compile(
    r"\b(for example|for instance|e\.g\.|such as|in my (project|internship|team|last)|i (built|implemented|"
    r"designed|developed|wrote|created|used)|we (built|implemented|designed|developed|used)|when i)\b|\d",
    re.I,
)
_REASONING = re.compile(
    r"\b(because|since|so that|therefore|which means|as a result|trade-?offs?|instead of|whereas|"
    r"compared to|the reason|this is why|otherwise)\b",
    re.I,
)
_STAR = {
    "situation": re.compile(r"\b(when|during|at my|in my|once|last (year|semester)|there was)\b", re.I),
    "action": re.compile(
        r"\bi (decided|took|built|led|talked|spoke|created|implemented|fixed|organi[sz]ed|proposed|"
        r"started|reached|split|planned|learned|worked|handled|made)\b",
        re.I,
    ),
    "result": re.compile(
        r"\b(result|outcome|in the end|finally|eventually|learn(ed|t)|improved|reduced|increased|"
        r"delivered|succeeded|won|completed|shipped)\b|%",
        re.I,
    ),
}


@dataclass
class AnswerReview:
    score: int  # 1-10
    relevance: float  # 0-1
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    comm: dict = field(default_factory=dict)
    has_example: bool = False
    has_reasoning: bool = False

    @property
    def text(self) -> str:
        lines = []
        if self.strengths:
            lines.append("What worked: " + " ".join(self.strengths))
        if self.improvements:
            lines.append("To improve: " + " ".join(self.improvements))
        return "\n".join(lines)


def _keywords(text: str) -> list[str]:
    seen = dict.fromkeys(w.lower() for w in _WORD_RE.findall(text))
    return [w for w in seen if w not in _STOPWORDS and len(w) > 2]


def _relevance(question: str, answer: str, embed: Callable | None) -> float:
    q_words = _keywords(question)
    a_words = set(_keywords(answer))
    lexical = (sum(1 for w in q_words if w in a_words) / len(q_words)) if q_words else 0.5

    if embed is None:
        return min(1.0, lexical * 1.5)

    try:
        vecs = np.asarray(embed([question, answer]))
        similarity = float(vecs[0] @ vecs[1])
    except Exception:
        return min(1.0, lexical * 1.5)

    # bge-small: on-topic answers land around 0.65-0.85, unrelated text
    # around 0.3-0.45.
    semantic = (similarity - 0.4) / 0.3
    return float(np.clip(0.75 * semantic + 0.25 * min(1.0, lexical * 1.5), 0.0, 1.0))


def _found(text: str, phrases: tuple[str, ...]) -> list[str]:
    lower = text.lower()
    return [p for p in phrases if re.search(r"\b" + re.escape(p) + r"\b", lower)]


def review_answer(question: str, answer: str, interview_type: str, embed: Callable | None = None) -> AnswerReview:
    answer = (answer or "").strip()
    comm = analyze_communication(answer)
    words = comm["word_count"]

    if words < 6:
        return AnswerReview(
            score=1,
            relevance=0.0,
            improvements=[
                "The answer was too short to evaluate. Aim for 4-6 sentences: your main point, how or why it "
                "works, and a concrete example."
            ],
            comm=comm,
        )

    if _DONT_KNOW.search(answer) and words < 25:
        return AnswerReview(
            score=2,
            relevance=0.2,
            strengths=["Being honest about a gap is better than bluffing."],
            improvements=[
                "Even when unsure, reason out loud: say what you do know, make an assumption, and work towards "
                "an answer. Interviewers grade the thinking, not just the final answer."
            ],
            comm=comm,
        )

    relevance = _relevance(question, answer, embed)
    has_example = bool(_EXAMPLE.search(answer))
    has_reasoning = bool(_REASONING.search(answer))
    behavioral = bool(_STORY_QUESTION.search(question))
    strengths, improvements = [], []

    # Relevance: up to 4 points.
    points = 4 * relevance
    if relevance >= 0.7:
        strengths.append("Stays focused on what was asked.")
    elif relevance < 0.4:
        missing = [w for w in _keywords(question) if w not in set(_keywords(answer))][:3]
        hint = f" (it barely touches on {', '.join(missing)})" if missing else ""
        improvements.append(f"The answer drifts from the question{hint}. Open with a direct answer, then expand.")

    # Depth: up to 4 points.
    if words < 25:
        improvements.append(
            f"At {words} words it is too brief to show depth; expand on the details behind your point."
        )
        points += 0.5
    elif words <= 300:
        points += 1.5
    else:
        points += 1
        improvements.append("It runs long. Lead with the key point and trim repetition so it lands in about a minute.")

    if behavioral:
        parts = [name for name, rx in _STAR.items() if rx.search(answer)]
        points += 2.5 * len(parts) / len(_STAR)
        missing_parts = [p for p in _STAR if p not in parts]

        if not missing_parts:
            strengths.append("Follows a clear situation, action, result structure.")
        else:
            improvements.append(
                "Use the STAR structure (Situation, Task, Action, Result); this answer is missing the "
                + " and ".join(missing_parts)
                + "."
            )
    else:
        if has_example:
            points += 1.25
            strengths.append("Backs the point up with something concrete.")
        else:
            improvements.append("Add a concrete example, from one of your projects or a small worked case.")

        if has_reasoning:
            points += 1.25
            strengths.append("Explains the reasoning, not just the conclusion.")
        else:
            improvements.append("Explain why: the reason or trade-off behind your answer.")

    # Delivery: up to 2 points.
    fillers = _found(answer, FILLER_WORDS)
    hedges = _found(answer, HEDGES)
    delivery = 2.0

    if comm["filler_rate"] > 0.04:
        delivery -= 1
        improvements.append(f"Cut filler words ({', '.join(repr(f) for f in fillers[:3])}); a short pause is fine.")
    if comm["hedge_count"] >= 2:
        delivery -= 0.75
        improvements.append(f"Sound more decisive: hedges like {', '.join(repr(h) for h in hedges[:2])} weaken the answer.")
    if delivery == 2.0 and words >= 25:
        strengths.append("Clear, confident delivery.")
    points += max(0.0, delivery)

    # A few words can't show depth however on-topic they are.
    if words < 15:
        points = min(points, 3)
    elif words < 25:
        points = min(points, 5)

    score = int(np.clip(round(points), 1, 10))
    return AnswerReview(
        score=score,
        relevance=relevance,
        strengths=strengths,
        improvements=improvements[:3],
        comm=comm,
        has_example=has_example,
        has_reasoning=has_reasoning,
    )


# --------------------------------------------------------------------------
# MKT-driven turns
# --------------------------------------------------------------------------

_PROBE_INTRO = {
    "base": "the core idea",
    "mr_paraphrase": "the same idea asked a different way",
    "mr_constraint": "the idea under a changed constraint",
    "mr_inversion": "the idea worked backwards",
    "mr_pushback": "holding your position when challenged",
    "mr_transfer": "applying the idea to a new problem",
}

_OUTCOME_SUMMARY = {
    "consistent_correct": "Correct and consistent with your earlier answers.",
    "partial": "Partly correct.",
    "inconsistent": "This contradicts or doesn't match your earlier answer on the same concept, which suggests the "
    "idea is memorised rather than understood.",
    "consistent_wrong": "Incorrect.",
    "empty": "No usable answer.",
    "capitulated": "You agreed with an incorrect claim when challenged.",
}


def mkt_feedback(concept_name: str, probe_type: str, outcome: str, spec: dict, assessment: dict) -> str:
    verdicts = assessment.get("verdicts") or {}
    must = spec.get("must_entail", [])
    covered = [s for s in must if (verdicts.get(s) or {}).get("label") == "supported"]
    missed = [s for s in must if s not in covered]

    lines = [f"{concept_name}, tested on {_PROBE_INTRO.get(probe_type, 'this concept')}. {_OUTCOME_SUMMARY.get(outcome, '')}"]

    if covered:
        lines.append("You covered: " + "; ".join(covered) + ".")
    if missed:
        lines.append("Missing: " + "; ".join(missed) + ".")
    for misconception in assessment.get("misconceptions_hit") or []:
        lines.append(f"Watch out for the misconception: \"{misconception}\".")
    if spec.get("false_claim") and assessment.get("false_claim") == "supported":
        lines.append(f"The claim \"{spec['false_claim']}\" is false; it is fine to politely disagree with an interviewer.")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Final report
# --------------------------------------------------------------------------

# Per-answer advice -> the general habit it points to, for the report.
_REPORT_AREAS = (
    ("The answer was too short", "Give fuller answers: the main point, how it works, and an example."),
    ("At ", "Give fuller answers: the main point, how it works, and an example."),
    ("Even when unsure", "When unsure, reason out loud instead of stopping."),
    ("The answer drifts", "Answer the question directly first, then expand."),
    ("It runs long", "Keep answers tighter by leading with the key point."),
    ("Use the STAR", "Structure behavioural answers with STAR (Situation, Task, Action, Result)."),
    ("Add a concrete example", "Support answers with concrete examples from your projects."),
    ("Explain why", "Explain the reasoning and trade-offs behind your answers."),
    ("Cut filler", "Reduce filler words such as 'like' and 'basically'."),
    ("Sound more decisive", "Reduce hedging ('I think', 'maybe') and sound more decisive."),
)


def _area(improvement: str) -> str:
    for prefix, area in _REPORT_AREAS:
        if improvement.startswith(prefix):
            return area
    return improvement


def _pct(x: float) -> int:
    return int(np.clip(round(x), 0, 100))


def build_report(interview_type: str, target_role: str, history: list[dict], embed: Callable | None = None) -> dict:
    """FinalReport fields computed from the answered turns in `history`."""

    if not history:
        return {
            "overall_score": 0, "communication": 0, "technical_knowledge": 0, "answer_relevance": 0,
            "clarity": 0, "problem_solving": 0, "strengths": [],
            "areas_for_improvement": ["Answer at least one question to get feedback."],
            "final_feedback": "No answers were recorded, so there is nothing to evaluate yet.",
        }

    # Prose signals (relevance, fillers, structure) don't apply to code or a
    # design diagram; those rounds count through their measured score only.
    spoken = [h for h in history if h.get("source") not in ("coding", "design")]
    reviews = [review_answer(h["question"], h["answer"], interview_type, embed) for h in spoken]
    review_by_entry = {id(h): r for h, r in zip(spoken, reviews)}
    scores = [h["score"] if h.get("score") is not None else review_by_entry[id(h)].score for h in history]

    if not reviews:
        reviews = [AnswerReview(score=round(sum(scores) / len(scores)), relevance=1.0)]

    mean_score = sum(scores) / len(scores)
    relevance = 100 * sum(r.relevance for r in reviews) / len(reviews)

    filler = sum(r.comm.get("filler_rate", 0) for r in reviews) / len(reviews)
    hedges = sum(r.comm.get("hedge_count", 0) for r in reviews) / len(reviews)
    words = sum(r.comm.get("word_count", 0) for r in reviews) / len(reviews)
    sentence_len = sum(r.comm.get("avg_sentence_length", 0) for r in reviews) / len(reviews)

    communication = 100 - 600 * filler - 8 * hedges - (25 if words < 25 else 0)
    clarity = 100 - 500 * filler - 2 * max(0, sentence_len - 25) - (30 if words < 15 else 0)
    clarity = min(clarity, 40 + relevance * 0.6)
    technical = 10 * mean_score
    reasoning_rate = sum(r.has_reasoning for r in reviews) / len(reviews)
    example_rate = sum(r.has_example for r in reviews) / len(reviews)
    problem_solving = 0.6 * technical + 20 * reasoning_rate + 20 * example_rate

    dims = {
        "communication": _pct(communication),
        "technical_knowledge": _pct(technical),
        "answer_relevance": _pct(relevance),
        "clarity": _pct(clarity),
        "problem_solving": _pct(problem_solving),
    }
    overall = _pct(0.6 * technical + 0.4 * sum(dims.values()) / len(dims))

    strength_counts = Counter(s for r in reviews for s in r.strengths)
    improvement_counts = Counter(_area(i) for r in reviews for i in r.improvements)

    strengths = [s for s, _ in strength_counts.most_common(4)]
    areas = [i for i, _ in improvement_counts.most_common(4)]
    if not strengths and max(scores) >= 6:
        strengths = [f"Your strongest answer was question {scores.index(max(scores)) + 1}."]

    best = scores.index(max(scores)) + 1
    worst = scores.index(min(scores)) + 1
    level = "strong" if overall >= 75 else "solid" if overall >= 60 else "developing" if overall >= 40 else "early-stage"

    feedback = [
        f"You answered {len(history)} question{'s' if len(history) != 1 else ''} in this {interview_type} interview "
        f"for {target_role}, averaging {mean_score:.1f}/10, a {level} performance."
    ]
    if len(history) > 1 and best != worst:
        feedback.append(f"Your best answer was question {best} and the weakest was question {worst}; compare the two to see what made the difference.")
    if areas:
        feedback.append(f"The biggest gain now: {areas[0][0].lower() + areas[0][1:]}")
    feedback.append("(Scored by InterviewIQ's built-in reviewer because the AI model was unavailable.)")

    return {
        "overall_score": overall,
        **dims,
        "strengths": strengths,
        "areas_for_improvement": areas,
        "final_feedback": " ".join(feedback),
    }
