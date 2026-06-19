# CVM Report Metrics

Source report: Google Sheet `Маркетинг - отчётность dodotm`, sheet `CVM влияние`.

## Primary Metrics From The Report

The sheet combines pizzeria/month dimensions with these source indicators:

- new client share;
- 30-day churn share;
- restaurant checks/day z-score;
- delivery checks/day z-score;
- city penetration;
- delivery zone penetration;
- 28-day load metrics: kitchen productivity, courier orders/hour, stop time,
  delivery certificates, restaurant handover time, courier travel time, heat
  shelf time;
- one-week load metrics with the same structure;
- local discount and CVM discount;
- discount category shares from the `Дисконт` tab.

## Implementation Priority

1. Accounting sales by channel and source.
   - Implemented as `GET /dodo/accounting/sales/channels-summary`.
   - Covers restaurant checks/day z-score, delivery checks/day z-score, kiosk
     order/source share, and supporting sales/order breakdowns.
   - Source: read-only Dodo IS `accounting/sales`.
2. Discount category summary.
   - Implemented as `GET /dodo/accounting/sales/discounts-summary`.
   - Covers a first-pass read-only classification for CVM/local/combo/coins/
     certificates/employee/other discount shares from Dodo sales product
     discount metadata.
   - Caveat: category labels are heuristic. Exact parity with the Google Sheet
     `Дисконт` tab still needs an approved Superset discount recipe.
3. Client metrics.
   - Needed for new client share and 30-day churn.
   - Direct Dodo API probe for `orders/clients-statistics` returned
     `InsufficientScopes`; the current token needs the `orders` scope or a
     Superset/web extraction recipe.
4. Production/load metrics.
   - Needed for kitchen productivity, handover time, and heat shelf time.
   - Direct Dodo API probes for production endpoints returned
     `InsufficientScopes`; the current token needs `productionefficiency` scope
     or Superset/web extraction recipes.
5. Courier productivity.
   - Needed for courier orders/hour and travel time.
   - Candidate source: delivery/courier endpoints plus staff shifts, but date
     behavior and token access need a focused verification pass.

## Read-Only Boundary

All report-facing ChatGPT Actions must remain read-only. Filling Google Sheets
or changing Dodo IS remains outside the public ChatGPT Action surface unless a
separate automation path is explicitly enabled.
