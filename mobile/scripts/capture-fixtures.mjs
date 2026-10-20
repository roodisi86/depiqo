#!/usr/bin/env node
// Captures real API responses from a running Depiqo backend into fixtures/*.json,
// so the zod schemas in src/api/schemas.ts can be tested against reality.
//
// Usage:  node scripts/capture-fixtures.mjs [baseUrl]
//         default baseUrl: http://127.0.0.1:5000/api/v1
//         Optional: DEPIQO_INVITE_TOKENS=tok1,tok2 (invitation tokens from the mails under Beheer > Mail);
//         the first one that is still valid is saved as fixtures/invite.json (read only, never accepted).
//
// What it does to the backend: it logs in as a few seeded demo tenants (this creates a device
// session and a "new login" notification per tenant), reads data, asks one buy quote
// (a quote moves no money) and logs out again at the end. It never agrees, disputes,
// orders, withdraws or uploads.
//
// Tokens are never written to disk: access, refresh and mfa tokens are replaced by placeholders,
// and invitation tokens are left out of the manifest.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const BASE = (process.argv[2] || process.env.DEPIQO_API || "http://127.0.0.1:5000/api/v1").replace(/\/$/, "");
const PASSWORD = process.env.DEPIQO_DEMO_PASSWORD || "Depiqo-demo-2026";
const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "fixtures");
mkdirSync(OUT, { recursive: true });

const manifest = [];
const SECRET_KEYS = new Set(["access_token", "refresh_token", "mfa_token"]);

function redact(value) {
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === "object") {
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      out[k] = SECRET_KEYS.has(k) && typeof v === "string" ? `REDACTED_${k.toUpperCase()}` : redact(v);
    }
    return out;
  }
  return value;
}

async function call(method, path, { token, body, lang = "nl", idem } = {}) {
  const headers = { Accept: "application/json", "Accept-Language": lang, "X-App-Platform": "ios", "X-App-Version": "1.0.0" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (idem) headers["Idempotency-Key"] = idem;
  const res = await fetch(BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch { json = null; }
  return { status: res.status, json, type: res.headers.get("content-type") || "" };
}

function save(name, method, shownPath, res, as) {
  if (res.json === null) {
    console.log(`skip ${name}: ${res.status} ${res.type}`);
    return;
  }
  writeFileSync(join(OUT, `${name}.json`), JSON.stringify(redact(res.json), null, 2) + "\n");
  manifest.push({ file: `${name}.json`, method, path: shownPath, status: res.status, as: as || null });
  console.log(`saved ${name} (${res.status})`);
}

async function get(name, path, token, as, lang) {
  const res = await call("GET", path, { token, lang });
  save(name, "GET", path, res, as);
  return res;
}

const device = { name: "Fixture capture", platform: "ios", app_version: "1.0.0" };

async function login(email) {
  const res = await call("POST", "/auth/login", { body: { email, password: PASSWORD, device } });
  if (res.status !== 200 || !res.json?.access_token) throw new Error(`login ${email}: ${res.status} ${JSON.stringify(res.json?.error)}`);
  return { res, token: res.json.access_token, refresh: res.json.refresh_token };
}

const sessions = [];

async function main() {
  await get("config", "/config", null, null);

  // Errors
  save("error-token-invalid", "GET", "/deposits", await call("GET", "/deposits", { token: "not-a-real-token" }), null);
  save("error-token-missing", "GET", "/me", await call("GET", "/me"), null);
  save("error-token-invalid-fr", "GET", "/me", await call("GET", "/me", { token: "not-a-real-token", lang: "fr" }), null);
  save("error-refresh-invalid", "POST", "/auth/refresh", await call("POST", "/auth/refresh", { body: { refresh_token: "nope" } }), null);
  save("error-login-validation", "POST", "/auth/login", await call("POST", "/auth/login", { body: { email: "", password: "", device } }), null);
  save("error-invite-expired", "GET", "/invites/<expired>", await call("GET", "/invites/this-token-does-not-exist-1234567890"), null);

  // A pending invitation, if the demo still has one (read only)
  for (const tok of (process.env.DEPIQO_INVITE_TOKENS || "").split(",").filter(Boolean)) {
    const r = await call("GET", `/invites/${tok}`);
    if (r.status === 200) { save("invite", "GET", "/invites/<token>", r, null); break; }
  }

  // Daan: deposits plus an active investment account
  const daan = await login("daan@huurder.test");
  save("login-session", "POST", "/auth/login", daan.res, "daan");
  const ref = await call("POST", "/auth/refresh", { body: { refresh_token: daan.refresh } });
  save("refresh-token-pair", "POST", "/auth/refresh", ref, "daan");
  const dt = ref.json.access_token;
  sessions.push(dt);
  await get("me-daan", "/me", dt, "daan");
  const deps = await get("deposits-daan", "/deposits", dt, "daan");
  for (const [i, d] of (deps.json?.items || []).slice(0, 2).entries()) {
    await get(`deposit-daan-${i}`, `/deposits/${d.pid}`, dt, "daan");
  }
  if (deps.json?.items?.[0]) {
    const pid = deps.json.items[0].pid;
    await get("deposit-events-daan", `/deposits/${pid}/events?limit=5`, dt, "daan");
    await get("documents-daan", `/deposits/${pid}/documents`, dt, "daan");
    await get("settlement-null", `/deposits/${pid}/settlement`, dt, "daan");
  }
  await get("error-not-found", "/deposits/does-not-exist", dt, "daan");
  await get("invest-overview-active", "/invest", dt, "daan");
  await get("invest-portfolios", "/invest/portfolios?amount_cents=100000", dt, "daan");
  await get("invest-appropriateness-daan", "/invest/appropriateness", dt, "daan");
  await get("invest-terms-daan", "/invest/terms", dt, "daan");
  await get("invest-deposit-instructions", "/invest/deposit-instructions", dt, "daan");
  await get("invest-orders", "/invest/orders?limit=5", dt, "daan");
  await get("invest-withdrawals", "/invest/withdrawals?limit=5", dt, "daan");
  await get("invest-transactions", "/invest/transactions?limit=5", dt, "daan");
  await get("invest-statements", "/invest/statements", dt, "daan");
  await get("invest-fee-change", "/invest/fee-change", dt, "daan");
  const q = await call("POST", "/invest/orders/quote", { token: dt, body: { side: "buy", amount_cents: 10000 } });
  save("invest-quote-buy", "POST", "/invest/orders/quote", q, "daan");
  const qs = await call("POST", "/invest/orders/quote", { token: dt, body: { side: "sell", amount_cents: 5000 } });
  save("invest-quote-sell", "POST", "/invest/orders/quote", qs, "daan");
  await get("activity-daan", "/activity?limit=10", dt, "daan");
  await get("notifications-daan", "/notifications?limit=10", dt, "daan");
  await get("notifications-daan-en", "/notifications?limit=3", dt, "daan", "en");
  await get("support-daan", "/support", dt, "daan");
  await get("devices-daan", "/auth/devices", dt, "daan");
  await get("delete-request-daan", "/me/delete-request", dt, "daan");

  // Sanne: settlement proposed, no investment account yet (onboarding)
  const sanne = await login("sanne@huurder.test");
  sessions.push(sanne.token);
  await get("me-sanne", "/me", sanne.token, "sanne");
  const sd = await get("deposits-sanne", "/deposits", sanne.token, "sanne");
  for (const d of sd.json?.items || []) {
    const det = await call("GET", `/deposits/${d.pid}`, { token: sanne.token });
    if (det.json?.status === "settlement_proposed") {
      save("deposit-settlement-proposed", "GET", `/deposits/${d.pid}`, det, "sanne");
      await get("settlement-proposed", `/deposits/${d.pid}/settlement`, sanne.token, "sanne");
      await get("documents-sanne", `/deposits/${d.pid}/documents`, sanne.token, "sanne");
      break;
    }
  }
  await get("invest-overview-onboarding", "/invest", sanne.token, "sanne");
  await get("invest-appropriateness-sanne", "/invest/appropriateness", sanne.token, "sanne");
  await get("invest-terms-sanne", "/invest/terms", sanne.token, "sanne");
  await get("delete-request-sanne", "/me/delete-request", sanne.token, "sanne");

  // Mila: guarantee, no money paid
  const mila = await login("mila@huurder.test");
  sessions.push(mila.token);
  await get("me-mila", "/me", mila.token, "mila");
  const md = await get("deposits-mila", "/deposits", mila.token, "mila");
  if (md.json?.items?.[0]) await get("deposit-guarantee", `/deposits/${md.json.items[0].pid}`, mila.token, "mila");
  await get("invest-mila", "/invest", mila.token, "mila");

  // Sofie: e-DEPO, release form ready
  const sofie = await login("sofie@huurder.test");
  sessions.push(sofie.token);
  const so = await get("deposits-sofie", "/deposits", sofie.token, "sofie");
  for (const d of so.json?.items || []) {
    const det = await call("GET", `/deposits/${d.pid}`, { token: sofie.token });
    if (det.json?.release_form_available) {
      save("deposit-external-release", "GET", `/deposits/${d.pid}`, det, "sofie");
      await get("settlement-agreed", `/deposits/${d.pid}/settlement`, sofie.token, "sofie");
      break;
    }
  }

  // Mohamed: doorbeleggen chosen
  const mo = await login("mohamed@huurder.test");
  sessions.push(mo.token);
  const mod = await get("deposits-mohamed", "/deposits", mo.token, "mohamed");
  for (const d of mod.json?.items || []) {
    const pc = await call("GET", `/deposits/${d.pid}/payout-choice`, { token: mo.token });
    if (pc.status === 200 && (pc.json?.choice || pc.json?.available)) {
      save("payout-choice", "GET", `/deposits/${d.pid}/payout-choice`, pc, "mohamed");
      await get("deposit-mohamed", `/deposits/${d.pid}`, mo.token, "mohamed");
      break;
    }
  }
  await get("activity-mohamed", "/activity?limit=10", mo.token, "mohamed");

  // Iris: appropriateness 'niet passend', confirmed
  const iris = await login("iris@huurder.test");
  sessions.push(iris.token);
  await get("invest-appropriateness-iris", "/invest/appropriateness", iris.token, "iris");
  await get("invest-overview-iris", "/invest", iris.token, "iris");
}

try {
  await main();
} finally {
  for (const t of sessions) await call("POST", "/auth/logout", { token: t }).catch(() => {});
  writeFileSync(join(OUT, "_manifest.json"), JSON.stringify({ base: "<dev server>", captured_at: new Date().toISOString(), items: manifest }, null, 2) + "\n");
  console.log(`manifest: ${manifest.length} fixtures`);
}
