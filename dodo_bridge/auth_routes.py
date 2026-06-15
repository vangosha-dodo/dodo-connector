from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from dodo_bridge.auth import DodoAuthCommandRunner
from dodo_bridge.config import Settings, get_settings
from dodo_bridge.security import api_key_is_valid

router = APIRouter(prefix="/auth/dodo", tags=["dodo-auth"])


def settings_dep() -> Settings:
    return get_settings()


@router.get("", response_class=HTMLResponse)
async def auth_page(settings: Settings = Depends(settings_dep)) -> HTMLResponse:
    return HTMLResponse(_render_page(settings=settings, result=None))


@router.post("/status")
async def auth_status(
    request: Request,
    settings: Settings = Depends(settings_dep),
) -> Response:
    payload = await _read_payload(request)
    _authorize(settings, payload.get("bridge_key"))
    result = await DodoAuthCommandRunner(settings).run("status")
    return _format_result(request, settings, result.data, result.ok, result.error)


@router.post("/refresh")
async def auth_refresh(
    request: Request,
    settings: Settings = Depends(settings_dep),
) -> Response:
    payload = await _read_payload(request)
    _authorize(settings, payload.get("bridge_key"))
    result = await DodoAuthCommandRunner(settings).run("refresh")
    return _format_result(request, settings, result.data, result.ok, result.error)


@router.post("/submit-code")
async def auth_submit_code(
    request: Request,
    settings: Settings = Depends(settings_dep),
) -> Response:
    payload = await _read_payload(request)
    _authorize(settings, payload.get("bridge_key"))
    code = str(payload.get("code") or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(status_code=422, detail="MFA code must be exactly 6 digits")
    result = await DodoAuthCommandRunner(settings).run("submit-code", code=code)
    return _format_result(request, settings, result.data, result.ok, result.error)


async def _read_payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    body = await request.body()
    if "application/json" in content_type:
        return json.loads(body.decode("utf-8") or "{}")
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _authorize(settings: Settings, bridge_key: Any) -> None:
    supplied = str(bridge_key) if bridge_key is not None else None
    if not api_key_is_valid(settings, supplied):
        raise HTTPException(status_code=401, detail="Invalid or missing bridge API key")


def _format_result(
    request: Request,
    settings: Settings,
    data: dict[str, Any],
    ok: bool,
    error: str | None,
) -> Response:
    wants_html = "application/x-www-form-urlencoded" in request.headers.get("content-type", "")
    payload = {"ok": ok, "error": error, "result": data}
    if wants_html:
        return HTMLResponse(_render_page(settings=settings, result=payload), status_code=200 if ok else 500)
    return JSONResponse(payload, status_code=200 if ok else 500)


def _render_page(settings: Settings, result: dict[str, Any] | None) -> str:
    configured = bool(settings.dodo_auth_helper_command)
    result_html = ""
    if result is not None:
        result_html = (
            "<section class=\"panel\"><h2>Result</h2><pre>"
            + html.escape(json.dumps(result, ensure_ascii=False, indent=2))
            + "</pre></section>"
        )

    helper = settings.dodo_auth_helper_command or "not configured"
    key_field = ""
    if settings.api_keys:
        key_field = """
        <label>
          Bridge API key
          <input name="bridge_key" type="password" autocomplete="current-password" required>
        </label>
        """

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dodo IS Auth</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #f6f7f9; color: #17202a; }}
    main {{ max-width: 920px; margin: 0 auto; padding: 32px 20px 56px; }}
    header {{ margin-bottom: 24px; }}
    h1 {{ font-size: 28px; margin: 0 0 8px; letter-spacing: 0; }}
    h2 {{ font-size: 18px; margin: 0 0 16px; letter-spacing: 0; }}
    p {{ margin: 0 0 12px; line-height: 1.5; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
    .panel {{ background: #fff; border: 1px solid #d9dee7; border-radius: 8px; padding: 18px; box-shadow: 0 1px 2px rgba(20, 31, 46, .05); }}
    form {{ display: grid; gap: 12px; }}
    label {{ display: grid; gap: 6px; font-weight: 600; font-size: 14px; }}
    input {{ min-height: 42px; border: 1px solid #c7cfdb; border-radius: 6px; padding: 0 12px; font-size: 16px; }}
    button {{ min-height: 42px; border: 0; border-radius: 6px; background: #1f6feb; color: #fff; font-weight: 700; cursor: pointer; }}
    button.secondary {{ background: #344054; }}
    .muted {{ color: #5f6b7a; font-size: 14px; }}
    .status {{ display: inline-flex; align-items: center; min-height: 28px; padding: 0 10px; border-radius: 999px; font-size: 13px; font-weight: 700; background: {"#e8f5e9" if configured else "#fff4e5"}; color: {"#1b5e20" if configured else "#8a4b00"}; }}
    pre {{ overflow: auto; white-space: pre-wrap; word-break: break-word; background: #101828; color: #eef4ff; border-radius: 6px; padding: 14px; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Dodo IS authorization</h1>
      <p class="muted">Internal MFA helper for OfficeManager/admin Dodo IS sessions.</p>
      <span class="status">Helper: {html.escape(helper)}</span>
    </header>
    <div class="grid">
      <section class="panel">
        <h2>Status</h2>
        <form method="post" action="/auth/dodo/status">
          {key_field}
          <button class="secondary" type="submit">Check session status</button>
        </form>
      </section>
      <section class="panel">
        <h2>Start / refresh</h2>
        <form method="post" action="/auth/dodo/refresh">
          {key_field}
          <button type="submit">Start authorization</button>
        </form>
        <p class="muted">If Dodo asks for email MFA, return here and submit the fresh code.</p>
      </section>
      <section class="panel">
        <h2>Email code</h2>
        <form method="post" action="/auth/dodo/submit-code">
          {key_field}
          <label>
            6-digit code
            <input name="code" inputmode="numeric" pattern="[0-9]{{6}}" maxlength="6" autocomplete="one-time-code" required>
          </label>
          <button type="submit">Submit code</button>
        </form>
      </section>
    </div>
    {result_html}
  </main>
</body>
</html>"""

