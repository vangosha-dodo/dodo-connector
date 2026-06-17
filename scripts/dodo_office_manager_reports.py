#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import requests


OM_BASE = os.environ.get("DODO_OFFICE_MANAGER_BASE_URL", "https://officemanager.dodois.io")
SECRET_DIR = Path(os.environ.get("DODO_AUTH_SECRET_DIR", "/home/ubuntu/.openclaw/secret"))
SESSION_FILES = [
    item.strip()
    for item in os.environ.get(
        "DODO_OFFICE_MANAGER_SESSION_FILES",
        "officemanager_app_session.json,officemanager_session.json,officemanager_session_checked.json",
    ).split(",")
    if item.strip()
]

RAW_SALARY_HEADERS = (
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
)

NUMERIC_COLUMNS = {
    11,
    12,
    13,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    25,
    26,
    27,
    31,
    32,
    33,
    34,
}


def read_stdin_json() -> dict[str, Any]:
    text = sys.stdin.read().strip()
    return json.loads(text or "{}")


def session_path(filename: str) -> Path:
    path = Path(filename)
    return path if path.is_absolute() else SECRET_DIR / path


def session_cookies(state: dict[str, Any]) -> dict[str, str]:
    source = state.get("cookies", state)
    if not isinstance(source, dict):
        return {}
    return {str(key): str(value) for key, value in source.items() if isinstance(value, str) and value}


def make_session() -> requests.Session:
    errors = []
    for filename in SESSION_FILES:
        path = session_path(filename)
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            session = requests.Session()
            session.headers.update({"User-Agent": "Dodo ChatGPT Bridge OfficeManager read-only helper"})
            requests.utils.add_dict_to_cookiejar(session.cookies, session_cookies(state))
            ensure_auth_to_officemanager(session)
            return session
        except Exception as exc:  # noqa: BLE001 - collect context for all configured session files.
            errors.append(f"{filename}: {exc}")
    raise RuntimeError("No usable Office Manager session file found: " + "; ".join(errors))


def fields_from_form(html_text: str, url: str) -> tuple[str, str, dict[str, str], str] | None:
    form = re.search(r"<form\b([^>]*)>(.*?)</form>", html_text, re.I | re.S)
    if not form:
        return None
    attrs, body = form.group(1), form.group(2)
    action = re.search(r"action=[\"']?([^\"' >]+)", attrs, re.I)
    method = re.search(r"method=[\"']?([^\"' >]+)", attrs, re.I)
    fields = {}
    for input_tag in re.findall(r"<input\b[^>]*>", body, re.I | re.S):
        name = re.search(r"name=[\"']([^\"']+)", input_tag, re.I)
        if name:
            value = re.search(r"value=[\"']([^\"']*)", input_tag, re.I)
            fields[html.unescape(name.group(1))] = html.unescape(value.group(1)) if value else ""
    return (
        urljoin(url, html.unescape(action.group(1))) if action else url,
        method.group(1).upper() if method else "GET",
        fields,
        body,
    )


def submit_form(
    session: requests.Session,
    response: requests.Response,
    extra: dict[str, str],
) -> requests.Response:
    parsed = fields_from_form(response.text, response.url)
    if not parsed:
        raise RuntimeError("form missing")
    action, method, fields, _body = parsed
    fields.update(extra)
    if method == "POST":
        return session.post(action, data=fields, headers={"Referer": response.url}, timeout=45, allow_redirects=True)
    return session.get(action, params=fields, headers={"Referer": response.url}, timeout=45, allow_redirects=True)


def ensure_auth_to_officemanager(session: requests.Session) -> requests.Response:
    response = session.get(OM_BASE + "/", timeout=45, allow_redirects=True)
    for _ in range(7):
        parsed_url = urlparse(response.url)
        if parsed_url.netloc == "officemanager.dodois.io" and parsed_url.path.startswith(
            "/Infrastructure/Authenticate/SelectRole"
        ):
            return response
        if parsed_url.netloc == "officemanager.dodois.io" and parsed_url.path.startswith(
            "/Infrastructure/Authenticate/SelectDepartment"
        ):
            return response
        if parsed_url.netloc == "officemanager.dodois.io" and not parsed_url.path.startswith(
            "/Infrastructure/Authenticate"
        ):
            return response
        parsed = fields_from_form(response.text, response.url)
        if not parsed:
            return response
        _action, _method, fields, _body = parsed
        if "client_id" in fields or "code" in fields:
            response = submit_form(session, response, {})
        else:
            return response
    return response


def get_departments(session: requests.Session) -> list[tuple[str, str]]:
    response = ensure_auth_to_officemanager(session)
    if not urlparse(response.url).path.startswith("/Infrastructure/Authenticate/SelectRole"):
        response = session.get(
            OM_BASE + "/Infrastructure/Authenticate/BackToSelectRole",
            timeout=45,
            allow_redirects=True,
        )
    response = submit_form(session, response, {"roleId": "7"})
    if not urlparse(response.url).path.startswith("/Infrastructure/Authenticate/SelectDepartment"):
        raise RuntimeError("select department page not reached: " + response.url)

    values = []
    for tag in re.findall(r"<(?:input|button)\b[^>]*>", response.text, re.I | re.S):
        if re.search(r"name=[\"']uuid[\"']", tag, re.I):
            value = re.search(r"value=[\"']([^\"']+)", tag, re.I)
            if value:
                values.append(value.group(1))

    plain = re.sub(r"<script.*?</script>|<style.*?</style>", " ", response.text, flags=re.I | re.S)
    plain = re.sub(r"<[^>]+>", "\n", plain)
    labels = [re.sub(r"\s+", " ", html.unescape(item)).strip() for item in plain.splitlines()]
    known_labels = ["Благовещенск", "Тамбов", "Чита", "Архангельск", "Белогорск", "Северодвинск"]
    labels = [item for item in labels if item in known_labels]
    if not labels and len(values) == len(known_labels):
        labels = known_labels
    return list(zip(labels, values))


def select_department(session: requests.Session, department_uuid: str) -> None:
    response = session.get(
        OM_BASE + "/Infrastructure/Authenticate/BackToSelectRole",
        timeout=45,
        allow_redirects=True,
    )
    response = submit_form(session, response, {"roleId": "7"})
    response = submit_form(session, response, {"uuid": department_uuid})
    parsed_url = urlparse(response.url)
    if not (parsed_url.netloc == "officemanager.dodois.io" and response.status_code == 200):
        raise RuntimeError("department select failed")


def om_unit_options(page_html: str) -> list[tuple[str, str]]:
    options = []
    for value, label in re.findall(r"<option\s+value=[\"']([^\"']+)[\"'][^>]*>(.*?)</option>", page_html, re.I | re.S):
        name = re.sub(r"\s+", " ", html.unescape(re.sub("<.*?>", " ", label))).strip()
        if "-" in name and value.isdigit():
            options.append((name, value))
    return options


def parse_xlsx(content: bytes) -> list[list[str]]:
    rows = []
    with zipfile.ZipFile(BytesIO(content)) as archive:
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", ns):
                shared_strings.append("".join(text.text or "" for text in item.findall(".//a:t", ns)))
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

        def column_index(ref: str) -> int:
            match = re.match(r"([A-Z]+)", ref)
            if not match:
                return 0
            number = 0
            for char in match.group(1):
                number = number * 26 + ord(char) - 64
            return number - 1

        for row in sheet.findall(".//a:row", ns):
            values: list[str] = []
            for cell in row.findall("a:c", ns):
                index = column_index(cell.attrib["r"])
                while len(values) <= index:
                    values.append("")
                value_node = cell.find("a:v", ns)
                value = ""
                if value_node is not None:
                    value = value_node.text or ""
                    if cell.attrib.get("t") == "s":
                        value = shared_strings[int(value)]
                values[index] = value
            rows.append(values)
    return rows


def excel_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime(1899, 12, 30) + timedelta(days=float(value))
    except Exception:  # noqa: BLE001 - report exports may contain already-formatted strings.
        return None


def as_date(value: Any) -> str:
    parsed = excel_datetime(value)
    return parsed.strftime("%d.%m.%Y") if parsed else str(value or "")


def as_time(value: Any) -> str:
    parsed = excel_datetime(value)
    return parsed.strftime("%H:%M:%S") if parsed else str(value or "")


def as_number(value: Any) -> Any:
    if value in (None, ""):
        return ""
    text = str(value).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return value
    number = float(text)
    return int(number) if number.is_integer() else number


def salary_row_to_dict(raw: list[str]) -> dict[str, Any]:
    base = list(raw[: len(RAW_SALARY_HEADERS)])
    while len(base) < len(RAW_SALARY_HEADERS):
        base.append("")
    base[0] = as_date(base[0])
    base[1] = as_time(base[1])
    base[2] = as_time(base[2])
    base[3] = as_date(base[3])
    if isinstance(base[4], str):
        base[4] = base[4].lstrip("+")
    for index in NUMERIC_COLUMNS:
        if index < len(base):
            base[index] = as_number(base[index])
    return {header: value for header, value in zip(RAW_SALARY_HEADERS, base)}


def export_salary_rows(payload: dict[str, Any]) -> dict[str, Any]:
    report_date = datetime.fromisoformat(str(payload["report_date"])).date()
    date_text = report_date.strftime("%d.%m.%Y")
    requested_names = {
        str(item.get("name") or "").strip()
        for item in payload.get("pizzerias", [])
        if isinstance(item, dict) and item.get("name")
    }
    if not requested_names:
        raise RuntimeError("payload.pizzerias with names is required")

    session = make_session()
    rows: list[dict[str, Any]] = []
    departments_used: list[str] = []
    units_used: list[str] = []
    not_found = set(requested_names)

    for department_name, department_uuid in get_departments(session):
        select_department(session, department_uuid)
        page = session.get(OM_BASE + "/Reports/Salary", timeout=60)
        page.raise_for_status()
        unit_options = [(name, unit_id) for name, unit_id in om_unit_options(page.text) if name in requested_names]
        if not unit_options:
            continue
        departments_used.append(department_name)
        units_used.extend(name for name, _unit_id in unit_options)
        not_found -= {name for name, _unit_id in unit_options}

        data: list[tuple[str, str]] = [
            ("beginDate", date_text + " "),
            ("endDate", date_text + " 23:59"),
            ("exportType", "0"),
            ("EmployeeName", ""),
            ("GroupedByEmployee", "false"),
            ("beginDatePicker", date_text),
            ("beginTimePicker", ""),
            ("endDatePicker", date_text),
            ("endTimePicker", ""),
            ("EmployeeTypes", "Courier"),
        ]
        for _name, unit_id in unit_options:
            data.append(("unitsIds", unit_id))

        response = session.post(
            OM_BASE + "/Reports/Salary/Export",
            data=data,
            headers={"Referer": OM_BASE + "/Reports/Salary"},
            timeout=180,
        )
        response.raise_for_status()
        if response.content[:2] != b"PK":
            raise RuntimeError(f"Salary export for {department_name} is not XLSX")
        for raw in parse_xlsx(response.content)[4:]:
            if any(raw):
                row = salary_row_to_dict(raw)
                if row.get("Пиццерия") in requested_names:
                    rows.append(row)

    return {
        "ok": True,
        "report_date": report_date.isoformat(),
        "staff_type": "Курьер",
        "departments": departments_used,
        "units": sorted(set(units_used)),
        "missing_units": sorted(not_found),
        "row_count": len(rows),
        "rows": rows,
    }


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DODO_OFFICE_MANAGER_BRIDGE_ACTION", "")
    payload = read_stdin_json()
    if action == "courier-payroll-daily":
        result = export_salary_rows(payload)
    else:
        raise RuntimeError(f"Unknown action: {action}")
    print(json.dumps({"action": action, **result}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - helper protocol returns JSON errors.
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
