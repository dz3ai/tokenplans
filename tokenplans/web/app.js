const $ = (sel) => document.querySelector(sel);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function loadAccounts() {
  const rows = await api("/api/accounts");
  $("tbody#account-rows").innerHTML = rows.map((a) => {
    const bal = a.latest_balance
      ? `${a.latest_balance.value} ${a.latest_balance.unit || ""}`.trim()
      : "—";
    return `<tr><td>${a.label}</td><td>${a.provider_id}</td><td>${a.status}</td><td>${bal}</td><td>${a.key_masked}</td><td><button data-add-balance="${a.id}">Add balance</button></td></tr>`;
  }).join("");
}

async function loadAgents() {
  const rows = await api("/api/agents");
  $("tbody#agent-rows").innerHTML = rows.map((a) =>
    `<tr><td>${a.name}</td><td>${a.api_type}</td><td><button data-gen-config="${a.slug}">Generate config</button></td></tr>`
  ).join("");
}

$("tbody#account-rows").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-add-balance]");
  if (!btn) return;
  const id = btn.dataset.addBalance;
  const v = prompt("Balance value:");
  if (v === null) return;
  const unit = prompt("Unit:", "");
  if (unit === null) return;
  await api(`/api/accounts/${id}/balance`, {
    method: "POST",
    body: { value: Number(v), unit, source: "manual" },
  });
  loadAccounts();
});

let accountsCache = null;
let endpointsCache = null;
async function ensureLookups() {
  if (accountsCache === null) accountsCache = await api("/api/accounts");
  if (endpointsCache === null) endpointsCache = await api("/api/endpoints");
}

$("tbody#agent-rows").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-gen-config]");
  if (!btn) return;
  const slug = btn.dataset.genConfig;
  await ensureLookups();
  const a = prompt("Account id:");
  if (a === null) return;
  const eid = prompt("Endpoint id:");
  if (eid === null) return;
  const model = prompt("Model:");
  if (model === null) return;
  const body = { agent_slug: slug, account_id: Number(a), endpoint_id: Number(eid), model };
  const preview = await api("/api/config/preview", { method: "POST", body });
  const files = (preview.files || []).map(([path]) => path).join("\n");
  const env = (preview.env || []).map(([k, v]) => `${k}=${v}`).join("\n");
  alert(`Files:\n${files}\n\nEnv:\n${env}`);
  if (confirm("Apply these files to disk?")) {
    const res = await api("/api/config/apply", { method: "POST", body });
    alert(`Written:\n${res.written.join("\n")}`);
  }
});

$("#sync").onclick = async () => { await api("/api/sync", { method: "POST" }); alert("synced"); };
$("#add-account").onsubmit = async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  await api("/api/accounts", { method: "POST", body: {
    provider_id: Number(f.get("provider_id")),
    label: f.get("label"), key: f.get("key"),
  }});
  loadAccounts();
};
$("#run-recommend").onclick = async () => {
  const t = $("#task-type").value, p = $("#preference").value;
  const results = await api(`/api/recommend?task_type=${t}&preference=${p}`);
  $("#recommend-results").innerHTML = results.map((r) =>
    `<li>${r.account_label} / ${r.model} — est cost ${r.cost} (${r.reasons.join(", ")})</li>`
  ).join("");
};

loadAccounts();
loadAgents();
