from __future__ import annotations

from fastapi import Header, HTTPException, Request

from dodo_bridge.config import Settings


def authenticate_actor(
    request: Request,
    settings: Settings,
    x_bridge_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    x_actor: str | None = Header(default=None),
) -> str:
    if not settings.api_keys:
        return x_actor or "anonymous-dev"

    bearer = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()

    supplied = x_bridge_key or bearer
    if supplied in settings.api_keys:
        return x_actor or "api-key"

    raise HTTPException(status_code=401, detail="Invalid or missing bridge API key")

