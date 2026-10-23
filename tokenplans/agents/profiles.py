from dataclasses import dataclass, field

import yaml

VALID_API_TYPES = {"openai", "anthropic"}


@dataclass
class FileTemplate:
    path: str
    template: str


@dataclass
class EnvVar:
    key: str
    template: str


@dataclass
class AgentProfile:
    name: str
    slug: str
    api_type: str
    files: list[FileTemplate] = field(default_factory=list)
    env: list[EnvVar] = field(default_factory=list)


def parse_agent_profile(data: dict) -> AgentProfile:
    return AgentProfile(
        name=data["name"],
        slug=data.get("slug", data["name"].lower()),
        api_type=data["api_type"],
        files=[FileTemplate(f["path"], f["template"]) for f in data.get("files", [])],
        env=[EnvVar(e["key"], e["template"]) for e in data.get("env", [])],
    )


def validate_agent_profile(data: dict) -> list[str]:
    errors = []
    if not isinstance(data, dict):
        return ["profile must be a mapping"]
    for field in ("name", "api_type"):
        if field not in data:
            errors.append(f"missing required field: {field}")
    if data.get("api_type") not in VALID_API_TYPES:
        errors.append(f"api_type must be one of {sorted(VALID_API_TYPES)}")
    for i, f in enumerate(data.get("files", [])):
        if not isinstance(f, dict) or "path" not in f or "template" not in f:
            errors.append(f"files[{i}] must have path and template")
    for i, e in enumerate(data.get("env", [])):
        if not isinstance(e, dict) or "key" not in e or "template" not in e:
            errors.append(f"env[{i}] must have key and template")
    return errors


def load_agent_profile(path) -> AgentProfile:
    with open(path) as f:
        return parse_agent_profile(yaml.safe_load(f))
