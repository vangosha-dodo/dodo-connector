# OpenClaw Task Review

Reviewed on 2026-06-14 via read-only SSH access to `ubuntu@92.243.27.224`.

Secrets were not read. The review used process lists, OpenClaw task metadata,
cron metadata, skill descriptions, script paths, and sanitized/export metadata.

## Evidence Sources

- OpenClaw process: `/home/ubuntu/.npm-global/lib/node_modules/openclaw/dist/index.js gateway --port 18789`.
- OpenClaw state DB: `/home/ubuntu/.openclaw/state/openclaw.sqlite`.
- OpenClaw task table: `task_runs`, 15 recent task records.
- Cron jobs:
  - `Daily Dodo IS auth refresh`;
  - `CVM влияние: ежедневный перенос из Google Sheets`;
  - `Доля продаж через киоски: ежемесячная выгрузка`;
  - `Клиенты с телефоном: ежемесячная выгрузка`.
- Skill: `/home/ubuntu/.openclaw/plugin-skills/dodo-courier-report/SKILL.md`.
- Skill proposals:
  - `dodo-auth-session-refresh`;
  - `dodo-client-delivery-time`;
  - `dodo-employee-discount`.
- Export hints:
  - `tambov1_slices_sales_writeoffs_2026-06-10_raw.json`;
  - `discount_employee_recompute_from_dodo_segment_jan_may_2026.json`;
  - `superset_employee_discount_evidence_2026-06-11/...`;
  - `dodo_measurements_tambov_2026-06-10_raw.json`.

## Observed OpenClaw Workflows

### 1. Courier Delivery Reports

OpenClaw has a dedicated `dodo-courier-report` skill. It refreshes courier names,
pulls Dodo API data, builds summaries/recommendations, generates XLSX, and can
publish typed values to Google Sheets.

Observed Dodo API dependencies:

- `GET /dodopizza/{country}/delivery/couriers-orders`
- `GET /dodopizza/{country}/staff/shifts`
- `GET /dodopizza/{country}/delivery/statistics`

Bridge decision: expose the three read-only API calls first. Report-building and
Google Sheets writing remain separate application logic.

### 2. Sales and Write-off Slice Analysis

OpenClaw export `tambov1_slices_sales_writeoffs_2026-06-10_raw.json` identifies
the source as `Dodo API accounting/sales + accounting/write-offs/products`.

Observed Dodo API dependencies:

- `GET /dodopizza/{country}/accounting/sales`
- `GET /dodopizza/{country}/accounting/write-offs/products`

Bridge decision: expose both as read-only first. Any sheet update/apply workflow
must remain outside ChatGPT tool access until reviewed.

### 3. Employee Discount Reconciliation

OpenClaw proposals and exports show repeated employee-discount work for Jan-May
2026. A sanitized Superset evidence file identifies:

- path: `/api/v1/chart/data?dashboard_id=1410`
- dashboard id: `1410`
- chart id: `26708`
- metric: `employee_segment_discount`

Bridge decision: expose a constrained Superset chart-data tool for only this
known dashboard/chart/metric. Do not expose arbitrary Superset SQL or generic
chart-data payloads.

### 4. Monthly Kiosk Sales Share

OpenClaw cron job `Доля продаж через киоски` uses Superset
`ordres_types_analytics` and the metric `Share sales via Kiosk`, then writes to a
marketing Google Sheet.

Bridge decision: keep as a candidate until dashboard/chart ids are captured.
Writing to Google Sheets is not part of the first ChatGPT bridge surface.

### 5. Monthly Clients With Phone

OpenClaw cron job `Клиенты с телефоном` uses Superset `Client_analytics` and the
metric `Share of dine in identified orders via cashier`, then writes to a
marketing Google Sheet.

Bridge decision: keep as a candidate until dashboard/chart ids are captured.
Writing to Google Sheets is not part of the first ChatGPT bridge surface.

### 6. Dodo IS Auth Session Refresh

OpenClaw daily task checks OfficeManager/admin Dodo IS sessions, refreshes
cookies, and handles MFA state. It uses pages such as:

- OfficeManager `EmployeeList`;
- admin `Infrastructure/Authenticate/Structure`.

Bridge decision: keep this restricted and disabled as a ChatGPT business tool.
The bridge now provides a separate internal `/auth/dodo` web flow for a human to
refresh sessions and enter the email MFA code. It remains outside the LLM tool
registry because it touches saved browser sessions, cookies, MFA, and admin
context.

### 7. Measurements / Shop Window / UI Workflows

Artifacts such as `dodo_measurements_tambov_2026-06-10_raw.json` and
`shopwindow_*` snapshots show browser/UI-driven operational work.

Bridge decision: backlog only. These need separate review because they may be
admin/UI actions rather than stable read-only API calls.

## First Active Tools

The first bridge allowlist is now:

- `dodo_delivery_courier_orders`
- `dodo_staff_shifts`
- `dodo_delivery_statistics`
- `dodo_accounting_sales`
- `dodo_accounting_writeoffs_products`
- `superset_employee_discount_chart`

## Candidate / Restricted Tools

- `superset_kiosk_sales_share`: candidate, needs captured dashboard/chart id.
- `superset_clients_phone_share`: candidate, needs captured dashboard/chart id.
- `dodo_auth_session_status`: restricted, disabled.
- `dodo_create_write_off`: restricted write operation, disabled.
