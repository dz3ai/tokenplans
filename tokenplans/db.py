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
