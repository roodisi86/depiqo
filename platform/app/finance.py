"""Read models for money: reconciliation (dossier versus bank versus evidence) and unit economics.

Nothing here changes a deposit. Staff settings hold the assumptions for unit economics until
partner contracts exist.
"""
import json
from datetime import timedelta

from flask import current_app

from . import billing, db, providers
from . import states as S
from .util import date_nl, now, now_iso, parse_dt, today

SECURED_LIKE = (S.SECURED, S.MOVE_OUT, S.SETTLEMENT_PROPOSED, S.AGREED, S.DISPUTED, S.PAYOUT_PENDING)


# ---------------------------------------------------------------- staff settings

SETTINGS = {
    "partner_cost_active_cents": ("Partnerkosten per actieve Depiqo-borgrekening per maand", 50),
    "partner_cost_new_cents": ("Partnerkosten per nieuw dossier op een Depiqo-borgrekening (KYC en openen)", 200),
    "partner_cost_external_cents": ("Partnerkosten per actief dossier met borg elders per maand", 0),
    "partner_cost_invest_account_cents": ("Partnerkosten per actieve beleggingsrekening per maand (Invest)", 30),
}


def get_settings():
    values = {k: default for k, (_, default) in SETTINGS.items()}
    for row in db.all_("SELECT key, value FROM staff_settings"):
        if row["key"] in SETTINGS:
            try:
                values[row["key"]] = int(row["value"])
            except ValueError:
                pass
    return values


def set_settings(values, user_id):
    with db.transaction():
        for key, value in values.items():
            if key not in SETTINGS or not isinstance(value, int) or value < 0:
                raise ValueError("Ongeldige instelling.")
            db.run("INSERT INTO staff_settings (key, value, updated_at, updated_by) VALUES (?, ?, ?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at, updated_by = excluded.updated_by",
                   (key, str(value), now_iso(), user_id))


# ---------------------------------------------------------------- reconciliation

def _instruction_summary(instrs):
    if not instrs:
        return None
    latest = instrs[-1]
    from .services import INSTRUCTION_KINDS, INSTRUCTION_STATUSES
    tone = {"pending": "wait", "sent": "wait", "acknowledged": "info", "failed": "alert", "confirmed": "ok"}[latest["status"]]
    return {"kind": INSTRUCTION_KINDS[latest["kind"]], "status": INSTRUCTION_STATUSES[latest["status"]], "tone": tone,
            "attempts": latest["attempts"], "error": latest["last_error"]}


def reconciliation(org_id=None, only_exceptions=False):
    """Per dossier: obligation, bank ledger, instruction status and evidence, plus the exceptions.
    Returns (rows, totals)."""
    cfg = current_app.config
    release_days = int(cfg.get("RELEASE_CONFIRM_DAYS", 5))
    declared_days = int(cfg.get("DECLARED_MAX_DAYS", 14))
    where, params = "", []
    if org_id is not None:
        where, params = " AND d.org_id = ?", [org_id]
    rows = db.all_(
        "SELECT d.*, o.name AS org_name, p.address, p.city, b.id AS acct_id, b.provider, b.external_id, b.status AS bank_status, "
        "b.ledger_balance_cents FROM deposits d JOIN organizations o ON o.id = d.org_id JOIN properties p ON p.id = d.property_id "
        "LEFT JOIN bank_accounts b ON b.deposit_id = d.id WHERE d.status NOT IN (?, ?)" + where + " ORDER BY o.name, d.reference",
        (S.CONCEPT, S.CANCELLED, *params))
    ids = [r["id"] for r in rows]
    instrs = {}
    if ids:
        for chunk in range(0, len(ids), 500):
            part = ids[chunk:chunk + 500]
            for i in db.all_(f"SELECT * FROM bank_instructions WHERE deposit_id IN ({','.join('?' * len(part))}) ORDER BY id", part):
                instrs.setdefault(i["deposit_id"], []).append(i)
    event_errors = {}
    for e in db.all_("SELECT provider, payload_json, type, error, received_at FROM bank_events WHERE error IS NOT NULL ORDER BY id"):
        try:
            ext = json.loads(e["payload_json"]).get("external_id")
        except ValueError:
            ext = None
        event_errors.setdefault((e["provider"], ext), []).append(e)
    from .services import active_provider
    active = active_provider()
    invest_issues = {}
    if org_id is None:
        # Depiqo staff only: doorbeleggen that fell back or was not recorded. Never in an organisation's reconciliation.
        from . import investing
        for c in investing.payout_exceptions():
            invest_issues[c["deposit_id"]] = c
    release_cutoff = now() - timedelta(days=release_days)
    declared_cutoff = now() - timedelta(days=declared_days)
    out = []
    totals = {"obligation": 0, "ledger": 0, "locked": 0, "exceptions": 0, "dossiers": 0}
    for d in rows:
        status = d["hold_previous_status"] if d["status"] == S.LEGAL_HOLD else d["status"]
        exceptions = []
        mine = instrs.get(d["id"], [])
        if d["holding"] == "depiqo" and d["acct_id"] and d["provider"] != active and d["status"] != S.CLOSED:
            exceptions.append("Sandboxrekening terwijl de sandbox niet de actieve partner is: telt niet als zekerheid"
                              if d["provider"] == "sandbox" else f"Rekening bij partner '{d['provider']}', niet bij de actieve partner")
        if d["holding"] == "depiqo" and d["acct_id"]:
            if status in SECURED_LIKE and d["status"] != S.PAYOUT_PENDING and d["ledger_balance_cents"] < d["amount_cents"]:
                exceptions.append("Saldo bij de bank is lager dan de vereiste borg terwijl de zekerheid geregistreerd staat")
            if status == S.SECURED and d["bank_status"] != "blocked":
                exceptions.append("Dossier staat als zekerheid, maar de bank meldt geen blokkering")
            if d["status"] == S.CLOSED and d["bank_status"] != "closed":
                exceptions.append("Dossier gesloten, maar de rekening bij de bank niet")
            for e in event_errors.get((d["provider"], d["external_id"]), []):
                exceptions.append(f"Bankbericht {e['type']} met fout: {e['error']}")
        for i in mine:
            if i["status"] == "failed":
                exceptions.append(f"Bankopdracht mislukt: {i['last_error'] or 'onbekende fout'}")
            elif i["kind"] == "release" and i["status"] != "confirmed" and parse_dt(i["created_at"]) < release_cutoff:
                days = (now() - parse_dt(i["created_at"])).days
                exceptions.append(f"Vrijgave al {days} dagen niet bevestigd door de bank")
        if (d["holding"] == "external" and d["evidence_level"] == "declared" and d["status"] not in (S.CLOSED,)
                and d["evidence_set_at"] and parse_dt(d["evidence_set_at"]) < declared_cutoff):
            days = (now() - parse_dt(d["evidence_set_at"])).days
            exceptions.append(f"Alleen verklaard door de beheerder, al {days} dagen zonder bewijs")
        if d["holding"] == "external" and d["status"] != S.CLOSED:
            if not d["provider_kind"]:
                exceptions.append("Borg elders zonder aanbieder: leg vast waar de borg staat")
            exp = providers.expiry_info(d)
            if exp and exp[0] < 0:
                exceptions.append(f"Garantie verlopen op {date_nl(exp[1])} terwijl het dossier nog loopt")
            elif exp and exp[0] <= providers.EXPIRY_WARN_DAYS:
                exceptions.append(f"Garantie verloopt over {exp[0]} {'dag' if exp[0] == 1 else 'dagen'} ({date_nl(exp[1])})")
        if d["id"] in invest_issues:
            c = invest_issues[d["id"]]
            exceptions.append(("Doorbeleggen niet gelukt, deel naar de eigen rekening van de huurder: " if c["status"] == "fallback"
                               else "Doorbeleggen betaald aan de partner, niet verwerkt op de beleggingsrekening: ") + (c["note"] or ""))
        if d["status"] == S.CLOSED and not exceptions:
            continue  # history without problems is not shown
        locked = None
        trusted = d["holding"] != "depiqo" or not d["acct_id"] or d["provider"] == active
        if d["holding"] == "depiqo" and d["legal_lock_status"] == "active" and trusted:
            locked = d["eligible_value_cents"]
        elif d["holding"] == "external" and d["evidence_level"] == "legal" and d["status"] != S.CLOSED:
            locked = d["amount_cents"]
        row = {"d": d, "obligation": d["amount_cents"], "ledger": d["ledger_balance_cents"] if d["acct_id"] else None,
               "locked": locked, "instruction": _instruction_summary(mine), "assurance": S.assurance(d, trusted), "exceptions": exceptions}
        if d["status"] != S.CLOSED:
            totals["dossiers"] += 1
            totals["obligation"] += d["amount_cents"]
            totals["ledger"] += row["ledger"] or 0
            totals["locked"] += locked or 0
        totals["exceptions"] += len(exceptions)
        if only_exceptions and not exceptions:
            continue
        out.append(row)
    out.sort(key=lambda r: (not r["exceptions"],))
    return out, totals


def failed_instructions():
    return db.all_("SELECT i.*, d.pid, d.reference, o.name AS org_name FROM bank_instructions i JOIN deposits d ON d.id = i.deposit_id "
                   "JOIN organizations o ON o.id = d.org_id WHERE i.status IN ('failed', 'pending', 'sent') ORDER BY i.id DESC LIMIT 100")


# ---------------------------------------------------------------- unit economics

def new_by_holding(org_id, period):
    start, end = billing.period_bounds(period)
    rows = db.all_("SELECT holding, COUNT(*) AS n FROM deposits WHERE org_id = ? AND activated_at IS NOT NULL "
                   "AND activated_at >= ? AND activated_at < ? AND status != ? GROUP BY holding",
                   (org_id, start.isoformat(), end.isoformat(), S.CANCELLED))
    counts = {"external": 0, "depiqo": 0}
    for r in rows:
        counts[r["holding"]] = r["n"]
    return counts


def unit_economics(period=None):
    """Per organisation and in total: active dossiers by holding, monthly revenue from the plan logic,
    assumed partner costs and gross margin. Partner costs come from staff settings (assumptions)."""
    period = period or today().strftime("%Y-%m")
    cost = get_settings()
    orgs = db.all_("SELECT * FROM organizations ORDER BY name")
    rows = []
    total = {"external": 0, "depiqo": 0, "new_depiqo": 0, "new": 0, "list": 0, "billed": 0, "cost": 0, "margin": 0}
    for org in orgs:
        est = billing.estimate(org, period)
        plan = est["plan"]
        counts = est["counts"]
        new = new_by_holding(org["id"], period)
        _, list_subtotal = billing.price(counts["external"], counts["depiqo"], est["new"], plan, pilot=False)
        partner_cost = (counts["depiqo"] * cost["partner_cost_active_cents"] + new["depiqo"] * cost["partner_cost_new_cents"]
                        + counts["external"] * cost["partner_cost_external_cents"])
        active = counts["external"] + counts["depiqo"]
        margin = est["subtotal"] - partner_cost
        marginal_depiqo = plan["extra_depiqo_cents"] - cost["partner_cost_active_cents"]
        marginal_new = plan["new_dossier_cents"] - cost["partner_cost_new_cents"]
        rows.append({
            "org": org, "plan": plan, "pilot": est["pilot"], "external": counts["external"], "depiqo": counts["depiqo"],
            "new": est["new"], "new_depiqo": new["depiqo"], "list": list_subtotal, "billed": est["subtotal"], "cost": partner_cost,
            "margin": margin, "margin_per_dossier": margin // active if active else None,
            "margin_list_per_dossier": (list_subtotal - partner_cost) // active if active else None,
            "marginal_depiqo": marginal_depiqo, "marginal_new": marginal_new,
            "warn": marginal_depiqo < 0 or (counts["depiqo"] and margin < 0),
        })
        for k, v in (("external", counts["external"]), ("depiqo", counts["depiqo"]), ("new_depiqo", new["depiqo"]), ("new", est["new"]),
                     ("list", list_subtotal), ("billed", est["subtotal"]), ("cost", partner_cost), ("margin", margin)):
            total[k] += v
    active_total = total["external"] + total["depiqo"]
    total["margin_per_dossier"] = total["margin"] // active_total if active_total else None
    per_plan = []
    for code in ("essential", "professional"):
        p = billing.PLANS[code]
        per_plan.append({"label": p["label"], "price_depiqo": p["extra_depiqo_cents"], "price_new": p["new_dossier_cents"],
                         "marginal_depiqo": p["extra_depiqo_cents"] - cost["partner_cost_active_cents"],
                         "marginal_new": p["new_dossier_cents"] - cost["partner_cost_new_cents"]})
    from . import investing
    invest = investing.economics(period, cost["partner_cost_invest_account_cents"])
    return {"period": period, "rows": rows, "total": total, "cost": cost, "per_plan": per_plan, "invest": invest}
