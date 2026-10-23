import os

from cryptography.fernet import Fernet

import tokenplans.config as config


def load_or_create_key(path=None):
    if path is None:
        path = config.key_path()
    path = os.fspath(path)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    return key


class Secrets:
    def __init__(self, key: bytes):
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()

    def mask(self, secret: str) -> str:
        if len(secret) <= 6:
            return "…"
        return f"{secret[:3]}…{secret[-3:]}"
