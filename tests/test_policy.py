from dodo_bridge.models import ConnectorName, RiskLevel, ToolInvocationRequest, ToolSpec
from dodo_bridge.policy import PolicyConfig, PolicyEngine


def test_policy_denies_unknown_tool() -> None:
    engine = PolicyEngine(PolicyConfig())

    decision = engine.evaluate(None, ToolInvocationRequest(), params_chars=2)

    assert decision.outcome == "deny"
    assert decision.reason == "unknown_tool"


def test_policy_requires_approval_for_write_tool() -> None:
    engine = PolicyEngine(PolicyConfig(allowed_tools=["write_tool"]))
    tool = ToolSpec(
        name="write_tool",
        connector=ConnectorName.DODO,
        method="POST",
        path="/write",
        risk_level=RiskLevel.WRITE,
        enabled=True,
    )

    decision = engine.evaluate(tool, ToolInvocationRequest(), params_chars=2)

    assert decision.outcome == "approval_required"
    assert decision.requires_approval is True


def test_policy_allows_enabled_read_tool_from_allowlist() -> None:
    engine = PolicyEngine(PolicyConfig(allowed_tools=["read_tool"]))
    tool = ToolSpec(
        name="read_tool",
        connector=ConnectorName.DODO,
        method="GET",
        path="/read",
        risk_level=RiskLevel.READ,
        enabled=True,
    )

    decision = engine.evaluate(tool, ToolInvocationRequest(), params_chars=2)

    assert decision.outcome == "allow"
    assert decision.reason == "tool_allowed"

