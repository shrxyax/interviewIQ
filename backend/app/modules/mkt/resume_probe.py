"""
Resume-grounded probe generation: instead of only asking a concept's
seeded BASE/MR_PARAPHRASE question, generate one grounded in something
specific from the candidate's own resume (a named project, technology,
or claimed skill) via the LLM gateway.

Only used for BASE and MR_PARAPHRASE. Correctness-critical relations
(MR_CONSTRAINT, MR_INVERSION, MR_PUSHBACK, MR_TRANSFER) keep using
static seeded templates, because an ungrounded or malformed LLM-generated
relation_spec would corrupt the belief update for those probes - getting
"does the candidate hold a specific false claim" or "does the answer
change as the constraint predicts" right requires an authored, verified
relation, not a one-off LLM guess.

A generated probe is validated before use:
- it must have at least one must_entail statement,
- its grounding_reference must be a real substring of the resume text
  (so the question can't invent resume facts), and
- the question/claims must topically overlap the target concept (so
  the probe still measures the intended concept, not something else).

Invalid or failed generations return None; the caller falls back to a
seeded template.
"""

import re

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.modules.mkt.models import Concept, ProbeTemplate
from app.modules.mkt.states import BASE, MR_PARAPHRASE


RESUME_GROUNDABLE_PROBE_TYPES = {BASE, MR_PARAPHRASE}

_STOPWORDS = {
    "the", "a", "an", "is", "are", "of", "to", "in", "on", "for", "and", "or",
    "with", "its", "this", "that", "it", "be", "as", "at", "by", "from",
}


class GeneratedProbe(BaseModel):
    question: str = Field(min_length=10, max_length=500)
    must_entail: list[str] = Field(min_length=1, max_length=4)
    must_not_entail: list[str] = Field(default_factory=list, max_length=4)
    grounding_reference: str = Field(min_length=3, max_length=300)


_PROMPT = """You are writing one interview probe question for a technical interview.

Target concept: {concept_name}
Concept key facts (ground truth, for your reference only - do not quote them verbatim):
{key_facts}

CANDIDATE'S RESUME CONTEXT:
{resume_text}

Write ONE {probe_label} question that:
- tests the candidate's understanding of "{concept_name}",
- is grounded in a SPECIFIC project, technology, or claim from the resume context
  above (name it explicitly in the question), and
- would be answered correctly only by someone who actually understands the concept,
  not just someone repeating a memorised definition.

Also provide:
- must_entail: 1-3 short factual statements a correct answer must support (phrased
  as plain factual claims about the concept, independent of the resume).
- must_not_entail: short factual statements a correct answer must NOT support
  (common misconceptions), or an empty list.
- grounding_reference: the exact short quote from the resume context you grounded
  the question in (copy it verbatim from the text above).

Do not invent resume facts. If nothing in the resume context is relevant to this
concept, make grounding_reference an empty string and keep the question generic.
"""

_PROBE_LABEL = {
    BASE: "direct, open-ended interview",
    MR_PARAPHRASE: "differently-worded but equivalent interview",
}


def _keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z0-9_+#-]{2,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _topically_relevant(concept: Concept, question: str, must_entail: list[str]) -> bool:
    concept_words = _keywords(concept.name) | {w for fact in concept.key_facts for w in _keywords(fact)}
    answer_words = _keywords(question) | {w for s in must_entail for w in _keywords(s)}
    return bool(concept_words & answer_words)


def _validate(concept: Concept, resume_text: str, generated: GeneratedProbe) -> bool:
    if not generated.must_entail or not generated.question.strip():
        return False

    if generated.grounding_reference.strip() and generated.grounding_reference.strip().lower() not in resume_text.lower():
        return False

    return _topically_relevant(concept, generated.question, generated.must_entail)


def generate_resume_grounded_probe(concept: Concept, probe_type: str, resume_text: str) -> GeneratedProbe | None:
    """
    Calls the LLM gateway to produce one resume-grounded probe for
    `concept`. Returns None (never raises) if generation fails validation
    or the LLM call errors - callers fall back to a seeded template.
    """

    if probe_type not in RESUME_GROUNDABLE_PROBE_TYPES or not resume_text.strip():
        return None

    from app.core.llm_gateway import generate_structured

    prompt = _PROMPT.format(
        concept_name=concept.name,
        key_facts="\n".join(f"- {f}" for f in concept.key_facts) or "(none provided)",
        resume_text=resume_text[:4000],
        probe_label=_PROBE_LABEL[probe_type],
    )

    try:
        generated = generate_structured(prompt, GeneratedProbe, task="mkt_resume_probe")
    except Exception as exc:
        print(f"Resume-grounded probe generation failed: {exc}")
        return None

    if not _validate(concept, resume_text, generated):
        return None

    return generated


def persist_generated_probe(db: Session, concept: Concept, probe_type: str, generated: GeneratedProbe) -> ProbeTemplate:
    """
    Stores a validated generated probe as a ProbeTemplate row (source =
    "generated") so it can be referenced the same way a seeded template
    is - by id, from an InterviewTurn.
    """

    template = ProbeTemplate(
        concept_id=concept.id,
        probe_type=probe_type,
        question=generated.question.strip(),
        relation_spec={
            "must_entail": generated.must_entail,
            "must_not_entail": generated.must_not_entail,
            "min_coverage": 0.5,
            "grounding_reference": generated.grounding_reference,
        },
        source="generated",
        validated=True,
        seed_key=None,
    )

    db.add(template)
    db.flush()
    return template
