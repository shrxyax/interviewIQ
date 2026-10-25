from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_user_or_guest
from app.core.db import get_db
from app.core.models import User
from app.modules.content import service
from app.modules.content.service import ContentError


router = APIRouter(tags=["Content"])


class StatusRequest(BaseModel):
    status: str = Field(pattern="^(unsolved|solved|revisit)$")


@router.get("/sheets/dsa")
def dsa_sheet(db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    return service.get_dsa_sheet(db, user)


@router.post("/sheets/dsa/problems/{problem_id}/status")
def set_status(problem_id: str, body: StatusRequest, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.set_problem_status(db, user, problem_id, body.status)
    except ContentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/sheets/core-cs")
def core_cs(db: Session = Depends(get_db)):
    return service.get_core_cs(db)


@router.get("/companies")
def companies(db: Session = Depends(get_db)):
    return service.list_companies(db)


@router.get("/companies/{company_id}/readiness")
def readiness(company_id: str, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.company_readiness(db, user, company_id)
    except ContentError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/companies/{company_id}/plan")
def plan(company_id: str, db: Session = Depends(get_db), user: User = Depends(get_user_or_guest)):
    try:
        return service.recommended_plan(db, user, company_id)
    except ContentError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
