from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_user_or_guest
from app.core.db import get_db
from app.core.models import User
from app.modules.interview import service
from app.modules.interview.models import EXPERIENCE_LEVELS, INTERVIEW_TYPES, PROCTORING_EVENT_TYPES
from app.modules.interview.service import InterviewContextError, InterviewDeps, InterviewSessionError, get_interview_deps
from app.modules.mkt.service import MKTDeps, get_mkt_deps


router = APIRouter(prefix="/interview", tags=["Interview"])


class CreateContextRequest(BaseModel):
    target_role: str = Field(min_length=2, max_length=128)
    company: str | None = Field(default=None, max_length=128)
    experience_level: Literal[EXPERIENCE_LEVELS]
    interview_type: Literal[INTERVIEW_TYPES]
    duration_minutes: int = Field(ge=5, le=90)
    num_questions: int | None = Field(default=None, ge=1, le=30)
    resume_id: int | None = None


class StartSessionRequest(BaseModel):
    context_id: str


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=8000)
    # Client-computed MediaPipe blendshape-derived affect proxies for this
    # turn's answer window (see frontend1/src/services/faceDetection.js);
    # None when the camera was unavailable/denied. Never raw video/frames.
    emotion_signal: dict | None = None


class ProctoringEventRequest(BaseModel):
    event_type: Literal[PROCTORING_EVENT_TYPES]


@router.post("/context")
def create_context(
    body: CreateContextRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_or_guest),
):
    try:
        context = service.create_context(db, user, **body.model_dump())
        return service.public_context(context)
    except InterviewContextError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/context/{context_id}")
def get_context(
    context_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_or_guest),
):
    try:
        context = service.get_context(db, user, context_id)
        return service.public_context(context)
    except InterviewContextError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/sessions")
def start_session(
    body: StartSessionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_or_guest),
    deps: InterviewDeps = Depends(get_interview_deps),
):
    try:
        return service.start_session(db, user, body.context_id, deps)
    except (InterviewContextError, InterviewSessionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/sessions/{session_id}/listening")
def mark_listening(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_or_guest),
    deps: InterviewDeps = Depends(get_interview_deps),
):
    try:
        return service.advance_to_listening(db, user, session_id, deps)
    except InterviewSessionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/sessions/{session_id}/answer")
def answer_session(
    session_id: str,
    body: AnswerRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_or_guest),
    deps: InterviewDeps = Depends(get_interview_deps),
    mkt_deps: MKTDeps = Depends(get_mkt_deps),
):
    try:
        return service.submit_turn_answer(db, user, session_id, body.answer, deps, mkt_deps, body.emotion_signal)
    except InterviewSessionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/sessions/{session_id}/proctoring-event")
def report_proctoring_event(
    session_id: str,
    body: ProctoringEventRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_or_guest),
):
    try:
        return service.record_proctoring_event(db, user, session_id, body.event_type)
    except InterviewSessionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/sessions/{session_id}/evidence")
def read_session_evidence(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_or_guest),
):
    try:
        return service.get_session_evidence(db, user, session_id)
    except InterviewSessionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/sessions/{session_id}")
def read_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_or_guest),
    deps: InterviewDeps = Depends(get_interview_deps),
):
    try:
        return service.get_session(db, user, session_id, deps)
    except InterviewSessionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
