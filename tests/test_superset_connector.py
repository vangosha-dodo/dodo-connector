from __future__ import annotations

import json

from dodo_bridge.config import Settings
from dodo_bridge.connectors.superset import SupersetConnector
from dodo_bridge.models import ConnectorName, ToolSpec


def test_settings_ignore_blank_superset_cookie_path() -> None:
    settings = Settings(
        api_keys=[],
        superset_session_cookies_path="",
        superset_browser_helper_command="",
    )

    assert settings.superset_session_cookies_path is None
    assert settings.superset_browser_helper_command is None


def test_superset_connector_loads_dict_cookies(tmp_path) -> None:
    path = tmp_path / "cookies.json"
    path.write_text(json.dumps({"cookies": {"session": "abc", "csrf": "def"}}), encoding="utf-8")
    connector = SupersetConnector(
        Settings(
            api_keys=[],
            superset_base_url="https://analytics.dodois.io",
            superset_session_cookies_path=path,
        )
    )

    assert connector._load_cookies() == {"session": "abc", "csrf": "def"}


def test_superset_connector_loads_playwright_cookies(tmp_path) -> None:
    path = tmp_path / "cookies.json"
    path.write_text(
        json.dumps(
            [
                {"name": "session", "value": "abc", "domain": "analytics.dodois.io"},
                {"name": "ignored"},
            ]
        ),
        encoding="utf-8",
    )
    connector = SupersetConnector(
        Settings(
            api_keys=[],
            superset_base_url="https://analytics.dodois.io",
            superset_session_cookies_path=path,
        )
    )

    assert connector._load_cookies() == {"session": "abc"}


def test_superset_connector_dry_run_uses_tool_base_url() -> None:
    connector = SupersetConnector(
        Settings(
            api_keys=[],
            superset_base_url="https://analytics.dodois.io",
        )
    )
    tool = ToolSpec(
        name="superset_clients_phone_share",
        connector=ConnectorName.SUPERSET,
        method="POST",
        path="/superset/api/v1/chart/data",
        base_url="https://officemanager.dodois.io",
        dashboard_url="https://officemanager.dodois.io/OfficeManager/Analytics/Client_analytics",
        allowed_query_params=["dashboard_id"],
    )

    result = awaitable(connector.invoke(tool, {"dashboard_id": 868, "body": {"ok": True}}, dry_run=True))

    assert result["request"]["url"] == (
        "https://officemanager.dodois.io/superset/api/v1/chart/data?dashboard_id=868"
    )


def awaitable(coro):  # noqa: ANN001
    import asyncio

    return asyncio.run(coro)
