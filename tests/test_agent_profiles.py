import yaml

import tokenplans.agents.profiles as ap


VALID = {
    "name": "Claude Code",
    "slug": "claude-code",
    "api_type": "anthropic",
    "files": [
        {
            "path": "~/.claude/settings.json",
            "template": '{"env":{"ANTHROPIC_BASE_URL":"{{ endpoint.base_url }}"}}',
        }
    ],
    "env": [{"key": "ANTHROPIC_API_KEY", "template": "{{ account.key }}"}],
}


def test_parse_valid():
    p = ap.parse_agent_profile(VALID)
    assert p.name == "Claude Code"
    assert p.api_type == "anthropic"
    assert p.files[0].path == "~/.claude/settings.json"
    assert p.env[0].key == "ANTHROPIC_API_KEY"


def test_validate_ok():
    assert ap.validate_agent_profile(VALID) == []


def test_validate_missing():
    errors = ap.validate_agent_profile({})
    assert any("name" in e for e in errors)
    assert any("api_type" in e for e in errors)


def test_validate_bad_api_type():
    errors = ap.validate_agent_profile({"name": "x", "api_type": "grpc"})
    assert any("api_type" in e for e in errors)


def test_validate_env_entry_missing_key():
    errors = ap.validate_agent_profile({"name": "x", "api_type": "openai", "env": [{"template": "x"}]})
    assert any("key" in e for e in errors)


def test_load_from_file(tmp_path):
    f = tmp_path / "claude-code.yaml"
    f.write_text(yaml.safe_dump(VALID))
    p = ap.load_agent_profile(f)
    assert p.slug == "claude-code"
