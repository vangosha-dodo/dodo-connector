from __future__ import annotations

import asyncio
import json
import os
import shlex
from dataclasses import dataclass
from typing import Any

from dodo_bridge.audit import redact
from dodo_bridge.config import Settings


@dataclass
class OfficeManagerCommandResult:
    configured: bool
    ok: bool
    action: str
    data: dict[str, Any]
    error: str | None = None


class DodoOfficeManagerCommandRunner:
    """Runs a local read-only Office Manager extraction helper.

    The helper receives JSON on stdin and must return JSON on stdout. This keeps
    browser automation outside the FastAPI request code and lets us reuse the
    existing OpenClaw/Playwright session approach later.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    async def run(self, action: str, payload: dict[str, Any]) -> OfficeManagerCommandResult:
        if not self.settings.dodo_office_manager_helper_command:
            return OfficeManagerCommandResult(
                configured=False,
                ok=False,
                action=action,
                data={},
                error="DODO_OFFICE_MANAGER_HELPER_COMMAND is not configured",
            )

        argv = self._command_argv(action)
        input_text = json.dumps(payload, ensure_ascii=False, default=str)
        env = dict(os.environ)
        env["DODO_OFFICE_MANAGER_BRIDGE_ACTION"] = action

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input_text.encode("utf-8")),
                timeout=self.settings.dodo_office_manager_command_timeout_seconds,
            )
        except TimeoutError:
            return OfficeManagerCommandResult(
                configured=True,
                ok=False,
                action=action,
                data={},
                error="office manager helper timed out",
            )
        except FileNotFoundError as exc:
            return OfficeManagerCommandResult(
                configured=True,
                ok=False,
                action=action,
                data={},
                error=f"office manager helper executable not found: {exc.filename}",
            )

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        parsed = self._parse_json(stdout_text)
        data = redact(parsed if isinstance(parsed, dict) else {"stdout": stdout_text[-2000:]})
        if stderr_text:
            data["stderr_tail"] = redact(stderr_text[-2000:])

        ok = process.returncode == 0 and bool(data.get("ok", True))
        error = None if ok else str(data.get("error") or stderr_text or "office manager helper failed")
        return OfficeManagerCommandResult(
            configured=True,
            ok=ok,
            action=action,
            data=data,
            error=error,
        )

    def _command_argv(self, action: str) -> list[str]:
        command = self.settings.dodo_office_manager_helper_command or ""
        argv = shlex.split(command, posix=os.name != "nt")
        return [*argv, action]

    def _parse_json(self, text: str) -> Any:
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.rfind("\n{")
            if start >= 0:
                return json.loads(text[start + 1 :])
            raise
