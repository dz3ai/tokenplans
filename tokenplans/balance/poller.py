from dataclasses import dataclass

import httpx

import tokenplans.balance.parse as parse
import tokenplans.db as db
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


def poll_all_accounts(conn, secrets, transport=None) -> list[PollResult]:
    results = []
    for account in db.list_accounts(conn):
        if account["manual_override"]:
            continue
        endpoints = db.list_endpoints(conn, account["provider_id"])
        # Poll via the first endpoint; balance endpoints are provider-scoped in v1.
        if not endpoints:
            continue
        spec = {"path": "/user/balance", "response_path": "balance_infos[0].total_balance",
                "method": "GET", "unit": ""}
        results.append(poll_account(conn, secrets, account["id"], endpoints[0], spec, transport))
    return results
