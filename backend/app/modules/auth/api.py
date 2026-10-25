from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import (
    GUEST_USERNAME,
    create_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.core.db import get_db
from app.core.models import User


router = APIRouter(prefix="/auth", tags=["Auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


@router.post("/register", response_model=TokenResponse)
def register(body: Credentials, db: Session = Depends(get_db)):
    if body.username.lower() == GUEST_USERNAME:
        raise HTTPException(status_code=400, detail="That username is reserved.")

    if db.query(User).filter_by(username=body.username).first():
        raise HTTPException(status_code=400, detail="Username already taken.")

    user = User(username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()

    return TokenResponse(access_token=create_token(user.id), username=user.username)


@router.post("/login", response_model=TokenResponse)
def login(body: Credentials, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=body.username).first()

    if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    return TokenResponse(access_token=create_token(user.id), username=user.username)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username}
