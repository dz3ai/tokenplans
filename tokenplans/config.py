import os
from pathlib import Path


def app_dir() -> Path:
    return Path(os.environ.get("TOKENPLANS_HOME", str(Path.home() / ".tokenplans")))


def db_path() -> Path:
    return app_dir() / "tokenplans.db"


def key_path() -> Path:
    return app_dir() / "key"


def profiles_dir() -> Path:
    return Path(__file__).parent / "profiles"


def web_dir() -> Path:
    return Path(__file__).parent / "web"


def ensure_app_dir() -> Path:
    d = app_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d
