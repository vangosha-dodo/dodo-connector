from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from dodo_bridge.automation.models import AutomationDryRunRequest, AutomationJobInfo
from dodo_bridge.automation.office_manager import DodoOfficeManagerCommandRunner
from dodo_bridge.config import Settings
from dodo_bridge.pizzerias import load_pizzerias

MSK = ZoneInfo("Europe/Moscow")


COURIER_PAYROLL_HEADERS: tuple[str, ...] = (
    "Дата начала смены",
    "Время начала смены",
    "Время окончания смены",
    "Дата окончания смены",
    "Номер телефона",
    "Фамилия",
    "Имя",
    "Отчество",
    "ИНН",
    "Табельный номер",
    "Категория",
    "Ставка в час",
    "Ставка за заказ",
    "Стаж, мес.",
    "Коэф-т особого дня",
    "Ночной коэф-т",
    "Ночные часы",
    "Дневные часы",
    "Праздничные часы",
    "Количество заказов",
    "ЗП, ночь",
    "ЗП, день",
    "ЗП, за заказ",
    "ЗП, премия",
    "Комментрий к премиям",
    "ЗП, премия за стаж",
    "Итого",
    "Id сотрудника",
    "UUId сотрудника",
    "Тип оформления",
    "Пиццерия",
    "Расстояние (км)",
    "ЗП, километраж",
    "Поездки (количество)",
    "ЗП, поездки",
    "Невыход по графику / не нашел замену",
    "Опоздание",
    "Кол-во проблем с заказами",
    "Вид доплаты за праздники / пики",
    "Кол-во заказов праздничных / пиковых",
    "Кол-во праздничных / пиковых часов",
    "Коэффициент праздничных / пиковых часов/заказов",
    "Сумма доплаты праздничных / пиковых часов/заказов",
    "Кол-во довозов (смена адреса)",
    "Премия за довозы",
    "Ставка за ГСМ, руб/км",
    "Компенсация ГСМ",
    "Компенсация ТО (5 руб./км) только СМЗ и ИП",
    "Погода (Обычно / Сложно / Экстрим)",
    "Вид доплаты за погоду",
    "Надбавка за заказ",
    "Надбавка за погоду км",
    "Надбавка за погоду ч",
    "Премия за разгрузку",
    "Итого зп",
    "Неделя",
    "Месяц",
    "Год",
)

COURIER_PAYROLL_MANUAL_COLUMNS: tuple[str, ...] = (
    "ЗП, премия",
    "Комментрий к премиям",
    "Невыход по графику / не нашел замену",
    "Опоздание",
    "Кол-во проблем с заказами",
    "Вид доплаты за праздники / пики",
    "Кол-во заказов праздничных / пиковых",
    "Кол-во праздничных / пиковых часов",
    "Коэффициент праздничных / пиковых часов/заказов",
    "Кол-во довозов (смена адреса)",
    "Ставка за ГСМ, руб/км",
    "Погода (Обычно / Сложно / Экстрим)",
    "Вид доплаты за погоду",
    "Премия за разгрузку",
)

COURIER_PAYROLL_FORMULA_COLUMNS: tuple[str, ...] = (
    "Сумма доплаты праздничных / пиковых часов/заказов",
    "Премия за довозы",
    "Компенсация ГСМ",
    "Компенсация ТО (5 руб./км) только СМЗ и ИП",
    "Надбавка за заказ",
    "Надбавка за погоду км",
    "Надбавка за погоду ч",
    "Итого зп",
    "Неделя",
    "Месяц",
    "Год",
)


class AutomationJob(Protocol):
    name: str

    def info(self, settings: Settings) -> AutomationJobInfo:
        ...

    async def dry_run(self, settings: Settings, request: AutomationDryRunRequest) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class CourierPayrollDailyExportJob:
    name: str = "courier_payroll_daily_export"

    def info(self, settings: Settings) -> AutomationJobInfo:
        return AutomationJobInfo(
            name=self.name,
            description="Read Office Manager courier payroll report and plan rows for 'Ежедневная выгрузка'.",
            schedule_msk="daily 00:30, previous Moscow day",
            status="dry_run_only",
            source="Dodo IS Office Manager: Отчеты -> Заработная плата, тип Курьер",
            target=self._target(settings),
            writes_enabled=False,
        )

    async def dry_run(self, settings: Settings, request: AutomationDryRunRequest) -> dict[str, Any]:
        report_date = request.report_date or yesterday_msk()
        pizzerias_payload = load_pizzerias(settings.dodo_pizzerias_path)
        selected_pizzerias = _select_pizzerias(pizzerias_payload.get("pizzerias", []), request.pizzerias)

        if request.pizzerias and not selected_pizzerias:
            raise HTTPException(status_code=422, detail="No pizzerias matched the requested filter")

        extraction_payload = {
            "report_date": report_date.isoformat(),
            "staff_type": "Курьер",
            "pizzerias": [
                {
                    "unit_id": item["unit_id"],
                    "name": item["name"],
                }
                for item in selected_pizzerias
            ],
        }
        helper_result = None
        source_rows: list[dict[str, Any]] = []
        if request.extract_source:
            helper_result = await DodoOfficeManagerCommandRunner(settings).run(
                "courier-payroll-daily",
                extraction_payload,
            )
            if helper_result.ok and isinstance(helper_result.data.get("rows"), list):
                source_rows = [row for row in helper_result.data["rows"] if isinstance(row, dict)]

        row_count = len(source_rows)
        source_snapshot_hash = _hash_rows(source_rows) if source_rows else None
        planned_write = {
            "mode": "append_or_upsert",
            "enabled": False,
            "reason": "Google Sheets writes are disabled in this implementation step",
            "target_sheet": "Ежедневная выгрузка",
            "target_range": "A:BF",
            "source_rows": row_count,
            "idempotency_key_fields": [
                "report_date",
                "pizzeria",
                "employee_id_or_uuid",
                "shift_start",
                "shift_end",
                "source_row_hash",
            ],
            "preserve_columns": list(COURIER_PAYROLL_MANUAL_COLUMNS),
            "formula_columns": list(COURIER_PAYROLL_FORMULA_COLUMNS),
        }

        result: dict[str, Any] = {
            "job_name": self.name,
            "dry_run": True,
            "status": "planned",
            "report_date": report_date.isoformat(),
            "dodo_is_changed": False,
            "google_sheets_changed": False,
            "source": {
                "type": "office_manager_web",
                "path": "Отчеты -> Заработная плата",
                "filters": {"date": report_date.isoformat(), "staff_type": "Курьер"},
                "pizzerias_source": pizzerias_payload.get("source"),
                "pizzerias_count": len(selected_pizzerias),
                "helper_configured": bool(settings.dodo_office_manager_helper_command),
                "helper_called": request.extract_source,
                "row_count": row_count,
                "source_snapshot_hash": source_snapshot_hash,
            },
            "target": self._target(settings),
            "extraction_requests": [
                {
                    "unit_id": item["unit_id"],
                    "pizzeria": item["name"],
                    "date": report_date.isoformat(),
                    "staff_type": "Курьер",
                    "read_only": True,
                }
                for item in selected_pizzerias
            ],
            "planned_writes": [planned_write],
            "safety": {
                "chatgpt_action_exposed": False,
                "dodo_is_write_allowed": False,
                "google_sheets_write_allowed": False,
            },
        }

        if helper_result:
            result["source"]["helper_ok"] = helper_result.ok
            result["source"]["helper_error"] = helper_result.error
            result["source"]["helper_data_keys"] = sorted(helper_result.data)
        if request.include_source_rows:
            result["source_rows"] = source_rows
        return result

    def _target(self, settings: Settings) -> dict[str, Any]:
        return {
            "spreadsheet_id": settings.courier_payroll_spreadsheet_id,
            "spreadsheet_title": "А-2 Зп курьеров (с 30.03.26)_агент",
            "sheet": "Ежедневная выгрузка",
            "range": "A:BF",
            "header_count": len(COURIER_PAYROLL_HEADERS),
            "headers": list(COURIER_PAYROLL_HEADERS),
        }


class AutomationJobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, AutomationJob] = {
            CourierPayrollDailyExportJob.name: CourierPayrollDailyExportJob(),
        }

    def list(self, settings: Settings) -> list[AutomationJobInfo]:
        return [job.info(settings) for job in self._jobs.values()]

    def get(self, name: str) -> AutomationJob:
        try:
            return self._jobs[name]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown automation job: {name}") from exc


def yesterday_msk() -> date:
    return datetime.now(MSK).date() - timedelta(days=1)


def _select_pizzerias(
    pizzerias: list[dict[str, Any]],
    requested: list[str] | None,
) -> list[dict[str, Any]]:
    if not requested:
        return pizzerias

    normalized_requested = {_normalize(value) for value in requested if value}
    selected = []
    for item in pizzerias:
        aliases = item.get("aliases") or []
        values = [item.get("unit_id"), item.get("name"), *aliases]
        if any(_normalize(value) in normalized_requested for value in values if value):
            selected.append(item)
    return selected


def _normalize(value: Any) -> str:
    return str(value).replace("-", " ").strip().casefold()


def _hash_rows(rows: list[dict[str, Any]]) -> str:
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
