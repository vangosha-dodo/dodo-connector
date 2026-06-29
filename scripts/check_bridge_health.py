#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests
import yaml

from dodo_bridge.config import get_settings


DEFAULT_BASE_URL = "https://dock-translations-investigated-basketball.trycloudflare.com"
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}
DEFAULT_FORBIDDEN_CAPABILITIES = ("courier_orders",)


def count_openapi_operations(schema: dict[str, Any]) -> int:
    paths = schema.get("paths", {})
    if not isinstance(paths, dict):
        return 0
    return sum(
        1
        for path_item in paths.values()
        if isinstance(path_item, dict)
        for method in path_item
        if method.lower() in HTTP_METHODS
    )


def build_report(
    *,
    base_url: str,
    health_payload: dict[str, Any],
    openapi_schema: dict[str, Any],
    capabilities_payload: dict[str, Any],
    max_openapi_operations: int = 30,
    forbidden_capabilities: tuple[str, ...] = DEFAULT_FORBIDDEN_CAPABILITIES,
) -> dict[str, Any]:
    paths = openapi_schema.get("paths", {})
    paths = paths if isinstance(paths, dict) else {}
    operation_count = count_openapi_operations(openapi_schema)
    capability_names = _capability_names(capabilities_payload)
    forbidden_found = sorted(set(capability_names).intersection(forbidden_capabilities))

    checks = [
        {
            "name": "health",
            "ok": health_payload.get("status") == "ok",
            "detail": f"status={health_payload.get('status')}",
        },
        {
            "name": "openapi_operation_limit",
            "ok": operation_count <= max_openapi_operations,
            "detail": f"{operation_count} <= {max_openapi_operations}",
        },
        {
            "name": "mcp_diagnostic_not_in_openapi",
            "ok": "/mcp/capabilities" not in paths,
            "detail": "absent" if "/mcp/capabilities" not in paths else "present",
        },
        {
            "name": "mcp_read_only",
            "ok": capabilities_payload.get("read_only") is True,
            "detail": f"read_only={capabilities_payload.get('read_only')}",
        },
        {
            "name": "forbidden_capabilities_absent",
            "ok": not forbidden_found,
            "detail": ",".join(forbidden_found) if forbidden_found else "absent",
        },
    ]

    summary = {
        "openapi_operations": operation_count,
        "dodo_capabilities": _count_items(capabilities_payload, "dodo_capabilities"),
        "superset_capabilities": _count_items(capabilities_payload, "superset_capabilities"),
        "office_manager_capabilities": _count_items(capabilities_payload, "office_manager_capabilities"),
    }
    return {
        "ok": all(item["ok"] for item in checks),
        "base_url": base_url.rstrip("/"),
        "checks": checks,
        "summary": summary,
    }


def fetch_report(
    *,
    base_url: str,
    api_key: str | None,
    timeout: int,
    max_openapi_operations: int,
) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    headers = _auth_headers(api_key)
    health_payload = _get_json(f"{base_url}/health", headers=headers, timeout=timeout)
    openapi_text = _get_text(f"{base_url}/chatgpt/openapi.yaml", headers=headers, timeout=timeout)
    openapi_schema = yaml.safe_load(openapi_text) or {}
    capabilities_payload = _get_json(f"{base_url}/mcp/capabilities", headers=headers, timeout=timeout)
    return build_report(
        base_url=base_url,
        health_payload=health_payload,
        openapi_schema=openapi_schema,
        capabilities_payload=capabilities_payload,
        max_openapi_operations=max_openapi_operations,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check public Dodo Bridge health after deployment.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Bridge base URL.")
    parser.add_argument("--api-key", help="Bridge API key. Prefer env vars for local use.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds.")
    parser.add_argument("--max-openapi-operations", type=int, default=30)
    parser.add_argument("--json", action="store_true", help="Print the raw JSON report.")
    args = parser.parse_args()

    try:
        report = fetch_report(
            base_url=args.base_url,
            api_key=_resolve_api_key(args.api_key),
            timeout=args.timeout,
            max_openapi_operations=args.max_openapi_operations,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_format_human_report(report))
    return 0 if report["ok"] else 1


def _auth_headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        return {}
    return {
        "Authorization": f"Bearer {api_key}",
        "X-Bridge-Key": api_key,
    }


def _resolve_api_key(cli_api_key: str | None) -> str | None:
    if cli_api_key:
        return cli_api_key
    for env_name in ("DODO_BRIDGE_API_KEY", "DODO_BRIDGE_API_KEYS", "API_KEYS"):
        value = os.environ.get(env_name)
        if value:
            return value.split(",", maxsplit=1)[0].strip()
    try:
        settings = get_settings()
    except Exception:
        return None
    return settings.api_keys[0] if settings.api_keys else None


def _get_json(url: str, *, headers: dict[str, str], timeout: int) -> dict[str, Any]:
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url} returned non-object JSON")
    return payload


def _get_text(url: str, *, headers: dict[str, str], timeout: int) -> str:
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


def _capability_names(payload: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("dodo_capabilities", "superset_capabilities", "office_manager_capabilities"):
        items = payload.get(key, [])
        if isinstance(items, list):
            names.extend(str(item.get("name")) for item in items if isinstance(item, dict) and item.get("name"))
    return names


def _count_items(payload: dict[str, Any], key: str) -> int:
    items = payload.get(key, [])
    return len(items) if isinstance(items, list) else 0


def _format_human_report(report: dict[str, Any]) -> str:
    status = "OK" if report["ok"] else "FAIL"
    lines = [f"{status} Bridge health-check: {report['base_url']}"]
    for item in report["checks"]:
        mark = "OK" if item["ok"] else "FAIL"
        lines.append(f"- {mark} {item['name']}: {item['detail']}")
    summary = report["summary"]
    lines.append(
        "- summary: "
        f"openapi_operations={summary['openapi_operations']}, "
        f"dodo_capabilities={summary['dodo_capabilities']}, "
        f"superset_capabilities={summary['superset_capabilities']}, "
        f"office_manager_capabilities={summary['office_manager_capabilities']}"
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
