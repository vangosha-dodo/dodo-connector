from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PIZZERIA_UNIT_TYPE = 1


def load_pizzerias(
    path: Path | None,
    *,
    search: str | None = None,
    include_non_pizzerias: bool = False,
) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "pizzerias": [],
            "count": 0,
            "source": "not_configured",
            "include_non_pizzerias": include_non_pizzerias,
        }

    raw_units = _load_units(path)
    units = [_normalize_unit(unit) for unit in raw_units if isinstance(unit, dict)]
    if not include_non_pizzerias:
        units = [unit for unit in units if unit["is_pizzeria"]]

    query = _normalize_search(search)
    if query:
        units = [unit for unit in units if _matches(unit, query)]

    units.sort(key=lambda item: item["name"])
    return {
        "pizzerias": units,
        "count": len(units),
        "source": "dodo_roles_units",
        "include_non_pizzerias": include_non_pizzerias,
    }


def _load_units(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("units", "items", "pizzerias"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _normalize_unit(unit: dict[str, Any]) -> dict[str, Any]:
    name = str(unit.get("name") or "")
    unit_type = unit.get("unitType")
    aliases = _aliases(name)
    return {
        "unit_id": str(unit.get("id") or ""),
        "name": name,
        "aliases": aliases,
        "country_code": unit.get("countryCode"),
        "business_id": unit.get("businessId"),
        "unit_type": unit_type,
        "is_pizzeria": unit_type == PIZZERIA_UNIT_TYPE,
    }


def _aliases(name: str) -> list[str]:
    aliases = {name}
    compact = re.sub(r"\s+", " ", name.replace("_", " ")).strip()
    if compact:
        aliases.add(compact)
        aliases.add(compact.replace("-", " "))
        aliases.add(compact.replace(" ", "-"))

    match = re.match(r"^(.+?)[-\s]+(\d+)$", compact)
    if match:
        city, number = match.groups()
        aliases.add(f"{city} {number}")
        aliases.add(f"{city}-{number}")
        aliases.add(f"{city} номер {number}")
        aliases.add(f"{city} #{number}")

    return sorted(alias for alias in aliases if alias)


def _matches(unit: dict[str, Any], query: str) -> bool:
    haystack = [unit["unit_id"], unit["name"], *unit["aliases"]]
    return any(query in _normalize_search(value) for value in haystack)


def _normalize_search(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.replace("-", " ")).strip().casefold()
