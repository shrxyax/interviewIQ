"""
Consistency checking: answer(s) -> one discrete outcome.

Pipeline for one answer:
    1. Verifier: extract atomic propositions and label each reference
       statement SUPPORTED / CONTRADICTED / NOT_ADDRESSED.
         - LLMVerifier   : one structured LLM call (default)
         - LocalVerifier : NLI cross-encoder (contradictions) +
                           bge similarity (support); no LLM
    2. Symbolic layer: keyword and Big-O checks that override
       NOT_ADDRESSED with exact evidence.
    3. Answer class: CORRECT / PARTIAL / WRONG / EMPTY against the
       template's relation spec.
    4. Relation table: (base class, transformed class, relation) -> outcome.

Steps 2-4 are deterministic code. The verifier only labels whether the
candidate asserted a specific statement; it never scores the answer.

Measured note (see README): general-domain NLI models label most correct
technical paraphrases as "neutral" but detect explicit contradictions
reliably, which is why LocalVerifier uses NLI only for contradiction.
"""

import re
from dataclasses import dataclass, field
from typing import Literal, Protocol

import numpy as np
from pydantic import BaseModel

from app.modules.mkt.states import (
    CAPITULATED,
    CONSISTENT_CORRECT,
    CONSISTENT_WRONG,
    EMPTY,
    INCONSISTENT,
    MR_CONSTRAINT,
    MR_PARAPHRASE,
    MR_PUSHBACK,
    PARTIAL,
)


SUPPORTED = "supported"
CONTRADICTED = "contradicted"
NOT_ADDRESSED = "not_addressed"

# Answer classes.
CORRECT = "correct"
A_PARTIAL = "partial"
WRONG = "wrong"
A_EMPTY = "empty"


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------

@dataclass
class Verdict:
    label: str
    evidence: str = ""
    source: str = ""  # llm | nli | similarity | keyword | complexity


@dataclass
class Verification:
    propositions: list[str]
    verdicts: dict[str, Verdict]  # statement text -> verdict


class Verifier(Protocol):
    name: str

    def verify(self, question: str, answer: str, statements: list[str]) -> Verification: ...


class _LLMVerdict(BaseModel):
    statement_id: int
    label: Literal["supported", "contradicted", "not_addressed"]
    evidence: str


class _LLMVerificationOutput(BaseModel):
    propositions: list[str]
    verdicts: list[_LLMVerdict]


_VERIFY_PROMPT = """You are a precise annotator for a technical interview system.

Your job has two parts and nothing else:
1. Split the candidate's answer into at most 8 short atomic propositions
   (one factual claim each, in the candidate's meaning, plain English).
2. For EACH numbered statement, decide what the CANDIDATE asserted:
   - "supported": the answer clearly asserts it, or asserts something that directly implies it
   - "contradicted": the answer asserts the opposite, or something incompatible with it
   - "not_addressed": the answer does not take a position on it

Critical rules:
- Some statements are deliberately FALSE. Label whether the candidate asserted
  them, not whether they are true.
- Do not use your own knowledge to fill gaps in the answer.
- Paraphrases count ("constant time" supports "O(1)").
- Evidence is a short quote from the answer, or "" if not addressed.

QUESTION:
{question}

CANDIDATE ANSWER:
{answer}

STATEMENTS:
{statements}
"""


class LLMVerifier:
    name = "llm"

    def verify(self, question: str, answer: str, statements: list[str]) -> Verification:
        from app.core.llm_gateway import generate_structured

        numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(statements))
        prompt = _VERIFY_PROMPT.format(question=question, answer=answer, statements=numbered)

        out = generate_structured(prompt, _LLMVerificationOutput, task="mkt_verify")

        verdicts = {s: Verdict(NOT_ADDRESSED, source="llm") for s in statements}

        for v in out.verdicts:
            if 0 <= v.statement_id < len(statements):
                verdicts[statements[v.statement_id]] = Verdict(v.label, v.evidence, "llm")

        return Verification(out.propositions[:8], verdicts)


def split_propositions(answer: str, limit: int = 8) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+|\n+|\s+(?:but|whereas|however|so)\s+", answer.strip())
    return [p.strip(" .;") for p in parts if len(p.strip()) > 2][:limit]


class LocalVerifier:
    """
    No-LLM verifier. NLI decides contradiction (its strength);
    embedding similarity decides support (NLI under-detects technical
    paraphrase). Thresholds were set on a small pilot set.
    """

    name = "local"

    SUPPORT_SIMILARITY = 0.80
    NLI_CONTRADICTION = 0.70
    NLI_ENTAILMENT = 0.50
    TOP_K = 3

    def __init__(self, embed=None, nli=None):
        self._embed = embed
        self._nli = nli

    def _embed_fn(self):
        if self._embed is None:
            from app.services.embeddings import generate_embeddings
            self._embed = generate_embeddings

        return self._embed

    def _nli_fn(self):
        if self._nli is None:
            self._nli = NLIScorer()

        return self._nli

    def verify(self, question: str, answer: str, statements: list[str]) -> Verification:
        props = split_propositions(answer)
        premises = props + ([answer] if len(props) > 1 else [])

        if not premises or not statements:
            return Verification(props, {s: Verdict(NOT_ADDRESSED) for s in statements})

        embed = self._embed_fn()
        p_vecs = np.asarray(embed(premises))
        s_vecs = np.asarray(embed(statements))
        sims = s_vecs @ p_vecs.T  # statements x premises

        # Alignment: only the top-k most similar premises go to NLI,
        # O(n*k) cross-encoder calls instead of O(n^2).
        pairs, owners = [], []

        for i, s in enumerate(statements):
            for j in np.argsort(-sims[i])[: self.TOP_K]:
                pairs.append((premises[j], s))
                owners.append((i, j))

        scores = self._nli_fn().score(pairs)

        verdicts = {}

        for i, s in enumerate(statements):
            best_sim = float(sims[i].max())
            best_j = int(sims[i].argmax())
            contra, entail, contra_j = 0.0, 0.0, best_j

            for (owner, j), (p_c, p_e, _p_n) in zip(owners, scores):
                if owner != i:
                    continue
                if p_c > contra:
                    contra, contra_j = p_c, j
                entail = max(entail, p_e)

            if contra >= self.NLI_CONTRADICTION:
                verdicts[s] = Verdict(CONTRADICTED, premises[contra_j], "nli")
            elif entail >= self.NLI_ENTAILMENT:
                verdicts[s] = Verdict(SUPPORTED, premises[best_j], "nli")
            elif best_sim >= self.SUPPORT_SIMILARITY and contra < 0.5:
                verdicts[s] = Verdict(SUPPORTED, premises[best_j], "similarity")
            else:
                verdicts[s] = Verdict(NOT_ADDRESSED)

        return Verification(props, verdicts)


class NLIScorer:
    """
    Wraps a sentence-transformers NLI cross-encoder and returns
    (P(contradiction), P(entailment), P(neutral)) per pair regardless of
    the model's internal label order.
    """

    def __init__(self, model_name: str | None = None):
        from sentence_transformers import CrossEncoder

        from app.core.config import settings

        self.model = CrossEncoder(model_name or settings.nli_model)
        id2label = {i: l.lower() for i, l in self.model.model.config.id2label.items()}
        label2id = {l: i for i, l in id2label.items()}
        self._order = [label2id["contradiction"], label2id["entailment"], label2id["neutral"]]

    def score(self, pairs: list[tuple[str, str]]) -> list[tuple[float, float, float]]:
        if not pairs:
            return []

        probs = self.model.predict(pairs, apply_softmax=True)
        return [tuple(float(row[k]) for k in self._order) for row in probs]


class FallbackVerifier:
    """
    Primary verifier with automatic fallback (e.g. LLM quota exhausted).
    """

    def __init__(self, primary: Verifier, fallback: Verifier):
        self.primary, self.fallback = primary, fallback
        self.name = primary.name

    def verify(self, question, answer, statements):
        try:
            result = self.primary.verify(question, answer, statements)
            self.name = self.primary.name
            return result
        except Exception as exc:
            print(f"Verifier '{self.primary.name}' failed, falling back: {exc}")
            self.name = self.fallback.name
            return self.fallback.verify(question, answer, statements)


# --------------------------------------------------------------------------
# Symbolic layer
# --------------------------------------------------------------------------

_BIG_O = re.compile(r"O\s*\(((?:[^()]|\([^()]*\))*)\)", re.IGNORECASE)

_COMPLEXITY_WORDS = {
    "constant time": "1",
    "logarithmic": "logn",
    "linear time": "n",
    "linearithmic": "nlogn",
    "quadratic": "n^2",
    "exponential": "2^n",
}


def normalise_complexity(expr: str) -> str:
    e = expr.lower().replace(" ", "").replace("*", "").replace("²", "^2")
    e = re.sub(r"log_?2?\(?([a-z])\)?", r"log\1", e)
    e = e.replace("lgn", "logn")
    return e


def complexities_in(text: str) -> set[str]:
    found = {normalise_complexity(m) for m in _BIG_O.findall(text)}
    lower = text.lower()

    for phrase, value in _COMPLEXITY_WORDS.items():
        if phrase in lower:
            found.add(value)

    return found


def apply_symbolic(verification: Verification, answer: str, spec: dict, must: list[str]) -> None:
    """
    Upgrade NOT_ADDRESSED verdicts using exact evidence. Never downgrades.
    """

    lower = answer.lower()

    keywords = [k.lower() for k in spec.get("keywords", [])]
    hit = next((k for k in keywords if k in lower), None)

    if hit and must and verification.verdicts[must[0]].label == NOT_ADDRESSED:
        verification.verdicts[must[0]] = Verdict(SUPPORTED, hit, "keyword")

    mentioned = complexities_in(answer)

    if not mentioned:
        return

    for statement in must:
        expected = complexities_in(statement)

        if expected and expected & mentioned and verification.verdicts[statement].label == NOT_ADDRESSED:
            verification.verdicts[statement] = Verdict(SUPPORTED, f"O({next(iter(expected & mentioned))})", "complexity")


# --------------------------------------------------------------------------
# Answer class and relation table
# --------------------------------------------------------------------------

_DONT_KNOW = re.compile(r"\b(i\s*don'?t\s*know|not\s*sure|no\s*idea|can'?t\s*remember|pass|skip)\b", re.IGNORECASE)


def is_empty(answer: str) -> bool:
    text = answer.strip()

    if len(text) < 2:
        return True

    return bool(_DONT_KNOW.search(text)) and len(text.split()) < 12


@dataclass
class AnswerAssessment:
    answer_class: str
    coverage: float
    propositions: list[str]
    verdicts: dict[str, dict]
    misconceptions_hit: list[str] = field(default_factory=list)
    false_claim: str | None = None  # supported | contradicted | not_addressed (pushback only)


def assess_answer(
    question: str,
    answer: str,
    spec: dict,
    misconceptions: list[str],
    verifier: Verifier,
    extra_statements: list[str] | None = None,
) -> tuple[AnswerAssessment, Verification | None]:
    """
    Classify one answer against its template's relation spec.
    """

    must = list(spec.get("must_entail", []))
    must_not = list(dict.fromkeys(spec.get("must_not_entail", []) + misconceptions))
    false_claim = spec.get("false_claim")

    if is_empty(answer):
        return AnswerAssessment(A_EMPTY, 0.0, [], {}), None

    statements = list(dict.fromkeys(must + must_not + ([false_claim] if false_claim else []) + (extra_statements or [])))
    verification = verifier.verify(question, answer, statements)
    apply_symbolic(verification, answer, spec, must)

    v = verification.verdicts
    supported_must = [s for s in must if v[s].label == SUPPORTED]
    contradicted_must = [s for s in must if v[s].label == CONTRADICTED]
    wrong_hits = [s for s in must_not if v[s].label == SUPPORTED]

    coverage = len(supported_must) / len(must) if must else 0.0
    min_coverage = spec.get("min_coverage", 0.5)

    if wrong_hits or (contradicted_must and coverage < min_coverage):
        answer_class = WRONG
    elif coverage >= min_coverage:
        answer_class = CORRECT
    elif coverage > 0:
        answer_class = A_PARTIAL
    else:
        # Non-empty but no relevant correct content: the "absent" signature.
        answer_class = A_EMPTY

    assessment = AnswerAssessment(
        answer_class=answer_class,
        coverage=round(coverage, 3),
        propositions=verification.propositions,
        verdicts={s: {"label": d.label, "evidence": d.evidence, "source": d.source} for s, d in v.items()},
        misconceptions_hit=[s for s in wrong_hits if s in misconceptions],
        false_claim=v[false_claim].label if false_claim else None,
    )

    return assessment, verification


BASE_OUTCOME = {
    CORRECT: CONSISTENT_CORRECT,
    A_PARTIAL: PARTIAL,
    WRONG: CONSISTENT_WRONG,
    A_EMPTY: EMPTY,
}

# (base answer class, transformed answer class) -> outcome, for
# paraphrase, constraint and inversion relations.
RELATION_TABLE = {
    (CORRECT, CORRECT): CONSISTENT_CORRECT,
    (CORRECT, A_PARTIAL): PARTIAL,
    (CORRECT, WRONG): INCONSISTENT,    # the memorisation signature
    (CORRECT, A_EMPTY): INCONSISTENT,
    (A_PARTIAL, CORRECT): PARTIAL,
    (A_PARTIAL, A_PARTIAL): PARTIAL,
    (A_PARTIAL, WRONG): INCONSISTENT,
    (A_PARTIAL, A_EMPTY): EMPTY,
    (WRONG, CORRECT): PARTIAL,
    (WRONG, A_PARTIAL): PARTIAL,
    (WRONG, WRONG): CONSISTENT_WRONG,  # the misconception signature
    (WRONG, A_EMPTY): EMPTY,
    (A_EMPTY, CORRECT): PARTIAL,
    (A_EMPTY, A_PARTIAL): PARTIAL,
    (A_EMPTY, WRONG): CONSISTENT_WRONG,
    (A_EMPTY, A_EMPTY): EMPTY,
}

UNCHANGED_SIMILARITY = 0.90


def relation_outcome(
    probe_type: str,
    base_class: str,
    transformed: AnswerAssessment,
    prior_claims_contradicted: int = 0,
    answer_similarity: float | None = None,
) -> tuple[str, list[str]]:
    """
    Decide the outcome of a transformed probe. Returns (outcome, reasons).
    """

    reasons = []
    t_class = transformed.answer_class

    if probe_type == MR_PUSHBACK:
        if transformed.false_claim == SUPPORTED:
            return CAPITULATED, ["accepted the interviewer's false claim"]

        if transformed.false_claim == CONTRADICTED or t_class == CORRECT:
            if base_class == CORRECT:
                return CONSISTENT_CORRECT, ["held a correct position under pushback"]
            return PARTIAL, ["rejected the false claim after a weak initial answer"]

        if t_class == A_EMPTY:
            return EMPTY, ["did not engage with the pushback"]

        return PARTIAL, ["neither accepted nor rejected the false claim"]

    outcome = RELATION_TABLE[(base_class, t_class)]
    reasons.append(f"base answer {base_class}, transformed answer {t_class}")

    if probe_type == MR_PARAPHRASE and prior_claims_contradicted and outcome == CONSISTENT_CORRECT:
        outcome = INCONSISTENT
        reasons.append(f"contradicted {prior_claims_contradicted} of its own earlier claims")

    if (
        probe_type == MR_CONSTRAINT
        and base_class == CORRECT
        and t_class != CORRECT
        and answer_similarity is not None
        and answer_similarity >= UNCHANGED_SIMILARITY
    ):
        outcome = INCONSISTENT
        reasons.append("answer did not adapt to the changed constraint")

    return outcome, reasons
