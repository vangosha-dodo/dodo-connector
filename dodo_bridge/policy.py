from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from dodo_bridge.models import PolicyDecision, RiskLevel, ToolInvocationRequest, ToolSpec


class RecommendationThresholds(BaseModel):
    denied_tool_count: int = 3
    negative_feedback_count: int = 2
    large_response_chars: int = 25000


class PolicyConfig(BaseModel):
    mode: Literal["enforce", "observe"] = "enforce"
    default_decision: Literal["deny", "allow"] = "deny"
    allowed_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[str] = Field(default_factory=list)
    require_approval_for_risk: list[RiskLevel] = Field(
        default_factory=lambda: [RiskLevel.WRITE, RiskLevel.ADMIN]
    )
    max_request_params_chars: int = 12000
    max_response_chars: int = 30000
    recommendation_thresholds: RecommendationThresholds = Field(
        default_factory=RecommendationThresholds
    )


class PolicyEngine:
    def __init__(self, config: PolicyConfig):
        self.config = config

    @classmethod
    def from_yaml(cls, path: Path) -> "PolicyEngine":
        if not path.exists():
            raise FileNotFoundError(f"Policy config not found: {path}")
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(PolicyConfig.model_validate(payload))

    def evaluate(
        self,
        tool: ToolSpec | None,
        request: ToolInvocationRequest,
        params_chars: int,
    ) -> PolicyDecision:
        if tool is None:
            return PolicyDecision(outcome="deny", reason="unknown_tool")

        if params_chars > self.config.max_request_params_chars:
            return PolicyDecision(outcome="deny", reason="request_params_too_large")

        if tool.name in self.config.blocked_tools:
            return PolicyDecision(outcome="deny", reason="tool_blocked")

        if not tool.enabled:
            return PolicyDecision(outcome="deny", reason="tool_disabled")

        constraint_reason = self._validate_constraints(tool, request.parameters)
        if constraint_reason:
            return PolicyDecision(outcome="deny", reason=constraint_reason)

        explicitly_allowed = "*" in self.config.allowed_tools or tool.name in self.config.allowed_tools
        if not explicitly_allowed:
            if self.config.mode == "observe" and tool.risk_level == RiskLevel.READ:
                return PolicyDecision(outcome="allow", reason="observe_mode_read_allow")
            if self.config.default_decision == "allow" and tool.risk_level == RiskLevel.READ:
                return PolicyDecision(outcome="allow", reason="default_allow_read")
            return PolicyDecision(outcome="deny", reason="tool_not_allowed")

        approval_needed = tool.requires_approval or tool.risk_level in self.config.require_approval_for_risk
        if approval_needed and not request.approval_token:
            return PolicyDecision(
                outcome="approval_required",
                reason="approval_token_required",
                requires_approval=True,
            )

        if approval_needed:
            return PolicyDecision(outcome="allow", reason="approval_token_present")

        return PolicyDecision(outcome="allow", reason="tool_allowed")

    def _validate_constraints(self, tool: ToolSpec, parameters: dict[str, Any]) -> str | None:
        for required in tool.required_params:
            if required not in parameters or parameters[required] in (None, ""):
                return f"missing_required_param:{required}"

        if tool.allowed_dashboard_ids:
            dashboard_id = parameters.get("dashboard_id")
            if dashboard_id not in tool.allowed_dashboard_ids and str(dashboard_id) not in {
                str(item) for item in tool.allowed_dashboard_ids
            }:
                return "dashboard_not_allowed"

        if tool.allowed_chart_ids:
            chart_id = parameters.get("chart_id", parameters.get("slice_id"))
            if chart_id not in tool.allowed_chart_ids and str(chart_id) not in {
                str(item) for item in tool.allowed_chart_ids
            }:
                return "chart_not_allowed"

        if tool.allowed_metrics:
            metric = parameters.get("metric")
            if metric not in tool.allowed_metrics:
                return "metric_not_allowed"

        return None
