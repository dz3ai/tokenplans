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
  $("tbody#account-rows").innerHTML = rows.map((a) =>
    `<tr><td>${a.label}</td><td>${a.provider_id}</td><td>${a.status}</td><td>—</td><td>${a.key_masked}</td></tr>`
  ).join("");
}

async function loadAgents() {
  const rows = await api("/api/agents");
  $("tbody#agent-rows").innerHTML = rows.map((a) =>
    `<tr><td>${a.name}</td><td>${a.api_type}</td><td>—</td></tr>`
  ).join("");
}

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
