from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import utcnow


class Concept(Base):
    __tablename__ = "concepts"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # e.g. dsa.graph.dijkstra
    domain: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    key_facts: Mapped[list] = mapped_column(JSON, default=list)
    misconceptions: Mapped[list] = mapped_column(JSON, default=list)


class ConceptEdge(Base):
    """
    Directed prerequisite edge: src must be understood before dst.
    """

    __tablename__ = "concept_edges"
    __table_args__ = (UniqueConstraint("src", "dst", "kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src: Mapped[str] = mapped_column(ForeignKey("concepts.id"), index=True)
    dst: Mapped[str] = mapped_column(ForeignKey("concepts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="prereq")


class ProbeTemplate(Base):
    __tablename__ = "probe_templates"
    __table_args__ = (UniqueConstraint("seed_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    concept_id: Mapped[str] = mapped_column(ForeignKey("concepts.id"), index=True)
    probe_type: Mapped[str] = mapped_column(String(32))
    question: Mapped[str] = mapped_column(Text)
    relation_spec: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(16), default="authored")  # authored | generated
    validated: Mapped[bool] = mapped_column(default=True)
    seed_key: Mapped[str | None] = mapped_column(String(192), nullable=True)


class MKTSession(Base):
    __tablename__ = "mkt_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    domain: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | completed
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    # Working state: beliefs, asked templates, pending turn. Replaced (not
    # mutated) on every update so SQLAlchemy detects the change.
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MKTTurn(Base):
    __tablename__ = "mkt_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("mkt_sessions.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    concept_id: Mapped[str] = mapped_column(ForeignKey("concepts.id"))
    probe_type: Mapped[str] = mapped_column(String(32))
    template_id: Mapped[int] = mapped_column(ForeignKey("probe_templates.id"))
    question: Mapped[str] = mapped_column(Text)
    eig: Mapped[float] = mapped_column(Float)
    belief_before: Mapped[list] = mapped_column(JSON)

    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verifier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    assessment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    belief_after: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConceptBelief(Base):
    """
    The candidate's persistent belief per concept, carried across sessions.
    """

    __tablename__ = "concept_beliefs"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    concept_id: Mapped[str] = mapped_column(ForeignKey("concepts.id"), primary_key=True)
    probs: Mapped[list] = mapped_column(JSON)  # [absent, memorised, misconceived, robust]
    n_obs: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
