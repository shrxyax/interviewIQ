import re

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_user_or_guest
from app.core.db import get_db
from app.core.models import User
from app.services.embeddings import generate_embeddings
from app.services.retriever import latest_resume, retrieve
from app.services.prompt import build_prompt
from app.core.llm_gateway import generate_text

router = APIRouter()


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    question: str
    # Recent messages, oldest first, so follow-up questions make sense.
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


# How much of the conversation goes into the prompt.
_HISTORY_TURNS = 8


# Resume text is bullets whose lines the PDF wrapped: rejoin wrapped lines,
# then split into bullets and sentences.
_BULLET = "•▪●◦"
_CONNECTORS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the", "to", "using", "via", "with"}
_ITEM_SPLIT = re.compile(rf"\s*\n\s*|(?<=[.!?])\s+(?=[A-Z])|\s*[{_BULLET}]\s*")
_HYPHENATED = re.compile(r"(?<=[a-z])- (?=[a-z])")
_CONTACT = re.compile(r"@|https?://|linkedin\.com|github\.com|\+?\d[\d ]{8,}")
# A date range on its own line ("Aug 2023 - Present"), which belongs to the
# entry above it.
_DATE_LINE = re.compile(
    r"^((jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+)?\d{4}\s*[-–—]\s*"
    r"(((jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+)?\d{4}|present|current|now)$",
    re.I,
)
# A section heading: a short all-caps line such as "TECHNICAL SKILLS".
_HEADING = re.compile(r"^[A-Z][A-Z&/ ]{2,40}$")
# Question words that point at a resume section (matched against the
# section heading); lines from that section get a ranking boost, since the
# small embedding model alone doesn't reliably tie "study" to "Education".
_SECTION_HINTS = {
    "educat": r"stud|college|universit|degree|school|educat|cgpa|gpa|graduat|b\.?tech|marks|percentage",
    "experien": r"intern|job|work(ed)?\b|experien|compan|employ|role",
    "project": r"project|built|build|made|develop|creat",
    "skill": r"skill|language|technolog|stack|tools?\b|framework|know",
    "achieve": r"achiev|award|hackathon|won|accomplish|leader|club|extracurricular",
    "certif": r"certif|course|training",
}
_SECTION_BOOST = 0.15
# Lines scoring this far below the best match are left out.
_RELEVANCE_MARGIN = 0.08


def _unwrap(text: str) -> str:
    """
    Rejoins lines the PDF wrapped mid-sentence: a line continues the previous
    one if it starts in lowercase, or the previous line ends mid-phrase (a
    comma, hyphen or connecting word like "and").
    """

    out = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        prev = out[-1] if out else ""
        last_word = prev.rsplit(" ", 1)[-1].lower()
        if prev and _DATE_LINE.match(line):
            out[-1] = f"{prev} ({line})"
            continue

        continues = prev and line[0] not in _BULLET and (
            line[0].islower() or line[0].isdigit() or line[0] == "("
            or prev[-1] in ",-–" or last_word in _CONNECTORS
        )

        if continues:
            out[-1] = f"{prev} {line}"
        else:
            out.append(line)

    return "\n".join(out)


def _resume_excerpts(question: str, chunks: list[dict], limit: int = 5) -> list[tuple[str | None, str]]:
    """
    The resume lines most similar to the question, best first, each with its
    section heading (e.g. "Education"). Used when the LLM can't be reached,
    so chat still answers from the resume. Lines are matched together with
    their heading, which is what places "where did I study?" in Education.
    """

    items: list[tuple[str | None, str]] = []
    section = None

    for chunk in sorted(chunks, key=lambda c: (c.get("page", 0), c.get("chunk_id", 0))):
        for n, line in enumerate(_unwrap(chunk["text"]).split("\n")):
            if _HEADING.match(line):
                section = line.title()
                continue

            for item in _ITEM_SPLIT.split(line):
                item = _HYPHENATED.sub("", " ".join(item.split()))
                # A chunk can start mid-sentence; skip that cut-off piece.
                if len(item.split()) < 3 or (n == 0 and item[:1].islower()) or _CONTACT.search(item):
                    continue

                # Chunks overlap, so the same line can appear cut off at the
                # end of one chunk and whole in the next: keep the whole one.
                overlap = next((i for i, (_, seen) in enumerate(items) if item in seen or seen in item), None)
                if overlap is None:
                    items.append((section, item))
                elif len(item) > len(items[overlap][1]):
                    items[overlap] = (section, item)

    if not items:
        return []

    vecs = np.asarray(
        generate_embeddings(
            [
                f"Represent this sentence for searching relevant passages: {question}",
                *(f"{sec}: {item}" if sec else item for sec, item in items),
            ]
        )
    )
    scores = vecs[1:] @ vecs[0]

    wanted = [key for key, hint in _SECTION_HINTS.items() if re.search(hint, question, re.I)]
    for i, (sec, _) in enumerate(items):
        if sec and any(key in sec.lower() for key in wanted):
            scores[i] += _SECTION_BOOST

    best = float(scores.max())

    ranked = sorted(zip(scores, range(len(items))), key=lambda pair: -pair[0])
    return [items[i] for score, i in ranked[:limit] if score >= best - _RELEVANCE_MARGIN]


def _fallback_answer(question: str, chunks: list[dict]) -> str:
    excerpts = _resume_excerpts(question, chunks)

    if not excerpts:
        return (
            "The AI model is unavailable right now (its daily free limit has been reached), and I couldn't find "
            "anything in your resume related to that question. Try again later or rephrase it."
        )

    bullets = "\n".join(f"- **{sec}:** {line}" if sec else f"- {line}" for sec, line in excerpts)
    return (
        "The AI model is unavailable right now (its daily free limit has been reached), so I can't write a full "
        f"answer. These are the parts of your resume most relevant to your question:\n\n{bullets}"
    )


@router.post("/chat")
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_or_guest),
):
    resume = latest_resume(db, user.id)

    if resume is None:
        raise HTTPException(status_code=409, detail="No resume found. Upload your resume first.")

    try:
        chunks = retrieve(request.question, resume_id=resume.id, filename=resume.filename)
    except Exception as exc:
        print(f"Resume retrieval failed: {exc}")
        raise HTTPException(status_code=503, detail="Couldn't search your resume right now. Please try again.")

    sources = [
        {
            "filename": chunk["filename"],
            "page": chunk["page"],
            "score": round(chunk["score"], 3),
        }
        for chunk in chunks
    ]

    history = [turn.model_dump() for turn in request.history[-_HISTORY_TURNS:]]
    prompt = build_prompt(request.question, chunks, history)

    try:
        answer = generate_text(prompt, task="chat")
        fallback = False
    except Exception as exc:
        print(f"Chat generation failed, answering from resume excerpts: {str(exc)[:200]}")
        # Rank lines from the whole resume, not just the top chunks.
        whole_resume = retrieve(request.question, k=50, resume_id=resume.id, filename=resume.filename, min_score=0)
        answer = _fallback_answer(request.question, whole_resume or chunks)
        fallback = True

    return {
        "answer": answer,
        "sources": sources,
        "fallback": fallback,
    }
