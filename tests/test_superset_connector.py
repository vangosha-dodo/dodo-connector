from __future__ import annotations

import json

from dodo_bridge.config import Settings
from dodo_bridge.connectors.superset import SupersetConnector


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
