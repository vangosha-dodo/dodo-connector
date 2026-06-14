from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

import httpx

from dodo_bridge.config import Settings
from dodo_bridge.models import ToolSpec


class DodoConnector:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def invoke(self, tool: ToolSpec, parameters: dict[str, Any], dry_run: bool) -> Any:
        request = self._build_request(tool, parameters)
        if dry_run or not self.settings.dodo_access_token:
            return {
                "dry_run": True,
                "external_not_configured": not bool(self.settings.dodo_access_token),
                "request": request,
            }

        headers = {"Authorization": f"Bearer {self.settings.dodo_access_token}"}
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.request(
                tool.method,
                request["url"],
                headers=headers,
                json=request.get("json"),
            )
            response.raise_for_status()
            return response.json()

    def _build_request(self, tool: ToolSpec, parameters: dict[str, Any]) -> dict[str, Any]:
        path = tool.path.replace("{country}", quote(self.settings.dodo_country))
        for key, value in parameters.items():
            placeholder = "{" + key + "}"
            if placeholder in path:
                path = path.replace(placeholder, quote(str(value)))

        base_url = self.settings.dodo_base_url.rstrip("/")
        query = {
            key: value
            for key, value in parameters.items()
            if key in tool.allowed_query_params and value is not None
        }
        url = f"{base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query, doseq=True)}"

        request: dict[str, Any] = {"method": tool.method, "url": url}
        if tool.method != "GET":
            request["json"] = parameters.get("body", parameters)
        return request

