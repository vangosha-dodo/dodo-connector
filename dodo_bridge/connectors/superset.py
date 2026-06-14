from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from dodo_bridge.config import Settings
from dodo_bridge.models import ToolSpec


class SupersetConnector:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def invoke(self, tool: ToolSpec, parameters: dict[str, Any], dry_run: bool) -> Any:
        base_url = (self.settings.superset_base_url or "").rstrip("/")
        path = tool.path
        for key, value in parameters.items():
            placeholder = "{" + key + "}"
            if placeholder in path:
                path = path.replace(placeholder, str(value))
        url = f"{base_url}{path}" if base_url else path
        query = {
            key: value
            for key, value in parameters.items()
            if key in tool.allowed_query_params and value is not None
        }
        if query:
            url = f"{url}?{urlencode(query, doseq=True)}"
        payload = parameters.get("body", parameters)
        if dry_run or not base_url:
            return {
                "dry_run": True,
                "external_not_configured": not bool(base_url),
                "request": {"method": tool.method, "url": url, "json": payload},
            }

        token = await self._access_token()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.request(tool.method, url, headers=headers, json=payload)
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
