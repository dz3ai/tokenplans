import pytest

import tokenplans.db as db


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENPLANS_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def conn(app_dir):
    c = db.connect()
    db.init_schema(c)
    yield c
    c.close()
