"""Storage model.

Criteria are dynamic, so a checklist is stored as immutable *versions* holding the criteria list as JSON.
Editing a checklist creates a new version; every evaluation pins the version it was produced with,
so historical results stay reproducible after the organizers swap a criterion.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class Checklist(Base):
    __tablename__ = "checklists"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    active_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    versions: Mapped[list["ChecklistVersion"]] = relationship(back_populates="checklist", order_by="ChecklistVersion.version")


class ChecklistVersion(Base):
    __tablename__ = "checklist_versions"
    __table_args__ = (UniqueConstraint("checklist_id", "version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checklist_id: Mapped[str] = mapped_column(ForeignKey("checklists.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    criteria: Mapped[list] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    checklist: Mapped[Checklist] = relationship(back_populates="versions")


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # organizer conversation_id, kept verbatim
    dataset_group_id: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(8), index=True)
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript: Mapped[list] = mapped_column(JSON)  # original turns + 1-based "turn"
    operator_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    started_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    checklist_version_id: Mapped[int] = mapped_column(ForeignKey("checklist_versions.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)  # queued|running|ok|error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluator: Mapped[str | None] = mapped_column(String(32), nullable=True)  # stub|nlp
    model_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    criteria: Mapped[list | None] = mapped_column(JSON, nullable=True)  # NLP output, as returned (original)
    breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # compute_score() of original values
    original_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # after appeal decisions
    final_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    critical_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Appeal(Base):
    __tablename__ = "appeals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), index=True)
    criterion_id: Mapped[str] = mapped_column(String(64))
    author_role: Mapped[str] = mapped_column(String(64), default="operator")
    comment: Mapped[str] = mapped_column(Text)
    original_value: Mapped[object] = mapped_column(JSON, nullable=True)
    suggested_value: Mapped[object] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open|accepted|rejected
    new_value: Mapped[object] = mapped_column(JSON, nullable=True)
    reviewer_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    improvement: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppealEvent(Base):
    """Stored appeal history: one row per action (filed / accepted / rejected). Append-only log that keeps a
    snapshot of what happened (titles, values, scores), so it reads correctly even after data changes.
    No FK on purpose: clearing the log never touches appeals, and the log never blocks deleting them."""
    __tablename__ = "appeal_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    appeal_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(16))  # created | accepted | rejected
    role: Mapped[str] = mapped_column(String(64))
    conversation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    criterion_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    criterion_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    old_value: Mapped[object] = mapped_column(JSON, nullable=True)
    new_value: Mapped[object] = mapped_column(JSON, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class Meta(Base):
    """Small key/value store for app state (e.g. whether first-start seeding already happened)."""
    __tablename__ = "meta"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
