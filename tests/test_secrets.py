import os

import pytest

import tokenplans.secrets as secrets


def test_encrypt_decrypt_roundtrip():
    s = secrets.Secrets(secrets.load_or_create_key())
    token = s.encrypt("sk-abcdef123456")
    assert token != "sk-abcdef123456"
    assert s.decrypt(token) == "sk-abcdef123456"


def test_encrypt_is_nondeterministic():
    s = secrets.Secrets(secrets.load_or_create_key())
    a = s.encrypt("same")
    b = s.encrypt("same")
    assert a != b
    assert s.decrypt(a) == s.decrypt(b) == "same"


def test_decrypt_wrong_key_fails(app_dir):
    k1 = secrets.load_or_create_key(app_dir / "key1")
    k2 = secrets.load_or_create_key(app_dir / "key2")
    token = secrets.Secrets(k1).encrypt("secret")
    with pytest.raises(Exception):
        secrets.Secrets(k2).decrypt(token)


def test_mask():
    s = secrets.Secrets(secrets.load_or_create_key())
    assert s.mask("sk-abcdef123456") == "sk-…456"
    assert s.mask("short") == "…"


def test_load_or_create_key_writes_file(app_dir):
    p = app_dir / "key"
    k = secrets.load_or_create_key(p)
    assert p.exists()
    assert os.stat(p).st_mode & 0o777 == 0o600
    assert secrets.load_or_create_key(p) == k
