from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_user_or_guest
from app.core.db import get_db
from app.core.models import User
from app.modules.coding import service
from app.modules.coding.service import CodingError

router = APIRouter(prefix="/code", tags=["Coding IDE"])


class RunRequest(BaseModel):
    code: str = Field(max_length=20000)


@router.get("/problems")
def problems(db: Session = Depends(get_db)):
    return service.list_problems(db)


@router.get("/problems/{problem_id}")
def problem(problem_id: str, db: Session = Depends(get_db)):
    try:
        return service.get_problem(db, problem_id)
    except CodingError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/problems/{problem_id}/run")
def run(problem_id: str, body: RunRequest, db: Session = Depends(get_db)):
    try:
        return service.run_samples(db, problem_id, body.code)
    except CodingError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/problems/{problem_id}/submit")
def submit(problem_id: str, body: RunRequest, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.submit(db, user, problem_id, body.code)
    except CodingError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/problems/{problem_id}/submissions")
def submissions(problem_id: str, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    return service.list_submissions(db, user, problem_id)
