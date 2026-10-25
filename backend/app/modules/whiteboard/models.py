from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import utcnow


class DesignPrompt(Base):
    """
    A system-design prompt card. `simulatable=False` prompts are
    lightweight (title/scenario/tags only, for browsing/breadth);
    `simulatable=True` prompts carry a starter graph + requirements and
    can be opened in the whiteboard for full analysis.
    """

    __tablename__ = "design_prompts"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    subtopic_id: Mapped[str] = mapped_column(String(64), index=True)
    subtopic_name: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(200))
    scenario: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(16))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    simulatable: Mapped[bool] = mapped_column(Boolean, default=False)
    requirements: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    starter_graph: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DesignSession(Base):
    __tablename__ = "design_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("design_prompts.id"))
    status: Mapped[str] = mapped_column(String(16), default="active")
    requirements: Mapped[dict] = mapped_column(JSON)
    client_id: Mapped[str] = mapped_column(String(64), default="client")
    resolved_findings: Mapped[list] = mapped_column(JSON, default=list)  # finding "keys" the candidate has addressed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DesignVersion(Base):
    __tablename__ = "design_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("design_sessions.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    graph: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("design_versions.id"), index=True)
    mode: Mapped[str] = mapped_column(String(16))  # analytic | simulation
    # none_as_null=True: a Python None must store SQL NULL (queried with
    # `.is_(None)`), not the JSON literal "null" (SQLAlchemy's default for
    # a nullable JSON column, which `.is_(None)` would not match).
    scenario: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    result: Mapped[dict] = mapped_column(JSON)
    findings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DesignDialogue(Base):
    __tablename__ = "design_dialogue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("design_sessions.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))  # interviewer | candidate
    text: Mapped[str] = mapped_column(Text)
    finding_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
