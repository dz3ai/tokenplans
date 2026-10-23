import json
import sqlite3
from datetime import datetime, timezone

import tokenplans.config as config

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_info (version INTEGER NOT NULL UNIQUE);

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
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_info'"
    ).fetchone()
    if table is None:
        init_schema(conn)
        return
    row = conn.execute("SELECT version FROM schema_info").fetchone()
    if row is None:
        init_schema(conn)
        return
    # v1 is the only version; future migrations go here keyed on row["version"].


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
