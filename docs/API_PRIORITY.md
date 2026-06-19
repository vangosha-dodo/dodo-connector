# Dodo API Priority for Management Decisions

Reviewed on 2026-06-16 against the current Bridge code and live Dodo API access.

## Priority Order

1. `customer_experience_rating`
   - Source: `GET /controlling/ratings/customer-experience`
   - Why: direct weekly quality KPI for unit/country management.
   - Status: implemented in Bridge.

2. `standards_rating`
   - Source: `GET /controlling/ratings/standards`
   - Why: operational discipline and audit compliance KPI.
   - Status: implemented in Bridge.

3. `inventory_stocks`
   - Source: `GET /dodopizza/{country}/accounting/inventory-stocks`
   - Why: stock balance, money in stock, and `daysUntilBalanceRunsOut`.
   - Status: implemented in Bridge.

4. `staff_vacancies_count`
   - Source: `GET /dodopizza/{country}/staff/vacancies/count`
   - Why: staffing gaps for recruiting and expansion decisions.
   - Status: implemented in Bridge.

5. `stock_consumptions_by_period`
   - Source: `GET /dodopizza/{country}/accounting/stock-consumptions-by-period`
   - Why: ingredient usage efficiency and anomaly detection.
   - Status: implemented in Bridge.

6. `new_clients_statistics`
   - Source: `GET /dodopizza/{country}/orders/clients-statistics`
   - Why: customer growth and marketing effectiveness.
   - Status: Bridge route added as `GET /dodo/orders/clients-statistics`; current Dodo token is still blocked by missing scope `orders`.

7. `production_orders_handover_time`
   - Source: `GET /dodopizza/{country}/production/orders-handover-time`
   - Why: one of the strongest operational service-speed KPIs.
   - Status: Bridge route added as `GET /dodo/production/orders-handover-time`; current Dodo token is still blocked by missing scope `productionefficiency`.

8. `production_productivity`
   - Source: `GET /dodopizza/{country}/production/productivity`
   - Why: kitchen throughput and labor efficiency.
   - Status: Bridge route added as `GET /dodo/production/productivity`; current Dodo token is still blocked by missing scope `productionefficiency`.

9. `staff_schedules_forecast`
   - Source: `GET /dodopizza/{country}/staff/schedules/forecast`
   - Why: labor planning and over/under-staffing prevention.
   - Status: blocked by live `404`; official docs exist, but current access/path needs separate verification.

10. `units_month_goals`
    - Source: `GET /dodopizza/{country}/units/month-goals`
    - Why: plan/fact management and execution tracking.
    - Status: implemented in Bridge.

## Notes

- We are prioritizing endpoints that are both management-useful and safe as read-only.
- Some endpoints are strategically higher-value but currently blocked by token scopes.
- Superset candidates stay separate and will be resumed after the API priority block.
