#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib import parse, request


TOKEN_URL = "https://auth.dodois.io/connect/token"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    tmp_path.replace(path)
    os.chmod(path, 0o600)


def update_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    prefix = f"{key}="
    replacement = f"{prefix}{value}"
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            break
    else:
        lines.append(replacement)

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    os.chmod(path, 0o600)


def refresh_token(auth: dict[str, Any], token: dict[str, Any], token_url: str) -> dict[str, Any]:
    client_id = auth.get("Client_Id") or auth.get("client_id")
    client_secret = auth.get("Client_Secret") or auth.get("client_secret")
    refresh_token_value = token.get("refresh_token")
    if not client_id or not client_secret or not refresh_token_value:
        raise RuntimeError("auth.json/token.json do not contain client id, client secret, and refresh token")

    payload = parse.urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token_value,
        }
    ).encode("utf-8")
    req = request.Request(
        token_url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with request.urlopen(req, timeout=45) as response:
        data = json.loads(response.read().decode("utf-8"))

    if not data.get("access_token"):
        raise RuntimeError("Dodo token refresh response did not include access_token")

    now = int(time.time())
    merged = {**token, **data}
    if data.get("refresh_token"):
        merged["refresh_token"] = data["refresh_token"]
    if data.get("expires_in"):
        merged["expires_at"] = now + int(data["expires_in"])
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Dodo IS OAuth token and sync Bridge .env.")
    parser.add_argument("--auth-json", type=Path, required=True)
    parser.add_argument("--token-json", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--token-url", default=TOKEN_URL)
    parser.add_argument("--min-ttl-seconds", type=int, default=3600)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    auth = load_json(args.auth_json)
    token = load_json(args.token_json)
    expires_at = int(token.get("expires_at") or 0)
    should_refresh = args.force or expires_at - int(time.time()) <= args.min_ttl_seconds

    if should_refresh:
        token = refresh_token(auth, token, args.token_url)
        write_json(args.token_json, token)

    access_token = token.get("access_token")
    if not access_token:
        raise RuntimeError("token.json does not contain access_token")
    update_env_value(args.env_file, "DODO_ACCESS_TOKEN", access_token)

    print(
        json.dumps(
            {
                "refreshed": should_refresh,
                "expires_at": token.get("expires_at"),
                "env_file": str(args.env_file),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
