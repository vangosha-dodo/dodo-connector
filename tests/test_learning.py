from dodo_bridge.audit import AuditStore
from dodo_bridge.learning import LearningEngine
from dodo_bridge.policy import PolicyConfig, RecommendationThresholds


def test_learning_recommends_policy_review_for_repeated_denials(tmp_path) -> None:
    audit = AuditStore(tmp_path / "audit.sqlite3")
    for _ in range(3):
        audit.record_event(
            actor="tester",
            intent="need sales",
            tool_name="dodo_sales",
            connector="dodo",
            decision="deny",
            reason="tool_disabled",
            outcome="blocked",
            params={"from": "2026-06-01"},
        )
    policy = PolicyConfig(
        recommendation_thresholds=RecommendationThresholds(denied_tool_count=3)
    )

    recommendations = LearningEngine(audit, policy).recommendations()

    assert len(recommendations) == 1
    assert recommendations[0].kind == "policy_review"
    assert recommendations[0].tool_name == "dodo_sales"


def test_learning_recommends_response_filter_for_large_payload(tmp_path) -> None:
    audit = AuditStore(tmp_path / "audit.sqlite3")
    audit.record_event(
        actor="tester",
        intent="inventory",
        tool_name="dodo_inventory_stocks",
        connector="dodo",
        decision="allow",
        reason="tool_allowed",
        outcome="success",
        params={},
        response_chars=40000,
    )
    policy = PolicyConfig(
        recommendation_thresholds=RecommendationThresholds(large_response_chars=25000)
    )

    recommendations = LearningEngine(audit, policy).recommendations()

    assert any(item.kind == "response_filter" for item in recommendations)

