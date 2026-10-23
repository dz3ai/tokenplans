from dataclasses import dataclass, field

import yaml

import tokenplans.agents.profiles as ap
import tokenplans.db as db
import tokenplans.providers.profiles as pp
import tokenplans.config as config


@dataclass
class SyncReport:
    providers: int = 0
    endpoints: int = 0
    models: int = 0
    agents: int = 0
    errors: list[str] = field(default_factory=list)


def _yaml_files(d):
    if d is None or not d.is_dir():
        return []
    return sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml"))


def sync_profiles(conn, providers_dir=None, agents_dir=None) -> SyncReport:
    report = SyncReport()
    if providers_dir is None:
        providers_dir = config.profiles_dir() / "providers"
    if agents_dir is None:
        agents_dir = config.profiles_dir() / "agents"

    for path in _yaml_files(providers_dir):
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            errors = pp.validate_provider_profile(data or {})
            if errors:
                report.errors.append(f"{path.name}: {'; '.join(errors)}")
                continue
            prof = pp.parse_provider_profile(data)
            provider_id = db.upsert_provider(conn, prof.name, prof.slug)
            report.providers += 1
            for e in prof.endpoints:
                eid = db.upsert_endpoint(conn, provider_id, e.pid, e.name,
                                         e.api_type, e.base_url, e.auth)
                report.endpoints += 1
                for m in e.models:
                    db.upsert_model(conn, eid, m.id, m.pricing_in, m.pricing_out,
                                    m.capabilities, m.quality, m.speed)
                    report.models += 1
        except Exception as exc:  # noqa: BLE001 - report and continue
            report.errors.append(f"{path.name}: {exc}")

    for path in _yaml_files(agents_dir):
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            errors = ap.validate_agent_profile(data or {})
            if errors:
                report.errors.append(f"{path.name}: {'; '.join(errors)}")
                continue
            prof = ap.parse_agent_profile(data)
            db.upsert_agent(conn, prof.name, prof.slug, prof.api_type)
            report.agents += 1
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"{path.name}: {exc}")

    return report
