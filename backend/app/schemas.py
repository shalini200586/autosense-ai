from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Status = Literal["available", "sold"]


class VehicleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_inr: int | None = Field(default=None, gt=0, le=100_000_000)
    status: Status | None = None
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _non_empty(self) -> "VehicleUpdate":
        if self.price_inr is None and self.status is None:
            raise ValueError("Provide price_inr and/or status")
        return self


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=600)
    last_vehicle_ids: list[str] = Field(default_factory=list, max_length=10)
    last_criteria: dict[str, Any] | None = None  # previous turn's filters, for "what about X?" follow-ups


class ChatResponse(BaseModel):
    reply: str
    language: Literal["en", "hi", "hinglish"]
    intent: str
    criteria: dict[str, Any]
    vehicles: list[dict[str, Any]]
    alternatives: list[dict[str, Any]] = []
    source: Literal["llm", "fallback"]
    fallback_reason: str | None = None
    checked_at: str
    test_drive_request_id: int | None = None


class SynthesizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1000)
    language: Literal["en", "hi", "hinglish"] = "en"
