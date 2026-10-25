from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.models import User


GUEST_USERNAME = "guest"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiry_minutes),
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _user_from_token(token: str, db: Session) -> User:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    user = db.get(User, int(payload["sub"]))

    if user is None:
        raise HTTPException(status_code=401, detail="User not found.")

    return user


def _guest_user(db: Session) -> User:
    user = db.query(User).filter_by(username=GUEST_USERNAME).first()

    if user is None:
        user = User(username=GUEST_USERNAME, is_guest=True)
        db.add(user)
        db.commit()

    return user


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return None


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _bearer(authorization)

    if token is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    return _user_from_token(token, db)


def get_user_or_guest(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    Logged-in user if a token is sent, otherwise a shared guest user.
    Lets the frontend work before it has a login screen.
    """

    token = _bearer(authorization)

    if token is None:
        return _guest_user(db)

    return _user_from_token(token, db)
