# tokenplans

Local dashboard for AI token-plan accounts, balances, and agent config.

## Run

    pip install -e ".[dev]"
    uvicorn tokenplans.app:app --reload
    open http://127.0.0.1:8000

## CLI

    tokenplans profiles validate path/to/profile.yaml
    tokenplans sync

## Test

    pytest
