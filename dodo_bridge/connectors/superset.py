from __future__ import annotations

import asyncio
import json
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

        if self.settings.superset_session_cookies_path:
            return await self._invoke_with_session_cookies(tool.method, url, payload)

        if self.settings.superset_browser_helper_command:
            return await self._invoke_with_browser_helper(tool.method, url, payload)

        token = await self._access_token()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.request(tool.method, url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def _invoke_with_session_cookies(self, method: str, url: str, payload: Any) -> Any:
        cookies = self._load_cookies()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        async with httpx.AsyncClient(timeout=60, cookies=cookies) as client:
            csrf_url = f"{self.settings.superset_base_url.rstrip('/')}/api/v1/security/csrf_token/"
            csrf_response = await client.get(csrf_url, headers={"Accept": "application/json"})
            csrf_response.raise_for_status()
            csrf = csrf_response.json().get("result")
            if csrf:
                headers["X-CSRFToken"] = csrf
            response = await client.request(method, url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    def _load_cookies(self) -> dict[str, str]:
        path = self.settings.superset_session_cookies_path
        if path is None or not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("cookies"), dict):
            payload = payload["cookies"]
        if isinstance(payload, dict):
            return {str(key): str(value) for key, value in payload.items()}
        if isinstance(payload, list):
            cookies = {}
            for item in payload:
                if isinstance(item, dict) and item.get("name") and item.get("value") is not None:
                    cookies[str(item["name"])] = str(item["value"])
            return cookies
        return {}

    async def _invoke_with_browser_helper(self, method: str, url: str, payload: Any) -> Any:
        command = self.settings.superset_browser_helper_command
        if not command:
            raise RuntimeError("Superset browser helper is not configured")
        process = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        input_payload = json.dumps(
            {
                "method": method,
                "url": url,
                "base_url": self.settings.superset_base_url,
                "json": payload,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input_payload),
                timeout=self.settings.superset_browser_command_timeout_seconds,
            )
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise RuntimeError("Superset browser helper timed out") from exc
        if process.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace")[-1000:]
            raise RuntimeError(f"Superset browser helper failed: {stderr_text}")
        try:
            return json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            preview = stdout.decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"Superset browser helper returned invalid JSON: {preview}") from exc

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
