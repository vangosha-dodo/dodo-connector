from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ConnectorName(StrEnum):
    DODO = "dodo"
    SUPERSET = "superset"
    INTERNAL = "internal"


class RiskLevel(StrEnum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    connector: ConnectorName
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    path: str = ""
    risk_level: RiskLevel = RiskLevel.READ
    enabled: bool = False
    requires_approval: bool = False
    allowed_query_params: list[str] = Field(default_factory=list)
    max_response_chars: int | None = None
    required_params: list[str] = Field(default_factory=list)
    allowed_dashboard_ids: list[str | int] = Field(default_factory=list)
    allowed_chart_ids: list[str | int] = Field(default_factory=list)
    allowed_metrics: list[str] = Field(default_factory=list)
    status: str = "candidate"
    tags: list[str] = Field(default_factory=list)
    source_evidence: list[str] = Field(default_factory=list)


class ToolInvocationRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    intent: str | None = None
    actor: str | None = None
    dry_run: bool = False
    approval_token: str | None = None


class ToolInvocationResult(BaseModel):
    audit_id: int
    tool_name: str
    decision: str
    result: Any | None = None
    error: str | None = None


class FeedbackRequest(BaseModel):
    audit_id: int
    score: int = Field(ge=-1, le=1)
    comment: str | None = None
    labels: list[str] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    outcome: Literal["allow", "deny", "approval_required"]
    reason: str
    requires_approval: bool = False


class LearningRecommendation(BaseModel):
    kind: str
    title: str
    detail: str
    tool_name: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
