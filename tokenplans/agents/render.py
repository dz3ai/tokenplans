from dataclasses import dataclass, field

from jinja2 import Environment, StrictUndefined

import tokenplans.agents.profiles as ap


@dataclass
class RenderedConfig:
    files: list[tuple[str, str]] = field(default_factory=list)
    env: list[tuple[str, str]] = field(default_factory=list)


def render_agent_config(profile: ap.AgentProfile, endpoint: dict, account_key: str,
                        model: str) -> RenderedConfig:
    context = {
        "endpoint": endpoint,
        "account": {"key": account_key},
        "model": model,
    }
    jinja_env = Environment(undefined=StrictUndefined)
    files = []
    for ft in profile.files:
        content = jinja_env.from_string(ft.template).render(context)
        files.append((ft.path, content))
    env = []
    for ev in profile.env:
        env.append((ev.key, jinja_env.from_string(ev.template).render(context)))
    return RenderedConfig(files=files, env=env)
