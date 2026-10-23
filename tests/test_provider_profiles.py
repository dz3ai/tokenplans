import yaml

import tokenplans.providers.profiles as pp


VALID = {
    "name": "DeepSeek",
    "slug": "deepseek",
    "endpoints": [
        {
            "id": "openai",
            "name": "OpenAI-compatible",
            "api_type": "openai",
            "base_url": "https://api.deepseek.com",
            "auth": "bearer",
            "models": [
                {"id": "deepseek-chat", "in": 0.27, "out": 1.10, "capabilities": ["coding", "chat"]}
            ],
        }
    ],
    "balance": {
        "endpoint": "openai",
        "path": "/user/balance",
        "response_path": "balance_infos[0].total_balance",
        "unit": "CNY",
    },
}


def test_parse_valid():
    p = pp.parse_provider_profile(VALID)
    assert p.name == "DeepSeek"
    assert p.slug == "deepseek"
    assert len(p.endpoints) == 1
    e = p.endpoints[0]
    assert e.pid == "openai"
    assert e.api_type == "openai"
    assert e.models[0].id == "deepseek-chat"
    assert e.models[0].pricing_in == 0.27
    assert p.balance.path == "/user/balance"
    assert p.balance.response_path == "balance_infos[0].total_balance"
    assert p.balance.unit == "CNY"


def test_validate_ok():
    assert pp.validate_provider_profile(VALID) == []


def test_validate_missing_required():
    errors = pp.validate_provider_profile({"name": "X"})
    assert any("slug" in e for e in errors)
    assert any("endpoints" in e for e in errors)


def test_validate_bad_api_type():
    data = dict(VALID, endpoints=[{**VALID["endpoints"][0], "api_type": "grpc"}])
    errors = pp.validate_provider_profile(data)
    assert any("api_type" in e for e in errors)


def test_validate_balance_points_to_missing_endpoint():
    data = dict(VALID, balance={**VALID["balance"], "endpoint": "nope"})
    errors = pp.validate_provider_profile(data)
    assert any("balance" in e for e in errors)


def test_validate_empty_endpoints_with_balance_returns_errors():
    errors = pp.validate_provider_profile({
        "name": "X", "slug": "x", "endpoints": [],
        "balance": {"endpoint": "a", "path": "p", "response_path": "r"},
    })
    assert isinstance(errors, list)
    assert any("balance" in e or "endpoints" in e for e in errors)


def test_validate_model_missing_id():
    data = dict(VALID, endpoints=[{**VALID["endpoints"][0],
                                   "models": [{"in": 0.27, "out": 1.10}]}])
    errors = pp.validate_provider_profile(data)
    assert any("models" in e for e in errors)


def test_load_from_file(tmp_path):
    f = tmp_path / "deepseek.yaml"
    f.write_text(yaml.safe_dump(VALID))
    p = pp.load_provider_profile(f)
    assert p.slug == "deepseek"
