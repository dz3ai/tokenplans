from dataclasses import dataclass

import httpx

import tokenplans.balance.parse as parse
import tokenplans.config as config
import tokenplans.db as db
import tokenplans.providers.profiles as pp
import tokenplans.secrets as secrets


@dataclass
class PollResult:
    ok: bool
    account_id: int
    value: float | None = None
    unit: str = ""
    error: str | None = None


def auth_headers(endpoint: dict, key: str) -> dict:
    if endpoint.get("auth") == "x-api-key":
        return {"x-api-key": key}
    return {"Authorization": f"Bearer {key}"}


def _field(spec, name, default=None):
    return getattr(spec, name, default) if not isinstance(spec, dict) else spec.get(name, default)


def poll_account(conn, secrets, account_id, endpoint, balance_spec, transport=None) -> PollResult:
    account = db.get_account(conn, account_id)
    if account is None:
        return PollResult(ok=False, account_id=account_id, error="account not found")
    try:
        key = secrets.decrypt(account["key_encrypted"])
        path = _field(balance_spec, "path", "")
        method = _field(balance_spec, "method", "GET")
        response_path = _field(balance_spec, "response_path")
        unit = _field(balance_spec, "unit", "")
        url = endpoint["base_url"].rstrip("/") + "/" + path.lstrip("/")
        with httpx.Client(transport=transport) as client:
            resp = client.request(method, url, headers=auth_headers(endpoint, key))
            resp.raise_for_status()
            data = resp.json()
        value = float(parse.extract_value(data, response_path))
        db.record_balance(conn, account_id, value, unit, "auto")
        db.set_account_status(conn, account_id, "ok")
        return PollResult(ok=True, account_id=account_id, value=value, unit=unit)
    except Exception as exc:  # noqa: BLE001
        db.set_account_status(conn, account_id, "error", str(exc))
        return PollResult(ok=False, account_id=account_id, error=str(exc))


def resolve_balance_spec(conn, account_id, profiles_dir=None):
    account = db.get_account(conn, account_id)
    if account is None:
        return None, None
    row = conn.execute("SELECT slug FROM providers WHERE id=?", (account["provider_id"],)).fetchone()
    if row is None:
        return None, None
    if profiles_dir is None:
        profiles_dir = config.profiles_dir() / "providers"
    path = profiles_dir / f"{row['slug']}.yaml"
    if not path.exists():
        return None, None
    prof = pp.load_provider_profile(path)
    if prof.balance is None:
        return None, None
    for e in prof.endpoints:
        if e.pid == prof.balance.endpoint:
            endpoint = {"pid": e.pid, "name": e.name, "api_type": e.api_type,
                        "base_url": e.base_url, "auth": e.auth}
            return endpoint, prof.balance
    return None, None


def poll_all_accounts(conn, secrets, transport=None, profiles_dir=None) -> list[PollResult]:
    results = []
    for account in db.list_accounts(conn):
        if account["manual_override"]:
            continue
        endpoint, spec = resolve_balance_spec(conn, account["id"], profiles_dir)
        if endpoint is None:
            db.set_account_status(conn, account["id"], "error", "no balance config")
            results.append(PollResult(ok=False, account_id=account["id"],
                                      error="no balance config"))
            continue
        results.append(poll_account(conn, secrets, account["id"], endpoint, spec, transport))
    return results
