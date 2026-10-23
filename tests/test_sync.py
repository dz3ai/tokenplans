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
