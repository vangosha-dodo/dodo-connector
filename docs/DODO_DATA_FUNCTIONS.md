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
- `countryCode`: optional Dodo country code for country-level rating endpoints.

Period length is capped by `DODO_DATA_MAX_PERIOD_DAYS`.

## Functions

### Pizzerias

```http
GET /dodo/pizzerias?search=Архангельск
```

Returns pizzeria names, aliases, and Dodo unit ids. Use this endpoint before
data requests when the user gives a pizzeria name instead of a `units` id.

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

### Staff Vacancy Counts

```http
GET /dodo/staff/vacancies/count?units=<unit-id>
```

Or country-wide:

```http
GET /dodo/staff/vacancies/count?countryCode=643&take=100
```

Uses:

```text
GET /dodopizza/{country}/staff/vacancies/count
```

Returns vacancy rows with `id`, `name`, `address`, `vacanciesCount`,
`location`, `countryId`, and `businessId`.

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

The Bridge accepts `to` as an inclusive user date. This endpoint is translated
to Dodo IS with an exclusive upper bound, so a one-day request like
`from=2026-06-16&to=2026-06-16` calls Dodo with `to=2026-06-17`.

### Inventory Stocks

```http
GET /dodo/accounting/inventory-stocks?units=<unit-id>&from=2026-06-01&to=2026-06-02&take=100
```

Uses:

```text
GET /dodopizza/{country}/accounting/inventory-stocks
```

Returns stock balance rows such as `quantity`, `balanceInMoney`,
`avgWeekdayExpense`, `avgWeekendExpense`, `daysUntilBalanceRunsOut`, and
`calculatedAt`.

### Stock Consumptions By Period

```http
GET /dodo/accounting/stock-consumptions-by-period?units=<unit-id>&from=2026-06-01&to=2026-06-02&take=100
```

Uses:

```text
GET /dodopizza/{country}/accounting/stock-consumptions-by-period
```

Returns ingredient consumption rows such as `unitName`, `consumptionType`,
`stockItemName`, `measurementUnit`, `quantity`, `costWithVat`,
`costWithoutVat`, and `currency`.

### Unit Month Goals

```http
GET /dodo/units/month-goals?unit=<unit-id>&month=6&year=2026
```

Uses:

```text
GET /dodopizza/{country}/units/month-goals
```

Returns monthly target values such as `sales`, `deliverySales`,
`salesPerPerson`, `productsPerPerson`, `leakage`,
`writeOffsDueToDefectiveProduct`, and `defectiveProduct`.

### Customer Experience Rating

```http
GET /dodo/ratings/customer-experience?units=<unit-id>
```

Or country-wide:

```http
GET /dodo/ratings/customer-experience?countryCode=643&take=100
```

Uses:

```text
GET /controlling/ratings/customer-experience
```

Returns `unitRates` plus top-level metadata such as `periodFrom`, `periodTo`,
`publishStatus`, and `publishedAt`.

### Standards Rating

```http
GET /dodo/ratings/standards?units=<unit-id>
```

Or country-wide:

```http
GET /dodo/ratings/standards?countryCode=643&take=100
```

Uses:

```text
GET /controlling/ratings/standards
```

Returns `unitRates` plus top-level metadata such as `periodFrom`, `periodTo`,
`publishStatus`, and `publishedAt`.

## Example Dry Run

```http
GET /dodo/accounting/sales?units=unit-1,unit-2&from=2026-06-01&to=2026-06-02&dry_run=true&take=100
```

The response includes the exact Dodo API request URL that would be called.

## Safety

These functions still pass through the registry and policy engine. If a tool is
disabled or removed from `configs/policy.example.yaml`, the corresponding route
returns `403`.
