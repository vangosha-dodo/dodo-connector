#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


class NoAliasSafeDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


COMMON_PERIOD_PARAMETERS: list[dict[str, Any]] = [
    {
        "name": "units",
        "in": "query",
        "required": True,
        "description": "Comma-separated Dodo IS unit ids.",
        "schema": {"type": "string"},
    },
    {
        "name": "from",
        "in": "query",
        "required": True,
        "description": "Start date, inclusive, in YYYY-MM-DD format.",
        "schema": {"type": "string", "format": "date"},
    },
    {
        "name": "to",
        "in": "query",
        "required": True,
        "description": "End date, inclusive, in YYYY-MM-DD format.",
        "schema": {"type": "string", "format": "date"},
    },
    {
        "name": "fields",
        "in": "query",
        "required": False,
        "description": "Optional comma-separated response fields to keep.",
        "schema": {"type": "string"},
    },
    {
        "name": "dry_run",
        "in": "query",
        "required": False,
        "description": "When true, return the planned Dodo IS GET request without calling Dodo IS.",
        "schema": {"type": "boolean", "default": False},
    },
]

PAGINATION_PARAMETERS: list[dict[str, Any]] = [
    {
        "name": "take",
        "in": "query",
        "required": False,
        "description": "Page size for paginated Dodo IS endpoints.",
        "schema": {"type": "integer", "minimum": 1},
    },
    {
        "name": "max_pages",
        "in": "query",
        "required": False,
        "description": "Maximum number of pages to fetch.",
        "schema": {"type": "integer", "minimum": 1},
    },
]


def build_schema(server_url: str) -> dict[str, Any]:
    server_url = server_url.rstrip("/")
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Dodo ChatGPT Bridge Read-Only API",
            "version": "0.1.0",
            "description": (
                "Read-only ChatGPT Action surface for Dodo IS data. "
                "Every business operation is a GET request; no write, update, delete, "
                "admin, auth, feedback, or generic invoke endpoints are exposed."
            ),
        },
        "servers": [{"url": server_url}],
        "security": [{"bearerAuth": []}],
        "paths": {
            "/dodo/functions": {
                "get": {
                    "operationId": "listDodoReadOnlyFunctions",
                    "summary": "List available read-only Dodo IS functions",
                    "description": "Returns the read-only Dodo IS functions exposed to ChatGPT.",
                    "responses": successful_object_response("Available functions."),
                }
            },
            "/dodo/delivery/courier-orders": {
                "get": {
                    "operationId": "getDodoCourierOrders",
                    "summary": "Get courier delivery orders",
                    "description": "Read Dodo IS courier delivery order rows for selected units and period.",
                    "parameters": COMMON_PERIOD_PARAMETERS + PAGINATION_PARAMETERS,
                    "responses": successful_object_response("Courier order rows."),
                }
            },
            "/dodo/staff/shifts": {
                "get": {
                    "operationId": "getDodoStaffShifts",
                    "summary": "Get staff shifts",
                    "description": "Read Dodo IS staff or courier shift rows for selected units and period.",
                    "parameters": COMMON_PERIOD_PARAMETERS
                    + [
                        {
                            "name": "staffTypeName",
                            "in": "query",
                            "required": False,
                            "description": "Dodo staff type name. Use Courier by default.",
                            "schema": {"type": "string", "default": "Courier"},
                        }
                    ]
                    + PAGINATION_PARAMETERS,
                    "responses": successful_object_response("Staff shift rows."),
                }
            },
            "/dodo/delivery/statistics": {
                "get": {
                    "operationId": "getDodoDeliveryStatistics",
                    "summary": "Get delivery statistics",
                    "description": "Read Dodo IS delivery statistics for selected units and period.",
                    "parameters": COMMON_PERIOD_PARAMETERS,
                    "responses": successful_object_response("Delivery statistics rows."),
                }
            },
            "/dodo/accounting/sales": {
                "get": {
                    "operationId": "getDodoAccountingSales",
                    "summary": "Get accounting sales",
                    "description": "Read Dodo IS accounting sales rows for selected units and period.",
                    "parameters": COMMON_PERIOD_PARAMETERS + PAGINATION_PARAMETERS,
                    "responses": successful_object_response("Accounting sales rows."),
                }
            },
            "/dodo/accounting/writeoffs/products": {
                "get": {
                    "operationId": "getDodoAccountingProductWriteoffs",
                    "summary": "Get product write-offs",
                    "description": "Read Dodo IS product write-off rows for selected units and period.",
                    "parameters": COMMON_PERIOD_PARAMETERS + PAGINATION_PARAMETERS,
                    "responses": successful_object_response("Product write-off rows."),
                }
            },
        },
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Bridge API key sent as Authorization: Bearer <key>.",
                }
            },
            "schemas": {
                "BridgeObjectResponse": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "JSON object returned by the Bridge. Row fields depend on the Dodo IS endpoint.",
                }
            },
        },
    }


def successful_object_response(description: str) -> dict[str, Any]:
    return {
        "200": {
            "description": description,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/BridgeObjectResponse"}
                }
            },
        },
        "401": {"description": "Invalid or missing Bridge API key."},
        "403": {"description": "The function is blocked by Bridge policy."},
        "422": {"description": "Invalid query parameters."},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the filtered OpenAPI schema for ChatGPT Actions.")
    parser.add_argument("--server-url", required=True, help="Public Bridge base URL.")
    parser.add_argument("--output", type=Path, required=True, help="Output YAML file.")
    args = parser.parse_args()

    schema = build_schema(args.server_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.dump(schema, Dumper=NoAliasSafeDumper, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
