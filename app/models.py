"""Request models. Unknown fields are ignored, per the brief."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ReviewOptions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str = "mock"
    maxFindings: int = Field(default=100, ge=1)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    diff: str | None = None
    options: ReviewOptions = Field(default_factory=ReviewOptions)
