from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CriterionDef(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    section: str = ""
    title: str
    type: Literal["binary", "scale", "flag"]
    weight: float = Field(ge=0)
    na_allowed: bool = False
    steps: list[int] | None = None
    step_labels: dict[str, str] | None = None
    description: str = ""
    na_condition: str | None = None
    prompt_hint: str = ""

    @model_validator(mode="after")
    def _check(self):
        if self.type == "scale":
            if not self.steps or len(self.steps) < 2 or sorted(set(self.steps)) != sorted(self.steps):
                raise ValueError(f"{self.id}: scale needs >=2 distinct steps")
            if max(self.steps) <= 0:
                raise ValueError(f"{self.id}: top step must be > 0")
            self.steps = sorted(self.steps)
        else:
            self.steps = None
            self.step_labels = None
        if self.type == "flag":
            self.weight = 0
        if self.na_allowed and not (self.na_condition or "").strip():
            raise ValueError(f"{self.id}: na_condition is required when N/A is allowed")
        return self


class ChecklistIn(BaseModel):
    name: str | None = None
    note: str | None = None
    criteria: list[CriterionDef]
    activate: bool = True

    @model_validator(mode="after")
    def _unique(self):
        ids = [c.id for c in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("criterion ids must be unique")
        if not any(c.type != "flag" and c.weight > 0 for c in self.criteria):
            raise ValueError("at least one weighted criterion is required")
        return self


class ChecklistCreate(ChecklistIn):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9\-]{1,63}$")
    name: str


class EvaluateRequest(BaseModel):
    conversation_ids: list[str] | None = None
    group_id: str | None = None
    checklist_id: str = "chat-quality"
    checklist_version: int | None = None  # default: active version
    wait: bool = False  # true -> respond after evaluation finishes

    @model_validator(mode="after")
    def _target(self):
        if not self.conversation_ids and not self.group_id:
            raise ValueError("conversation_ids or group_id is required")
        return self
