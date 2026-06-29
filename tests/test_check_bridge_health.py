from __future__ import annotations

from scripts.check_bridge_health import build_report, count_openapi_operations


def test_count_openapi_operations_counts_http_methods_only() -> None:
    schema = {
        "paths": {
            "/health": {"get": {}, "parameters": []},
            "/analytics/employee-discount": {"post": {}},
            "/ignored": {"summary": "not an operation"},
        }
    }

    assert count_openapi_operations(schema) == 2


def test_build_report_marks_expected_bridge_checks_ok() -> None:
    report = build_report(
        base_url="https://bridge.example.com",
        health_payload={"status": "ok"},
        openapi_schema={
            "paths": {
                "/dodo/pizzerias": {"get": {}},
                "/analytics/employee-discount": {"post": {}},
            }
        },
        capabilities_payload={
            "read_only": True,
            "dodo_capabilities": [
                {"name": "accounting_sales_summary"},
                {"name": "production_productivity"},
            ],
            "superset_capabilities": [{"name": "employee_discount"}],
            "office_manager_capabilities": [{"name": "courier_payroll_daily_export"}],
        },
    )

    assert report["ok"] is True
    assert report["base_url"] == "https://bridge.example.com"
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["health"]["ok"] is True
    assert checks["openapi_operation_limit"]["detail"] == "2 <= 30"
    assert checks["mcp_diagnostic_not_in_openapi"]["ok"] is True
    assert checks["mcp_read_only"]["ok"] is True
    assert checks["forbidden_capabilities_absent"]["ok"] is True
    assert report["summary"]["dodo_capabilities"] == 2
    assert report["summary"]["office_manager_capabilities"] == 1


def test_build_report_detects_mcp_diagnostic_leaking_into_openapi() -> None:
    report = build_report(
        base_url="https://bridge.example.com",
        health_payload={"status": "ok"},
        openapi_schema={"paths": {"/mcp/capabilities": {"get": {}}}},
        capabilities_payload={"read_only": True, "dodo_capabilities": []},
    )

    checks = {item["name"]: item for item in report["checks"]}
    assert report["ok"] is False
    assert checks["mcp_diagnostic_not_in_openapi"]["ok"] is False


def test_build_report_detects_forbidden_capability_names() -> None:
    report = build_report(
        base_url="https://bridge.example.com",
        health_payload={"status": "ok"},
        openapi_schema={"paths": {}},
        capabilities_payload={
            "read_only": True,
            "dodo_capabilities": [{"name": "courier_orders"}],
        },
    )

    checks = {item["name"]: item for item in report["checks"]}
    assert report["ok"] is False
    assert checks["forbidden_capabilities_absent"]["ok"] is False
    assert checks["forbidden_capabilities_absent"]["detail"] == "courier_orders"
