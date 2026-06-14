from __future__ import annotations

from dodo_bridge.audit import AuditStore
from dodo_bridge.models import LearningRecommendation
from dodo_bridge.policy import PolicyConfig


class LearningEngine:
    def __init__(self, audit: AuditStore, policy: PolicyConfig):
        self.audit = audit
        self.policy = policy

    def recommendations(self) -> list[LearningRecommendation]:
        thresholds = self.policy.recommendation_thresholds
        recommendations: list[LearningRecommendation] = []

        for row in self.audit.fetch_denied_counts():
            if row["count"] < thresholds.denied_tool_count:
                continue
            reason = row["reason"]
            title = "Review frequently denied tool"
            detail = (
                f"Tool '{row['tool_name']}' was denied {row['count']} times "
                f"with reason '{reason}'. Review whether it should stay blocked, "
                "be enabled as read-only, or be represented by a safer aggregate tool."
            )
            recommendations.append(
                LearningRecommendation(
                    kind="policy_review",
                    title=title,
                    detail=detail,
                    tool_name=row["tool_name"],
                    confidence=min(0.95, 0.45 + row["count"] / 20),
                )
            )

        for row in self.audit.fetch_negative_feedback_counts():
            if row["count"] < thresholds.negative_feedback_count:
                continue
            recommendations.append(
                LearningRecommendation(
                    kind="quality_review",
                    title="Review tool with negative feedback",
                    detail=(
                        f"Tool '{row['tool_name']}' has {row['count']} negative feedback "
                        "events. Consider tightening parameters, adding response filters, "
                        "or requiring approval."
                    ),
                    tool_name=row["tool_name"],
                    confidence=min(0.9, 0.5 + row["count"] / 10),
                )
            )

        for row in self.audit.fetch_large_response_counts(thresholds.large_response_chars):
            recommendations.append(
                LearningRecommendation(
                    kind="response_filter",
                    title="Add response filtering or aggregation",
                    detail=(
                        f"Tool '{row['tool_name']}' returned responses up to "
                        f"{row['max_response_chars']} characters. Add field filters, "
                        "pagination defaults, or aggregate endpoints before exposing it broadly."
                    ),
                    tool_name=row["tool_name"],
                    confidence=0.8,
                )
            )

        return recommendations

