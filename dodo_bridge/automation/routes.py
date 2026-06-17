from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from dodo_bridge.audit import AuditStore
from dodo_bridge.automation.jobs import AutomationJobRegistry
from dodo_bridge.automation.models import AutomationDryRunRequest, AutomationRunBlocked
from dodo_bridge.config import Settings, get_settings
from dodo_bridge.security import authenticate_actor

router = APIRouter(prefix="/automation", tags=["automation"], include_in_schema=False)


def settings_dep() -> Settings:
    return get_settings()


def audit_dep(settings: Settings = Depends(settings_dep)) -> AuditStore:
    audit = AuditStore(settings.audit_db_path)
    audit.initialize()
    return audit


def actor_dep(
    request: Request,
    settings: Settings = Depends(settings_dep),
    x_bridge_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    x_actor: str | None = Header(default=None),
) -> str:
    return authenticate_actor(
        request,
        settings,
        x_bridge_key=x_bridge_key,
        authorization=authorization,
        x_actor=x_actor,
    )


def jobs_dep() -> AutomationJobRegistry:
    return AutomationJobRegistry()


@router.get("/jobs")
def list_automation_jobs(
    settings: Settings = Depends(settings_dep),
    jobs: AutomationJobRegistry = Depends(jobs_dep),
    actor: str = Depends(actor_dep),
) -> dict[str, Any]:
    del actor
    return {
        "jobs": [item.model_dump(mode="json") for item in jobs.list(settings)],
        "chatgpt_action_exposed": False,
    }


@router.post("/jobs/{job_name}/dry-run")
async def dry_run_automation_job(
    job_name: str,
    body: AutomationDryRunRequest,
    settings: Settings = Depends(settings_dep),
    jobs: AutomationJobRegistry = Depends(jobs_dep),
    audit: AuditStore = Depends(audit_dep),
    actor: str = Depends(actor_dep),
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = await jobs.get(job_name).dry_run(settings, body)
        response_chars = len(json.dumps(result, ensure_ascii=False, default=str))
        audit_id = audit.record_event(
            actor=actor,
            intent=f"automation dry-run: {job_name}",
            tool_name=f"automation.{job_name}",
            connector="internal",
            decision="allow",
            reason="dry_run_only",
            outcome="success",
            params=body.model_dump(mode="json"),
            response_chars=response_chars,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        return {"audit_id": audit_id, **result}
    except HTTPException:
        raise
    except Exception as exc:
        audit_id = audit.record_event(
            actor=actor,
            intent=f"automation dry-run: {job_name}",
            tool_name=f"automation.{job_name}",
            connector="internal",
            decision="allow",
            reason="dry_run_only",
            outcome="error",
            params=body.model_dump(mode="json"),
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail={"audit_id": audit_id, "error": str(exc)}) from exc


@router.post("/jobs/{job_name}/run", response_model=AutomationRunBlocked)
def run_automation_job(
    job_name: str,
    settings: Settings = Depends(settings_dep),
    jobs: AutomationJobRegistry = Depends(jobs_dep),
    actor: str = Depends(actor_dep),
) -> AutomationRunBlocked:
    del actor
    jobs.get(job_name)
    if not settings.automation_google_sheets_write_enabled:
        raise HTTPException(
            status_code=409,
            detail=AutomationRunBlocked(
                job_name=job_name,
                reason="Google Sheets writes are disabled. Use dry-run until the writer is implemented and enabled.",
            ).model_dump(),
        )
    raise HTTPException(
        status_code=501,
        detail=AutomationRunBlocked(
            job_name=job_name,
            reason="Automation writes are not implemented yet.",
        ).model_dump(),
    )
