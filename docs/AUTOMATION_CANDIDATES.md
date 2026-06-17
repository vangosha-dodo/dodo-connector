# Automation Candidates

Captured on 2026-06-17 from user-provided examples. These are setup notes only:
do not fill or modify the referenced Google Sheets until each automation is
implemented, tested in dry-run mode, and explicitly enabled.

## Safety Boundary

- Current ChatGPT Action surface remains read-only for Dodo IS and Superset.
- These candidates require scheduled jobs and Google Sheets writes.
- Dodo IS should still be treated as read-only: read reports/pages, never modify
  Dodo IS data.
- Google Sheets writes must be idempotent, audited, and scoped to approved tabs
  and columns.
- Every job should support dry-run/preview mode before writes are enabled.

## 1. Courier Payroll Daily Export and Weekly Payment Register

- Priority: highest.
- Spreadsheet: `А-2 Зп курьеров (с 30.03.26)_агент`.
- URL: `https://docs.google.com/spreadsheets/d/1eq81n7NL7hgmSYYm6RRwA1-zlRnsBeXX0QW7uuN2dHU/edit?gid=2112197102#gid=2112197102`.
- Source: Dodo IS Office Manager web interface.
- Source path: `Отчеты -> Заработная плата`.
- Source filters:
  - Select pizzeria.
  - Type: `Курьер`.

### Daily Export

- Target sheet: `Ежедневная выгрузка`.
- Schedule: daily at `00:30 Europe/Moscow`, on the day after the reporting day.
- Required behavior:
  - Read courier payroll report from Dodo IS Office Manager for the reporting day.
  - Append or upsert rows for each approved pizzeria and courier.
  - Avoid duplicates on rerun.
  - Store enough keys to prove idempotency, for example report date, unit,
    courier/person identifier if available, and source row hash.

### Weekly Payment Register

- Target sheet: `Реестр выплат`.
- Schedule: Monday at `06:00 Europe/Moscow`.
- Source sheet: `Ежедневная выгрузка`.
- Period: previous week.
- Required behavior:
  - Fill unique rows for the previous week.
  - Preserve formulas from row 2.
  - Preserve manual correction columns:
    - `Стоимость заказа`
    - `Корректировка`
  - Do not overwrite manual corrections on rerun.

### Implementation Notes

- Start with a read-only extractor and a dry-run diff for both tabs.
- Add a job lock so the daily and weekly jobs cannot overlap.
- Add audit rows with source timestamp, run id, affected range, and row counts.
- This automation likely needs Dodo web-session refresh support similar to the
  existing OpenClaw/OfficeManager authorization flow.

## 2. Dodo Cost Analysis 2026 Rollup

- Spreadsheet: `Анализ затрат ДОДО 2025-2026 dodotm`.
- URL: `https://docs.google.com/spreadsheets/d/13boKjrNUGPnq1tvS0841p23sJYDi0GHDOddq2npOCDw/edit?gid=576555451#gid=576555451`.
- Target sheet: `Общий анализ_2026`.
- Reference sheet: `Общий анализ_2025`.
- Required behavior:
  - Fill `Общий анализ_2026` by analogy with `Общий анализ_2025`.
  - Use corresponding source sheets for 2026 only.
  - Preserve formulas, formatting-sensitive columns, and any manual entries.

### Implementation Notes

- First step is sheet-structure discovery in read-only mode:
  - tabs;
  - headers;
  - formulas in reference row/ranges;
  - source-sheet naming pattern.
- Then generate a dry-run mapping from 2025 logic to 2026 sources.
- Enable writes only after the mapping is reviewed.

## 3. Measurements Change Tracker

- Spreadsheet: `Анализ замеров (робот)`.
- URL: `https://docs.google.com/spreadsheets/d/1RG6-UUK_WKuOMVIwyCnpnJn4ixLyNsZ03GujiW-8uoI/edit?gid=1550618190#gid=1550618190`.
- Target sheet: `Замеры_агент`.
- Reference sheet: `Замеры`.
- Source: Dodo IS Office Manager web interface.
- Source path: `Учет -> Замеры`.
- Schedule: daily.
- Required behavior:
  - Check whether measurements changed.
  - If changed, append a new row to `Замеры_агент`.
  - Mark the new row as `Актуально`.
  - Mark the previous matching record as `Неактуально`.

### Implementation Notes

- Define the identity key for a measurement before enabling writes:
  - likely unit, item/product, measurement type, and effective date/time.
- Store source snapshot hash to avoid duplicate rows on rerun.
- Treat the `Актуально`/`Неактуально` update as a controlled Google Sheets write,
  not a Dodo IS write.

## Proposed Build Order

1. Courier payroll extractor in read-only dry-run mode.
2. Courier payroll daily sheet writer with idempotency and audit.
3. Weekly payment register dry-run and writer.
4. Measurements tracker dry-run and writer.
5. Cost analysis 2026 structure discovery and mapping.

## Open Questions

- Which Google account/service account should own scheduled sheet writes?
- Should these jobs run inside the Bridge service or as a separate worker process?
- What exact pizzeria set applies to each spreadsheet?
- What are the stable keys in the Dodo payroll and measurement pages?
- How long should source snapshots and job audit logs be retained?
