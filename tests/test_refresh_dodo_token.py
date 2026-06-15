from __future__ import annotations

import os

from scripts.refresh_dodo_token import update_env_value, write_json


def test_update_env_value_replaces_existing_key(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\nDODO_ACCESS_TOKEN=old\nB=2\n", encoding="utf-8")

    update_env_value(env_file, "DODO_ACCESS_TOKEN", "new")

    assert env_file.read_text(encoding="utf-8") == "A=1\nDODO_ACCESS_TOKEN=new\nB=2\n"
    if os.name != "nt":
        assert (os.stat(env_file).st_mode & 0o777) == 0o600


def test_update_env_value_appends_missing_key(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\n", encoding="utf-8")

    update_env_value(env_file, "DODO_ACCESS_TOKEN", "new")

    assert env_file.read_text(encoding="utf-8") == "A=1\nDODO_ACCESS_TOKEN=new\n"


def test_write_json_uses_private_permissions(tmp_path) -> None:
    path = tmp_path / "token.json"

    write_json(path, {"access_token": "secret"})

    assert '"access_token": "secret"' in path.read_text(encoding="utf-8")
    if os.name != "nt":
        assert (os.stat(path).st_mode & 0o777) == 0o600
