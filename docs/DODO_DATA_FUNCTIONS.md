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

The default production catalog lives at `configs/pizzerias.generated.json` and
currently includes 16 pizzerias: Архангельск-1/2/3, Белогорск-1,
Благовещенск-1/2/3, Северодвинск-1/2, Тамбов-1/2/3, and Чита-1/2/3/4.

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

The Bridge accepts `to` as an inclusive user date and sends Dodo IS an exclusive
upper bound for this endpoint.

### Accounting Sales Summary

```http
GET /dodo/accounting/sales/summary?units=<unit-id>&from=2026-06-01&to=2026-06-30
```

Uses the same Dodo IS read-only accounting sales endpoint, but aggregates rows
inside the Bridge and returns compact revenue totals by pizzeria instead of raw
check rows. Prefer this endpoint for ChatGPT requests like "выручка по всем
пиццериям за месяц".

For all configured pizzerias, omit `units`. Provide `units` only when the user
asks for specific pizzerias.

Metrics:

- `salesWithDiscount` - sum of `products[].priceWithDiscount`.
- `salesWithoutDiscount` - sum of `products[].price`.
- `discount` - `salesWithoutDiscount - salesWithDiscount`.
- `orders` - number of accounting sales rows aggregated.

For large periods, the endpoint fetches Dodo pages per pizzeria in parallel.
If `complete=false`, increase `maxPagesPerUnit` or split the period.

Cache modes:

- `cacheMode=auto` - default. Use cached daily pizzeria summaries when all
  requested days are present; fetch missing units live and save daily rows.
- `cacheMode=refresh` - recalculate the requested period live and overwrite
  cached daily summaries.
- `cacheMode=bypass` - ignore cache and do not write cache rows.

The response `source` block shows `dailyRowsHit`, `dailyRowsMissed`,
`cacheWrites`, and `unitsFetchedLive`, so the agent can explain whether the
answer came from cache or live Dodo API reads.

### Accounting Sales Channels Summary

```http
GET /dodo/accounting/sales/channels-summary?from=2026-06-01&to=2026-06-30
```

Uses the same Dodo IS read-only accounting sales endpoint, but groups checks by
`salesChannel` and `orderSource`. Prefer this endpoint for CVM report metrics
based on order volume by restaurant/delivery channel and for kiosk share checks
when Superset is not required.

For all configured pizzerias, omit `units`. For a narrowed report, pass
`units=<unit-id>`.

Returned metrics:

- `salesChannels` - per-pizzeria aggregation by `salesChannel`, for example
  `Dine-in` and `Delivery`.
- `orderSources` - per-pizzeria aggregation by `orderSource`, for example
  `Kiosk`, `MobileApp`, `Website`, `CallCenter`, and `Dine-in`.
- `kioskShare` - kiosk orders/sales and kiosk share of restaurant/all orders.
- `zScores.restaurantOrdersPerDayZScore` - restaurant checks/day z-score versus
  the selected pizzeria set.
- `zScores.deliveryOrdersPerDayZScore` - delivery checks/day z-score versus the
  selected pizzeria set.

This endpoint does not use the daily sales cache because it needs dimensions
that are not stored in the compact revenue cache.

### Accounting Sales Discounts Summary

```http
GET /dodo/accounting/sales/discounts-summary?from=2026-06-01&to=2026-06-30
```

Uses the same Dodo IS read-only accounting sales endpoint, but aggregates
product discounts inside the Bridge. Prefer this endpoint for first-pass CVM
report discount metrics when the task asks for CVM/local/combo/dodocoin/
certificate discount shares by pizzeria.

For all configured pizzerias, omit `units`. For a narrowed report, pass
`units=<unit-id>`.

Returned metrics:

- `total.discountAmount` - total product discount amount.
- `total.discountShareOfSalesWithoutDiscountPercent` - total discount as a
  percent of sales without discount.
- `categories` - heuristic discount buckets such as `cvm`, `local`, `combo`,
  `dodo_coins`, `certificate`, `voucher`, `employee`, `sauces_addons`, and
  `other`.
- `shareOfTotalSalesWithoutDiscountPercent` - category discount as a percent of
  all sales without discount.
- `discountPercentOfCategorySalesWithoutDiscount` - category discount as a
  percent of products that fell into this category.

Optional flags:

- `includeActions=true` - include top source Dodo discount actions under each
  category.
- `topActionsLimit=10` - maximum action rows per category.

The category label is a transparent heuristic from Dodo action names and masked
promocode metadata. Use `includeActions=true` to inspect source action names.
For exact parity with the Google Sheet `Дисконт` tab, add a dedicated approved
Superset recipe.

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

### Product Write-offs Summary

```http
GET /dodo/accounting/writeoffs/products/summary?from=2026-06-01&to=2026-06-02&productNamePrefix=Кус
```

Uses the same Dodo IS read-only product write-off endpoint, then aggregates
inside the Bridge by pizzeria. Prefer this endpoint for broad ChatGPT requests
like "списания кусочков по всем пиццериям", because it returns compact totals
instead of raw rows and avoids `ResponseTooLargeError`.

For specific pizzerias, pass `units=<unit-id>`. Without `units`, the Bridge uses
the configured pizzeria catalog.

Optional flags:

- `includeProducts=true` - include product breakdown by pizzeria.
- `includeReasons=true` - include reason breakdown by pizzeria.

### Slice Write-off Rate

```http
GET /dodo/accounting/slices/writeoff-rate?from=2026-06-01&to=2026-06-02&productNamePrefix=Кус
```

Uses read-only Dodo IS product write-offs plus accounting sales. The Bridge
counts sales products whose name starts with `productNamePrefix`, then computes:

```text
laidOutQuantity = soldQuantity + writeoffQuantity
writeoffPercent = writeoffQuantity / laidOutQuantity * 100
```

Use this for questions like "списания кусочков в процентах от выложенного
количества". The endpoint returns compact totals by pizzeria and does not
return raw sales or write-off rows.

For all configured pizzerias, omit `units`. For a narrowed report, pass
`units=<unit-id>`.

Optional flag:

- `includeProducts=true` - include per-product percentages inside each pizzeria.

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
