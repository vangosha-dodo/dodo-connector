# Dodo ChatGPT Bridge

Service layer for connecting ChatGPT to Dodo IS and Superset without routing every
request through OpenClaw.

The bridge is intentionally conservative:

- tools are declared in YAML and denied by default;
- every invocation is audited;
- write/admin tools require explicit approval;
- the learning loop produces recommendations, but never changes policy by itself.

## MVP Architecture

```text
ChatGPT Action / MCP client
        |
        v
Dodo ChatGPT Bridge
  - API key guard
  - tool registry
  - policy engine
  - audit log
  - learning recommendations
        |
        +--> Dodo IS API
        |
        +--> Superset REST API
```

## Local Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
uvicorn dodo_bridge.main:app --reload
```

OpenAPI is exposed at `http://127.0.0.1:8000/docs`.

## First Useful Endpoints

- `GET /health` - service status.
- `GET /tools` - declared tools and policy state.
- `POST /tools/{tool_name}/invoke` - invoke a tool or dry-run it.
- `POST /feedback` - attach human feedback to an audit event.
- `GET /learning/recommendations` - policy/tooling recommendations from audit data.

## First Tool Set

The initial allowlist is derived from real OpenClaw tasks rather than guesses.
See `docs/OPENCLAW_TASKS.md`.

Active tools:

- Dodo courier orders, staff shifts, and delivery statistics;
- Dodo accounting sales and product write-offs;
- constrained Superset employee-discount chart data.

## Implementation Principle

The bridge learns from usage, denials, errors, and human feedback, but it only
creates recommendations. Enabling a new Dodo/Superset function or relaxing a
restriction must be a deliberate code/config change committed to git.
