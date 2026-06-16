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

RATINGS_PARAMETERS: list[dict[str, Any]] = [
    {
        "name": "units",
        "in": "query",
        "required": False,
        "description": "Comma-separated Dodo unit ids. Provide this or countryCode.",
        "schema": {"type": "string"},
    },
    {
        "name": "countryCode",
        "in": "query",
        "required": False,
        "description": "Dodo country code. Provide this or units.",
        "schema": {"type": "integer"},
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
        "description": "When true, return the planned Dodo API GET request without calling Dodo IS.",
        "schema": {"type": "boolean", "default": False},
    },
    {
        "name": "take",
        "in": "query",
        "required": False,
        "description": "Optional page size for the ratings feed.",
        "schema": {"type": "integer", "minimum": 1},
    },
    {
        "name": "max_pages",
        "in": "query",
        "required": False,
        "description": "Maximum number of pages to fetch from the ratings feed.",
        "schema": {"type": "integer", "minimum": 1},
    },
]

MONTH_GOALS_PARAMETERS: list[dict[str, Any]] = [
    {
        "name": "unit",
        "in": "query",
        "required": True,
        "description": "Dodo unit id.",
        "schema": {"type": "string"},
    },
    {
        "name": "month",
        "in": "query",
        "required": True,
        "description": "Month number, 1-12.",
        "schema": {"type": "integer", "minimum": 1, "maximum": 12},
    },
    {
        "name": "year",
        "in": "query",
        "required": True,
        "description": "Calendar year.",
        "schema": {"type": "integer", "minimum": 2000, "maximum": 2100},
    },
    {
        "name": "dry_run",
        "in": "query",
        "required": False,
        "description": "When true, return the planned Dodo IS GET request without calling Dodo IS.",
        "schema": {"type": "boolean", "default": False},
    },
]

OPTIONAL_UNIT_COUNTRY_PARAMETERS: list[dict[str, Any]] = [
    {
        "name": "units",
        "in": "query",
        "required": False,
        "description": "Optional comma-separated Dodo unit ids.",
        "schema": {"type": "string"},
    },
    {
        "name": "countryCode",
        "in": "query",
        "required": False,
        "description": "Optional Dodo country code.",
        "schema": {"type": "integer"},
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
        "description": "When true, return the planned Dodo API GET request without calling Dodo IS.",
        "schema": {"type": "boolean", "default": False},
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
                "Business operations do not write to Dodo IS. The system endpoint only records "
                "internal Bridge backlog entries for missing read-only capabilities; no admin, "
                "auth, feedback, or generic invoke endpoints are exposed."
            ),
        },
        "servers": [{"url": server_url}],
        "security": [{"bearerAuth": []}],
        "paths": {
            "/analytics/employee-discount": {
                "post": {
                    "operationId": "getEmployeeDiscount",
                    "summary": "Get employee discount from Superset",
                    "description": (
                        "Return employee discount totals from the approved Superset recipe. "
                        "Use this for questions like employee discount by pizzeria and period."
                    ),
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/EmployeeDiscountRequest"}
                            }
                        },
                    },
                    "responses": successful_response(
                        "Employee discount summary.",
                        "#/components/schemas/EmployeeDiscountResponse",
                    ),
                }
            },
            "/analytics/kiosk-sales-share": {
                "post": {
                    "operationId": "getKioskSalesShare",
                    "summary": "Get kiosk sales share from Superset",
                    "description": (
                        "Read-only approved Superset recipe for monthly dine-in sales share via kiosks. "
                        "Does not write to Dodo IS, Superset, or Google Sheets."
                    ),
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/KioskSalesShareRequest"}
                            }
                        },
                    },
                    "responses": successful_response(
                        "Kiosk sales share by unit.",
                        "#/components/schemas/KioskSalesShareResponse",
                    ),
                }
            },
            "/system/missing-capability": {
                "post": {
                    "operationId": "reportMissingCapability",
                    "summary": "Report a missing read-only capability",
                    "description": (
                        "Record an internal Bridge backlog entry when the user asks for data "
                        "that is not covered by the current approved read-only actions. "
                        "This never changes Dodo IS or Superset data."
                    ),
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/MissingCapabilityRequest"}
                            }
                        },
                    },
                    "responses": successful_response(
                        "Missing capability backlog entry.",
                        "#/components/schemas/MissingCapabilityResponse",
                    ),
                }
            },
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
                            "name": "query",
                            "in": "query",
                            "required": False,
                            "description": "Alias for search. Use this for user-provided pizzeria text.",
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
            "/dodo/ratings/customer-experience": {
                "get": {
                    "operationId": "getDodoCustomerExperienceRatings",
                    "summary": "Get customer experience ratings",
                    "description": (
                        "Read Dodo IS customer experience ratings by unit or by country. "
                        "Provide either units or countryCode."
                    ),
                    "parameters": RATINGS_PARAMETERS,
                    "responses": data_response("Customer experience rating rows."),
                }
            },
            "/dodo/ratings/standards": {
                "get": {
                    "operationId": "getDodoStandardsRatings",
                    "summary": "Get standards ratings",
                    "description": (
                        "Read Dodo IS standards ratings by unit or by country. "
                        "Provide either units or countryCode."
                    ),
                    "parameters": RATINGS_PARAMETERS,
                    "responses": data_response("Standards rating rows."),
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
            "/dodo/staff/vacancies/count": {
                "get": {
                    "operationId": "getDodoStaffVacancyCounts",
                    "summary": "Get staff vacancy counts",
                    "description": "Read Dodo IS open vacancy counts by unit.",
                    "parameters": OPTIONAL_UNIT_COUNTRY_PARAMETERS + PAGINATION_PARAMETERS,
                    "responses": data_response("Staff vacancy count rows."),
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
            "/dodo/accounting/inventory-stocks": {
                "get": {
                    "operationId": "getDodoAccountingInventoryStocks",
                    "summary": "Get inventory stocks",
                    "description": (
                        "Read Dodo IS inventory stock balances for selected units and period."
                    ),
                    "parameters": COMMON_PERIOD_PARAMETERS + PAGINATION_PARAMETERS,
                    "responses": data_response("Inventory stock rows."),
                }
            },
            "/dodo/accounting/stock-consumptions-by-period": {
                "get": {
                    "operationId": "getDodoAccountingStockConsumptionsByPeriod",
                    "summary": "Get stock consumptions by period",
                    "description": (
                        "Read Dodo IS ingredient stock consumption rows for selected units and period."
                    ),
                    "parameters": COMMON_PERIOD_PARAMETERS + PAGINATION_PARAMETERS,
                    "responses": data_response("Stock consumption rows."),
                }
            },
            "/dodo/units/month-goals": {
                "get": {
                    "operationId": "getDodoUnitMonthGoals",
                    "summary": "Get unit month goals",
                    "description": "Read Dodo IS monthly goal values for one unit.",
                    "parameters": MONTH_GOALS_PARAMETERS,
                    "responses": data_response("Unit month goal values."),
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
                "EmployeeDiscountRequest": employee_discount_request_schema(),
                "EmployeeDiscountPeriod": employee_discount_period_schema(),
                "EmployeeDiscountResponse": employee_discount_response_schema(),
                "EmployeeDiscountFilters": employee_discount_filters_schema(),
                "EmployeeDiscountSummary": employee_discount_summary_schema(),
                "EmployeeDiscountRow": employee_discount_row_schema(),
                "EmployeeDiscountSupersetMeta": employee_discount_superset_meta_schema(),
                "KioskSalesShareRequest": kiosk_sales_share_request_schema(),
                "KioskSalesShareResponse": kiosk_sales_share_response_schema(),
                "KioskSalesShareFilters": kiosk_sales_share_filters_schema(),
                "KioskSalesShareSummary": kiosk_sales_share_summary_schema(),
                "KioskSalesShareRow": kiosk_sales_share_row_schema(),
                "KioskSalesShareSupersetMeta": kiosk_sales_share_superset_meta_schema(),
                "MissingCapabilityRequest": missing_capability_request_schema(),
                "MissingCapabilityPeriod": missing_capability_period_schema(),
                "MissingCapabilityResponse": missing_capability_response_schema(),
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


def missing_capability_request_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": (
            "Backlog entry for a missing read-only capability. Use only when the current "
            "actions cannot answer the user's data request."
        ),
        "properties": {
            "user_question": {
                "type": "string",
                "description": "Original user request or concise paraphrase.",
                "minLength": 3,
                "maxLength": 2000,
            },
            "requested_capability": {
                "type": "string",
                "description": "Stable snake_case name for the desired capability.",
                "minLength": 3,
                "maxLength": 200,
            },
            "desired_output": {
                "type": "string",
                "description": "Expected output shape, metric, dimensions, or aggregation.",
                "maxLength": 1000,
            },
            "source_type": {
                "type": "string",
                "description": "Best known source for the data.",
                "enum": [
                    "dodo_api",
                    "superset",
                    "web_interface",
                    "google_sheet",
                    "unknown",
                    "other",
                ],
                "default": "unknown",
            },
            "known_source": {
                "type": "string",
                "description": "Known dashboard, report, sheet, URL, or Dodo IS section.",
                "maxLength": 500,
            },
            "unit_names": {
                "type": "array",
                "description": "Human pizzeria names mentioned by the user.",
                "items": {"type": "string"},
                "maxItems": 20,
            },
            "period": {"$ref": "#/components/schemas/MissingCapabilityPeriod"},
            "priority": {
                "type": "string",
                "enum": ["low", "normal", "high"],
                "default": "normal",
            },
            "confidence": {
                "type": "number",
                "description": "Agent confidence that this capability is genuinely missing.",
                "minimum": 0,
                "maximum": 1,
                "default": 0.5,
            },
            "notes": {
                "type": "string",
                "description": "Additional context for maintainers.",
                "maxLength": 2000,
            },
        },
        "required": ["user_question", "requested_capability"],
        "additionalProperties": False,
    }


def missing_capability_period_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Optional period mentioned in the unsupported user request.",
        "properties": {
            "from": {"type": "string", "format": "date"},
            "to": {"type": "string", "format": "date"},
        },
        "additionalProperties": False,
    }


def missing_capability_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Accepted internal Bridge backlog entry. Dodo IS is never modified.",
        "properties": {
            "status": {"type": "string", "enum": ["accepted"]},
            "request_id": {"type": "integer"},
            "audit_id": {"type": "integer"},
            "dodo_is_changed": {
                "type": "boolean",
                "description": "Always false; this action only writes to the Bridge backlog.",
                "const": False,
            },
            "writes": {
                "type": "array",
                "description": "Internal Bridge stores affected by the action.",
                "items": {"type": "string"},
            },
            "next_step": {"type": "string"},
        },
        "required": ["status", "request_id", "audit_id", "dodo_is_changed", "writes"],
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
            "meta": {
                "type": "object",
                "description": "Optional top-level metadata kept from the source response.",
                "properties": {},
                "additionalProperties": True,
            },
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


def employee_discount_request_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Input for the employee discount Superset capability.",
        "properties": {
            "period": {"$ref": "#/components/schemas/EmployeeDiscountPeriod"},
            "unit_names": {
                "type": "array",
                "description": "Superset UnitName values, for example Тамбов-3.",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "group_by": {
                "type": "array",
                "description": "Optional grouping columns.",
                "items": {"type": "string", "enum": ["unit", "action", "promocode"]},
                "default": ["unit", "action", "promocode"],
            },
            "row_limit": {
                "type": "integer",
                "description": "Superset row limit.",
                "minimum": 1,
                "maximum": 50000,
                "default": 50000,
            },
            "dry_run": {
                "type": "boolean",
                "description": "When true, return the planned Superset request without calling Superset.",
                "default": False,
            },
        },
        "required": ["period", "unit_names"],
        "additionalProperties": False,
    }


def employee_discount_period_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Closed date interval in local business dates.",
        "properties": {
            "from": {"type": "string", "format": "date"},
            "to": {"type": "string", "format": "date"},
        },
        "required": ["from", "to"],
        "additionalProperties": False,
    }


def employee_discount_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Employee discount summary returned by the approved Superset recipe.",
        "properties": {
            "status": {"type": "string", "enum": ["ok", "dry_run", "partial", "no_data", "error"]},
            "capability_id": {"type": "string"},
            "source": {"type": "string"},
            "filters": {"$ref": "#/components/schemas/EmployeeDiscountFilters"},
            "summary": {"$ref": "#/components/schemas/EmployeeDiscountSummary"},
            "rows": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/EmployeeDiscountRow"},
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "array", "items": {"type": "string"}},
            "superset": {"$ref": "#/components/schemas/EmployeeDiscountSupersetMeta"},
            "request": {
                "type": "object",
                "description": "Planned Superset request for dry_run responses.",
                "properties": {
                    "method": {"type": "string"},
                    "url": {"type": "string"},
                    "json": {"type": "object", "properties": {}, "additionalProperties": True},
                },
                "additionalProperties": False,
            },
        },
        "required": ["status", "capability_id", "source"],
        "additionalProperties": False,
    }


def employee_discount_filters_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "period": {"$ref": "#/components/schemas/EmployeeDiscountPeriod"},
            "unit_names": {"type": "array", "items": {"type": "string"}},
            "discount_type": {"type": "string"},
        },
        "required": ["period", "unit_names"],
        "additionalProperties": False,
    }


def employee_discount_summary_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "employee_discount_amount": {"type": "number"},
            "sales_without_discount": {"type": "number"},
            "discount_share_of_sales_without_discount_pct": {"type": "number"},
            "rows_count": {"type": "integer"},
        },
        "required": ["employee_discount_amount", "rows_count"],
        "additionalProperties": False,
    }


def employee_discount_row_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "unit_name": {"type": "string"},
            "discount_segment": {"type": "string"},
            "bonus_action_uuid": {"type": "string"},
            "action_name": {"type": "string"},
            "promocode_masked": {"type": "string"},
            "discount_amount": {"type": "number"},
            "sales_without_discount": {"type": "number"},
        },
        "required": ["unit_name", "discount_amount"],
        "additionalProperties": False,
    }


def employee_discount_superset_meta_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "dashboard_id": {"type": "integer"},
            "chart_id": {"type": "integer"},
            "rowcount": {"type": "integer"},
            "is_cached": {"type": "boolean"},
        },
        "required": ["dashboard_id", "chart_id"],
        "additionalProperties": False,
    }


def kiosk_sales_share_request_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Input for the kiosk sales share Superset capability.",
        "properties": {
            "month": {
                "type": "string",
                "description": "Target month in YYYY-MM format.",
                "pattern": r"^\d{4}-\d{2}$",
            },
            "unit_names": {
                "type": "array",
                "description": "Superset UnitName values, for example Тамбов-3.",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "row_limit": {"type": "integer", "minimum": 1, "maximum": 50000, "default": 50000},
            "dry_run": {"type": "boolean", "default": False},
        },
        "required": ["month", "unit_names"],
        "additionalProperties": False,
    }


def kiosk_sales_share_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Read-only kiosk sales share result from the approved Superset chart.",
        "properties": {
            "status": {"type": "string"},
            "capability_id": {"type": "string"},
            "source": {"type": "string"},
            "filters": {"$ref": "#/components/schemas/KioskSalesShareFilters"},
            "summary": {"$ref": "#/components/schemas/KioskSalesShareSummary"},
            "rows": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/KioskSalesShareRow"},
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "array", "items": {"type": "string"}},
            "superset": {"$ref": "#/components/schemas/KioskSalesShareSupersetMeta"},
            "request": {
                "type": "object",
                "description": "Planned Superset request for dry_run responses.",
                "properties": {
                    "method": {"type": "string"},
                    "url": {"type": "string"},
                    "json": {"type": "object", "properties": {}, "additionalProperties": True},
                },
                "additionalProperties": False,
            },
        },
        "required": ["status", "capability_id", "source", "filters", "warnings"],
        "additionalProperties": False,
    }


def kiosk_sales_share_filters_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "month": {"type": "string"},
            "period": {"$ref": "#/components/schemas/EmployeeDiscountPeriod"},
            "unit_names": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["month", "unit_names"],
        "additionalProperties": False,
    }


def kiosk_sales_share_summary_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "rows_count": {"type": "integer"},
            "average_kiosk_sales_share_pct": {"type": "number"},
        },
        "required": ["rows_count"],
        "additionalProperties": False,
    }


def kiosk_sales_share_row_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "unit_name": {"type": "string"},
            "kiosk_sales_share": {"type": "number"},
            "kiosk_sales_share_pct": {"type": "number"},
        },
        "required": ["unit_name"],
        "additionalProperties": False,
    }


def kiosk_sales_share_superset_meta_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "dashboard": {"type": "string"},
            "dashboard_id": {"type": "integer"},
            "chart_id": {"type": "integer"},
            "datasource_id": {"type": "integer"},
            "metric": {"type": "string"},
            "rowcount": {"type": "integer"},
            "is_cached": {"type": "boolean"},
        },
        "required": ["dashboard_id", "chart_id", "datasource_id", "metric"],
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
