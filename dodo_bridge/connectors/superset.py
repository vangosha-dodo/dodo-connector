from __future__ import annotations

from typing import Any

import httpx

from dodo_bridge.config import Settings
from dodo_bridge.models import ToolSpec


class SupersetConnector:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def invoke(self, tool: ToolSpec, parameters: dict[str, Any], dry_run: bool) -> Any:
        base_url = (self.settings.superset_base_url or "").rstrip("/")
        url = f"{base_url}{tool.path}" if base_url else tool.path
        if dry_run or not base_url:
            return {
                "dry_run": True,
                "external_not_configured": not bool(base_url),
                "request": {"method": tool.method, "url": url, "json": parameters},
            }

        token = await self._access_token()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.request(tool.method, url, headers=headers, json=parameters)
            response.raise_for_status()
            return response.json()

    async def _access_token(self) -> str | None:
        if self.settings.superset_access_token:
            return self.settings.superset_access_token
        if not (
            self.settings.superset_base_url
            and self.settings.superset_username
            and self.settings.superset_password
        ):
            return None

        login_url = f"{self.settings.superset_base_url.rstrip('/')}/api/v1/security/login"
        payload = {
            "username": self.settings.superset_username,
            "password": self.settings.superset_password,
            "provider": "db",
            "refresh": True,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(login_url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("access_token")

