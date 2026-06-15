# Dodo IS Data Functions

These routes are the first ChatGPT-facing data functions. They sit above the
generic `/tools/{tool_name}/invoke` endpoint and expose stable business-readable
operations.

All routes require the bridge API key when `DODO_BRIDGE_API_KEYS` is configured.

## Common Query Parameters

- `units`: comma-separated Dodo unit ids.
- `from`: start date, `YYYY-MM-DD`.
- `to`: end date, `YYYY-MM-DD`.
- `dry_run`: when `true`, returns the planned Dodo API request without calling
  Dodo IS.
- `fields`: optional comma-separated list of row fields to keep.
- `take`: page size for paginated Dodo endpoints.
- `max_pages`: maximum number of pages to fetch.

Period length is capped by `DODO_DATA_MAX_PERIOD_DAYS`.

## Functions

### List Functions

```http
GET /dodo/functions
```

### Courier Orders

```http
GET /dodo/delivery/courier-orders?units=<unit-id>&from=2026-06-01&to=2026-06-02
```

Uses:

```text
GET /dodopizza/{country}/delivery/couriers-orders
```

### Staff Shifts

```http
GET /dodo/staff/shifts?units=<unit-id>&from=2026-06-01&to=2026-06-02&staffTypeName=Courier
```

Uses:

```text
GET /dodopizza/{country}/staff/shifts
```

### Delivery Statistics

```http
GET /dodo/delivery/statistics?units=<unit-id>&from=2026-06-01&to=2026-06-02
```

Uses:

```text
GET /dodopizza/{country}/delivery/statistics
```

### Accounting Sales

```http
GET /dodo/accounting/sales?units=<unit-id>&from=2026-06-01&to=2026-06-02
```

Uses:

```text
GET /dodopizza/{country}/accounting/sales
```

### Product Write-offs

```http
GET /dodo/accounting/writeoffs/products?units=<unit-id>&from=2026-06-01&to=2026-06-02
```

Uses:

```text
GET /dodopizza/{country}/accounting/write-offs/products
```

## Example Dry Run

```http
GET /dodo/accounting/sales?units=unit-1,unit-2&from=2026-06-01&to=2026-06-02&dry_run=true&take=100
```

The response includes the exact Dodo API request URL that would be called.

## Safety

These functions still pass through the registry and policy engine. If a tool is
disabled or removed from `configs/policy.example.yaml`, the corresponding route
returns `403`.

