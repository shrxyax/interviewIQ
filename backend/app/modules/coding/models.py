from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import utcnow


class CodingProblem(Base):
    __tablename__ = "coding_problems"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    difficulty: Mapped[str] = mapped_column(String(16))
    statement: Mapped[str] = mapped_column(Text)
    signature: Mapped[str] = mapped_column(String(200))
    starter_code: Mapped[str] = mapped_column(Text)
    sample_tests: Mapped[list] = mapped_column(JSON)
    hidden_tests: Mapped[list] = mapped_column(JSON)
    order: Mapped[int] = mapped_column(Integer, default=0)


class Submission(Base):
    __tablename__ = "coding_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    problem_id: Mapped[str] = mapped_column(ForeignKey("coding_problems.id"), index=True)
    code: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(16))  # AC | WA | RE | TLE | UNSAFE
    passed: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    runtime_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
