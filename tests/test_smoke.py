import asyncio

import httpx

import tokenplans.app as app_mod
import tokenplans.db as db


def test_full_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENPLANS_HOME", str(tmp_path))

    async def run():
        transport = httpx.ASGITransport(app=app_mod.create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # sync profiles
            assert (await client.post("/api/sync")).json()["providers"] >= 4
            # add an account with a real key, masked in response
            acct = (await client.post("/api/accounts", json={
                "provider_id": 1, "label": "my plan", "key": "sk-live-secret-key-000"
            })).json()
            assert "sk-live-secret-key-000" not in str(acct)
            # manual balance
            r = await client.post(f"/api/accounts/{acct['id']}/balance",
                                  json={"value": 100.0, "unit": "CNY", "source": "manual"})
            assert r.status_code == 200
            # recommend returns at least one candidate
            recs = (await client.get("/api/recommend", params={"task_type": "coding"})).json()
            assert isinstance(recs, list)
            assert len(recs) >= 1

    asyncio.run(run())
