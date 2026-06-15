import sys
from pathlib import Path

from fastapi.testclient import TestClient

from dodo_bridge.auth_routes import settings_dep as auth_settings_dep
from dodo_bridge.config import Settings
from dodo_bridge.main import app


def test_dodo_auth_page_renders(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[auth_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.get("/auth/dodo")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Dodo IS authorization" in response.text
    assert "Submit code" in response.text


def test_dodo_auth_form_requires_bridge_key(tmp_path) -> None:
    settings = make_settings(tmp_path, api_keys=["secret"])
    app.dependency_overrides[auth_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post("/auth/dodo/status", data={})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_dodo_auth_submit_code_passes_code_via_stdin(tmp_path) -> None:
    helper = tmp_path / "fake_auth_helper.py"
    helper.write_text(
        "import json, sys\n"
        "action = sys.argv[1]\n"
        "code = sys.stdin.read().strip()\n"
        "print(json.dumps({'ok': True, 'action': action, 'code_len': len(code)}))\n",
        encoding="utf-8",
    )
    settings = make_settings(
        tmp_path,
        api_keys=["secret"],
        helper_command=f"{sys.executable} {helper}",
    )
    app.dependency_overrides[auth_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post(
            "/auth/dodo/submit-code",
            data={"bridge_key": "secret", "code": "123456"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "123456" not in response.text
    assert "&quot;action&quot;: &quot;submit-code&quot;" in response.text
    assert "&quot;code_len&quot;: 6" in response.text


def test_dodo_auth_submit_code_validates_format(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app.dependency_overrides[auth_settings_dep] = lambda: settings
    try:
        client = TestClient(app)
        response = client.post("/auth/dodo/submit-code", data={"code": "12"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def make_settings(
    tmp_path: Path,
    api_keys: list[str] | None = None,
    helper_command: str | None = None,
) -> Settings:
    return Settings(
        api_keys=api_keys or [],
        tool_registry_path=Path("configs/tools.example.yaml"),
        policy_path=Path("configs/policy.example.yaml"),
        audit_db_path=tmp_path / "audit.sqlite3",
        dodo_auth_helper_command=helper_command,
    )
