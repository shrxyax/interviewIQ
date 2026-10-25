from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_user_or_guest
from app.core.db import get_db
from app.core.models import User
from app.modules.mkt import service
from app.modules.mkt.service import MKTDeps, MKTError, get_mkt_deps


router = APIRouter(tags=["Metamorphic Knowledge Testing"])


class StartSessionRequest(BaseModel):
    domain: str = "dsa"
    concept_ids: list[str] | None = None
    budget: int = Field(default=10, ge=1, le=40)


class AnswerRequest(BaseModel):
    turn_id: int
    answer: str = Field(max_length=5000)
    latency_ms: int | None = Field(default=None, ge=0)


def _bad_request(exc: MKTError):
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/concepts/graph")
def get_concept_graph(domain: str = "dsa", db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    return service.concept_graph(db, user, domain)


@router.post("/mkt/sessions")
def start_session(body: StartSessionRequest, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.start_session(db, user, body.domain, body.concept_ids, body.budget)
    except MKTError as exc:
        raise _bad_request(exc)


@router.post("/mkt/sessions/{session_id}/answer")
def answer(
    session_id: str,
    body: AnswerRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_or_guest),
    deps: MKTDeps = Depends(get_mkt_deps),
):
    try:
        return service.submit_answer(db, user, session_id, body.turn_id, body.answer, body.latency_ms, deps)
    except MKTError as exc:
        raise _bad_request(exc)


@router.get("/mkt/sessions/{session_id}/trace")
def trace(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.get_trace(db, user, session_id)
    except MKTError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/mkt/sessions/{session_id}/report")
def report(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.get_report(db, user, session_id)
    except MKTError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/profile/beliefs")
def profile_beliefs(domain: str = "dsa", db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    graph = service.concept_graph(db, user, domain)
    return {"domain": domain, "concepts": [n for n in graph["nodes"] if n["observations"] > 0]}
