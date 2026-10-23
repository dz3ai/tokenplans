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


def test_accounts_include_latest_balance(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post("/api/sync")
        aid = client.post("/api/accounts", json={
            "provider_id": 1, "label": "plan", "key": "sk-123"}).json()["id"]
        r = client.post(f"/api/accounts/{aid}/balance",
                        json={"value": 42.0, "unit": "CNY", "source": "manual"})
        assert r.status_code == 200
        accounts = client.get("/api/accounts").json()
        match = next(a for a in accounts if a["id"] == aid)
        assert match["latest_balance"]["value"] == 42.0


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


def test_models_route(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post("/api/sync")
        r = client.get("/api/models")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        model_ids = [m["model_id"] for m in r.json()]
        assert "deepseek-chat" in model_ids


def test_app_instance_exists():
    assert hasattr(app_mod, "app")


def test_config_preview_out_of_scope_400(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post("/api/sync")
        c = db.connect()
        anthropic_eid = db.upsert_endpoint(c, 1, "anthropic", "Anthropic", "anthropic",
                                           "https://api.anthropic.com", "bearer")
        c.close()
        aid = client.post("/api/accounts", json={
            "provider_id": 1, "label": "scoped", "key": "sk-123",
            "endpoint_scope": ["openai"]}).json()["id"]
        r = client.post("/api/config/preview", json={
            "agent_slug": "claude-code", "account_id": aid,
            "endpoint_id": anthropic_eid, "model": "some-model"})
        assert r.status_code == 400


def test_create_account_missing_provider_404(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        r = client.post("/api/accounts", json={
            "provider_id": 9999, "label": "x", "key": "sk-1"})
        assert r.status_code == 404


def test_put_binding_missing_account_404(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        r = client.put("/api/bindings/claude-code", json={
            "account_id": 9999, "endpoint_id": 1, "model": "m"})
        assert r.status_code == 404


def test_manual_override_toggle(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.post("/api/sync")
        aid = client.post("/api/accounts", json={
            "provider_id": 1, "label": "plan", "key": "sk-123"}).json()["id"]
        r = client.post(f"/api/accounts/{aid}/override", json={"manual_override": True})
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        match = next(a for a in client.get("/api/accounts").json() if a["id"] == aid)
        assert match["manual_override"] == 1
        r = client.post(f"/api/accounts/{aid}/override", json={"manual_override": False})
        assert r.status_code == 200
        match = next(a for a in client.get("/api/accounts").json() if a["id"] == aid)
        assert match["manual_override"] == 0


def test_poll_missing_account_404(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        r = client.post("/api/poll/9999")
        assert r.status_code == 404
