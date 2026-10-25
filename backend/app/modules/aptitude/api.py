from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_user_or_guest
from app.core.db import get_db
from app.core.models import User
from app.modules.aptitude import service
from app.modules.aptitude.service import AptitudeError

router = APIRouter(prefix="/aptitude", tags=["Aptitude"])


class SubmitRequest(BaseModel):
    answers: dict[str, int]


@router.post("/attempts")
def start_attempt(db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.start_attempt(db, user)
    except AptitudeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/attempts")
def list_attempts(db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    return service.list_attempts(db, user)


@router.get("/attempts/{attempt_id}")
def get_attempt(attempt_id: int, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.get_attempt(db, user, attempt_id)
    except AptitudeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/attempts/{attempt_id}/submit")
def submit_attempt(attempt_id: int, body: SubmitRequest, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.submit_attempt(db, user, attempt_id, body.answers)
    except AptitudeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
