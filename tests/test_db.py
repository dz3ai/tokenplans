import json
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
