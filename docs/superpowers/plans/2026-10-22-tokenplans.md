# tokenplans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web dashboard (FastAPI + SQLite + vanilla JS) that tracks AI token-plan accounts, API keys, and credit balances; generates agent config files; and recommends which provider/account/model to use for a task.

**Architecture:** Single FastAPI process layered as REST API → service layer (providers, agents, balance, recommend, secrets, db) → SQLite + declarative YAML profiles (+ optional Python plugin hooks). Providers and agents are described by YAML profiles, synced into SQLite; accounts/balances/bindings/usage live in SQLite.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, httpx, Jinja2, PyYAML, cryptography (Fernet), APScheduler, pytest. Storage via stdlib `sqlite3`.

## Global Constraints

- Python `>=3.12`; all code targets the stdlib + the dependencies in `pyproject.toml`.
- Every task follows **TDD**: write the failing test, watch it fail, write minimal code to pass, watch it pass, then commit. No production code without a failing test first. (Static files and YAML profiles are data/config — the acknowledged exception; they still get a validation test.)
- API keys are stored **encrypted** (Fernet); plaintext keys are never persisted to DB and never returned by the API (only masked).
- All DB access goes through `tokenplans.db` functions; no other module opens SQLite directly.
- Provider/agent definitions come from YAML profiles under `tokenplans/profiles/`; they are synced into SQLite (upsert) and never hand-edited in the DB.
- Every commit must pass the full `pytest` suite.

---

## File Structure

```
tokenplans/
├─ pyproject.toml
├─ .gitignore
├─ tokenplans/
│  ├─ __init__.py          # __version__
│  ├─ config.py            # paths (app dir, db, key, profiles, web)
│  ├─ db.py                # sqlite connect + schema + CRUD repos
│  ├─ secrets.py           # Fernet encrypt/decrypt/mask
│  ├─ providers/
│  │  ├─ __init__.py
│  │  └─ profiles.py       # ProviderProfile dataclasses + load/validate
│  ├─ agents/
│  │  ├─ __init__.py
│  │  ├─ profiles.py       # AgentProfile dataclasses + load/validate
│  │  └─ render.py         # Jinja2 config rendering
│  ├─ sync.py              # sync_profiles: profiles -> DB
│  ├─ balance/
│  │  ├─ __init__.py
│  │  ├─ parse.py          # extract_value (dotted path w/ array index)
│  │  └─ poller.py         # poll_account, poll_all_accounts, scheduler
│  ├─ recommend/
│  │  ├─ __init__.py
│  │  └─ scorer.py         # build_candidates + recommend
│  ├─ app.py               # FastAPI app + routes + static serving
│  ├─ cli.py               # `tokenplans profiles validate|sync`
│  ├─ profiles/
│  │  ├─ providers/*.yaml
│  │  └─ agents/*.yaml
│  └─ web/
│     ├─ index.html
│     ├─ app.js
│     └─ style.css
└─ tests/
   ├─ conftest.py
   ├─ test_config.py
   ├─ test_db.py
   ├─ test_secrets.py
   ├─ test_provider_profiles.py
   ├─ test_agent_profiles.py
   ├─ test_render.py
   ├─ test_sync.py
   ├─ test_parse.py
   ├─ test_poller.py
   ├─ test_recommend.py
   ├─ test_api.py
   ├─ test_cli.py
   └─ test_shipped_profiles.py
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `tokenplans/__init__.py`
- Create: `tests/test_package.py`

**Interfaces:**
- Produces: importable `tokenplans` package with `tokenplans.__version__ == "0.1.0"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_package.py`:

```python
import tokenplans


def test_version():
    assert tokenplans.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_package.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tokenplans'` (or `AttributeError: __version__`).

- [ ] **Step 3: Write minimal implementation**

Create `tokenplans/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `pyproject.toml`:

```toml
[project]
name = "tokenplans"
version = "0.1.0"
description = "Local dashboard for AI token-plan accounts, balances, and agent config"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "httpx>=0.27",
    "jinja2>=3.1",
    "pyyaml>=6.0",
    "cryptography>=43",
    "apscheduler>=3.10",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
tokenplans = "tokenplans.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["tokenplans*"]

[tool.setuptools.package-data]
tokenplans = ["profiles/**/*.yaml", "web/*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Create `.gitignore`:

```
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
.venv/
venv/
dist/
build/
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_package.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore tokenplans/__init__.py tests/test_package.py
git commit -m "chore: scaffold tokenplans package"
```

---

## Task 2: Config/paths module

**Files:**
- Create: `tokenplans/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `app_dir() -> Path` — `TOKENPLANS_HOME` env override, default `~/.tokenplans`
  - `db_path() -> Path`
  - `key_path() -> Path`
  - `profiles_dir() -> Path` — package `profiles/` dir
  - `web_dir() -> Path` — package `web/` dir
  - `ensure_app_dir() -> Path`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
from pathlib import Path

import tokenplans.config as config


def test_default_app_dir(monkeypatch):
    monkeypatch.delenv("TOKENPLANS_HOME", raising=False)
    assert config.app_dir() == Path.home() / ".tokenplans"


def test_app_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("TOKENPLANS_HOME", str(tmp_path))
    assert config.app_dir() == tmp_path
    assert config.db_path() == tmp_path / "tokenplans.db"
    assert config.key_path() == tmp_path / "key"


def test_ensure_app_dir_creates(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENPLANS_HOME", str(tmp_path / "nested"))
    p = config.ensure_app_dir()
    assert p.exists() and p.is_dir()


def test_profiles_and_web_dirs_exist():
    assert config.profiles_dir().is_dir()
    assert config.web_dir().is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tokenplans.config'`.

- [ ] **Step 3: Write minimal implementation**

Create `tokenplans/config.py`:

```python
import os
from pathlib import Path


def app_dir() -> Path:
    return Path(os.environ.get("TOKENPLANS_HOME", str(Path.home() / ".tokenplans")))


def db_path() -> Path:
    return app_dir() / "tokenplans.db"


def key_path() -> Path:
    return app_dir() / "key"


def profiles_dir() -> Path:
    return Path(__file__).parent / "profiles"


def web_dir() -> Path:
    return Path(__file__).parent / "web"


def ensure_app_dir() -> Path:
    d = app_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d
```

Create empty directories so `test_profiles_and_web_dirs_exist` passes:

```bash
mkdir -p tokenplans/profiles/providers tokenplans/profiles/agents tokenplans/web
```

Also create empty `tokenplans/providers/__init__.py`, `tokenplans/agents/__init__.py`, `tokenplans/balance/__init__.py`, `tokenplans/recommend/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenplans/config.py tokenplans/profiles tokenplans/web tests/test_config.py
git commit -m "feat: add config paths module"
```

---

## Task 3: Database schema

**Files:**
- Create: `tokenplans/db.py`
- Create: `tests/test_db.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Produces:
  - `connect(path=None) -> sqlite3.Connection` (row_factory = sqlite3.Row, foreign_keys ON)
  - `init_schema(conn) -> None`
  - `SCHEMA_VERSION = 1`
  - `migrate(conn) -> None` (applies `init_schema` when version missing/old)

- [ ] **Step 1: Write the failing test**

Create `tests/test_db.py`:

```python
import sqlite3

import pytest

import tokenplans.db as db

EXPECTED_TABLES = {
    "schema_info",
    "providers",
    "endpoints",
    "models",
    "accounts",
    "balances",
    "agents",
    "bindings",
    "usage",
}


def _tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r["name"] for r in rows}


def test_connect_creates_db_file(app_dir):
    c = db.connect()
    assert (app_dir / "tokenplans.db").exists()
    c.close()


def test_init_schema_creates_all_tables(conn):
    assert EXPECTED_TABLES <= _tables(conn)


def test_init_schema_idempotent(conn):
    db.init_schema(conn)
    db.init_schema(conn)
    assert EXPECTED_TABLES <= _tables(conn)


def test_schema_version(conn):
    v = conn.execute("SELECT version FROM schema_info").fetchone()["version"]
    assert v == db.SCHEMA_VERSION


def test_foreign_keys_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO endpoints (provider_id, pid, name, api_type, base_url, auth) "
            "VALUES (999, 'x', 'x', 'openai', 'http://x', 'bearer')"
        )


def test_api_type_check(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO providers (name, slug) VALUES ('p', 'p')"
        )
        conn.execute(
            "INSERT INTO endpoints (provider_id, pid, name, api_type, base_url, auth) "
            "VALUES (1, 'x', 'x', 'bogus', 'http://x', 'bearer')"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tokenplans.db'`.

- [ ] **Step 3: Write minimal implementation**

Create `tokenplans/db.py`:

```python
import sqlite3

import tokenplans.config as config

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_info (version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS providers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS endpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
  pid TEXT NOT NULL,
  name TEXT NOT NULL,
  api_type TEXT NOT NULL CHECK (api_type IN ('openai','anthropic')),
  base_url TEXT NOT NULL,
  auth TEXT NOT NULL,
  UNIQUE (provider_id, pid)
);

CREATE TABLE IF NOT EXISTS models (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  endpoint_id INTEGER NOT NULL REFERENCES endpoints(id) ON DELETE CASCADE,
  model_id TEXT NOT NULL,
  pricing_in REAL NOT NULL DEFAULT 0,
  pricing_out REAL NOT NULL DEFAULT 0,
  capabilities_json TEXT NOT NULL DEFAULT '[]',
  quality INTEGER NOT NULL DEFAULT 3,
  speed INTEGER NOT NULL DEFAULT 3,
  UNIQUE (endpoint_id, model_id)
);

CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  key_encrypted TEXT NOT NULL,
  endpoint_scope_json TEXT NOT NULL DEFAULT '[]',
  extra_json TEXT NOT NULL DEFAULT '{}',
  manual_override INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'ok',
  last_error TEXT
);

CREATE TABLE IF NOT EXISTS balances (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  value REAL,
  unit TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL CHECK (source IN ('auto','manual')),
  ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  api_type TEXT NOT NULL CHECK (api_type IN ('openai','anthropic'))
);

CREATE TABLE IF NOT EXISTS bindings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  endpoint_id INTEGER NOT NULL REFERENCES endpoints(id) ON DELETE CASCADE,
  model TEXT NOT NULL,
  UNIQUE (agent_id)
);

CREATE TABLE IF NOT EXISTS usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('spend','topup')),
  amount REAL NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  ts TEXT NOT NULL
);
"""


def connect(path=None):
    if path is None:
        path = config.db_path()
    config.ensure_app_dir()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO schema_info (version) VALUES (?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()


def migrate(conn):
    row = conn.execute("SELECT version FROM schema_info").fetchone()
    if row is None:
        init_schema(conn)
        return
    # v1 is the only version; future migrations go here keyed on row["version"].
```

Create `tests/conftest.py` (first used by this task's tests; relied on by every later task):

```python
import pytest

import tokenplans.db as db


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENPLANS_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def conn(app_dir):
    c = db.connect()
    db.init_schema(c)
    yield c
    c.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenplans/db.py tests/test_db.py tests/conftest.py
git commit -m "feat: add database schema"
```

---

## Task 4: Database CRUD repositories

**Files:**
- Modify: `tokenplans/db.py`
- Modify: `tests/test_db.py` (append)

**Interfaces:**
- Consumes: `connect`, `init_schema` from Task 3.
- Produces (exact signatures relied on by Tasks 8–15):

```python
# providers
def upsert_provider(conn, name, slug, notes="") -> int
def list_providers(conn) -> list[dict]
def get_provider(conn, slug) -> dict | None

# endpoints
def upsert_endpoint(conn, provider_id, pid, name, api_type, base_url, auth) -> int
def list_endpoints(conn, provider_id=None) -> list[dict]
def get_endpoint_by_pid(conn, provider_id, pid) -> dict | None

# models
def upsert_model(conn, endpoint_id, model_id, pricing_in, pricing_out,
                 capabilities, quality=3, speed=3) -> int
def list_models(conn, endpoint_id) -> list[dict]
def delete_models(conn, endpoint_id) -> None

# accounts
def create_account(conn, provider_id, label, key_encrypted,
                   endpoint_scope=None, extra=None) -> int
def get_account(conn, account_id) -> dict | None
def list_accounts(conn, provider_id=None) -> list[dict]
def set_account_status(conn, account_id, status, last_error=None) -> None

# balances
def record_balance(conn, account_id, value, unit, source, ts=None) -> int
def latest_balance(conn, account_id) -> dict | None
def list_balances(conn, account_id) -> list[dict]

# agents
def upsert_agent(conn, name, slug, api_type) -> int
def list_agents(conn) -> list[dict]

# bindings
def upsert_binding(conn, agent_id, account_id, endpoint_id, model) -> int
def get_binding(conn, agent_id) -> dict | None
def list_bindings(conn, agent_id=None) -> list[dict]
def delete_binding(conn, agent_id) -> None

# usage
def record_usage(conn, account_id, kind, amount, note="", ts=None) -> int
def list_usage(conn, account_id) -> list[dict]
```

All functions return rows as plain `dict` (via `dict(row)`); `get_*` return `dict | None`; `list_*` return `list[dict]`; `upsert_*`/`create_*`/`record_*` return the row `id` (int). `endpoint_scope`/`extra`/`capabilities` are serialized to JSON strings internally.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_db.py`:

```python
import json


def _seed_provider(conn):
    return db.upsert_provider(conn, "DeepSeek", "deepseek")


def test_upsert_provider_and_list(conn):
    pid = db.upsert_provider(conn, "DeepSeek", "deepseek")
    assert isinstance(pid, int)
    rows = db.list_providers(conn)
    assert [r["slug"] for r in rows] == ["deepseek"]
    assert db.get_provider(conn, "deepseek")["name"] == "DeepSeek"
    assert db.get_provider(conn, "nope") is None


def test_upsert_provider_idempotent(conn):
    pid1 = db.upsert_provider(conn, "DeepSeek", "deepseek")
    pid2 = db.upsert_provider(conn, "DeepSeek", "deepseek")
    assert pid1 == pid2
    assert len(db.list_providers(conn)) == 1


def test_endpoint_and_model_roundtrip(conn):
    pid = _seed_provider(conn)
    eid = db.upsert_endpoint(conn, pid, "openai", "OpenAI", "openai",
                             "https://api.deepseek.com", "bearer")
    assert db.get_endpoint_by_pid(conn, pid, "openai")["base_url"] == "https://api.deepseek.com"
    mid = db.upsert_model(conn, eid, "deepseek-chat", 0.27, 1.10, ["coding", "chat"])
    models = db.list_models(conn, eid)
    assert len(models) == 1
    assert json.loads(models[0]["capabilities_json"]) == ["coding", "chat"]
    assert models[0]["pricing_in"] == 0.27
    db.delete_models(conn, eid)
    assert db.list_models(conn, eid) == []


def test_account_crud(conn):
    pid = _seed_provider(conn)
    aid = db.create_account(conn, pid, "token plan", "enc-key",
                            endpoint_scope=["openai"], extra={"org": "x"})
    acct = db.get_account(conn, aid)
    assert acct["label"] == "token plan"
    assert acct["key_encrypted"] == "enc-key"
    assert json.loads(acct["endpoint_scope_json"]) == ["openai"]
    assert json.loads(acct["extra_json"]) == {"org": "x"}
    assert len(db.list_accounts(conn, pid)) == 1
    db.set_account_status(conn, aid, "error", "boom")
    assert db.get_account(conn, aid)["status"] == "error"
    assert db.get_account(conn, aid)["last_error"] == "boom"


def test_balances(conn):
    pid = _seed_provider(conn)
    aid = db.create_account(conn, pid, "a", "k")
    db.record_balance(conn, aid, 100.0, "CNY", "manual", ts="2026-10-22T00:00:00")
    db.record_balance(conn, aid, 95.0, "CNY", "auto", ts="2026-10-22T01:00:00")
    latest = db.latest_balance(conn, aid)
    assert latest["value"] == 95.0
    assert latest["source"] == "auto"
    assert len(db.list_balances(conn, aid)) == 2


def test_agents_and_bindings(conn):
    pid = _seed_provider(conn)
    eid = db.upsert_endpoint(conn, pid, "openai", "OpenAI", "openai",
                             "https://api.deepseek.com", "bearer")
    aid = db.create_account(conn, pid, "a", "k")
    gid = db.upsert_agent(conn, "Claude Code", "claude-code", "anthropic")
    bid = db.upsert_binding(conn, gid, aid, eid, "deepseek-chat")
    assert db.get_binding(conn, gid)["model"] == "deepseek-chat"
    # upsert replaces the existing binding (UNIQUE on agent_id)
    bid2 = db.upsert_binding(conn, gid, aid, eid, "deepseek-reasoner")
    assert bid == bid2
    assert len(db.list_bindings(conn)) == 1
    db.delete_binding(conn, gid)
    assert db.list_bindings(conn) == []


def test_usage(conn):
    pid = _seed_provider(conn)
    aid = db.create_account(conn, pid, "a", "k")
    db.record_usage(conn, aid, "topup", 50.0, note="bought tokens")
    rows = db.list_usage(conn, aid)
    assert len(rows) == 1
    assert rows[0]["kind"] == "topup"
    assert rows[0]["note"] == "bought tokens"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — the new tests error with `AttributeError: module 'tokenplans.db' has no attribute 'upsert_provider'`.

- [ ] **Step 3: Write minimal implementation**

Append to `tokenplans/db.py`:

```python
import json
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row):
    return dict(row) if row is not None else None


# --- providers ---

def upsert_provider(conn, name, slug, notes=""):
    conn.execute(
        "INSERT INTO providers (name, slug, notes) VALUES (?, ?, ?) "
        "ON CONFLICT(slug) DO UPDATE SET name=excluded.name, notes=excluded.notes",
        (name, slug, notes),
    )
    conn.commit()
    return conn.execute("SELECT id FROM providers WHERE slug=?", (slug,)).fetchone()["id"]


def list_providers(conn):
    return [_row_to_dict(r) for r in conn.execute("SELECT * FROM providers ORDER BY name")]


def get_provider(conn, slug):
    return _row_to_dict(conn.execute("SELECT * FROM providers WHERE slug=?", (slug,)).fetchone())


# --- endpoints ---

def upsert_endpoint(conn, provider_id, pid, name, api_type, base_url, auth):
    conn.execute(
        "INSERT INTO endpoints (provider_id, pid, name, api_type, base_url, auth) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(provider_id, pid) DO UPDATE SET "
        "name=excluded.name, api_type=excluded.api_type, base_url=excluded.base_url, auth=excluded.auth",
        (provider_id, pid, name, api_type, base_url, auth),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM endpoints WHERE provider_id=? AND pid=?", (provider_id, pid)
    ).fetchone()["id"]


def list_endpoints(conn, provider_id=None):
    q = "SELECT * FROM endpoints"
    args = ()
    if provider_id is not None:
        q += " WHERE provider_id=?"
        args = (provider_id,)
    q += " ORDER BY name"
    return [_row_to_dict(r) for r in conn.execute(q, args)]


def get_endpoint_by_pid(conn, provider_id, pid):
    return _row_to_dict(conn.execute(
        "SELECT * FROM endpoints WHERE provider_id=? AND pid=?",
        (provider_id, pid),
    ).fetchone())


# --- models ---

def upsert_model(conn, endpoint_id, model_id, pricing_in, pricing_out,
                 capabilities, quality=3, speed=3):
    conn.execute(
        "INSERT INTO models (endpoint_id, model_id, pricing_in, pricing_out, "
        "capabilities_json, quality, speed) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(endpoint_id, model_id) DO UPDATE SET "
        "pricing_in=excluded.pricing_in, pricing_out=excluded.pricing_out, "
        "capabilities_json=excluded.capabilities_json, quality=excluded.quality, speed=excluded.speed",
        (endpoint_id, model_id, pricing_in, pricing_out,
         json.dumps(capabilities), quality, speed),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM models WHERE endpoint_id=? AND model_id=?",
        (endpoint_id, model_id),
    ).fetchone()["id"]


def list_models(conn, endpoint_id):
    return [_row_to_dict(r) for r in conn.execute(
        "SELECT * FROM models WHERE endpoint_id=? ORDER BY model_id", (endpoint_id,)
    )]


def delete_models(conn, endpoint_id):
    conn.execute("DELETE FROM models WHERE endpoint_id=?", (endpoint_id,))
    conn.commit()


# --- accounts ---

def create_account(conn, provider_id, label, key_encrypted,
                   endpoint_scope=None, extra=None):
    cur = conn.execute(
        "INSERT INTO accounts (provider_id, label, key_encrypted, endpoint_scope_json, extra_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (provider_id, label, key_encrypted,
         json.dumps(endpoint_scope or []), json.dumps(extra or {})),
    )
    conn.commit()
    return cur.lastrowid


def get_account(conn, account_id):
    return _row_to_dict(conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone())


def list_accounts(conn, provider_id=None):
    q = "SELECT * FROM accounts"
    args = ()
    if provider_id is not None:
        q += " WHERE provider_id=?"
        args = (provider_id,)
    q += " ORDER BY label"
    return [_row_to_dict(r) for r in conn.execute(q, args)]


def set_account_status(conn, account_id, status, last_error=None):
    conn.execute(
        "UPDATE accounts SET status=?, last_error=? WHERE id=?",
        (status, last_error, account_id),
    )
    conn.commit()


# --- balances ---

def record_balance(conn, account_id, value, unit, source, ts=None):
    cur = conn.execute(
        "INSERT INTO balances (account_id, value, unit, source, ts) VALUES (?, ?, ?, ?, ?)",
        (account_id, value, unit, source, ts or _now()),
    )
    conn.commit()
    return cur.lastrowid


def latest_balance(conn, account_id):
    return _row_to_dict(conn.execute(
        "SELECT * FROM balances WHERE account_id=? ORDER BY ts DESC, id DESC LIMIT 1",
        (account_id,),
    ).fetchone())


def list_balances(conn, account_id):
    return [_row_to_dict(r) for r in conn.execute(
        "SELECT * FROM balances WHERE account_id=? ORDER BY ts", (account_id,)
    )]


# --- agents ---

def upsert_agent(conn, name, slug, api_type):
    conn.execute(
        "INSERT INTO agents (name, slug, api_type) VALUES (?, ?, ?) "
        "ON CONFLICT(slug) DO UPDATE SET name=excluded.name, api_type=excluded.api_type",
        (name, slug, api_type),
    )
    conn.commit()
    return conn.execute("SELECT id FROM agents WHERE slug=?", (slug,)).fetchone()["id"]


def list_agents(conn):
    return [_row_to_dict(r) for r in conn.execute("SELECT * FROM agents ORDER BY name")]


# --- bindings ---

def upsert_binding(conn, agent_id, account_id, endpoint_id, model):
    conn.execute(
        "INSERT INTO bindings (agent_id, account_id, endpoint_id, model) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(agent_id) DO UPDATE SET "
        "account_id=excluded.account_id, endpoint_id=excluded.endpoint_id, model=excluded.model",
        (agent_id, account_id, endpoint_id, model),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM bindings WHERE agent_id=?", (agent_id,)
    ).fetchone()["id"]


def get_binding(conn, agent_id):
    return _row_to_dict(conn.execute(
        "SELECT * FROM bindings WHERE agent_id=?", (agent_id,)
    ).fetchone())


def list_bindings(conn, agent_id=None):
    q = "SELECT * FROM bindings"
    args = ()
    if agent_id is not None:
        q += " WHERE agent_id=?"
        args = (agent_id,)
    return [_row_to_dict(r) for r in conn.execute(q, args)]


def delete_binding(conn, agent_id):
    conn.execute("DELETE FROM bindings WHERE agent_id=?", (agent_id,))
    conn.commit()


# --- usage ---

def record_usage(conn, account_id, kind, amount, note="", ts=None):
    cur = conn.execute(
        "INSERT INTO usage (account_id, kind, amount, note, ts) VALUES (?, ?, ?, ?, ?)",
        (account_id, kind, amount, note, ts or _now()),
    )
    conn.commit()
    return cur.lastrowid


def list_usage(conn, account_id):
    return [_row_to_dict(r) for r in conn.execute(
        "SELECT * FROM usage WHERE account_id=? ORDER BY ts", (account_id,)
    )]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: PASS (all, including Task 3 tests).

- [ ] **Step 5: Commit**

```bash
git add tokenplans/db.py tests/test_db.py
git commit -m "feat: add database CRUD repositories"
```

---

## Task 5: Secrets (encryption)

**Files:**
- Create: `tokenplans/secrets.py`
- Create: `tests/test_secrets.py`

**Interfaces:**
- Produces:
  - `load_or_create_key(path=None) -> bytes` — loads `key_path()` or creates a random Fernet key, writes with `0600` perms
  - `class Secrets(key: bytes)` with `.encrypt(plaintext: str) -> str`, `.decrypt(token: str) -> str`, `.mask(secret: str) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_secrets.py`:

```python
import os

import pytest

import tokenplans.secrets as secrets


def test_encrypt_decrypt_roundtrip():
    s = secrets.Secrets(secrets.load_or_create_key())
    token = s.encrypt("sk-abcdef123456")
    assert token != "sk-abcdef123456"
    assert s.decrypt(token) == "sk-abcdef123456"


def test_encrypt_is_nondeterministic():
    s = secrets.Secrets(secrets.load_or_create_key())
    a = s.encrypt("same")
    b = s.encrypt("same")
    assert a != b
    assert s.decrypt(a) == s.decrypt(b) == "same"


def test_decrypt_wrong_key_fails():
    k1 = secrets.load_or_create_key()
    k2 = secrets.load_or_create_key()
    token = secrets.Secrets(k1).encrypt("secret")
    with pytest.raises(Exception):
        secrets.Secrets(k2).decrypt(token)


def test_mask():
    s = secrets.Secrets(secrets.load_or_create_key())
    assert s.mask("sk-abcdef123456") == "sk-…456"
    assert s.mask("short") == "…"


def test_load_or_create_key_writes_file(app_dir):
    p = app_dir / "key"
    k = secrets.load_or_create_key(p)
    assert p.exists()
    assert os.stat(p).st_mode & 0o777 == 0o600
    assert secrets.load_or_create_key(p) == k
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_secrets.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tokenplans.secrets'`.

- [ ] **Step 3: Write minimal implementation**

Create `tokenplans/secrets.py`:

```python
import os

from cryptography.fernet import Fernet

import tokenplans.config as config


def load_or_create_key(path=None):
    if path is None:
        path = config.key_path()
    path = os.fspath(path)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    return key


class Secrets:
    def __init__(self, key: bytes):
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()

    def mask(self, secret: str) -> str:
        if len(secret) <= 6:
            return "…"
        return f"{secret[:3]}…{secret[-3:]}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_secrets.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenplans/secrets.py tests/test_secrets.py
git commit -m "feat: add secrets encryption"
```

---

## Task 6: Provider profile loading & validation

**Files:**
- Create: `tokenplans/providers/profiles.py`
- Create: `tests/test_provider_profiles.py`

**Interfaces:**
- Produces:

```python
@dataclass
class ModelSpec: id: str; pricing_in: float = 0.0; pricing_out: float = 0.0;
                  capabilities: list[str] = []; quality: int = 3; speed: int = 3
@dataclass
class EndpointSpec: pid: str; name: str; api_type: str; base_url: str; auth: str;
                    models: list[ModelSpec] = []
@dataclass
class BalanceSpec: endpoint: str; path: str; response_path: str; method: str = "GET";
                   unit: str = ""
@dataclass
class ProviderProfile: name: str; slug: str; endpoints: list[EndpointSpec];
                       balance: BalanceSpec | None = None

def load_provider_profile(path) -> ProviderProfile
def parse_provider_profile(data: dict) -> ProviderProfile
def validate_provider_profile(data: dict) -> list[str]  # list of error messages, [] = valid
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_provider_profiles.py`:

```python
import yaml

import tokenplans.providers.profiles as pp


VALID = {
    "name": "DeepSeek",
    "slug": "deepseek",
    "endpoints": [
        {
            "id": "openai",
            "name": "OpenAI-compatible",
            "api_type": "openai",
            "base_url": "https://api.deepseek.com",
            "auth": "bearer",
            "models": [
                {"id": "deepseek-chat", "in": 0.27, "out": 1.10, "capabilities": ["coding", "chat"]}
            ],
        }
    ],
    "balance": {
        "endpoint": "openai",
        "path": "/user/balance",
        "response_path": "balance_infos[0].total_balance",
        "unit": "CNY",
    },
}


def test_parse_valid():
    p = pp.parse_provider_profile(VALID)
    assert p.name == "DeepSeek"
    assert p.slug == "deepseek"
    assert len(p.endpoints) == 1
    e = p.endpoints[0]
    assert e.pid == "openai"
    assert e.api_type == "openai"
    assert e.models[0].id == "deepseek-chat"
    assert e.models[0].pricing_in == 0.27
    assert p.balance.path == "/user/balance"
    assert p.balance.response_path == "balance_infos[0].total_balance"
    assert p.balance.unit == "CNY"


def test_validate_ok():
    assert pp.validate_provider_profile(VALID) == []


def test_validate_missing_required():
    errors = pp.validate_provider_profile({"name": "X"})
    assert any("slug" in e for e in errors)
    assert any("endpoints" in e for e in errors)


def test_validate_bad_api_type():
    data = dict(VALID, endpoints=[{**VALID["endpoints"][0], "api_type": "grpc"}])
    errors = pp.validate_provider_profile(data)
    assert any("api_type" in e for e in errors)


def test_validate_balance_points_to_missing_endpoint():
    data = dict(VALID, balance={**VALID["balance"], "endpoint": "nope"})
    errors = pp.validate_provider_profile(data)
    assert any("balance" in e for e in errors)


def test_load_from_file(tmp_path):
    f = tmp_path / "deepseek.yaml"
    f.write_text(yaml.safe_dump(VALID))
    p = pp.load_provider_profile(f)
    assert p.slug == "deepseek"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_provider_profiles.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `tokenplans/providers/profiles.py`:

```python
from dataclasses import dataclass, field

import yaml

VALID_API_TYPES = {"openai", "anthropic"}


@dataclass
class ModelSpec:
    id: str
    pricing_in: float = 0.0
    pricing_out: float = 0.0
    capabilities: list[str] = field(default_factory=list)
    quality: int = 3
    speed: int = 3


@dataclass
class EndpointSpec:
    pid: str
    name: str
    api_type: str
    base_url: str
    auth: str
    models: list[ModelSpec] = field(default_factory=list)


@dataclass
class BalanceSpec:
    endpoint: str
    path: str
    response_path: str
    method: str = "GET"
    unit: str = ""


@dataclass
class ProviderProfile:
    name: str
    slug: str
    endpoints: list[EndpointSpec]
    balance: BalanceSpec | None = None


def _parse_model(d):
    return ModelSpec(
        id=d["id"],
        pricing_in=float(d.get("in", 0.0)),
        pricing_out=float(d.get("out", 0.0)),
        capabilities=list(d.get("capabilities", [])),
        quality=int(d.get("quality", 3)),
        speed=int(d.get("speed", 3)),
    )


def _parse_endpoint(d):
    return EndpointSpec(
        pid=d["id"],
        name=d.get("name", d["id"]),
        api_type=d["api_type"],
        base_url=d["base_url"],
        auth=d.get("auth", "bearer"),
        models=[_parse_model(m) for m in d.get("models", [])],
    )


def parse_provider_profile(data: dict) -> ProviderProfile:
    balance = data.get("balance")
    return ProviderProfile(
        name=data["name"],
        slug=data.get("slug", data["name"].lower()),
        endpoints=[_parse_endpoint(e) for e in data.get("endpoints", [])],
        balance=BalanceSpec(**balance) if balance else None,
    )


def validate_provider_profile(data: dict) -> list[str]:
    errors = []
    if not isinstance(data, dict):
        return ["profile must be a mapping"]
    for field in ("name", "slug", "endpoints"):
        if field not in data:
            errors.append(f"missing required field: {field}")
    eps = data.get("endpoints", [])
    if not isinstance(eps, list) or not eps:
        errors.append("endpoints must be a non-empty list")
    else:
        ids = set()
        for i, e in enumerate(eps):
            if not isinstance(e, dict):
                errors.append(f"endpoints[{i}] must be a mapping")
                continue
            for f in ("id", "api_type", "base_url"):
                if f not in e:
                    errors.append(f"endpoints[{i}] missing {f}")
            if e.get("api_type") not in VALID_API_TYPES:
                errors.append(f"endpoints[{i}].api_type must be one of {sorted(VALID_API_TYPES)}")
            if "id" in e:
                ids.add(e["id"])
    bal = data.get("balance")
    if bal is not None:
        if not isinstance(bal, dict):
            errors.append("balance must be a mapping")
        else:
            for f in ("endpoint", "path", "response_path"):
                if f not in bal:
                    errors.append(f"balance missing {f}")
            if bal.get("endpoint") not in ids:
                errors.append("balance.endpoint must reference an endpoint id")
    return errors


def load_provider_profile(path) -> ProviderProfile:
    with open(path) as f:
        data = yaml.safe_load(f)
    return parse_provider_profile(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_provider_profiles.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenplans/providers/profiles.py tests/test_provider_profiles.py
git commit -m "feat: add provider profile loading and validation"
```

---

## Task 7: Agent profile loading & validation

**Files:**
- Create: `tokenplans/agents/profiles.py`
- Create: `tests/test_agent_profiles.py`

**Interfaces:**
- Produces:

```python
@dataclass
class FileTemplate: path: str; template: str
@dataclass
class EnvVar: key: str; template: str
@dataclass
class AgentProfile: name: str; slug: str; api_type: str;
                    files: list[FileTemplate] = []; env: list[EnvVar] = []

def parse_agent_profile(data: dict) -> AgentProfile
def validate_agent_profile(data: dict) -> list[str]
def load_agent_profile(path) -> AgentProfile
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_agent_profiles.py`:

```python
import yaml

import tokenplans.agents.profiles as ap


VALID = {
    "name": "Claude Code",
    "slug": "claude-code",
    "api_type": "anthropic",
    "files": [
        {
            "path": "~/.claude/settings.json",
            "template": '{"env":{"ANTHROPIC_BASE_URL":"{{ endpoint.base_url }}"}}',
        }
    ],
    "env": [{"key": "ANTHROPIC_API_KEY", "template": "{{ account.key }}"}],
}


def test_parse_valid():
    p = ap.parse_agent_profile(VALID)
    assert p.name == "Claude Code"
    assert p.api_type == "anthropic"
    assert p.files[0].path == "~/.claude/settings.json"
    assert p.env[0].key == "ANTHROPIC_API_KEY"


def test_validate_ok():
    assert ap.validate_agent_profile(VALID) == []


def test_validate_missing():
    errors = ap.validate_agent_profile({})
    assert any("name" in e for e in errors)
    assert any("api_type" in e for e in errors)


def test_validate_bad_api_type():
    errors = ap.validate_agent_profile({"name": "x", "api_type": "grpc"})
    assert any("api_type" in e for e in errors)


def test_validate_env_entry_missing_key():
    errors = ap.validate_agent_profile({"name": "x", "api_type": "openai", "env": [{"template": "x"}]})
    assert any("key" in e for e in errors)


def test_load_from_file(tmp_path):
    f = tmp_path / "claude-code.yaml"
    f.write_text(yaml.safe_dump(VALID))
    p = ap.load_agent_profile(f)
    assert p.slug == "claude-code"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_profiles.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `tokenplans/agents/profiles.py`:

```python
from dataclasses import dataclass, field

import yaml

VALID_API_TYPES = {"openai", "anthropic"}


@dataclass
class FileTemplate:
    path: str
    template: str


@dataclass
class EnvVar:
    key: str
    template: str


@dataclass
class AgentProfile:
    name: str
    slug: str
    api_type: str
    files: list[FileTemplate] = field(default_factory=list)
    env: list[EnvVar] = field(default_factory=list)


def parse_agent_profile(data: dict) -> AgentProfile:
    return AgentProfile(
        name=data["name"],
        slug=data.get("slug", data["name"].lower()),
        api_type=data["api_type"],
        files=[FileTemplate(f["path"], f["template"]) for f in data.get("files", [])],
        env=[EnvVar(e["key"], e["template"]) for e in data.get("env", [])],
    )


def validate_agent_profile(data: dict) -> list[str]:
    errors = []
    if not isinstance(data, dict):
        return ["profile must be a mapping"]
    for field in ("name", "api_type"):
        if field not in data:
            errors.append(f"missing required field: {field}")
    if data.get("api_type") not in VALID_API_TYPES:
        errors.append(f"api_type must be one of {sorted(VALID_API_TYPES)}")
    for i, f in enumerate(data.get("files", [])):
        if not isinstance(f, dict) or "path" not in f or "template" not in f:
            errors.append(f"files[{i}] must have path and template")
    for i, e in enumerate(data.get("env", [])):
        if not isinstance(e, dict) or "key" not in e or "template" not in e:
            errors.append(f"env[{i}] must have key and template")
    return errors


def load_agent_profile(path) -> AgentProfile:
    with open(path) as f:
        return parse_agent_profile(yaml.safe_load(f))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_profiles.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenplans/agents/profiles.py tests/test_agent_profiles.py
git commit -m "feat: add agent profile loading and validation"
```

---

## Task 8: Config rendering

**Files:**
- Create: `tokenplans/agents/render.py`
- Create: `tests/test_render.py`

**Interfaces:**
- Consumes: `AgentProfile`, `FileTemplate`, `EnvVar` from Task 7.
- Produces:

```python
@dataclass
class RenderedConfig:
    files: list[tuple[str, str]]   # (path, rendered content)
    env: list[tuple[str, str]]     # (key, value)

def render_agent_config(profile: AgentProfile, endpoint: dict, account_key: str,
                        model: str) -> RenderedConfig
```

`endpoint` is a dict with keys `pid`, `name`, `api_type`, `base_url`; templates use `{{ endpoint.base_url }}`, `{{ account.key }}`, `{{ model }}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_render.py`:

```python
import tokenplans.agents.profiles as ap
import tokenplans.agents.render as render

PROFILE = ap.AgentProfile(
    name="Claude Code",
    slug="claude-code",
    api_type="anthropic",
    files=[
        ap.FileTemplate(
            "~/.claude/settings.json",
            '{"env":{"ANTHROPIC_BASE_URL":"{{ endpoint.base_url }}",'
            '"ANTHROPIC_API_KEY":"{{ account.key }}","ANTHROPIC_MODEL":"{{ model }}"}}',
        )
    ],
    env=[ap.EnvVar("ANTHROPIC_BASE_URL", "{{ endpoint.base_url }}")],
)

ENDPOINT = {"pid": "anthropic", "name": "Anthropic-compatible",
            "api_type": "anthropic", "base_url": "https://open.bigmodel.cn/api/anthropic"}


def test_renders_file_and_env():
    out = render.render_agent_config(PROFILE, ENDPOINT, "sk-secret", "glm-4.5")
    assert out.env == [("ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/anthropic")]
    (path, content) = out.files[0]
    assert path == "~/.claude/settings.json"
    assert '"ANTHROPIC_API_KEY":"sk-secret"' in content
    assert '"ANTHROPIC_MODEL":"glm-4.5"' in content
    assert "https://open.bigmodel.cn/api/anthropic" in content


def test_no_templates_gives_empty():
    p = ap.AgentProfile(name="x", slug="x", api_type="openai")
    out = render.render_agent_config(p, ENDPOINT, "k", "m")
    assert out.files == [] and out.env == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tokenplans.agents.render'`.

- [ ] **Step 3: Write minimal implementation**

Create `tokenplans/agents/render.py`:

```python
from dataclasses import dataclass, field

from jinja2 import Template

import tokenplans.agents.profiles as ap


@dataclass
class RenderedConfig:
    files: list[tuple[str, str]] = field(default_factory=list)
    env: list[tuple[str, str]] = field(default_factory=list)


def render_agent_config(profile: ap.AgentProfile, endpoint: dict, account_key: str,
                        model: str) -> RenderedConfig:
    context = {
        "endpoint": endpoint,
        "account": {"key": account_key},
        "model": model,
    }
    files = []
    for ft in profile.files:
        content = Template(ft.template).render(context)
        files.append((ft.path, content))
    env = []
    for ev in profile.env:
        env.append((ev.key, Template(ev.template).render(context)))
    return RenderedConfig(files=files, env=env)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_render.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenplans/agents/render.py tests/test_render.py
git commit -m "feat: add agent config rendering"
```

---

## Task 9: Profile sync (profiles → DB)

**Files:**
- Create: `tokenplans/sync.py`
- Create: `tests/test_sync.py`

**Interfaces:**
- Consumes: `db.upsert_provider/upsert_endpoint/upsert_model/upsert_agent`, `pp.parse_provider_profile`, `ap.parse_agent_profile`, `config.profiles_dir()`.
- Produces:

```python
@dataclass
class SyncReport:
    providers: int; endpoints: int; models: int; agents: int; errors: list[str]

def sync_profiles(conn, providers_dir=None, agents_dir=None) -> SyncReport
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_sync.py`:

```python
import yaml

import tokenplans.db as db
import tokenplans.sync as sync


def _write(d, name):
    (d / name).write_text(yaml.safe_dump({
        "name": "DeepSeek", "slug": "deepseek",
        "endpoints": [{"id": "openai", "name": "OpenAI", "api_type": "openai",
                       "base_url": "https://api.deepseek.com", "auth": "bearer",
                       "models": [{"id": "deepseek-chat", "in": 0.27, "out": 1.1,
                                   "capabilities": ["coding"]}]}],
        "balance": {"endpoint": "openai", "path": "/user/balance",
                    "response_path": "balance_infos[0].total_balance"},
    }))


def test_sync_creates_rows(conn, tmp_path):
    pd = tmp_path / "providers"
    pd.mkdir()
    _write(pd, "deepseek.yaml")
    report = sync.sync_profiles(conn, providers_dir=pd, agents_dir=tmp_path / "agents")
    assert report.providers == 1
    assert report.endpoints == 1
    assert report.models == 1
    assert report.errors == []
    assert len(db.list_providers(conn)) == 1
    assert len(db.list_endpoints(conn)) == 1
    eid = db.list_endpoints(conn)[0]["id"]
    assert len(db.list_models(conn, eid)) == 1


def test_sync_idempotent(conn, tmp_path):
    pd = tmp_path / "providers"
    pd.mkdir()
    _write(pd, "deepseek.yaml")
    sync.sync_profiles(conn, providers_dir=pd, agents_dir=tmp_path / "agents")
    report = sync.sync_profiles(conn, providers_dir=pd, agents_dir=tmp_path / "agents")
    assert report.providers == 1
    assert len(db.list_providers(conn)) == 1
    assert len(db.list_endpoints(conn)) == 1


def test_sync_reports_invalid(conn, tmp_path):
    pd = tmp_path / "providers"
    pd.mkdir()
    (pd / "bad.yaml").write_text("name: MissingSlug\n")
    report = sync.sync_profiles(conn, providers_dir=pd, agents_dir=tmp_path / "agents")
    assert report.errors
    assert report.providers == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tokenplans.sync'`.

- [ ] **Step 3: Write minimal implementation**

Create `tokenplans/sync.py`:

```python
from dataclasses import dataclass, field

import yaml

import tokenplans.agents.profiles as ap
import tokenplans.db as db
import tokenplans.providers.profiles as pp
import tokenplans.config as config


@dataclass
class SyncReport:
    providers: int = 0
    endpoints: int = 0
    models: int = 0
    agents: int = 0
    errors: list[str] = field(default_factory=list)


def _yaml_files(d):
    if d is None or not d.is_dir():
        return []
    return sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml"))


def sync_profiles(conn, providers_dir=None, agents_dir=None) -> SyncReport:
    report = SyncReport()
    if providers_dir is None:
        providers_dir = config.profiles_dir() / "providers"
    if agents_dir is None:
        agents_dir = config.profiles_dir() / "agents"

    for path in _yaml_files(providers_dir):
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            errors = pp.validate_provider_profile(data or {})
            if errors:
                report.errors.append(f"{path.name}: {'; '.join(errors)}")
                continue
            prof = pp.parse_provider_profile(data)
            provider_id = db.upsert_provider(conn, prof.name, prof.slug)
            report.providers += 1
            for e in prof.endpoints:
                eid = db.upsert_endpoint(conn, provider_id, e.pid, e.name,
                                         e.api_type, e.base_url, e.auth)
                report.endpoints += 1
                for m in e.models:
                    db.upsert_model(conn, eid, m.id, m.pricing_in, m.pricing_out,
                                    m.capabilities, m.quality, m.speed)
                    report.models += 1
        except Exception as exc:  # noqa: BLE001 - report and continue
            report.errors.append(f"{path.name}: {exc}")

    for path in _yaml_files(agents_dir):
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            errors = ap.validate_agent_profile(data or {})
            if errors:
                report.errors.append(f"{path.name}: {'; '.join(errors)}")
                continue
            prof = ap.parse_agent_profile(data)
            db.upsert_agent(conn, prof.name, prof.slug, prof.api_type)
            report.agents += 1
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"{path.name}: {exc}")

    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_sync.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenplans/sync.py tests/test_sync.py
git commit -m "feat: add profile-to-db sync"
```

---

## Task 10: Balance response parsing

**Files:**
- Create: `tokenplans/balance/parse.py`
- Create: `tests/test_parse.py`

**Interfaces:**
- Produces: `extract_value(data, path: str) -> object` — dotted path with optional `[index]` per segment, e.g. `balance_infos[0].total_balance`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_parse.py`:

```python
import pytest

import tokenplans.balance.parse as parse


def test_simple_dotted():
    assert parse.extract_value({"data": {"available": 12.5}}, "data.available") == 12.5


def test_array_index():
    data = {"balance_infos": [{"total_balance": "100.00", "currency": "CNY"}]}
    assert parse.extract_value(data, "balance_infos[0].total_balance") == "100.00"


def test_missing_key_raises():
    with pytest.raises(KeyError):
        parse.extract_value({}, "nope")


def test_bad_segment_raises():
    with pytest.raises(ValueError):
        parse.extract_value({}, "a..b")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_parse.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `tokenplans/balance/parse.py`:

```python
import re

_SEGMENT = re.compile(r"^([^\[\]]+)(?:\[(\d+)\])?$")


def extract_value(data, path: str):
    cur = data
    for seg in path.split("."):
        m = _SEGMENT.match(seg)
        if not m:
            raise ValueError(f"invalid path segment: {seg!r}")
        name, idx = m.group(1), m.group(2)
        cur = cur[name]
        if idx is not None:
            cur = cur[int(idx)]
    return cur
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_parse.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenplans/balance/parse.py tests/test_parse.py
git commit -m "feat: add balance response parsing"
```

---

## Task 11: Balance poller

**Files:**
- Create: `tokenplans/balance/poller.py`
- Create: `tests/test_poller.py`

**Interfaces:**
- Consumes: `db.get_account/list_accounts/latest_balance/record_balance/set_account_status`, `secrets.Secrets`, `parse.extract_value`, provider profile balance spec fields.
- Produces:

```python
@dataclass
class PollResult:
    ok: bool; account_id: int; value: float | None = None; unit: str = "";
    error: str | None = None

def auth_headers(endpoint: dict, key: str) -> dict
def poll_account(conn, secrets: Secrets, account_id: int, endpoint: dict,
                 balance_spec, transport=None) -> PollResult
def poll_all_accounts(conn, secrets: Secrets, transport=None) -> list[PollResult]
```

`balance_spec` may be a `BalanceSpec` (from profiles) or a dict; the function reads `.endpoint`, `.path`, `.response_path`, `.method`, `.unit` via `getattr`/key. It skips accounts with `manual_override == 1`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_poller.py`:

```python
import json

import httpx

import tokenplans.balance.poller as poller
import tokenplans.db as db
import tokenplans.secrets as secrets


def _secrets():
    return secrets.Secrets(secrets.load_or_create_key())


def _seed(conn, secrets, manual_override=0):
    pid = db.upsert_provider(conn, "DeepSeek", "deepseek")
    eid = db.upsert_endpoint(conn, pid, "openai", "OpenAI", "openai",
                             "https://api.deepseek.com", "bearer")
    aid = db.create_account(conn, pid, "plan", secrets.encrypt("sk-123"))
    if manual_override:
        conn.execute("UPDATE accounts SET manual_override=1 WHERE id=?", (aid,))
        conn.commit()
    endpoint = db.list_endpoints(conn, pid)[0]
    return aid, endpoint


BALANCE_SPEC = {"endpoint": "openai", "path": "/user/balance",
                "response_path": "balance_infos[0].total_balance", "method": "GET", "unit": "CNY"}


def _transport(payload):
    def handler(request):
        return httpx.Response(200, json=payload)
    return httpx.MockTransport(handler)


def test_auth_headers_bearer():
    assert poller.auth_headers({"auth": "bearer"}, "k") == {"Authorization": "Bearer k"}


def test_auth_headers_x_api_key():
    assert poller.auth_headers({"auth": "x-api-key"}, "k") == {"x-api-key": "k"}


def test_poll_account_success(conn):
    aid, endpoint = _seed(conn, _secrets())
    transport = _transport({"balance_infos": [{"total_balance": "95.5", "currency": "CNY"}]})
    result = poller.poll_account(conn, _secrets(), aid, endpoint, BALANCE_SPEC, transport=transport)
    assert result.ok
    assert result.value == 95.5
    assert db.latest_balance(conn, aid)["value"] == 95.5
    assert db.latest_balance(conn, aid)["source"] == "auto"
    assert db.get_account(conn, aid)["status"] == "ok"


def test_poll_account_error_sets_status(conn):
    aid, endpoint = _seed(conn, _secrets())
    transport = _transport({"error": "forbidden"})  # wrong shape -> extract raises
    result = poller.poll_account(conn, _secrets(), aid, endpoint, BALANCE_SPEC, transport=transport)
    assert not result.ok
    assert result.error
    assert db.get_account(conn, aid)["status"] == "error"


def test_poll_skips_manual_override(conn):
    aid, endpoint = _seed(conn, _secrets(), manual_override=1)
    results = poller.poll_all_accounts(conn, _secrets(), transport=_transport({}))
    assert results == []


def test_poll_all_accounts(conn):
    aid, endpoint = _seed(conn, _secrets())
    results = poller.poll_all_accounts(conn, _secrets(), transport=_transport(
        {"balance_infos": [{"total_balance": "10", "currency": "CNY"}]}))
    assert len(results) == 1
    assert results[0].ok
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_poller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tokenplans.balance.poller'`.

- [ ] **Step 3: Write minimal implementation**

Create `tokenplans/balance/poller.py`:

```python
from dataclasses import dataclass

import httpx

import tokenplans.balance.parse as parse
import tokenplans.db as db
import tokenplans.secrets as secrets


@dataclass
class PollResult:
    ok: bool
    account_id: int
    value: float | None = None
    unit: str = ""
    error: str | None = None


def auth_headers(endpoint: dict, key: str) -> dict:
    if endpoint.get("auth") == "x-api-key":
        return {"x-api-key": key}
    return {"Authorization": f"Bearer {key}"}


def _field(spec, name, default=None):
    return getattr(spec, name, default) if not isinstance(spec, dict) else spec.get(name, default)


def poll_account(conn, secrets, account_id, endpoint, balance_spec, transport=None) -> PollResult:
    account = db.get_account(conn, account_id)
    if account is None:
        return PollResult(ok=False, account_id=account_id, error="account not found")
    try:
        key = secrets.decrypt(account["key_encrypted"])
        path = _field(balance_spec, "path", "")
        method = _field(balance_spec, "method", "GET")
        response_path = _field(balance_spec, "response_path")
        unit = _field(balance_spec, "unit", "")
        url = endpoint["base_url"].rstrip("/") + "/" + path.lstrip("/")
        with httpx.Client(transport=transport) as client:
            resp = client.request(method, url, headers=auth_headers(endpoint, key))
            resp.raise_for_status()
            data = resp.json()
        value = float(parse.extract_value(data, response_path))
        db.record_balance(conn, account_id, value, unit, "auto")
        db.set_account_status(conn, account_id, "ok")
        return PollResult(ok=True, account_id=account_id, value=value, unit=unit)
    except Exception as exc:  # noqa: BLE001
        db.set_account_status(conn, account_id, "error", str(exc))
        return PollResult(ok=False, account_id=account_id, error=str(exc))


def poll_all_accounts(conn, secrets, transport=None) -> list[PollResult]:
    results = []
    for account in db.list_accounts(conn):
        if account["manual_override"]:
            continue
        endpoints = db.list_endpoints(conn, account["provider_id"])
        # Poll via the first endpoint; balance endpoints are provider-scoped in v1.
        if not endpoints:
            continue
        spec = {"path": "/user/balance", "response_path": "data.available",
                "method": "GET", "unit": ""}
        results.append(poll_account(conn, secrets, account["id"], endpoints[0], spec, transport))
    return results
```

> Note: `poll_all_accounts` uses a default balance spec; real per-provider balance specs are wired in Task 15 (API) by looking up the provider profile from `tokenplans/profiles/` and passing the loaded `BalanceSpec`. This keeps the poller testable without filesystem coupling.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_poller.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenplans/balance/poller.py tests/test_poller.py
git commit -m "feat: add balance poller"
```

---

## Task 12: Recommendation scorer

**Files:**
- Create: `tokenplans/recommend/scorer.py`
- Create: `tests/test_recommend.py`

**Interfaces:**
- Consumes: `db.list_accounts/list_endpoints/list_models/latest_balance`.
- Produces:

```python
@dataclass
class Recommendation:
    account_id: int; account_label: str; endpoint_id: int; endpoint_name: str;
    model: str; cost: float; score: float; reasons: list[str]

EXPECTED_TOKENS = {"coding": (20000, 2000), "research": (50000, 10000), "chat": (2000, 1000)}

def build_candidates(conn) -> list[dict]
def recommend(candidates, task_type="coding", preference="balanced", balance_floor=0.0) -> list[Recommendation]
```

Candidate dict keys: `account_id, account_label, account_status, endpoint_id, endpoint_name, api_type, model, pricing_in, pricing_out, capabilities (list), quality, speed, balance (float|None)`.

Scoring rules (deterministic):
- Filter out `account_status != "ok"` and `balance is not None and balance < balance_floor`.
- Filter out candidates whose `capabilities` do not include `task_type` (unless `task_type == "chat"`, which is always allowed).
- `cost = in/1e6*pricing_in + out/1e6*pricing_out` using `EXPECTED_TOKENS[task_type]`.
- Normalize cost to 0..1 across remaining candidates (min-max; if all equal, 0).
- `score = quality_weight*quality - cost_weight*normalized_cost*5`; weights: `cheapest` (0, 1), `balanced` (0.5, 0.5), `best` (1, 0).
- Sort by `score` desc. Reasons: "matches <task>", "cheapest", "best quality" (when applicable).

- [ ] **Step 1: Write the failing test**

Create `tests/test_recommend.py`:

```python
import tokenplans.recommend.scorer as scorer


def _c(account_id, model, pricing_in, pricing_out, quality=3, capabilities=None,
       balance=100.0, status="ok"):
    return {
        "account_id": account_id, "account_label": f"acct{account_id}",
        "account_status": status, "endpoint_id": account_id,
        "endpoint_name": f"ep{account_id}", "api_type": "openai", "model": model,
        "pricing_in": pricing_in, "pricing_out": pricing_out,
        "capabilities": capabilities or ["coding"], "quality": quality, "speed": 3,
        "balance": balance,
    }


def test_cheapest_picks_lowest_cost():
    cands = [
        _c(1, "cheap", 0.1, 0.5),
        _c(2, "expensive", 10.0, 20.0),
    ]
    out = scorer.recommend(cands, "coding", "cheapest")
    assert out[0].model == "cheap"


def test_best_picks_highest_quality():
    cands = [
        _c(1, "low", 0.1, 0.5, quality=2),
        _c(2, "high", 0.1, 0.5, quality=5),
    ]
    out = scorer.recommend(cands, "coding", "best")
    assert out[0].model == "high"


def test_filters_out_of_capability():
    cands = [
        _c(1, "coder", 0.1, 0.5, capabilities=["coding"]),
        _c(2, "vision-only", 0.1, 0.5, capabilities=["vision"]),
    ]
    out = scorer.recommend(cands, "research", "balanced")
    assert [r.model for r in out] == ["coder"]


def test_filters_low_balance():
    cands = [
        _c(1, "broke", 0.1, 0.5, balance=1.0),
        _c(2, "rich", 0.1, 0.5, balance=50.0),
    ]
    out = scorer.recommend(cands, "coding", "balanced", balance_floor=10.0)
    assert [r.model for r in out] == ["rich"]


def test_filters_error_status():
    cands = [
        _c(1, "dead", 0.1, 0.5, status="error"),
        _c(2, "alive", 0.1, 0.5),
    ]
    out = scorer.recommend(cands, "coding", "balanced")
    assert [r.model for r in out] == ["alive"]


def test_chat_always_allowed():
    cands = [_c(1, "vision-only", 0.1, 0.5, capabilities=["vision"])]
    out = scorer.recommend(cands, "chat", "balanced")
    assert len(out) == 1


def test_reasons_include_task():
    out = scorer.recommend([_c(1, "m", 0.1, 0.5)], "coding", "balanced")
    assert "coding" in " ".join(out[0].reasons)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_recommend.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tokenplans.recommend.scorer'`.

- [ ] **Step 3: Write minimal implementation**

Create `tokenplans/recommend/scorer.py`:

```python
import json
from dataclasses import dataclass, field

import tokenplans.db as db

EXPECTED_TOKENS = {"coding": (20000, 2000), "research": (50000, 10000), "chat": (2000, 1000)}
WEIGHTS = {"cheapest": (0.0, 1.0), "balanced": (0.5, 0.5), "best": (1.0, 0.0)}


@dataclass
class Recommendation:
    account_id: int
    account_label: str
    endpoint_id: int
    endpoint_name: str
    model: str
    cost: float
    score: float
    reasons: list[str] = field(default_factory=list)


def build_candidates(conn) -> list[dict]:
    candidates = []
    for account in db.list_accounts(conn):
        latest = db.latest_balance(conn, account["id"])
        for endpoint in db.list_endpoints(conn, account["provider_id"]):
            for model in db.list_models(conn, endpoint["id"]):
                candidates.append({
                    "account_id": account["id"],
                    "account_label": account["label"],
                    "account_status": account["status"],
                    "endpoint_id": endpoint["id"],
                    "endpoint_name": endpoint["name"],
                    "api_type": endpoint["api_type"],
                    "model": model["model_id"],
                    "pricing_in": model["pricing_in"],
                    "pricing_out": model["pricing_out"],
                    "capabilities": json.loads(model["capabilities_json"]),
                    "quality": model["quality"],
                    "speed": model["speed"],
                    "balance": latest["value"] if latest else None,
                })
    return candidates


def recommend(candidates, task_type="coding", preference="balanced",
              balance_floor=0.0) -> list[Recommendation]:
    if task_type not in EXPECTED_TOKENS:
        task_type = "coding"
    quality_weight, cost_weight = WEIGHTS.get(preference, WEIGHTS["balanced"])
    in_tokens, out_tokens = EXPECTED_TOKENS[task_type]

    filtered = []
    for c in candidates:
        if c.get("account_status") != "ok":
            continue
        bal = c.get("balance")
        if bal is not None and bal < balance_floor:
            continue
        if task_type != "chat" and task_type not in c.get("capabilities", []):
            continue
        filtered.append(c)

    if not filtered:
        return []

    costs = [in_tokens / 1e6 * c["pricing_in"] + out_tokens / 1e6 * c["pricing_out"]
             for c in filtered]
    lo, hi = min(costs), max(costs)
    results = []
    for c, cost in zip(filtered, costs):
        normalized = 0.0 if hi == lo else (cost - lo) / (hi - lo)
        score = quality_weight * c["quality"] - cost_weight * normalized * 5
        reasons = [f"matches {task_type}"]
        if cost == lo:
            reasons.append("cheapest")
        if c["quality"] == max(x["quality"] for x in filtered):
            reasons.append("best quality")
        results.append(Recommendation(
            account_id=c["account_id"], account_label=c["account_label"],
            endpoint_id=c["endpoint_id"], endpoint_name=c["endpoint_name"],
            model=c["model"], cost=round(cost, 4), score=round(score, 4),
            reasons=reasons,
        ))
    results.sort(key=lambda r: r.score, reverse=True)
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_recommend.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenplans/recommend/scorer.py tests/test_recommend.py
git commit -m "feat: add recommendation scorer"
```

---

## Task 13: FastAPI app + API

**Files:**
- Create: `tokenplans/app.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Consumes: everything from Tasks 1–12.
- Produces: `app` (FastAPI instance) and `create_app() -> FastAPI`.

Routes (JSON):
- `POST /api/sync` → `SyncReport`
- `GET /api/providers`, `GET /api/endpoints`, `GET /api/models`
- `GET /api/accounts`, `POST /api/accounts` (body: `provider_id`, `label`, `key`, `endpoint_scope?`, `extra?`) — encrypts `key`, returns masked account
- `POST /api/accounts/{id}/balance` (body: `value`, `unit`, `source`) → records manual balance
- `GET /api/agents`, `GET /api/bindings`, `PUT /api/bindings/{agent_slug}` (body: `account_id`, `endpoint_id`, `model`)
- `POST /api/config/preview` (body: `agent_slug`, `account_id`, `endpoint_id`, `model`) → `{files: [[path, content]], env: [[k,v]]}` (key is real inside content; endpoint/account metadata returned masked separately)
- `POST /api/config/apply` (same body) → writes files, backs up prior, returns written paths
- `GET /api/recommend?task_type=&preference=&balance_floor=` → `list[Recommendation]`
- `POST /api/poll/{account_id}` → `PollResult`
- `GET /` → serves `web/index.html`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api.py`:

```python
import json

import httpx

import tokenplans.app as app_mod
import tokenplans.db as db
import tokenplans.secrets as secrets


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENPLANS_HOME", str(tmp_path))
    c = db.connect()
    db.init_schema(c)
    pid = db.upsert_provider(c, "DeepSeek", "deepseek")
    db.upsert_endpoint(c, pid, "openai", "OpenAI", "openai",
                       "https://api.deepseek.com", "bearer")
    db.upsert_agent(c, "Claude Code", "claude-code", "anthropic")
    c.close()
    return httpx.Client(transport=httpx.ASGITransport(app=app_mod.create_app()),
                        base_url="http://test")


def test_sync_and_providers(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        r = client.post("/api/sync")
        assert r.status_code == 200
        assert r.json()["providers"] >= 1
        r = client.get("/api/providers")
        assert r.status_code == 200
        slugs = [p["slug"] for p in r.json()]
        assert "deepseek" in slugs


def test_account_key_is_masked(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post("/api/sync")
        r = client.post("/api/accounts", json={
            "provider_id": 1, "label": "plan", "key": "sk-supersecret123"})
        assert r.status_code == 200
        body = r.json()
        assert "sk-supersecret123" not in json.dumps(body)
        assert body["key_masked"] == "sk-…123"
        # stored encrypted
        c = db.connect()
        acct = db.get_account(c, body["id"])
        assert acct["key_encrypted"] != "sk-supersecret123"
        c.close()


def test_manual_balance(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post("/api/sync")
        aid = client.post("/api/accounts", json={
            "provider_id": 1, "label": "plan", "key": "sk-123"}).json()["id"]
        r = client.post(f"/api/accounts/{aid}/balance",
                        json={"value": 42.0, "unit": "CNY", "source": "manual"})
        assert r.status_code == 200
        c = db.connect()
        assert db.latest_balance(c, aid)["value"] == 42.0
        c.close()


def test_config_preview(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post("/api/sync")
        aid = client.post("/api/accounts", json={
            "provider_id": 1, "label": "plan", "key": "sk-123"}).json()["id"]
        eid = client.get("/api/endpoints").json()[0]["id"]
        r = client.post("/api/config/preview", json={
            "agent_slug": "claude-code", "account_id": aid,
            "endpoint_id": eid, "model": "deepseek-chat"})
        assert r.status_code == 200
        body = r.json()
        assert body["files"] or body["env"]


def test_recommend(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post("/api/sync")
        r = client.get("/api/recommend", params={"task_type": "coding"})
        assert r.status_code == 200
        assert isinstance(r.json(), list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tokenplans.app'`.

- [ ] **Step 3: Write minimal implementation**

Create `tokenplans/app.py`:

```python
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import tokenplans.agents.profiles as ap
import tokenplans.agents.render as render
import tokenplans.config as config
import tokenplans.db as db
import tokenplans.balance.poller as poller
import tokenplans.recommend.scorer as scorer
import tokenplans.secrets as secrets
import tokenplans.sync as sync


class AccountIn(BaseModel):
    provider_id: int
    label: str
    key: str
    endpoint_scope: list[str] | None = None
    extra: dict | None = None


class BalanceIn(BaseModel):
    value: float
    unit: str = ""
    source: str = "manual"


class BindingIn(BaseModel):
    account_id: int
    endpoint_id: int
    model: str


class ConfigIn(BaseModel):
    agent_slug: str
    account_id: int
    endpoint_id: int
    model: str


def create_app() -> FastAPI:
    app = FastAPI(title="tokenplans")
    app.mount("/static", StaticFiles(directory=str(config.web_dir())), name="static")

    @app.get("/")
    def index():
        return FileResponse(config.web_dir() / "index.html")

    def _conn():
        c = db.connect()
        db.migrate(c)
        return c

    def _secrets():
        return secrets.Secrets(secrets.load_or_create_key())

    @app.post("/api/sync")
    def api_sync():
        with _conn() as c:
            return sync.sync_profiles(c).__dict__

    @app.get("/api/providers")
    def api_providers():
        with _conn() as c:
            return db.list_providers(c)

    @app.get("/api/endpoints")
    def api_endpoints(provider_id: int | None = None):
        with _conn() as c:
            return db.list_endpoints(c, provider_id)

    @app.get("/api/accounts")
    def api_accounts():
        with _conn() as c:
            out = []
            for a in db.list_accounts(c):
                a = dict(a)
                a["key_masked"] = _secrets().mask(_secrets().decrypt(a["key_encrypted"]))
                a.pop("key_encrypted")
                out.append(a)
            return out

    @app.post("/api/accounts")
    def api_create_account(body: AccountIn):
        with _conn() as c:
            aid = db.create_account(c, body.provider_id, body.label,
                                    _secrets().encrypt(body.key),
                                    endpoint_scope=body.endpoint_scope, extra=body.extra)
            acct = db.get_account(c, aid)
            return {"id": aid, "label": acct["label"], "key_masked": _secrets().mask(body.key)}

    @app.post("/api/accounts/{account_id}/balance")
    def api_manual_balance(account_id: int, body: BalanceIn):
        with _conn() as c:
            if db.get_account(c, account_id) is None:
                raise HTTPException(404, "account not found")
            db.record_balance(c, account_id, body.value, body.unit, body.source)
            return {"ok": True}

    @app.get("/api/agents")
    def api_agents():
        with _conn() as c:
            return db.list_agents(c)

    @app.get("/api/bindings")
    def api_bindings():
        with _conn() as c:
            return db.list_bindings(c)

    @app.put("/api/bindings/{agent_slug}")
    def api_put_binding(agent_slug: str, body: BindingIn):
        with _conn() as c:
            agent = c.execute("SELECT id FROM agents WHERE slug=?", (agent_slug,)).fetchone()
            if agent is None:
                raise HTTPException(404, "agent not found")
            db.upsert_binding(c, agent["id"], body.account_id, body.endpoint_id, body.model)
            return {"ok": True}

    @app.post("/api/config/preview")
    def api_config_preview(body: ConfigIn):
        with _conn() as c:
            return _render(c, body.agent_slug, body.account_id, body.endpoint_id, body.model)

    @app.post("/api/config/apply")
    def api_config_apply(body: ConfigIn):
        with _conn() as c:
            rendered = _render(c, body.agent_slug, body.account_id, body.endpoint_id, body.model)
            written = []
            for path, content in rendered["files"]:
                p = Path(path).expanduser()
                p.parent.mkdir(parents=True, exist_ok=True)
                if p.exists():
                    shutil.copy2(p, str(p) + ".bak")
                p.write_text(content)
                written.append(str(p))
            return {"written": written}

    @app.get("/api/recommend")
    def api_recommend(task_type: str = "coding", preference: str = "balanced",
                      balance_floor: float = 0.0):
        with _conn() as c:
            return scorer.recommend(scorer.build_candidates(c), task_type, preference, balance_floor)

    @app.post("/api/poll/{account_id}")
    def api_poll(account_id: int):
        with _conn() as c:
            account = db.get_account(c, account_id)
            if account is None:
                raise HTTPException(404, "account not found")
            endpoint = db.list_endpoints(c, account["provider_id"])[0]
            return poller.poll_account(c, _secrets(), account_id, endpoint,
                                       {"path": "/user/balance",
                                        "response_path": "data.available",
                                        "method": "GET", "unit": ""})

    return app


def _render(conn, agent_slug, account_id, endpoint_id, model):
    agent_row = conn.execute("SELECT id FROM agents WHERE slug=?", (agent_slug,)).fetchone()
    if agent_row is None:
        raise HTTPException(404, "agent not found")
    account = db.get_account(conn, account_id)
    if account is None:
        raise HTTPException(404, "account not found")
    endpoint = conn.execute("SELECT * FROM endpoints WHERE id=?", (endpoint_id,)).fetchone()
    if endpoint is None:
        raise HTTPException(404, "endpoint not found")

    # Templates live in the YAML files; load the agent profile by slug.
    profile_path = config.profiles_dir() / "agents" / f"{agent_slug}.yaml"
    if not profile_path.exists():
        raise HTTPException(404, f"agent profile not found: {agent_slug}.yaml")
    profile = ap.load_agent_profile(profile_path)

    key = secrets.Secrets(secrets.load_or_create_key()).decrypt(account["key_encrypted"])
    rendered = render.render_agent_config(profile, dict(endpoint), key, model)
    return {"files": rendered.files, "env": rendered.env}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api.py -v`
Expected: PASS. (The agent profile `claude-code.yaml` must exist in `tokenplans/profiles/agents/` for `test_config_preview` — create it in this task, see below.)

Create `tokenplans/profiles/agents/claude-code.yaml` (needed by the test):

```yaml
name: Claude Code
slug: claude-code
api_type: anthropic
files:
  - path: ~/.claude/settings.json
    template: |
      {"env":{"ANTHROPIC_BASE_URL":"{{ endpoint.base_url }}","ANTHROPIC_API_KEY":"{{ account.key }}","ANTHROPIC_MODEL":"{{ model }}"}}
env:
  - key: ANTHROPIC_BASE_URL
    template: "{{ endpoint.base_url }}"
  - key: ANTHROPIC_API_KEY
    template: "{{ account.key }}"
```

- [ ] **Step 5: Commit**

```bash
git add tokenplans/app.py tests/test_api.py tokenplans/profiles/agents/claude-code.yaml
git commit -m "feat: add FastAPI app and API"
```

---

## Task 14: CLI (`profiles validate` / `sync`)

**Files:**
- Create: `tokenplans/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Produces: `main(argv=None) -> int` (argparse; subcommands `validate PATH` and `sync`). `validate` prints errors and returns 0 if valid, 1 if invalid. `sync` runs `sync_profiles` on a temp connection and prints a report.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
import yaml

import tokenplans.cli as cli


def _write_valid(path):
    path.write_text(yaml.safe_dump({
        "name": "DeepSeek", "slug": "deepseek",
        "endpoints": [{"id": "openai", "api_type": "openai",
                       "base_url": "https://api.deepseek.com", "auth": "bearer"}],
    }))


def test_validate_valid(tmp_path, capsys):
    f = tmp_path / "p.yaml"
    _write_valid(f)
    assert cli.main(["validate", str(f)]) == 0


def test_validate_invalid(tmp_path, capsys):
    f = tmp_path / "p.yaml"
    f.write_text("name: X\n")
    assert cli.main(["validate", str(f)]) == 1
    assert "slug" in capsys.readouterr().err


def test_validate_agent_file(tmp_path):
    f = tmp_path / "a.yaml"
    f.write_text(yaml.safe_dump({"name": "Claude Code", "api_type": "anthropic"}))
    assert cli.main(["validate", str(f)]) == 0


def test_validate_missing_file():
    assert cli.main(["validate", "/no/such/file.yaml"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tokenplans.cli'`.

- [ ] **Step 3: Write minimal implementation**

Create `tokenplans/cli.py`:

```python
import argparse
import sys

import yaml

import tokenplans.agents.profiles as ap
import tokenplans.providers.profiles as pp


def _validate(path) -> int:
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"file not found: {path}", file=sys.stderr)
        return 1
    if not isinstance(data, dict):
        print("profile must be a mapping", file=sys.stderr)
        return 1
    # try provider shape first, then agent shape
    errors = pp.validate_provider_profile(data)
    if errors and ("name" in data) and ("api_type" in data):
        errors = ap.validate_agent_profile(data)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    return 0


def _sync() -> int:
    import tokenplans.db as db
    import tokenplans.sync as sync

    conn = db.connect()
    db.migrate(conn)
    report = sync.sync_profiles(conn)
    conn.close()
    print(f"providers={report.providers} endpoints={report.endpoints} "
          f"models={report.models} agents={report.agents} errors={len(report.errors)}")
    for e in report.errors:
        print(e, file=sys.stderr)
    return 1 if report.errors else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tokenplans")
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("path")
    sub.add_parser("sync")
    args = parser.parse_args(argv)
    if args.cmd == "validate":
        return _validate(args.path)
    return _sync()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenplans/cli.py tests/test_cli.py
git commit -m "feat: add CLI validate/sync"
```

---

## Task 15: Shipped provider & agent profiles

**Files:**
- Create: `tokenplans/profiles/providers/qwen.yaml`, `zhipu.yaml`, `deepseek.yaml`, `moonshot.yaml`
- Create: `tokenplans/profiles/agents/pi.yaml`, `opencode.yaml`, `hermes.yaml`, `deepseek-harness.yaml`, `reasonix.yaml`, `openclaw.yaml`
- Create: `tests/test_shipped_profiles.py`

**Interfaces:**
- Consumes: `config.profiles_dir()`, `pp.load_provider_profile`/`validate_provider_profile`, `ap.load_agent_profile`/`validate_agent_profile`, `sync.sync_profiles`.

> These are data files (config exception to TDD); they are covered by a validation test instead.

- [ ] **Step 1: Write the failing test**

Create `tests/test_shipped_profiles.py`:

```python
import tokenplans.config as config
import tokenplans.providers.profiles as pp
import tokenplans.agents.profiles as ap


def test_all_provider_profiles_valid():
    d = config.profiles_dir() / "providers"
    files = sorted(d.glob("*.yaml"))
    assert len(files) >= 4
    for f in files:
        assert pp.validate_provider_profile(_load(f)) == [], f.name


def test_all_agent_profiles_valid():
    d = config.profiles_dir() / "agents"
    files = sorted(d.glob("*.yaml"))
    assert len(files) >= 7
    for f in files:
        assert ap.validate_agent_profile(_load(f)) == [], f.name


def test_sync_ships_all(conn):
    import tokenplans.sync as sync
    import tokenplans.db as db
    report = sync.sync_profiles(conn)
    assert report.errors == []
    assert report.providers >= 4
    assert report.agents >= 7
    assert len(db.list_providers(conn)) >= 4
    assert len(db.list_agents(conn)) >= 7


def _load(f):
    import yaml
    with open(f) as fh:
        return yaml.safe_load(fh)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_shipped_profiles.py -v`
Expected: FAIL — missing profile files / `len(files) >= 4` fails.

- [ ] **Step 3: Write the profile files**

`tokenplans/profiles/providers/deepseek.yaml`:

```yaml
name: DeepSeek
slug: deepseek
endpoints:
  - id: openai
    name: OpenAI-compatible
    api_type: openai
    base_url: https://api.deepseek.com
    auth: bearer
    models:
      - id: deepseek-chat
        in: 0.27
        out: 1.10
        capabilities: [coding, research, chat]
      - id: deepseek-reasoner
        in: 0.55
        out: 2.19
        capabilities: [research, coding]
balance:
  endpoint: openai
  path: /user/balance
  response_path: balance_infos[0].total_balance
  unit: CNY
```

`tokenplans/profiles/providers/moonshot.yaml`:

```yaml
name: Moonshot
slug: moonshot
endpoints:
  - id: openai
    name: OpenAI-compatible
    api_type: openai
    base_url: https://api.moonshot.cn/v1
    auth: bearer
    models:
      - id: kimi-k2-0711-preview
        in: 4.0
        out: 16.0
        capabilities: [coding, research, chat]
      - id: moonshot-v1-8k
        in: 12.0
        out: 12.0
        capabilities: [chat, research]
balance:
  endpoint: openai
  path: /users/me/balance
  response_path: data.available_balance
  unit: CNY
```

`tokenplans/profiles/providers/qwen.yaml`:

```yaml
name: Qwen
slug: qwen
endpoints:
  - id: openai
    name: OpenAI-compatible
    api_type: openai
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    auth: bearer
    models:
      - id: qwen-max
        in: 1.6
        out: 6.4
        capabilities: [coding, research, chat]
      - id: qwen-plus
        in: 0.4
        out: 1.2
        capabilities: [chat, research]
  - id: anthropic
    name: Anthropic-compatible
    api_type: anthropic
    base_url: https://dashscope.aliyuncs.com/api/anthropic
    auth: bearer
    models:
      - id: qwen-max
        in: 1.6
        out: 6.4
        capabilities: [coding, research, chat]
balance:
  endpoint: openai
  path: /api/v1/quota
  response_path: data.available
  unit: tokens
```

`tokenplans/profiles/providers/zhipu.yaml`:

```yaml
name: Zhipu
slug: zhipu
endpoints:
  - id: openai
    name: OpenAI-compatible
    api_type: openai
    base_url: https://open.bigmodel.cn/api/paas/v4
    auth: bearer
    models:
      - id: glm-4.5
        in: 4.0
        out: 16.0
        capabilities: [coding, research, chat]
  - id: anthropic
    name: Anthropic-compatible (coding plan)
    api_type: anthropic
    base_url: https://open.bigmodel.cn/api/anthropic
    auth: bearer
    models:
      - id: glm-4.5
        in: 4.0
        out: 16.0
        capabilities: [coding, research, chat]
balance:
  endpoint: openai
  path: /api/paas/v4/user/balance
  response_path: data.balance
  unit: CNY
```

Agent profiles (env-based where file paths are agent-specific; file-based where well-known):

`tokenplans/profiles/agents/pi.yaml`:

```yaml
name: Pi
slug: pi
api_type: openai
env:
  - key: OPENAI_BASE_URL
    template: "{{ endpoint.base_url }}"
  - key: OPENAI_API_KEY
    template: "{{ account.key }}"
  - key: OPENAI_MODEL
    template: "{{ model }}"
```

`tokenplans/profiles/agents/opencode.yaml`:

```yaml
name: opencode
slug: opencode
api_type: openai
env:
  - key: OPENAI_BASE_URL
    template: "{{ endpoint.base_url }}"
  - key: OPENAI_API_KEY
    template: "{{ account.key }}"
  - key: OPENAI_MODEL
    template: "{{ model }}"
```

`tokenplans/profiles/agents/hermes.yaml`:

```yaml
name: Hermes
slug: hermes
api_type: anthropic
env:
  - key: ANTHROPIC_BASE_URL
    template: "{{ endpoint.base_url }}"
  - key: ANTHROPIC_API_KEY
    template: "{{ account.key }}"
  - key: ANTHROPIC_MODEL
    template: "{{ model }}"
```

`tokenplans/profiles/agents/deepseek-harness.yaml`:

```yaml
name: DeepSeek Harness
slug: deepseek-harness
api_type: openai
env:
  - key: OPENAI_BASE_URL
    template: "{{ endpoint.base_url }}"
  - key: OPENAI_API_KEY
    template: "{{ account.key }}"
  - key: OPENAI_MODEL
    template: "{{ model }}"
```

`tokenplans/profiles/agents/reasonix.yaml`:

```yaml
name: Reasonix
slug: reasonix
api_type: anthropic
env:
  - key: ANTHROPIC_BASE_URL
    template: "{{ endpoint.base_url }}"
  - key: ANTHROPIC_API_KEY
    template: "{{ account.key }}"
  - key: ANTHROPIC_MODEL
    template: "{{ model }}"
```

`tokenplans/profiles/agents/openclaw.yaml`:

```yaml
name: OpenClaw
slug: openclaw
api_type: openai
env:
  - key: OPENAI_BASE_URL
    template: "{{ endpoint.base_url }}"
  - key: OPENAI_API_KEY
    template: "{{ account.key }}"
  - key: OPENAI_MODEL
    template: "{{ model }}"
```

> **Verification note (not a code placeholder):** the balance endpoint paths (`/user/balance`, `/users/me/balance`, `/api/v1/quota`, `/api/paas/v4/user/balance`) are best-effort from public docs and **must be confirmed against each provider's current API docs** before relying on auto-poll in production. The poller and all tests use mocked HTTP, so this does not affect correctness of the code — only the live accuracy. Adjust the YAML `balance.path`/`response_path` if a provider's actual endpoint differs.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_shipped_profiles.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tokenplans/profiles tests/test_shipped_profiles.py
git commit -m "feat: ship provider and agent profiles"
```

---

## Task 16: Frontend (dashboard)

**Files:**
- Create: `tokenplans/web/index.html`
- Create: `tokenplans/web/app.js`
- Create: `tokenplans/web/style.css`

**Interfaces:**
- Consumes: the REST API from Task 13. Served at `/` by `app.py`.

> Static UI is a config/asset exception to TDD; correctness is covered by the existing `GET /` route and manual verification. Keep it minimal: a dashboard with three panels — Accounts (with balance + manual entry), Agents (with config preview/apply), and Recommendations.

- [ ] **Step 1: Write the UI**

`tokenplans/web/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>tokenplans</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header>
    <h1>tokenplans</h1>
    <button id="sync">Sync profiles</button>
  </header>
  <main>
    <section id="accounts">
      <h2>Accounts</h2>
      <form id="add-account">
        <input name="label" placeholder="label" required>
        <input name="key" placeholder="API key" required>
        <input name="provider_id" placeholder="provider id" required>
        <button>Add account</button>
      </form>
      <table><thead><tr><th>Label</th><th>Provider</th><th>Status</th><th>Balance</th><th>Key</th></tr></thead><tbody id="account-rows"></tbody></table>
    </section>
    <section id="agents">
      <h2>Agents</h2>
      <table><thead><tr><th>Agent</th><th>API type</th><th>Action</th></tr></thead><tbody id="agent-rows"></tbody></table>
    </section>
    <section id="recommend">
      <h2>Recommend</h2>
      <select id="task-type"><option>coding</option><option>research</option><option>chat</option></select>
      <select id="preference"><option>cheapest</option><option>balanced</option><option>best</option></select>
      <button id="run-recommend">Recommend</button>
      <ol id="recommend-results"></ol>
    </section>
  </main>
  <script src="/static/app.js"></script>
</body>
</html>
```

`tokenplans/web/app.js`:

```js
const $ = (sel) => document.querySelector(sel);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function loadAccounts() {
  const rows = await api("/api/accounts");
  $("tbody#account-rows").innerHTML = rows.map((a) =>
    `<tr><td>${a.label}</td><td>${a.provider_id}</td><td>${a.status}</td><td>—</td><td>${a.key_masked}</td></tr>`
  ).join("");
}

async function loadAgents() {
  const rows = await api("/api/agents");
  $("tbody#agent-rows").innerHTML = rows.map((a) =>
    `<tr><td>${a.name}</td><td>${a.api_type}</td><td>—</td></tr>`
  ).join("");
}

$("#sync").onclick = async () => { await api("/api/sync", { method: "POST" }); alert("synced"); };
$("#add-account").onsubmit = async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  await api("/api/accounts", { method: "POST", body: {
    provider_id: Number(f.get("provider_id")),
    label: f.get("label"), key: f.get("key"),
  }});
  loadAccounts();
};
$("#run-recommend").onclick = async () => {
  const t = $("#task-type").value, p = $("#preference").value;
  const results = await api(`/api/recommend?task_type=${t}&preference=${p}`);
  $("#recommend-results").innerHTML = results.map((r) =>
    `<li>${r.account_label} / ${r.model} — est cost ${r.cost} (${r.reasons.join(", ")})</li>`
  ).join("");
};

loadAccounts();
loadAgents();
```

`tokenplans/web/style.css`:

```css
body { font-family: system-ui, sans-serif; margin: 2rem; }
header { display: flex; gap: 1rem; align-items: center; }
table { border-collapse: collapse; width: 100%; margin-bottom: 2rem; }
th, td { border: 1px solid #ddd; padding: .5rem; text-align: left; }
section { margin-bottom: 2rem; }
```

- [ ] **Step 2: Verify served**

Run: `pytest tests/test_api.py::test_sync_and_providers -v` (still passes) and manually `uvicorn tokenplans.app:app --reload`, open `http://127.0.0.1:8000/`.

- [ ] **Step 3: Commit**

```bash
git add tokenplans/web
git commit -m "feat: add dashboard frontend"
```

---

## Task 17: End-to-end smoke test & run instructions

**Files:**
- Create: `tests/test_smoke.py`
- Modify: `README.md` (create)

**Interfaces:**
- Consumes: the whole stack.

- [ ] **Step 1: Write the failing test**

Create `tests/test_smoke.py`:

```python
import httpx

import tokenplans.app as app_mod
import tokenplans.db as db


def test_full_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENPLANS_HOME", str(tmp_path))
    client = httpx.Client(transport=httpx.ASGITransport(app=app_mod.create_app()),
                          base_url="http://test")
    # sync profiles
    assert client.post("/api/sync").json()["providers"] >= 4
    # add an account with a real key, masked in response
    acct = client.post("/api/accounts", json={
        "provider_id": 1, "label": "my plan", "key": "sk-live-secret-key-000"
    }).json()
    assert "sk-live-secret-key-000" not in str(acct)
    # manual balance
    client.post(f"/api/accounts/{acct['id']}/balance",
                json={"value": 100.0, "unit": "CNY", "source": "manual"})
    # recommend returns at least one candidate
    recs = client.get("/api/recommend", params={"task_type": "coding"}).json()
    assert isinstance(recs, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_smoke.py -v`
Expected: FAIL if any earlier wiring is missing (otherwise it passes; then treat this as a regression gate).

- [ ] **Step 3: Write README**

Create `README.md`:

```markdown
# tokenplans

Local dashboard for AI token-plan accounts, balances, and agent config.

## Run

    pip install -e ".[dev]"
    uvicorn tokenplans.app:app --reload
    open http://127.0.0.1:8000

## CLI

    tokenplans profiles validate path/to/profile.yaml
    tokenplans sync

## Test

    pytest
```

- [ ] **Step 4: Run full suite**

Run: `pytest -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_smoke.py README.md
git commit -m "test: end-to-end smoke test and README"
```

---

## Self-Review Notes

- **Spec coverage:** accounts/keys (Tasks 4, 5, 13), balances auto+manual (Tasks 10, 11, 13), config generation (Tasks 7, 8, 13), recommendations (Task 12), profiles for 4 providers + 7 agents (Task 15), dashboard (Task 16), CLI validate for future skill (Task 14). Future roadmap (gateway/MCP/skill) is intentionally out of scope.
- **Placeholders:** none — all code/test steps are concrete. Balance endpoint URLs are data with an explicit verification note (not code TODOs).
- **Type consistency:** `render_agent_config(profile, endpoint: dict, account_key, model) -> RenderedConfig`, `recommend(candidates, task_type, preference, balance_floor) -> list[Recommendation]`, `poll_account(conn, secrets, account_id, endpoint, balance_spec, transport=None) -> PollResult` are used consistently across Tasks 11–13.
