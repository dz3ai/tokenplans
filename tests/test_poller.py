import json

import httpx
import yaml

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


def test_resolve_balance_spec(tmp_path, conn):
    pid = db.upsert_provider(conn, "DeepSeek", "deepseek")
    db.upsert_endpoint(conn, pid, "openai", "OpenAI", "openai",
                       "https://api.deepseek.com", "bearer")
    aid = db.create_account(conn, pid, "plan", _secrets().encrypt("sk-123"))
    profiles_dir = tmp_path / "providers"
    profiles_dir.mkdir()
    profile = {
        "name": "DeepSeek", "slug": "deepseek",
        "endpoints": [{"id": "openai", "name": "OpenAI", "api_type": "openai",
                       "base_url": "https://api.deepseek.com", "auth": "bearer"}],
        "balance": {"endpoint": "openai", "path": "/user/balance",
                    "response_path": "balance_infos[0].total_balance", "unit": "CNY"},
    }
    (profiles_dir / "deepseek.yaml").write_text(yaml.safe_dump(profile))
    endpoint, spec = poller.resolve_balance_spec(conn, aid, profiles_dir=profiles_dir)
    assert endpoint["base_url"] == "https://api.deepseek.com"
    assert spec.response_path == "balance_infos[0].total_balance"


def test_poll_all_accounts(conn):
    aid, endpoint = _seed(conn, _secrets())
    results = poller.poll_all_accounts(conn, _secrets(), transport=_transport(
        {"balance_infos": [{"total_balance": "10", "currency": "CNY"}]}))
    assert len(results) == 1
    assert results[0].ok
