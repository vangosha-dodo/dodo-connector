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
DRY_RUN_ROW_PREVIEW_LIMIT = 10


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

COURIER_PAYROLL_SOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    "Дата начала смены": ("shiftStartDate", "clockInDate", "dateFrom"),
    "Время начала смены": ("shiftStartTime", "clockInTime", "clockIn"),
    "Время окончания смены": ("shiftEndTime", "clockOutTime", "clockOut"),
    "Дата окончания смены": ("shiftEndDate", "clockOutDate", "dateTo"),
    "Номер телефона": ("phone", "phoneNumber", "employeePhone"),
    "Фамилия": ("lastName", "surname", "employeeLastName"),
    "Имя": ("firstName", "employeeFirstName"),
    "Отчество": ("middleName", "patronymic", "employeeMiddleName"),
    "ИНН": ("inn", "taxId"),
    "Табельный номер": ("personnelNumber", "tabNumber"),
    "Категория": ("category", "courierCategory"),
    "Ставка в час": ("hourRate", "hourlyRate"),
    "Ставка за заказ": ("orderRate", "ratePerOrder"),
    "Стаж, мес.": ("tenureMonths", "experienceMonths"),
    "Количество заказов": ("ordersCount", "orderCount"),
    "Id сотрудника": ("employeeId", "staffId", "personId"),
    "UUId сотрудника": ("employeeUuid", "employeeUUId", "staffUuid", "staffUUId"),
    "Тип оформления": ("employmentType", "contractType"),
    "Пиццерия": ("pizzeria", "unitName", "unit"),
    "Расстояние (км)": ("distanceKm", "distance"),
    "Поездки (количество)": ("tripsCount", "tripCount"),
}

COURIER_PAYROLL_FORMULA_TEMPLATES: dict[str, str] = {
    "Сумма доплаты праздничных / пиковых часов/заказов": (
        '=IF(AM{row}="Часы";AO{row}*24*L{row}*AP{row};'
        'IF(AM{row}="Заказ";AN{row}*AP{row}*M{row};0))'
    ),
    "Премия за довозы": "=AR{row}*M{row}",
    "Компенсация ГСМ": "=AF{row}*AT{row}",
    "Компенсация ТО (5 руб./км) только СМЗ и ИП": (
        '=IF(OR(AD{row}="Самозанятый"; AND(AD{row}="ГПХ"; I{row}<>"")); 5*AF{row}; 0)'
    ),
    "Надбавка за заказ": (
        '=IF(AX{row}="Заказ"; IF(AW{row}="Сложно";M{row}*50%;'
        'IF(AW{row}="Экстрим";M{row}*100%;0))*T{row};0)'
    ),
    "Надбавка за погоду км": (
        '=IF(AX{row}="Км и час"; IF(AW{row}="Сложно";AT{row}*20%;'
        'IF(AW{row}="Экстрим";AT{row}*50%;0))*AF{row};0)'
    ),
    "Надбавка за погоду ч": (
        '=IF(AX{row}="Км и час"; IF(AW{row}="Сложно";L{row}*50%;'
        'IF(AW{row}="Экстрим";L{row}*100%;0))*R{row}*24;0)'
    ),
    "Итого зп": (
        "=V{row}+W{row}+X{row}+AS{row}+AU{row}+AV{row}+"
        "AZ{row}+BA{row}+AQ{row}+BB{row}+AY{row}"
    ),
    "Неделя": "=WEEKNUM(A{row};2)",
    "Месяц": "=DATE(YEAR(A{row});MONTH(A{row});1)",
    "Год": "=YEAR(BE{row})",
}


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
            if helper_result.ok:
                source_rows = _extract_helper_rows(helper_result.data)

        source_rows = _filter_rows_by_pizzeria(source_rows, selected_pizzerias)
        row_plans, invalid_rows = _plan_payroll_rows(source_rows, report_date)
        pizzeria_summary = _summarize_planned_rows(row_plans, invalid_rows)
        row_count = len(source_rows)
        source_snapshot_hash = _hash_rows(source_rows) if source_rows else None
        planned_write = {
            "mode": "append_or_upsert",
            "enabled": False,
            "reason": "Google Sheets writes are disabled in this implementation step",
            "target_sheet": "Ежедневная выгрузка",
            "target_range": "A:BF",
            "source_rows": row_count,
            "ready_rows": len(row_plans),
            "invalid_rows": len(invalid_rows),
            "upsert_match_key_fields": [
                "report_date",
                "pizzeria",
                "employee_id_or_uuid",
                "shift_start",
                "shift_end",
            ],
            "change_detection_hash": "source_row_hash",
            "preserve_columns": list(COURIER_PAYROLL_MANUAL_COLUMNS),
            "formula_columns": list(COURIER_PAYROLL_FORMULA_COLUMNS),
            "formula_templates": _formula_templates_by_column(),
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
            "row_summary": {
                "source_rows": row_count,
                "ready_rows": len(row_plans),
                "invalid_rows": len(invalid_rows),
                "by_pizzeria": pizzeria_summary,
            },
            "planned_rows_preview": row_plans[:DRY_RUN_ROW_PREVIEW_LIMIT],
            "invalid_rows_preview": invalid_rows[:DRY_RUN_ROW_PREVIEW_LIMIT],
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


def _extract_helper_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        data.get("rows"),
        data.get("data", {}).get("rows") if isinstance(data.get("data"), dict) else None,
        data.get("result", {}).get("rows") if isinstance(data.get("result"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [row for row in candidate if isinstance(row, dict)]
    return []


def _filter_rows_by_pizzeria(
    rows: list[dict[str, Any]],
    selected_pizzerias: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not rows or not selected_pizzerias:
        return rows

    selected_names = {_normalize(item["name"]) for item in selected_pizzerias if item.get("name")}
    selected_ids = {_normalize(item["unit_id"]) for item in selected_pizzerias if item.get("unit_id")}
    filtered = []
    for row in rows:
        lookup = _row_lookup(row)
        pizzeria = _lookup_value(lookup, "Пиццерия")
        unit_id = _lookup_alias(lookup, ("unitId", "unit_id", "pizzeriaId"))
        if pizzeria and _normalize(pizzeria) in selected_names:
            filtered.append(row)
        elif unit_id and _normalize(unit_id) in selected_ids:
            filtered.append(row)
        elif not pizzeria and not unit_id:
            filtered.append(row)
    return filtered


def _plan_payroll_rows(
    source_rows: list[dict[str, Any]],
    report_date: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ready: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for index, source_row in enumerate(source_rows):
        lookup = _row_lookup(source_row)
        normalized = _normalized_sheet_row(lookup, report_date)
        employee_id = normalized.get("Id сотрудника")
        employee_uuid = normalized.get("UUId сотрудника")
        employee_key = employee_id or employee_uuid
        pizzeria = normalized.get("Пиццерия")
        shift_start = _shift_point(
            normalized.get("Дата начала смены"),
            normalized.get("Время начала смены"),
        )
        shift_end = _shift_point(
            normalized.get("Дата окончания смены"),
            normalized.get("Время окончания смены"),
        )
        missing = [
            field
            for field, value in {
                "Пиццерия": pizzeria,
                "Id сотрудника/UUId сотрудника": employee_key,
                "Дата начала смены": normalized.get("Дата начала смены"),
                "Время начала смены": normalized.get("Время начала смены"),
                "Время окончания смены": normalized.get("Время окончания смены"),
            }.items()
            if value in (None, "")
        ]
        source_row_hash = _hash_rows([source_row])
        if missing:
            invalid.append(
                {
                    "source_index": index,
                    "status": "invalid",
                    "reason": "missing_required_fields",
                    "missing_fields": missing,
                    "source_row_hash": source_row_hash,
                }
            )
            continue

        match_key_payload = {
            "report_date": report_date.isoformat(),
            "pizzeria": pizzeria,
            "employee_id_or_uuid": str(employee_key),
            "shift_start": shift_start,
            "shift_end": shift_end,
        }
        ready.append(
            {
                "source_index": index,
                "status": "ready",
                "pizzeria": pizzeria,
                "employee": {
                    "id": employee_id,
                    "uuid": employee_uuid,
                    "name": _employee_name(normalized),
                },
                "shift": {
                    "start": shift_start,
                    "end": shift_end,
                },
                "upsert_match_key": _hash_payload(match_key_payload),
                "source_row_hash": source_row_hash,
                "non_empty_columns": sum(1 for value in normalized.values() if value not in (None, "")),
                "sheet_columns": len(COURIER_PAYROLL_HEADERS),
                "formula_columns": list(COURIER_PAYROLL_FORMULA_COLUMNS),
            }
        )
    return ready, invalid


def _normalized_sheet_row(lookup: dict[str, Any], report_date: date) -> dict[str, Any]:
    row = {}
    for header in COURIER_PAYROLL_HEADERS:
        if header in COURIER_PAYROLL_FORMULA_COLUMNS:
            row[header] = None
        else:
            row[header] = _lookup_value(lookup, header)
    if row.get("Дата начала смены") in (None, ""):
        row["Дата начала смены"] = report_date.isoformat()
    if row.get("Дата окончания смены") in (None, ""):
        row["Дата окончания смены"] = row["Дата начала смены"]
    return row


def _row_lookup(row: dict[str, Any]) -> dict[str, Any]:
    return {_normalize_key(key): value for key, value in row.items()}


def _lookup_value(lookup: dict[str, Any], header: str) -> Any:
    return _lookup_alias(lookup, (header, *COURIER_PAYROLL_SOURCE_ALIASES.get(header, ())))


def _lookup_alias(lookup: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        value = lookup.get(_normalize_key(alias))
        if value not in (None, ""):
            return value
    return None


def _normalize_key(value: Any) -> str:
    return "".join(char for char in str(value).casefold() if char.isalnum())


def _shift_point(date_value: Any, time_value: Any) -> str:
    return f"{date_value} {time_value}".strip()


def _employee_name(row: dict[str, Any]) -> str:
    parts = [row.get("Фамилия"), row.get("Имя"), row.get("Отчество")]
    return " ".join(str(part).strip() for part in parts if part not in (None, ""))


def _summarize_planned_rows(
    ready: list[dict[str, Any]],
    invalid: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for row in ready:
        name = str(row.get("pizzeria") or "unknown")
        summary = by_name.setdefault(name, {"pizzeria": name, "ready_rows": 0, "invalid_rows": 0})
        summary["ready_rows"] += 1
    for row in invalid:
        name = str(row.get("pizzeria") or "unknown")
        summary = by_name.setdefault(name, {"pizzeria": name, "ready_rows": 0, "invalid_rows": 0})
        summary["invalid_rows"] += 1
    return sorted(by_name.values(), key=lambda item: item["pizzeria"])


def _formula_templates_by_column() -> dict[str, dict[str, str]]:
    return {
        header: {
            "column": _column_letter(COURIER_PAYROLL_HEADERS.index(header) + 1),
            "formula": COURIER_PAYROLL_FORMULA_TEMPLATES[header],
        }
        for header in COURIER_PAYROLL_FORMULA_COLUMNS
    }


def _column_letter(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _normalize(value: Any) -> str:
    return str(value).replace("-", " ").strip().casefold()


def _hash_rows(rows: list[dict[str, Any]]) -> str:
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
