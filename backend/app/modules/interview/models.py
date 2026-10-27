from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import utcnow

INTERVIEW_TYPES = ("hr", "technical", "dsa", "core_cs", "system_design", "mixed", "custom")
EXPERIENCE_LEVELS = ("intern", "junior", "mid", "senior")

PROCTORING_EVENT_TYPES = ("tab_hidden", "tab_visible", "face_lost", "face_regained")
PROCTORING_LOG_LIMIT = 200

# Legal state machine for a live interview session. Any state may jump to
# TIME_EXPIRED when the server-side clock runs out; see
# service.TRANSITIONS for the rest of the legal-transition map.
SESSION_STATES = (
    "READY",
    "AI_SPEAKING",
    "LISTENING",
    "PROCESSING",
    "TIME_EXPIRED",
    "GENERATING_REPORT",
    "REPORT",
)


class InterviewContext(Base):
    """
    Everything that should shape one interview, captured once at setup
    time: target_role + resume + interview_type + duration. The
    conversational interview state machine (InterviewSession) reads this
    instead of taking these as loose request parameters.
    """

    __tablename__ = "interview_contexts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id"), nullable=True)

    target_role: Mapped[str] = mapped_column(String(128))
    company: Mapped[str | None] = mapped_column(String(128), nullable=True)
    experience_level: Mapped[str] = mapped_column(String(32))
    interview_type: Mapped[str] = mapped_column(String(32))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    num_questions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="active")  # active | completed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InterviewSession(Base):
    """
    One live, persisted run through the interview state machine. The
    session owns the server-side clock (ends_at) and the pointer to the
    currently pending turn; InterviewTurn rows are the question/answer
    history. Nothing here lives only in memory, so a page refresh just
    re-reads this row.
    """

    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    context_id: Mapped[str] = mapped_column(ForeignKey("interview_contexts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    state: Mapped[str] = mapped_column(String(32), default="READY")
    num_questions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turns_asked: Mapped[int] = mapped_column(Integer, default=0)
    current_turn_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Proctoring signal log (tab-switch / face-presence events reported by
    # the frontend), e.g. [{"type": "tab_hidden", "at": "2026-01-01T00:00:00+00:00"}].
    # Capped at PROCTORING_LOG_LIMIT entries so a flaky client can't bloat the row.
    proctoring_events: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)

    # Working state for MKT-driven turns within this session: beliefs,
    # asked template ids, base-answered concepts, EIG selection context.
    # Mirrors MKTSession.state's shape (see app/modules/mkt/service.py)
    # but is scoped to this interview session rather than a standalone
    # MKT session. None until the first MKT-driven turn is created.
    mkt_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class InterviewTurn(Base):
    __tablename__ = "interview_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)

    question: Mapped[str] = mapped_column(Text)
    state_at_ask: Mapped[str] = mapped_column(String(32))

    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evaluation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Which mechanism produced this turn's question: "llm" (the default,
    # plain LLM-driven interview flow) or "mkt" (MKT's belief-tracking
    # probe selection - see app/modules/interview/service.py's MKT
    # integration). The report (Phase 10) uses this to distinguish turns;
    # it is never surfaced to the candidate mid-interview.
    source: Mapped[str] = mapped_column(String(16), default="llm")
    mkt_concept_id: Mapped[str | None] = mapped_column(ForeignKey("concepts.id"), nullable=True)
    mkt_probe_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mkt_template_id: Mapped[int | None] = mapped_column(ForeignKey("probe_templates.id"), nullable=True)
    mkt_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mkt_assessment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mkt_belief_before: Mapped[list | None] = mapped_column(JSON, nullable=True)
    mkt_belief_after: Mapped[list | None] = mapped_column(JSON, nullable=True)

    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Stamped by advance_to_listening - the moment the candidate was handed the
    # mic, distinct from asked_at (when the question was created, before TTS
    # played it out loud). Used to compute response latency for comm_metrics.
    listening_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Phase 9/9b soft signals, attached silently (never shown mid-interview),
    # same pattern as the mkt_* columns above. comm_metrics comes from
    # app.modules.communication (text + timing, computed server-side).
    # emotion_metrics is whatever app.modules.emotion's client-side MediaPipe
    # pipeline derived from webcam blendshapes for this turn's window (or None
    # if the camera was unavailable/denied).
    comm_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    emotion_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class InterviewCodingRound(Base):
    """
    The coding problem asked in an interview turn (InterviewTurn.source ==
    "coding"): the candidate's latest code and its test results. A separate
    table, not columns on InterviewTurn, so existing databases pick it up
    through create_all without a migration.
    """

    __tablename__ = "interview_coding_rounds"

    turn_id: Mapped[int] = mapped_column(ForeignKey("interview_turns.id"), primary_key=True)
    problem_id: Mapped[str] = mapped_column(ForeignKey("coding_problems.id"))

    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)

    # Set on submit (after all tests ran).
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)  # AC | WA | RE | TLE | UNSAFE
    passed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Per-test detail for the visible tests only.
    results: Mapped[list | None] = mapped_column(JSON, nullable=True)


class InterviewDesignRound(Base):
    """
    The system-design lab question asked in an interview turn
    (InterviewTurn.source == "design"): the candidate's latest design graph
    and, once submitted, the engine's verdict on it. Like
    InterviewCodingRound, a separate table so create_all picks it up.
    """

    __tablename__ = "interview_design_rounds"

    turn_id: Mapped[int] = mapped_column(ForeignKey("interview_turns.id"), primary_key=True)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("design_prompts.id"))

    graph: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    analyze_count: Mapped[int] = mapped_column(Integer, default=0)

    # Set on submit.
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    slo_satisfied: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    resilience_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    findings: Mapped[list | None] = mapped_column(JSON, nullable=True)

