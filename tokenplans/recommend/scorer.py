import json
from dataclasses import dataclass, field

import tokenplans.db as db

EXPECTED_TOKENS = {"coding": (20000, 2000), "research": (50000, 10000), "chat": (2000, 1000)}
WEIGHTS = {"cheapest": (0.0, 1.0), "balanced": (0.5, 0.5), "best": (1.0, 0.0)}


@dataclass
class Recommendation:
    account_id: int
    account_label: str
    endpoint_id: int
    endpoint_name: str
    model: str
    cost: float
    score: float
    reasons: list[str] = field(default_factory=list)


def build_candidates(conn) -> list[dict]:
    candidates = []
    for account in db.list_accounts(conn):
        latest = db.latest_balance(conn, account["id"])
        scope = json.loads(account["endpoint_scope_json"])
        for endpoint in db.list_endpoints(conn, account["provider_id"]):
            if scope and endpoint["pid"] not in scope:
                continue
            for model in db.list_models(conn, endpoint["id"]):
                candidates.append({
                    "account_id": account["id"],
                    "account_label": account["label"],
                    "account_status": account["status"],
                    "endpoint_id": endpoint["id"],
                    "endpoint_name": endpoint["name"],
                    "api_type": endpoint["api_type"],
                    "model": model["model_id"],
                    "pricing_in": model["pricing_in"],
                    "pricing_out": model["pricing_out"],
                    "capabilities": json.loads(model["capabilities_json"]),
                    "quality": model["quality"],
                    "speed": model["speed"],
                    "balance": latest["value"] if latest else None,
                })
    return candidates


def recommend(candidates, task_type="coding", preference="balanced",
              balance_floor=0.0) -> list[Recommendation]:
    if task_type not in EXPECTED_TOKENS:
        task_type = "coding"
    quality_weight, cost_weight = WEIGHTS.get(preference, WEIGHTS["balanced"])
    in_tokens, out_tokens = EXPECTED_TOKENS[task_type]

    filtered = []
    for c in candidates:
        if c.get("account_status") != "ok":
            continue
        bal = c.get("balance")
        if bal is not None and bal < balance_floor:
            continue
        caps = c.get("capabilities", [])
        if task_type != "chat" and task_type not in caps:
            continue
        filtered.append(c)

    if not filtered:
        return []

    costs = [in_tokens / 1e6 * c["pricing_in"] + out_tokens / 1e6 * c["pricing_out"]
             for c in filtered]
    lo, hi = min(costs), max(costs)
    results = []
    for c, cost in zip(filtered, costs):
        normalized = 0.0 if hi == lo else (cost - lo) / (hi - lo)
        score = quality_weight * c["quality"] - cost_weight * normalized * 5
        reasons = [f"matches {task_type}"]
        if cost == lo:
            reasons.append("cheapest")
        if c["quality"] == max(x["quality"] for x in filtered):
            reasons.append("best quality")
        results.append(Recommendation(
            account_id=c["account_id"], account_label=c["account_label"],
            endpoint_id=c["endpoint_id"], endpoint_name=c["endpoint_name"],
            model=c["model"], cost=round(cost, 4), score=round(score, 4),
            reasons=reasons,
        ))
    results.sort(key=lambda r: r.score, reverse=True)
    return results
