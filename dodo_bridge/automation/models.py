from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class AutomationDryRunRequest(BaseModel):
    report_date: date | None = Field(
        default=None,
        description="Reporting date in Europe/Moscow. Defaults to yesterday in Moscow.",
    )
    pizzerias: list[str] | None = Field(
        default=None,
        description="Optional pizzeria names, aliases, or unit ids to include.",
    )
    extract_source: bool = Field(
        default=False,
        description="When true, call the configured Office Manager helper in read-only mode.",
    )
    include_source_rows: bool = Field(
        default=False,
        description="When true, include helper-returned source rows in the dry-run response.",
    )


class AutomationJobInfo(BaseModel):
    name: str
    description: str
    schedule_msk: str | None = None
    status: str
    source: str
    target: dict[str, Any]
    writes_enabled: bool


class AutomationRunBlocked(BaseModel):
    job_name: str
    status: str = "blocked"
    reason: str
    dodo_is_changed: bool = False
    google_sheets_changed: bool = False
