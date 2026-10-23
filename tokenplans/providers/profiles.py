from dataclasses import dataclass, field

import yaml

VALID_API_TYPES = {"openai", "anthropic"}


@dataclass
class ModelSpec:
    id: str
    pricing_in: float = 0.0
    pricing_out: float = 0.0
    capabilities: list[str] = field(default_factory=list)
    quality: int = 3
    speed: int = 3


@dataclass
class EndpointSpec:
    pid: str
    name: str
    api_type: str
    base_url: str
    auth: str
    models: list[ModelSpec] = field(default_factory=list)


@dataclass
class BalanceSpec:
    endpoint: str
    path: str
    response_path: str
    method: str = "GET"
    unit: str = ""


@dataclass
class ProviderProfile:
    name: str
    slug: str
    endpoints: list[EndpointSpec]
    balance: BalanceSpec | None = None


def _parse_model(d):
    return ModelSpec(
        id=d["id"],
        pricing_in=float(d.get("in", 0.0)),
        pricing_out=float(d.get("out", 0.0)),
        capabilities=list(d.get("capabilities", [])),
        quality=int(d.get("quality", 3)),
        speed=int(d.get("speed", 3)),
    )


def _parse_endpoint(d):
    return EndpointSpec(
        pid=d["id"],
        name=d.get("name", d["id"]),
        api_type=d["api_type"],
        base_url=d["base_url"],
        auth=d.get("auth", "bearer"),
        models=[_parse_model(m) for m in d.get("models", [])],
    )


def parse_provider_profile(data: dict) -> ProviderProfile:
    balance = data.get("balance")
    return ProviderProfile(
        name=data["name"],
        slug=data.get("slug", data["name"].lower()),
        endpoints=[_parse_endpoint(e) for e in data.get("endpoints", [])],
        balance=BalanceSpec(**balance) if balance else None,
    )


def validate_provider_profile(data: dict) -> list[str]:
    errors = []
    if not isinstance(data, dict):
        return ["profile must be a mapping"]
    for field in ("name", "slug", "endpoints"):
        if field not in data:
            errors.append(f"missing required field: {field}")
    eps = data.get("endpoints", [])
    ids = set()
    if not isinstance(eps, list) or not eps:
        errors.append("endpoints must be a non-empty list")
    else:
        ids = set()
        for i, e in enumerate(eps):
            if not isinstance(e, dict):
                errors.append(f"endpoints[{i}] must be a mapping")
                continue
            for f in ("id", "api_type", "base_url"):
                if f not in e:
                    errors.append(f"endpoints[{i}] missing {f}")
            if e.get("api_type") not in VALID_API_TYPES:
                errors.append(f"endpoints[{i}].api_type must be one of {sorted(VALID_API_TYPES)}")
            if "id" in e:
                ids.add(e["id"])
    bal = data.get("balance")
    if bal is not None:
        if not isinstance(bal, dict):
            errors.append("balance must be a mapping")
        else:
            for f in ("endpoint", "path", "response_path"):
                if f not in bal:
                    errors.append(f"balance missing {f}")
            if bal.get("endpoint") not in ids:
                errors.append("balance.endpoint must reference an endpoint id")
    return errors


def load_provider_profile(path) -> ProviderProfile:
    with open(path) as f:
        data = yaml.safe_load(f)
    return parse_provider_profile(data)
