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
class AuthCommandResult:
    configured: bool
    ok: bool
    action: str
    data: dict[str, Any]
    error: str | None = None


class DodoAuthCommandRunner:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def run(self, action: str, code: str | None = None) -> AuthCommandResult:
        if not self.settings.dodo_auth_helper_command:
            return AuthCommandResult(
                configured=False,
                ok=False,
                action=action,
                data={},
                error="DODO_AUTH_HELPER_COMMAND is not configured",
            )

        argv = self._command_argv(action)
        input_text = f"{code}\n" if code else None
        env = dict(os.environ)
        env["DODO_AUTH_BRIDGE_ACTION"] = action

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE if input_text is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input_text.encode("utf-8") if input_text else None),
                timeout=self.settings.dodo_auth_command_timeout_seconds,
            )
        except TimeoutError:
            return AuthCommandResult(
                configured=True,
                ok=False,
                action=action,
                data={},
                error="auth helper timed out",
            )
        except FileNotFoundError as exc:
            return AuthCommandResult(
                configured=True,
                ok=False,
                action=action,
                data={},
                error=f"auth helper executable not found: {exc.filename}",
            )

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        parsed = self._parse_json(stdout_text)
        data = redact(parsed if isinstance(parsed, dict) else {"stdout": stdout_text[-2000:]})
        if stderr_text:
            data["stderr_tail"] = redact(stderr_text[-2000:])

        ok = process.returncode == 0 and bool(data.get("ok", True))
        error = None if ok else str(data.get("error") or stderr_text or "auth helper failed")
        return AuthCommandResult(
            configured=True,
            ok=ok,
            action=action,
            data=data,
            error=error,
        )

    def _command_argv(self, action: str) -> list[str]:
        command = self.settings.dodo_auth_helper_command or ""
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

