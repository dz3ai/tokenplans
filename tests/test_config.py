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


def test_app_dir_empty_env_defaults(monkeypatch):
    monkeypatch.setenv("TOKENPLANS_HOME", "")
    assert config.app_dir() == Path.home() / ".tokenplans"


def test_app_dir_tilde_expands(monkeypatch):
    monkeypatch.setenv("TOKENPLANS_HOME", "~/foo")
    assert config.app_dir() == Path.home() / "foo"


def test_ensure_app_dir_creates(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENPLANS_HOME", str(tmp_path / "nested"))
    p = config.ensure_app_dir()
    assert p.exists() and p.is_dir()


def test_profiles_and_web_dirs_exist():
    assert config.profiles_dir().is_dir()
    assert config.web_dir().is_dir()
