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
