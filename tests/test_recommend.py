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
        _c(1, "coder", 0.1, 0.5, capabilities=["coding"]),
        _c(2, "vision-only", 0.1, 0.5, capabilities=["vision"]),
    ]
    out = scorer.recommend(cands, "research", "balanced")
    assert [r.model for r in out] == ["coder"]


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
