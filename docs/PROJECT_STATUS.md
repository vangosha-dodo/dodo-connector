# Dodo ChatGPT Bridge - project status

Updated: 2026-06-18

## Goal

Build a read-only Bridge between ChatGPT and Dodo IS so the ChatGPT agent can
answer operational and management questions directly from approved data sources
without routing normal requests through OpenClaw.

The public Bridge endpoint is:

```text
https://dock-translations-investigated-basketball.trycloudflare.com
```

The GitHub repository is:

```text
https://github.com/vangosha-dodo/dodo-connector
```

## Current Rule

Everything exposed to ChatGPT must remain read-only.

ChatGPT Action OpenAPI must not expose write/admin/internal automation routes.
Any write-capable automation remains outside the agent surface and requires a
separate explicit enablement path.

## Implemented And Deployed

### Bridge foundation

- FastAPI Bridge service on the Ubuntu server.
- API-key protection for Bridge endpoints.
- Tool registry and policy layer.
- Audit log for Bridge calls.
- Public Cloudflare URL for ChatGPT Action calls.
- OpenAPI export script for ChatGPT Actions.
- GitHub synchronization for the local project.

### Pizzeria catalog

- `GET /dodo/pizzerias`
- Production catalog currently includes 16 pizzerias:
  - Архангельск-1
  - Архангельск-2
  - Архангельск-3
  - Белогорск-1
  - Благовещенск-1
  - Благовещенск-2
  - Благовещенск-3
  - Северодвинск-1
  - Северодвинск-2
  - Тамбов-1
  - Тамбов-2
  - Тамбов-3
  - Чита-1
  - Чита-2
  - Чита-3
  - Чита-4

### Dodo API read-only endpoints

- `GET /dodo/functions`
- `GET /dodo/delivery/courier-orders`
- `GET /dodo/delivery/statistics`
- `GET /dodo/staff/shifts`
- `GET /dodo/staff/vacancies/count`
- `GET /dodo/accounting/sales`
- `GET /dodo/accounting/sales/summary`
- `GET /dodo/accounting/writeoffs/products`
- `GET /dodo/accounting/writeoffs/products/summary`
- `GET /dodo/accounting/slices/writeoff-rate`
- `GET /dodo/accounting/inventory-stocks`
- `GET /dodo/accounting/stock-consumptions-by-period`
- `GET /dodo/units/month-goals`
- `GET /dodo/ratings/customer-experience`
- `GET /dodo/ratings/standards`

### Compact aggregations for ChatGPT

These endpoints are preferred for agent questions because they return compact
answers instead of huge raw Dodo rows.

- Product write-off summary:
  - `GET /dodo/accounting/writeoffs/products/summary`
  - For questions like "списания кусочков по всем пиццериям".
- Slice write-off rate:
  - `GET /dodo/accounting/slices/writeoff-rate`
  - Computes write-offs as a percent of laid-out quantity.
- Sales revenue summary:
  - `GET /dodo/accounting/sales/summary`
  - For questions like "выручка по всем пиццериям за май 2026".
  - `salesWithDiscount` is computed from `products[].priceWithDiscount`.
  - `salesWithoutDiscount` is computed from `products[].price`.
  - Supports daily SQLite cache modes: `auto`, `refresh`, and `bypass`.

### Superset read-only capabilities

- Employee discount:
  - `POST /analytics/employee-discount`
  - Uses approved Superset chart payloads.
- Kiosk sales share:
  - `POST /analytics/kiosk-sales-share`
  - Uses approved Superset chart payloads.

### Authorization support

- Internal Dodo IS web authorization page:
  - `GET /auth/dodo`
  - Supports session refresh and email MFA code entry.
- This is admin/internal and is not exported to ChatGPT Action schema.

### Learning / missing capability capture

- `POST /system/missing-capability`
- Allows the agent to record a missing read-only capability in the Bridge
  backlog without changing Dodo IS.

## Verified Recently

### Tests

- Local test suite after sales summary changes:
  - `74 passed`
- Server test suite after deployment:
  - `69 passed`

### Live checks

- Public Cloudflare route for `GET /dodo/accounting/sales/summary` returns `200`.
- Small live sales summary query through the public URL returned correct compact
  totals.
- Dodo OAuth token on the server was refreshed and synced into Bridge `.env`.

### Example result

The May 2026 sales summary across all 16 pizzerias was computed from Dodo API
raw accounting sales:

- Sales with discount: `243093174`
- Sales without discount: `269752883`
- Discount: `26659709`
- Raw sales rows aggregated: `235734`
- Product rows aggregated: `926037`
- Dodo pages fetched: `243`

This full-month live computation took about 4 minutes 25 seconds. A daily
SQLite cache has been added so repeated requests can answer from Bridge cache
after the first calculation or scheduled refresh.

## Known Issues And Constraints

- Raw `GET /dodo/accounting/sales` is too heavy for broad month-long questions.
  The agent should use `GET /dodo/accounting/sales/summary` instead.
- Full-month sales summaries are correct but slow without cache.
- Some Dodo API endpoints are blocked by token scopes or may require additional
  role/access review.
- Superset-only metrics require an explicit extraction recipe:
  dashboard, chart, payload, filters, formula, and expected output.
- Some pizzerias can legitimately return zero rows for a period; the Bridge uses
  the pizzeria catalog to keep their names visible.

## Deferred

Google Sheets automations are intentionally paused for now:

- Courier payroll daily export / weekly registry.
- Cost analysis 2026 sheet filling.
- Measurements tracker filling.

The existing dry-run scaffold and technical notes remain in the repository, but
they are not part of the active next steps.

## Active Next Steps

### 1. Warm and schedule the sales summary cache

Goal: make questions like "выручка за май по всем пиццериям" answer in seconds.

Implemented foundation:

- Store daily pizzeria sales summaries in a local Bridge database table.
- Let `GET /dodo/accounting/sales/summary` read from cache when available.
- Return source metadata showing whether the answer came from cache, live Dodo
  API, or mixed mode.

Remaining work:

- Warm the cache for high-value historical periods.
- Add a scheduled refresh job for yesterday / current month.
- Decide cache freshness rules for current-day data.

### 2. Update ChatGPT agent configuration

Goal: make the agent reliably choose compact endpoints.

Actions:

- Upload the latest OpenAPI schema from `outputs/dodo-chatgpt-openapi.yaml`.
- Update the agent prompt:
  - read-only mode is mandatory;
  - use `getDodoAccountingSalesSummary` for revenue;
  - use compact write-off endpoints for broad write-off questions;
  - do not call raw row endpoints for wide monthly questions unless the user
    explicitly asks for raw rows.
- Run a checklist of typical questions.

### 3. Add management aggregations

Priority candidates:

- Revenue, orders, products, average check.
- Discounts by pizzeria and period.
- Write-offs by product/reason/pizzeria.
- Slice write-off rate by pizzeria.
- Channel split: delivery, dine-in, pickup, kiosk where data source is available.
- Period comparison: day/week/month versus previous period or previous year.

### 4. Continue Superset capabilities

Goal: support metrics that Dodo API does not expose directly.

Process for each metric:

- Confirm source dashboard/chart.
- Capture Superset payload.
- Define filters and allowed dimensions.
- Define output schema.
- Add read-only Bridge endpoint.
- Add tests and OpenAPI operation.

Initial candidates:

- Employee discount details.
- Showcase / laid-out quantity metrics if they exist only in Superset.
- Kiosk and cashier identification metrics.

## Next Decision

Recommended next implementation step:

```text
Build the sales summary cache / pre-aggregation layer.
```

Reason: it directly fixes the current slow path and makes the ChatGPT agent much
more reliable for management questions.
