from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_user_or_guest
from app.core.db import get_db
from app.core.models import User
from app.modules.whiteboard import service
from app.modules.whiteboard.service import WhiteboardError


router = APIRouter(prefix="/design", tags=["Executable Whiteboard"])


def _bad_request(exc: WhiteboardError):
    return HTTPException(status_code=400, detail=str(exc))


class StartSessionRequest(BaseModel):
    prompt_id: str


class SaveVersionRequest(BaseModel):
    graph: dict


class AnalyzeRequest(BaseModel):
    requirements: dict | None = None
    scenario: dict | None = None


class SimulateRequest(BaseModel):
    requirements: dict | None = None
    scenario: dict | None = None
    n_requests: int = Field(default=3000, ge=200, le=20000)
    replications: int = Field(default=3, ge=1, le=10)


class RespondRequest(BaseModel):
    text: str = Field(max_length=4000)


@router.get("/catalog")
def catalog():
    return service.get_catalog()


@router.get("/scenario-catalog")
def scenario_catalog():
    return service.scenario_catalog()


@router.get("/subtopics")
def subtopics(db: Session = Depends(get_db)):
    return service.list_subtopics(db)


@router.get("/prompts")
def prompts(subtopic_id: str | None = None, simulatable_only: bool = False, db: Session = Depends(get_db)):
    return service.list_prompts(db, subtopic_id, simulatable_only)


@router.post("/sessions")
def start_session(body: StartSessionRequest, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.start_session(db, user, body.prompt_id)
    except WhiteboardError as exc:
        raise _bad_request(exc)


@router.post("/sessions/{session_id}/versions")
def save_version(session_id: str, body: SaveVersionRequest, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.save_version(db, user, session_id, body.graph)
    except WhiteboardError as exc:
        raise _bad_request(exc)


@router.post("/versions/{version_id}/analyze")
def analyze(version_id: int, body: AnalyzeRequest, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.analyze(db, user, version_id, body.requirements, body.scenario)
    except WhiteboardError as exc:
        raise _bad_request(exc)


@router.post("/versions/{version_id}/simulate")
def simulate(version_id: int, body: SimulateRequest, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.simulate(db, user, version_id, body.requirements, body.scenario, body.n_requests, body.replications)
    except WhiteboardError as exc:
        raise _bad_request(exc)


@router.post("/versions/{version_id}/resilience")
def resilience(version_id: int, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.run_scenario_suite(db, user, version_id)
    except WhiteboardError as exc:
        raise _bad_request(exc)


@router.post("/sessions/{session_id}/interviewer/next")
def interviewer_next(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.next_question(db, user, session_id)
    except WhiteboardError as exc:
        raise _bad_request(exc)


@router.post("/sessions/{session_id}/respond")
def respond(session_id: str, body: RespondRequest, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.respond(db, user, session_id, body.text)
    except WhiteboardError as exc:
        raise _bad_request(exc)


@router.get("/sessions/{session_id}/dialogue")
def dialogue(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.get_dialogue(db, user, session_id)
    except WhiteboardError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/sessions/{session_id}/report")
def report(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.get_report(db, user, session_id)
    except WhiteboardError as exc:
        raise _bad_request(exc)
