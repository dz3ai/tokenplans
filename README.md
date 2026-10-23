# tokenplans

Local dashboard for AI token-plan accounts, balances, and agent config.

## Run

    pip install -e ".[dev]"
    uvicorn tokenplans.app:app --reload
    open http://127.0.0.1:8000

## CLI

    tokenplans validate path/to/profile.yaml
    tokenplans sync

## Test

    pytest

## Not yet in v1

- Background auto-poll scheduler is not started.
- Balance endpoint URLs/paths in provider profiles are best-effort and must be
  verified against each provider's live docs.
- Config apply keeps only one `.bak` generation.
