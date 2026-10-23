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


def test_migrate_on_empty_connection_creates_schema(app_dir):
    c = db.connect()
    try:
        db.migrate(c)
        assert EXPECTED_TABLES <= _tables(c)
    finally:
        c.close()


def test_migrate_is_noop_when_version_present(conn):
    db.migrate(conn)
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM schema_info"
    ).fetchone()["n"]
    assert count == 1


def test_init_schema_does_not_duplicate_schema_info(conn):
    db.init_schema(conn)
    db.init_schema(conn)
    db.init_schema(conn)
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM schema_info"
    ).fetchone()["n"]
    assert count == 1
