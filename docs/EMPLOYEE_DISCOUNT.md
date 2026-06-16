# Employee Discount Capability

`POST /analytics/employee-discount` exposes the approved Superset employee
discount recipe as a read-only business capability.

It uses dashboard `1410`, chart `26708`, datasource `3110__table`, filters
`UnitName IN (...)` and `ActionSegmentationAndSource IN ("Сотрудникам")`, and
metrics `Discount` and `SalesWithoutDiscount`.

The recipe is documented in `recipes/get_employee_discount.yml`.

## Example

```http
POST /analytics/employee-discount
Authorization: Bearer <bridge-key>
Content-Type: application/json
```

```json
{
  "period": {"from": "2026-03-01", "to": "2026-03-31"},
  "unit_names": ["Тамбов-3"],
  "group_by": ["unit", "action", "promocode"]
}
```

## Safety

- Read-only.
- Dodo/Superset credentials stay on the Bridge server.
- No guest phones, guest addresses, or employee names are requested.
- If Superset live auth is not configured, use `dry_run=true` to inspect the
  planned request without calling Superset.
