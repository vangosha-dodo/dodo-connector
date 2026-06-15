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
        "openapi": "3.1.0",
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
            "/dodo/pizzerias": {
                "get": {
                    "operationId": "listDodoPizzerias",
                    "summary": "List available pizzerias",
                    "description": (
                        "Return pizzeria names, aliases, and Dodo unit ids. "
                        "Use this before data requests when the user names a pizzeria instead of a unit id."
                    ),
                    "parameters": [
                        {
                            "name": "search",
                            "in": "query",
                            "required": False,
                            "description": "Optional pizzeria name, alias, or unit id search.",
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "include_non_pizzerias",
                            "in": "query",
                            "required": False,
                            "description": "When true, include office/production units from the same Dodo catalog.",
                            "schema": {"type": "boolean", "default": False},
                        },
                    ],
                    "responses": successful_response(
                        "Pizzeria catalog.",
                        "#/components/schemas/DodoPizzeriasResponse",
                    ),
                }
            },
            "/dodo/functions": {
                "get": {
                    "operationId": "listDodoReadOnlyFunctions",
                    "summary": "List available read-only Dodo IS functions",
                    "description": "Returns the read-only Dodo IS functions exposed to ChatGPT.",
                    "responses": successful_response(
                        "Available functions.",
                        "#/components/schemas/DodoFunctionsResponse",
                    ),
                }
            },
            "/dodo/delivery/courier-orders": {
                "get": {
                    "operationId": "getDodoCourierOrders",
                    "summary": "Get courier delivery orders",
                    "description": "Read Dodo IS courier delivery order rows for selected units and period.",
                    "parameters": COMMON_PERIOD_PARAMETERS + PAGINATION_PARAMETERS,
                    "responses": data_response("Courier order rows."),
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
                    "responses": data_response("Staff shift rows."),
                }
            },
            "/dodo/delivery/statistics": {
                "get": {
                    "operationId": "getDodoDeliveryStatistics",
                    "summary": "Get delivery statistics",
                    "description": "Read Dodo IS delivery statistics for selected units and period.",
                    "parameters": COMMON_PERIOD_PARAMETERS,
                    "responses": data_response("Delivery statistics rows."),
                }
            },
            "/dodo/accounting/sales": {
                "get": {
                    "operationId": "getDodoAccountingSales",
                    "summary": "Get accounting sales",
                    "description": "Read Dodo IS accounting sales rows for selected units and period.",
                    "parameters": COMMON_PERIOD_PARAMETERS + PAGINATION_PARAMETERS,
                    "responses": data_response("Accounting sales rows."),
                }
            },
            "/dodo/accounting/writeoffs/products": {
                "get": {
                    "operationId": "getDodoAccountingProductWriteoffs",
                    "summary": "Get product write-offs",
                    "description": "Read Dodo IS product write-off rows for selected units and period.",
                    "parameters": COMMON_PERIOD_PARAMETERS + PAGINATION_PARAMETERS,
                    "responses": data_response("Product write-off rows."),
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
                "DodoFunctionsResponse": dodo_functions_response_schema(),
                "DodoFunction": dodo_function_schema(),
                "DodoPizzeriasResponse": dodo_pizzerias_response_schema(),
                "DodoPizzeria": dodo_pizzeria_schema(),
                "DodoDataResponse": dodo_data_response_schema(),
                "DodoRequest": dodo_request_schema(),
                "DodoPagination": dodo_pagination_schema(),
                "DodoRow": dodo_row_schema(),
            },
        },
    }


def data_response(description: str) -> dict[str, Any]:
    return successful_response(description, "#/components/schemas/DodoDataResponse")


def successful_response(description: str, schema_ref: str) -> dict[str, Any]:
    return {
        "200": {
            "description": description,
            "content": {
                "application/json": {
                    "schema": {"$ref": schema_ref}
                }
            },
        },
        "401": {"description": "Invalid or missing Bridge API key."},
        "403": {"description": "The function is blocked by Bridge policy."},
        "422": {"description": "Invalid query parameters."},
    }


def dodo_functions_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "List of Dodo IS read-only functions exposed by the Bridge.",
        "properties": {
            "functions": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/DodoFunction"},
            }
        },
        "required": ["functions"],
        "additionalProperties": False,
    }


def dodo_function_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "One read-only Dodo IS function exposed by the Bridge.",
        "properties": {
            "name": {"type": "string", "description": "Function name for humans and agents."},
            "description": {"type": "string", "description": "Short function description."},
            "tool_name": {"type": "string", "description": "Internal Bridge tool id."},
            "enabled": {"type": "boolean", "description": "Whether the backing tool is enabled."},
            "allowed_by_policy": {"type": "boolean", "description": "Whether Bridge policy allows this function."},
            "paginated": {"type": "boolean", "description": "Whether pagination parameters are supported."},
        },
        "required": ["name", "description", "tool_name", "enabled", "allowed_by_policy", "paginated"],
        "additionalProperties": False,
    }


def dodo_pizzerias_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Pizzeria catalog used to map human names to Dodo IS unit ids.",
        "properties": {
            "pizzerias": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/DodoPizzeria"},
            },
            "count": {"type": "integer", "description": "Number of returned records."},
            "source": {"type": "string", "description": "Catalog source identifier."},
            "include_non_pizzerias": {
                "type": "boolean",
                "description": "Whether office/production units were included.",
            },
        },
        "required": ["pizzerias", "count", "source", "include_non_pizzerias"],
        "additionalProperties": False,
    }


def dodo_pizzeria_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "One Dodo IS unit from the pizzeria catalog.",
        "properties": {
            "unit_id": {"type": "string", "description": "Dodo IS unit id to pass as units parameter."},
            "name": {"type": "string", "description": "Official unit name."},
            "aliases": {
                "type": "array",
                "description": "Name variants useful for matching user wording.",
                "items": {"type": "string"},
            },
            "country_code": {"type": "integer", "description": "Dodo country code."},
            "business_id": {"type": "string", "description": "Dodo business id."},
            "unit_type": {"type": "integer", "description": "Dodo unit type. Type 1 is a pizzeria."},
            "is_pizzeria": {"type": "boolean", "description": "True for normal pizzeria units."},
        },
        "required": [
            "unit_id",
            "name",
            "aliases",
            "country_code",
            "business_id",
            "unit_type",
            "is_pizzeria",
        ],
        "additionalProperties": False,
    }


def dodo_data_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Read-only Dodo IS data response. Dry-run responses contain request instead of rows.",
        "properties": {
            "function": {"type": "string", "description": "Bridge function name."},
            "tool_name": {"type": "string", "description": "Internal Bridge tool id."},
            "dry_run": {"type": "boolean", "description": "True when Dodo IS was not called."},
            "request": {"$ref": "#/components/schemas/DodoRequest"},
            "pagination": {"$ref": "#/components/schemas/DodoPagination"},
            "rows_key": {"type": "string", "description": "Name of the Dodo response field used as rows."},
            "row_count": {"type": "integer", "description": "Number of returned rows."},
            "pages_fetched": {"type": "integer", "description": "Number of fetched pages."},
            "truncated": {"type": "boolean", "description": "True when result was capped by Bridge limits."},
            "next_skip": {"type": "integer", "description": "Skip value for the next page when truncated."},
            "rows": {
                "type": "array",
                "description": "Projected Dodo IS rows. Row fields depend on endpoint and selected fields.",
                "items": {"$ref": "#/components/schemas/DodoRow"},
            },
            "response": {
                "type": "object",
                "description": "Original Dodo IS response payload when Bridge cannot extract rows.",
                "properties": {
                    "payload": {
                        "type": "string",
                        "description": "Optional textual payload summary.",
                    }
                },
                "additionalProperties": True,
            },
            "external_not_configured": {
                "type": "boolean",
                "description": "True when the Dodo connector lacks an access token and returned a dry run.",
            },
        },
        "required": ["function", "tool_name"],
        "additionalProperties": False,
    }


def dodo_request_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Planned outbound Dodo IS request. Present for dry_run responses.",
        "properties": {
            "method": {"type": "string", "description": "HTTP method. Current public functions use GET."},
            "url": {"type": "string", "description": "Dodo IS API URL that would be called."},
        },
        "required": ["method", "url"],
        "additionalProperties": False,
    }


def dodo_pagination_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Pagination settings applied by the Bridge.",
        "properties": {
            "enabled": {"type": "boolean", "description": "Whether endpoint pagination is enabled."},
            "take": {"type": "integer", "description": "Page size used by the Bridge."},
            "max_pages": {"type": "integer", "description": "Maximum pages requested by the Bridge."},
        },
        "required": ["enabled"],
        "additionalProperties": False,
    }


def dodo_row_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "One Dodo IS row. Exact fields depend on endpoint and fields projection.",
        "properties": {
            "id": {
                "type": "string",
                "description": "Optional row id when Dodo IS returns one.",
            }
        },
        "additionalProperties": True,
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
