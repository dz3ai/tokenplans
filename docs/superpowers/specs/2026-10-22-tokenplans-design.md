# tokenplans — Design

**Date:** 2026-10-22
**Status:** Approved design, pending implementation plan

## 1. Overview

A local web application (dashboard) for managing AI token plans: accounts, API
keys, and credit balances across multiple providers, plus generation of agent
configuration files and cost-aware routing recommendations.

- Runs locally on the user's machine (`localhost`).
- Single user.
- Data stays local in SQLite.

## 2. Goals & scope

### v1 scope

1. **Track** providers, accounts (API keys), and credit balances in one database.
2. **Generate configuration files** for supported agent tools.
3. **Recommend** which provider/account/model to use for a task, to work smarter
   across many agents at managed cost (suggestions only — no proxy).

### Out of scope for v1 (future roadmap)

- **Active routing gateway** (LiteLLM-style local proxy that auto-routes
  requests). The design must not preclude adding this later.
- **MCP endpoint** — expose config loading and operations over Model Context
  Protocol so agents can query the app instead of reading files. Will be a thin
  adapter over the existing service layer.
- **Agent skill endpoint** — ship a `SKILL.md`-style document + a
  `profiles validate` command so an agent can learn to operate the app and add
  new agent templates (declarative YAML, no code).

## 3. Tech stack

- **Python 3.12** + **FastAPI** (REST API + serves static frontend).
- **SQLite** for storage (no ORM required; use `sqlite3` stdlib or SQLAlchemy —
  decide in plan).
- **APScheduler** for background balance polling.
- **cryptography (Fernet)** for API key encryption at rest.
- **Lightweight frontend:** vanilla JS + fetch + minimal CSS, no build step,
  served by FastAPI from `web/`.
- **pytest** for testing; implementation follows **Test-Driven Development**.

## 4. Architecture

Single FastAPI process, layered:

```
web (static UI)
   │ fetch/JSON
REST API (/api/...)
   │
service layer (providers, agents, balance, recommend, secrets, db)
   │
SQLite + profile files (YAML) + plugins (Python hooks)
```

Providers and agents are defined **declaratively** as YAML profiles, with an
optional Python plugin hook for the minority of cases that need custom logic
(unusual auth, balance parsing, or config formats). 80% of providers/agents are
pure data; weird cases get code only where needed. This scales to 30+ agents
with near-zero per-agent code.

## 5. Data model (SQLite)

| Table | Purpose |
|---|---|
| `providers` | Identity only: `id`, `name`, `slug`, `notes` |
| `endpoints` | One provider → many endpoints. Each has `id`, `provider_id`, `name`, `api_type` (`openai` \| `anthropic`), `base_url`, auth header scheme, balance-query config |
| `accounts` | Credentials (encrypted API key) belonging to a provider. Many per provider. Optional `endpoint_scope` (which endpoints this key is valid for; empty = all). Also `label`, `extra` |
| `balances` | Time series: `account_id`, `value`, `unit`, `source` (`auto` \| `manual`), `timestamp` |
| `models` | Belong to an **endpoint**: `id`, `endpoint_id`, `model_id`, `pricing_in`, `pricing_out` (per 1M tokens), `capabilities` (coding/research/vision/…), quality/speed ratings |
| `agents` | `id`, `name`, `slug`, `api_type` preference, config strategy (files/env/both) |
| `bindings` | agent → **account + endpoint + model** (drives config generation) |
| `usage` | Optional manual spend/top-up log to reconcile balances |

### Endpoints example

```
Qwen
 ├─ "OpenAI-compatible"    → openai    base_url (DashScope compatible-mode)
 └─ "Anthropic-compatible" → anthropic base_url (Qwen coding endpoint)

Zhipu
 ├─ "Coding plan"   → anthropic
 └─ "token plan"    → openai
```

### Account switching

Switching accounts for a provider = update the affected `bindings`' `account_id`
and regenerate configs. A quick action updates every binding for a provider and
regenerates all affected configs in one click. Old balances are retained.

## 6. Provider profiles (declarative YAML)

One file per provider describing endpoints, auth, balance query, and models:

```yaml
# profiles/providers/qwen.yaml
name: Qwen
endpoints:
  - id: qwen-openai
    name: "OpenAI-compatible"
    api_type: openai
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    auth: bearer
  - id: qwen-anthropic
    name: "Anthropic-compatible"
    api_type: anthropic
    base_url: https://dashscope.aliyuncs.com/api/anthropic
    auth: x-api-key
balance:
  endpoint: qwen-openai
  path: /api/v1/quota
  response_path: data.available
models:
  - qwen-max: {in: 1.6, out: 6.4, capabilities: [coding, research]}
```

## 7. Agent profiles (declarative YAML)

Each declares what files and env vars it reads, and which API type it speaks:

```yaml
# profiles/agents/claude-code.yaml
name: Claude Code
api_type: anthropic
files:
  - path: ~/.claude/settings.json
    template: |
      { "env": { "ANTHROPIC_BASE_URL": "{{ endpoint.base_url }}",
                 "ANTHROPIC_API_KEY": "{{ account.key }}" } }
env:
  - ANTHROPIC_BASE_URL = {{ endpoint.base_url }}
  - ANTHROPIC_API_KEY = {{ account.key }}
```

Any agent not expressible via templates (e.g. `hermes`) gets a plugin hook.
Adding a new agent = adding a YAML profile (no code).

## 8. Config generation

Flow: pick a binding → render templates → **preview/diff** → **apply** (write to
disk with backup of the prior file). Also support "generate shell snippet" for
agents that use exported env vars. Written config files contain the real API key
(agents need it); the UI only ever shows masked keys.

## 9. Secrets

- API keys encrypted in SQLite with Fernet (AES).
- Master key at `~/.tokenplans/key`, permissions `0600`.
- Missing/wrong master key → clear actionable error.

## 10. Balance polling (auto + manual)

- APScheduler polls each account's balance endpoint at a per-provider interval.
- Append each reading to `balances` (`source=auto`).
- Manual entry writes `source=manual`; when manual override is enabled, auto
  polling is paused for that account.
- Poll failures record `last_error` and surface a status badge (`ok`/`stale`/
  `error`); never fatal.

## 11. Routing recommendations

Input: task type (`coding`/`research`/`chat`) + preference
(`cheapest`/`balanced`/`best`).

Scoring: filter by capability match → drop accounts below balance floor or in
`error` state → rank by effective cost (price per 1M tokens × expected usage)
plus quality/speed ratings.

Output: top recommendation + 2–3 alternatives, each with estimated cost.
Suggestions only; applying one creates/updates a binding and regenerates configs.

## 12. Error handling

- Provider/balance failures: recorded, surfaced as status, never fatal.
- Config apply: atomic write + backup; revert available.
- Expired/invalid credentials (short-lived tokens): marked `error`, prompt to
  refresh.
- Secrets errors: clear, actionable messages.

## 13. Testing (TDD)

Implementation follows Test-Driven Development: write a failing test, make it
pass, refactor.

- Unit tests (`pytest`):
  - Profile loading & validation (including `profiles validate` CLI).
  - Config rendering (golden files).
  - Recommendation scoring.
  - Balance parsing against mocked provider responses.
  - Secrets encryption/decryption round-trip.
- Integration tests: SQLite test DB + FastAPI `TestClient`.
- `profiles validate` command doubles as the hook for the future agent skill.

## 14. Project layout

```
tokenplans/
├─ pyproject.toml
├─ tokenplans/
│  ├─ app.py              # FastAPI app + routes
│  ├─ db.py               # SQLite + migrations
│  ├─ secrets.py          # Fernet encryption + master key
│  ├─ providers/          # registry + profile loader + plugin hooks
│  ├─ agents/             # registry + config renderer
│  ├─ balance/            # background poller
│  ├─ recommend/          # scoring engine
│  ├─ profiles/
│  │  ├─ providers/*.yaml # declarative provider profiles
│  │  └─ agents/*.yaml    # declarative agent profiles
│  ├─ plugins/            # custom Python for odd cases
│  └─ web/                # static HTML/JS/CSS (no build step)
└─ tests/
```

## 15. Future roadmap (not built in v1)

1. **Routing gateway** — local proxy that auto-routes to cheapest/live provider.
2. **MCP endpoint** — agents load configs / operate via MCP over the service
   layer.
3. **Agent skill endpoint** — `SKILL.md` + `profiles validate` for agents to
   learn to add templates.

All three are enabled by v1's declarative profiles + clean service layer +
versioned REST API.
