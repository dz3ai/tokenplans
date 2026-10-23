import argparse
import sys

import yaml

import tokenplans.agents.profiles as ap
import tokenplans.providers.profiles as pp


def _validate(path) -> int:
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"file not found: {path}", file=sys.stderr)
        return 1
    if not isinstance(data, dict):
        print("profile must be a mapping", file=sys.stderr)
        return 1
    # try provider shape first, then agent shape
    errors = pp.validate_provider_profile(data)
    if errors and ("name" in data) and ("api_type" in data):
        errors = ap.validate_agent_profile(data)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    return 0


def _sync() -> int:
    import tokenplans.db as db
    import tokenplans.sync as sync

    conn = db.connect()
    db.migrate(conn)
    report = sync.sync_profiles(conn)
    conn.close()
    print(f"providers={report.providers} endpoints={report.endpoints} "
          f"models={report.models} agents={report.agents} errors={len(report.errors)}")
    for e in report.errors:
        print(e, file=sys.stderr)
    return 1 if report.errors else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tokenplans")
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("path")
    sub.add_parser("sync")
    args = parser.parse_args(argv)
    if args.cmd == "validate":
        return _validate(args.path)
    return _sync()
