import jinja2
import pytest

import tokenplans.agents.profiles as ap
import tokenplans.agents.render as render

PROFILE = ap.AgentProfile(
    name="Claude Code",
    slug="claude-code",
    api_type="anthropic",
    files=[
        ap.FileTemplate(
            "~/.claude/settings.json",
            '{"env":{"ANTHROPIC_BASE_URL":"{{ endpoint.base_url }}",'
            '"ANTHROPIC_API_KEY":"{{ account.key }}","ANTHROPIC_MODEL":"{{ model }}"}}',
        )
    ],
    env=[ap.EnvVar("ANTHROPIC_BASE_URL", "{{ endpoint.base_url }}")],
)

ENDPOINT = {"pid": "anthropic", "name": "Anthropic-compatible",
            "api_type": "anthropic", "base_url": "https://open.bigmodel.cn/api/anthropic"}


def test_renders_file_and_env():
    out = render.render_agent_config(PROFILE, ENDPOINT, "sk-secret", "glm-4.5")
    assert out.env == [("ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/anthropic")]
    (path, content) = out.files[0]
    assert path == "~/.claude/settings.json"
    assert '"ANTHROPIC_API_KEY":"sk-secret"' in content
    assert '"ANTHROPIC_MODEL":"glm-4.5"' in content
    assert "https://open.bigmodel.cn/api/anthropic" in content


def test_strict_undefined_raises():
    p = ap.AgentProfile(name="x", slug="x", api_type="openai",
                        env=[ap.EnvVar("KEY", "{{ account.key_typo }}")])
    with pytest.raises(jinja2.UndefinedError):
        render.render_agent_config(p, ENDPOINT, "k", "m")


def test_no_templates_gives_empty():
    p = ap.AgentProfile(name="x", slug="x", api_type="openai")
    out = render.render_agent_config(p, ENDPOINT, "k", "m")
    assert out.files == [] and out.env == []
