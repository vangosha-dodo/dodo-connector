# Architecture Notes

## Why a Tool Registry

We do not know the final set of useful Dodo IS/Superset functions yet. The
registry lets us add candidates cheaply while keeping them disabled until they
are reviewed.

Each tool has:

- name and description;
- connector: `dodo`, `superset`, or `internal`;
- HTTP method/path for external connectors;
- risk level: `read`, `write`, or `admin`;
- enabled flag;
- optional response-size and query-parameter constraints.

## Why Policy Is Separate

Policy answers a different question than the registry:

- registry: "Can this tool exist?"
- policy: "May this actor call it now?"

The default policy denies anything not explicitly allowed. This is important
because Postman/Superset imports can create many candidates that should not be
available to ChatGPT.

## Learning Without Unsafe Autonomy

The learning loop analyzes audit events and feedback, then emits recommendations
such as:

- "This denied read tool was requested often; consider enabling it."
- "This tool returned large payloads; add a response filter."
- "This tool has negative feedback; consider requiring approval."

It does not modify config files. Changes remain human-reviewed git commits.

## Superset Boundary

Superset helps with analytics: dashboards, chart data, datasets, and saved
queries. It does not replace the Dodo IS API for operational actions.

For Superset 4.1.1, prefer REST API or a community MCP adapter. Keep arbitrary
SQL disabled until database/table permissions and row-level security are clear.

