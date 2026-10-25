from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import utcnow


class SheetTopic(Base):
    """
    A topic within a sheet (e.g. 'Arrays' in the DSA sheet, or the 18
    system-design subtopics are tracked separately in the whiteboard
    module's DesignPrompt.subtopic_id — this table is for DSA/Core CS).
    """

    __tablename__ = "sheet_topics"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sheet: Mapped[str] = mapped_column(String(32), index=True)  # "dsa" | "core_cs"
    name: Mapped[str] = mapped_column(String(128))
    order: Mapped[int] = mapped_column(Integer, default=0)


class SheetProblem(Base):
    __tablename__ = "sheet_problems"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey("sheet_topics.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    difficulty: Mapped[str] = mapped_column(String(16))
    pattern: Mapped[str] = mapped_column(String(64), default="")
    leetcode_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    concept_id: Mapped[str | None] = mapped_column(String(128), nullable=True)  # links to MKT concepts
    order: Mapped[int] = mapped_column(Integer, default=0)


class UserProblemStatus(Base):
    __tablename__ = "user_problem_status"
    __table_args__ = (UniqueConstraint("user_id", "problem_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    problem_id: Mapped[str] = mapped_column(ForeignKey("sheet_problems.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="unsolved")  # unsolved | solved | revisit
    solved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revisit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CoreCSNote(Base):
    __tablename__ = "core_cs_notes"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey("sheet_topics.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body_markdown: Mapped[str] = mapped_column(Text)
    concept_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    order: Mapped[int] = mapped_column(Integer, default=0)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    tier: Mapped[str] = mapped_column(String(16), default="standard")  # top | standard
    rounds: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["DSA", "System Design", "Behavioral"]


class CompanyWeight(Base):
    """
    Relative emphasis a company places on a topic/domain, used by the
    readiness formula. Weights are on an arbitrary relative scale (not a
    probability), only ratios across concepts for the same company matter.
    """

    __tablename__ = "company_weights"
    __table_args__ = (UniqueConstraint("company_id", "ref_type", "ref_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    ref_type: Mapped[str] = mapped_column(String(16))  # "topic" | "concept" | "domain"
    ref_id: Mapped[str] = mapped_column(String(128))
    weight: Mapped[float] = mapped_column(Float, default=1.0)
