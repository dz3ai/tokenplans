import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import tokenplans.agents.profiles as ap
import tokenplans.agents.render as render
import tokenplans.config as config
import tokenplans.db as db
import tokenplans.balance.poller as poller
import tokenplans.recommend.scorer as scorer
import tokenplans.secrets as secrets
import tokenplans.sync as sync


class AccountIn(BaseModel):
    provider_id: int
    label: str
    key: str
    endpoint_scope: list[str] | None = None
    extra: dict | None = None


class BalanceIn(BaseModel):
    value: float
    unit: str = ""
    source: str = "manual"


class BindingIn(BaseModel):
    account_id: int
    endpoint_id: int
    model: str


class ConfigIn(BaseModel):
    agent_slug: str
    account_id: int
    endpoint_id: int
    model: str


def create_app() -> FastAPI:
    app = FastAPI(title="tokenplans")
    app.mount("/static", StaticFiles(directory=str(config.web_dir())), name="static")

    @app.get("/")
    def index():
        return FileResponse(config.web_dir() / "index.html")

    def _conn():
        c = db.connect()
        db.migrate(c)
        return c

    def _secrets():
        return secrets.Secrets(secrets.load_or_create_key())

    @app.post("/api/sync")
    def api_sync():
        with _conn() as c:
            return sync.sync_profiles(c).__dict__

    @app.get("/api/providers")
    def api_providers():
        with _conn() as c:
            return db.list_providers(c)

    @app.get("/api/endpoints")
    def api_endpoints(provider_id: int | None = None):
        with _conn() as c:
            return db.list_endpoints(c, provider_id)

    @app.get("/api/accounts")
    def api_accounts():
        with _conn() as c:
            out = []
            for a in db.list_accounts(c):
                a = dict(a)
                a["key_masked"] = _secrets().mask(_secrets().decrypt(a["key_encrypted"]))
                a.pop("key_encrypted")
                out.append(a)
            return out

    @app.post("/api/accounts")
    def api_create_account(body: AccountIn):
        with _conn() as c:
            aid = db.create_account(c, body.provider_id, body.label,
                                    _secrets().encrypt(body.key),
                                    endpoint_scope=body.endpoint_scope, extra=body.extra)
            acct = db.get_account(c, aid)
            return {"id": aid, "label": acct["label"], "key_masked": _secrets().mask(body.key)}

    @app.post("/api/accounts/{account_id}/balance")
    def api_manual_balance(account_id: int, body: BalanceIn):
        with _conn() as c:
            if db.get_account(c, account_id) is None:
                raise HTTPException(404, "account not found")
            db.record_balance(c, account_id, body.value, body.unit, body.source)
            return {"ok": True}

    @app.get("/api/agents")
    def api_agents():
        with _conn() as c:
            return db.list_agents(c)

    @app.get("/api/bindings")
    def api_bindings():
        with _conn() as c:
            return db.list_bindings(c)

    @app.put("/api/bindings/{agent_slug}")
    def api_put_binding(agent_slug: str, body: BindingIn):
        with _conn() as c:
            agent = c.execute("SELECT id FROM agents WHERE slug=?", (agent_slug,)).fetchone()
            if agent is None:
                raise HTTPException(404, "agent not found")
            db.upsert_binding(c, agent["id"], body.account_id, body.endpoint_id, body.model)
            return {"ok": True}

    @app.post("/api/config/preview")
    def api_config_preview(body: ConfigIn):
        with _conn() as c:
            return _render(c, body.agent_slug, body.account_id, body.endpoint_id, body.model)

    @app.post("/api/config/apply")
    def api_config_apply(body: ConfigIn):
        with _conn() as c:
            rendered = _render(c, body.agent_slug, body.account_id, body.endpoint_id, body.model)
            written = []
            for path, content in rendered["files"]:
                p = Path(path).expanduser()
                p.parent.mkdir(parents=True, exist_ok=True)
                if p.exists():
                    shutil.copy2(p, str(p) + ".bak")
                p.write_text(content)
                written.append(str(p))
            return {"written": written}

    @app.get("/api/recommend")
    def api_recommend(task_type: str = "coding", preference: str = "balanced",
                      balance_floor: float = 0.0):
        with _conn() as c:
            return scorer.recommend(scorer.build_candidates(c), task_type, preference, balance_floor)

    @app.post("/api/poll/{account_id}")
    def api_poll(account_id: int):
        with _conn() as c:
            account = db.get_account(c, account_id)
            if account is None:
                raise HTTPException(404, "account not found")
            endpoint = db.list_endpoints(c, account["provider_id"])[0]
            return poller.poll_account(c, _secrets(), account_id, endpoint,
                                       {"path": "/user/balance",
                                        "response_path": "data.available",
                                        "method": "GET", "unit": ""})

    return app


def _render(conn, agent_slug, account_id, endpoint_id, model):
    agent_row = conn.execute("SELECT id FROM agents WHERE slug=?", (agent_slug,)).fetchone()
    if agent_row is None:
        raise HTTPException(404, "agent not found")
    account = db.get_account(conn, account_id)
    if account is None:
        raise HTTPException(404, "account not found")
    endpoint = conn.execute("SELECT * FROM endpoints WHERE id=?", (endpoint_id,)).fetchone()
    if endpoint is None:
        raise HTTPException(404, "endpoint not found")

    # Templates live in the YAML files; load the agent profile by slug.
    profile_path = config.profiles_dir() / "agents" / f"{agent_slug}.yaml"
    if not profile_path.exists():
        raise HTTPException(404, f"agent profile not found: {agent_slug}.yaml")
    profile = ap.load_agent_profile(profile_path)

    key = secrets.Secrets(secrets.load_or_create_key()).decrypt(account["key_encrypted"])
    rendered = render.render_agent_config(profile, dict(endpoint), key, model)
    return {"files": rendered.files, "env": rendered.env}
