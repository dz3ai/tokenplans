import tokenplans.db as db
import tokenplans.recommend.scorer as scorer


def _c(account_id, model, pricing_in, pricing_out, quality=3, capabilities=None,
       balance=100.0, status="ok"):
    return {
        "account_id": account_id, "account_label": f"acct{account_id}",
        "account_status": status, "endpoint_id": account_id,
        "endpoint_name": f"ep{account_id}", "api_type": "openai", "model": model,
        "pricing_in": pricing_in, "pricing_out": pricing_out,
        "capabilities": capabilities or ["coding"], "quality": quality, "speed": 3,
        "balance": balance,
    }


def test_cheapest_picks_lowest_cost():
    cands = [
        _c(1, "cheap", 0.1, 0.5),
        _c(2, "expensive", 10.0, 20.0),
    ]
    out = scorer.recommend(cands, "coding", "cheapest")
    assert out[0].model == "cheap"


def test_best_picks_highest_quality():
    cands = [
        _c(1, "low", 0.1, 0.5, quality=2),
        _c(2, "high", 0.1, 0.5, quality=5),
    ]
    out = scorer.recommend(cands, "coding", "best")
    assert out[0].model == "high"


def test_filters_out_of_capability():
    cands = [
        _c(1, "researcher", 0.1, 0.5, capabilities=["research"]),
        _c(2, "vision-only", 0.1, 0.5, capabilities=["vision"]),
    ]
    out = scorer.recommend(cands, "research", "balanced")
    assert [r.model for r in out] == ["researcher"]


def test_filters_low_balance():
    cands = [
        _c(1, "broke", 0.1, 0.5, balance=1.0),
        _c(2, "rich", 0.1, 0.5, balance=50.0),
    ]
    out = scorer.recommend(cands, "coding", "balanced", balance_floor=10.0)
    assert [r.model for r in out] == ["rich"]


def test_filters_error_status():
    cands = [
        _c(1, "dead", 0.1, 0.5, status="error"),
        _c(2, "alive", 0.1, 0.5),
    ]
    out = scorer.recommend(cands, "coding", "balanced")
    assert [r.model for r in out] == ["alive"]


def test_chat_always_allowed():
    cands = [_c(1, "vision-only", 0.1, 0.5, capabilities=["vision"])]
    out = scorer.recommend(cands, "chat", "balanced")
    assert len(out) == 1


def test_reasons_include_task():
    out = scorer.recommend([_c(1, "m", 0.1, 0.5)], "coding", "balanced")
    assert "coding" in " ".join(out[0].reasons)


def test_build_candidates_from_db(conn):
    pid = db.upsert_provider(conn, "DeepSeek", "deepseek")
    eid = db.upsert_endpoint(conn, pid, "openai", "OpenAI", "openai",
                             "https://api.deepseek.com", "bearer")
    db.upsert_model(conn, eid, "deepseek-chat", 0.27, 1.10, ["coding", "chat"])
    aid = db.create_account(conn, pid, "token plan", "enc-key")
    db.record_balance(conn, aid, 42.5, "CNY", "manual", ts="2026-10-22T00:00:00")

    cands = scorer.build_candidates(conn)

    assert len(cands) == 1
    c = cands[0]
    assert c["model"] == "deepseek-chat"
    assert c["account_label"] == "token plan"
    assert c["capabilities"] == ["coding", "chat"]
    assert c["balance"] == 42.5
