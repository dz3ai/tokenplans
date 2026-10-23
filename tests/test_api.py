import json

from fastapi.testclient import TestClient

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
    return TestClient(app_mod.create_app())


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
