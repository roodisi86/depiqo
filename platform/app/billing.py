"""Pricing and invoicing for Depiqo Business.

Three plans (amounts in euro cents, excluding VAT, per organisation per month):

  essential     EUR 99 base, 100 active dossiers included.
                Extra active dossier: EUR 0,75 (borg elders) or EUR 0,40 (Depiqo-borgrekening).
                Per new dossier activated in the month: EUR 5,00.
  professional  EUR 299 base, 500 included. Extra: EUR 0,45 / EUR 0,25. Per new dossier: EUR 3,00.
  enterprise    Custom. The numbers are stored per organisation (organizations.ent_*);
                any number left empty falls back to Professional. Only Depiqo staff set it.

"Active" means the dossier was active at any moment in the month (see active_counts).
"New" means the dossier was activated (invitation sent) in the month and is not cancelled.
The included dossiers are applied to external dossiers first, because those are the more
expensive ones (in the customer's favour). Pilot organisations get a 100% discount line.
Tenants never pay.

Plan history: every plan change writes a row in organization_plan_history with a valid_from
date. An estimate or invoice for a month uses the plan in force on the first day of that
month (plan_for_period). A self-service change takes effect on the first day of the next
month, so a month that already started is never billed on a plan chosen later. Staff may set
a change from the current month. organizations.plan always holds the most recent choice.

Invoices have a payment status (open, paid; overdue is open after the due date). Depiqo staff
can mark an invoice paid and credit it: the original gets status 'credited' and a credit note
with negative amounts refers to it. A credited month can be invoiced again.
"""
import io
import re
from datetime import date, timedelta

from . import db
from . import states as S
from .util import add_months, dumps, eur, now_iso, parse_date, today

FIELDS = ("base_cents", "included", "extra_external_cents", "extra_depiqo_cents", "new_dossier_cents")

PLANS = {
    "essential": {"label": "Essential", "base_cents": 9900, "included": 100,
                  "extra_external_cents": 75, "extra_depiqo_cents": 40, "new_dossier_cents": 500},
    "professional": {"label": "Professional", "base_cents": 29900, "included": 500,
                     "extra_external_cents": 45, "extra_depiqo_cents": 25, "new_dossier_cents": 300},
    "enterprise": {"label": "Enterprise", "base_cents": 29900, "included": 500,
                   "extra_external_cents": 45, "extra_depiqo_cents": 25, "new_dossier_cents": 300},
}
SELF_SERVICE = ("essential", "professional")  # an organisation admin may switch between these
ENTERPRISE_COLUMNS = {"base_cents": "ent_base_cents", "included": "ent_included",
                      "extra_external_cents": "ent_extra_external_cents", "extra_depiqo_cents": "ent_extra_depiqo_cents",
                      "new_dossier_cents": "ent_new_dossier_cents"}

NOT_BILLABLE = (S.CONCEPT, S.CANCELLED)


def plan_for(org):
    """The effective numbers for an organisation: dict with code, label and the FIELDS."""
    code = org["plan"] if org["plan"] in PLANS else "essential"
    plan = {"code": code, **PLANS[code]}
    if code == "enterprise":
        for field, column in ENTERPRISE_COLUMNS.items():
            if org[column] is not None:
                plan[field] = int(org[column])
    return plan


HISTORY_FIELDS = ("base_cents", "included", "extra_external_cents", "extra_depiqo_cents", "new_dossier_cents")
PAYMENT_TERM_DAYS = 14


def _plan_from_history(row):
    code = row["plan"] if row["plan"] in PLANS else "essential"
    plan = {"code": code, **PLANS[code], "valid_from": row["valid_from"]}
    if code == "enterprise":
        for field in HISTORY_FIELDS:
            if row[field] is not None:
                plan[field] = int(row[field])
    return plan


def plan_history(org_id):
    return db.all_("SELECT h.*, u.name AS user_name FROM organization_plan_history h LEFT JOIN users u ON u.id = h.created_by "
                   "WHERE h.org_id = ? ORDER BY h.valid_from DESC, h.id DESC", (org_id,))


def plan_on(org, day):
    """The plan in force on a given date. Before the first history row, the first row applies
    (the plan the organisation started with). Without any history: the organisation's columns."""
    row = db.one("SELECT * FROM organization_plan_history WHERE org_id = ? AND valid_from <= ? ORDER BY valid_from DESC, id DESC LIMIT 1",
                 (org["id"], day.isoformat()))
    if not row:
        row = db.one("SELECT * FROM organization_plan_history WHERE org_id = ? ORDER BY valid_from, id LIMIT 1", (org["id"],))
    return _plan_from_history(row) if row else plan_for(org)


def plan_for_period(org, period):
    start, _ = period_bounds(period)
    return plan_on(org, start)


def next_month_start(day=None):
    return add_months((day or today()).replace(day=1), 1)


def record_plan_change(org, plan, overrides, valid_from, user_id):
    """Writes the history row and keeps organizations.plan (most recent choice) in step.
    overrides: dict field -> cents/number for Enterprise (others are ignored)."""
    if plan not in PLANS:
        raise ValueError("Onbekend plan.")
    values = {f: (overrides or {}).get(f) if plan == "enterprise" else None for f in HISTORY_FIELDS}
    with db.transaction():
        # The newest decision wins: a change that was scheduled for later (e.g. a self-service switch
        # from next month) is superseded by this one. The audit log keeps the history of decisions.
        db.run("DELETE FROM organization_plan_history WHERE org_id = ? AND valid_from > ?", (org["id"], valid_from.isoformat()))
        db.run("INSERT INTO organization_plan_history (org_id, plan, base_cents, included, extra_external_cents, extra_depiqo_cents, "
               "new_dossier_cents, valid_from, created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (org["id"], plan, *values.values(), valid_from.isoformat(), now_iso(), user_id))
        sets = ", ".join(f"{ENTERPRISE_COLUMNS[f]} = ?" for f in HISTORY_FIELDS)  # fixed column names
        db.run(f"UPDATE organizations SET plan = ?, {sets} WHERE id = ?", (plan, *values.values(), org["id"]))


def period_bounds(period):
    y, m = map(int, period.split("-"))
    start = date(y, m, 1)
    return start, add_months(start, 1)


def active_counts(org_id, period):
    """Dossiers that were active at any moment in the period: invited before the period ended
    and not closed before it started. Concepts and cancelled dossiers are never billed."""
    start, end = period_bounds(period)
    rows = db.all_(
        "SELECT holding, COUNT(*) AS n FROM deposits WHERE org_id = ? AND activated_at IS NOT NULL "
        "AND activated_at < ? AND (closed_at IS NULL OR closed_at >= ?) AND status NOT IN (?, ?) GROUP BY holding",
        (org_id, end.isoformat(), start.isoformat(), *NOT_BILLABLE))
    counts = {"external": 0, "depiqo": 0}
    for r in rows:
        counts[r["holding"]] = r["n"]
    # Closed-in-period dossiers keep status CLOSED, which is billable for that month; cancelled ones are not.
    return counts


def new_count(org_id, period):
    """Dossiers activated (first invitation sent) in the period, not cancelled."""
    start, end = period_bounds(period)
    return db.scalar("SELECT COUNT(*) FROM deposits WHERE org_id = ? AND activated_at IS NOT NULL "
                     "AND activated_at >= ? AND activated_at < ? AND status != ?",
                     (org_id, start.isoformat(), end.isoformat(), S.CANCELLED))


def _line(kind, description, quantity, unit_cents):
    return {"kind": kind, "description": description, "quantity": quantity, "unit_cents": unit_cents,
            "total_cents": quantity * unit_cents}


def price(external, depiqo, new=0, plan="essential", pilot=False):
    """Returns (lines, subtotal_cents). `plan` is a plan code or a dict from plan_for()."""
    p = {"code": plan, **PLANS[plan]} if isinstance(plan, str) else plan
    included_left = p["included"]
    ext_included = min(external, included_left)
    included_left -= ext_included
    dep_included = min(depiqo, included_left)
    ext_extra = external - ext_included
    dep_extra = depiqo - dep_included
    lines = [
        _line("base", f"Basisprijs {p['label']}", 1, p["base_cents"]),
        _line("included", f"Inbegrepen dossiers (max. {p['included']})", ext_included + dep_included, 0),
        _line("extra_external", "Extra dossiers, borg elders", ext_extra, p["extra_external_cents"]),
        _line("extra_depiqo", "Extra dossiers, Depiqo-borgrekening", dep_extra, p["extra_depiqo_cents"]),
        _line("new", "Nieuwe dossiers deze maand", new, p["new_dossier_cents"]),
    ]
    subtotal = sum(l["total_cents"] for l in lines)
    if pilot:
        lines.append({"kind": "pilot", "description": "Pilotkorting (100%)", "quantity": 1,
                      "unit_cents": -subtotal, "total_cents": -subtotal})
        subtotal = 0
    return lines, subtotal


def is_pilot(org, period):
    _, end = period_bounds(period)
    return bool(org["pilot_until"]) and org["pilot_until"] >= end.isoformat()


def estimate(org, period):
    counts = active_counts(org["id"], period)
    new = new_count(org["id"], period)
    plan = plan_for_period(org, period)
    pilot = is_pilot(org, period)
    lines, subtotal = price(counts["external"], counts["depiqo"], new, plan, pilot)
    vat = vat_cents(subtotal, org["vat_rate_bps"])
    return {"period": period, "counts": counts, "new": new, "plan": plan, "lines": lines, "subtotal": subtotal,
            "vat": vat, "total": subtotal + vat, "pilot": pilot}


def vat_cents(subtotal_cents, rate_bps):
    """Integer maths; half a cent rounds up (not to even)."""
    return (subtotal_cents * rate_bps + 5000) // 10000


def valid_period(org, period):
    """YYYY-MM, a real month, not before the organisation existed."""
    if not isinstance(period, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        return False
    return period >= (org["created_at"] or "")[:7]


def _next_number(year):
    seq = db.scalar("SELECT COUNT(*) FROM invoices WHERE number LIKE ?", (f"DPQ-{year}-%",)) + 1
    return f"DPQ-{year}-{seq:05d}"


def issue_invoice(org, period):
    if not valid_period(org, period):
        raise ValueError("Ongeldige factuurperiode.")
    if db.one("SELECT id FROM invoices WHERE org_id = ? AND period = ? AND kind = 'invoice' AND status = 'issued'", (org["id"], period)):
        raise ValueError("Voor deze maand is al een factuur uitgereikt.")
    est = estimate(org, period)
    issued = now_iso()
    due = (parse_date(issued) + timedelta(days=PAYMENT_TERM_DAYS)).isoformat()
    with db.transaction():
        number = _next_number(issued[:4])
        inv_id = db.run("INSERT INTO invoices (org_id, period, number, kind, status, payment_status, plan, subtotal_cents, vat_cents, total_cents, "
                        "lines_json, issued_at, due_at) VALUES (?, ?, ?, 'invoice', 'issued', ?, ?, ?, ?, ?, ?, ?, ?)",
                        (org["id"], period, number, "none" if est["total"] == 0 else "open", est["plan"]["code"],
                         est["subtotal"], est["vat"], est["total"], dumps(est["lines"]), issued, due))
    return db.one("SELECT * FROM invoices WHERE id = ?", (inv_id,))


def credit_invoice(invoice_id, reason, user_id=None):
    """Staff only. The original becomes 'credited'; a credit note with negative amounts refers to it."""
    import json
    inv = db.one("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    if not inv or inv["kind"] != "invoice" or inv["status"] != "issued":
        raise ValueError("Alleen een uitgereikte factuur kan worden gecrediteerd.")
    if inv["payment_status"] == "paid":
        raise ValueError("Deze factuur is al betaald. Crediteren kan pas als de terugbetaling geregeld is; "
                         "dat kan nog niet in Depiqo. Neem contact op met finance.")
    if len((reason or "").strip()) < 5:
        raise ValueError("Geef een reden voor de creditnota.")
    lines = [{**l, "description": f"Credit: {l['description']}", "unit_cents": -l["unit_cents"], "total_cents": -l["total_cents"]}
             for l in json.loads(inv["lines_json"])]
    issued = now_iso()
    with db.transaction():
        number = _next_number(issued[:4])
        credit_id = db.run("INSERT INTO invoices (org_id, period, number, kind, status, payment_status, credit_for_id, plan, subtotal_cents, vat_cents, "
                           "total_cents, lines_json, issued_at, note) VALUES (?, ?, ?, 'credit', 'issued', 'none', ?, ?, ?, ?, ?, ?, ?, ?)",
                           (inv["org_id"], inv["period"], number, inv["id"], inv["plan"], -inv["subtotal_cents"], -inv["vat_cents"],
                            -inv["total_cents"], dumps(lines), issued, reason.strip()[:300]))
        db.run("UPDATE invoices SET status = 'credited', note = ? WHERE id = ?", (f"Gecrediteerd met {number}: {reason.strip()[:200]}", inv["id"]))
    return db.one("SELECT * FROM invoices WHERE id = ?", (credit_id,))


def mark_paid(invoice_id):
    inv = db.one("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    if not inv or inv["kind"] != "invoice" or inv["status"] != "issued" or inv["payment_status"] != "open":
        raise ValueError("Deze factuur staat niet open.")
    db.run("UPDATE invoices SET payment_status = 'paid', paid_at = ? WHERE id = ?", (now_iso(), invoice_id))
    return db.one("SELECT * FROM invoices WHERE id = ?", (invoice_id,))


def payment_state(inv, on=None):
    """(code, label, tone) for screens: open, overdue, paid, credited, credit note, nothing to pay."""
    if inv["kind"] == "credit":
        return "credit", "Creditnota", "info"
    if inv["status"] == "credited":
        return "credited", "Gecrediteerd", "neutral"
    if inv["status"] == "void":
        return "void", "Vervallen", "neutral"
    if inv["payment_status"] == "paid":
        return "paid", "Betaald", "ok"
    if inv["payment_status"] == "none":
        return "none", "Niets te betalen", "neutral"
    if inv["due_at"] and inv["due_at"] < (on or today()).isoformat():
        return "overdue", "Te laat", "alert"
    return "open", "Open", "wait"


def invoice_pdf(invoice, org):
    """Renders the invoice with reportlab. Returns PDF bytes."""
    import json

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    navy = (0.043, 0.078, 0.149)
    teal = (0.031, 0.498, 0.471)
    c.setFillColorRGB(*navy)
    c.rect(0, h - 38 * mm, w, 38 * mm, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(20 * mm, h - 22 * mm, "depiqo")
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, h - 29 * mm, "Creditnota" if invoice["kind"] == "credit" else "Factuur")
    c.drawRightString(w - 20 * mm, h - 22 * mm, invoice["number"])
    c.drawRightString(w - 20 * mm, h - 29 * mm, f"Periode {invoice['period']}")
    c.setFillColorRGB(*navy)
    y = h - 55 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, org["name"])
    c.setFont("Helvetica", 10)
    if org["registration_number"]:
        c.drawString(20 * mm, y - 5 * mm, f"Registratienummer {org['registration_number']}")
    if org["billing_email"]:
        c.drawString(20 * mm, y - 10 * mm, org["billing_email"])
    c.drawRightString(w - 20 * mm, y, f"Datum {invoice['issued_at'][:10]}")
    if invoice["kind"] == "credit" and invoice["credit_for_id"]:
        original = db.scalar("SELECT number FROM invoices WHERE id = ?", (invoice["credit_for_id"],))
        c.drawRightString(w - 20 * mm, y - 5 * mm, f"Crediteert factuur {original}")
    elif invoice["due_at"]:
        c.drawRightString(w - 20 * mm, y - 5 * mm, f"Te betalen voor {invoice['due_at'][:10]}")
    y -= 28 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "OMSCHRIJVING")
    c.drawRightString(130 * mm, y, "AANTAL")
    c.drawRightString(158 * mm, y, "PRIJS")
    c.drawRightString(w - 20 * mm, y, "BEDRAG")
    c.setStrokeColorRGB(0.85, 0.88, 0.9)
    c.line(20 * mm, y - 3 * mm, w - 20 * mm, y - 3 * mm)
    c.setFont("Helvetica", 10)
    y -= 10 * mm
    for line in json.loads(invoice["lines_json"]):
        c.drawString(20 * mm, y, line["description"])
        c.drawRightString(130 * mm, y, str(line["quantity"]))
        c.drawRightString(158 * mm, y, eur(line["unit_cents"]))
        c.drawRightString(w - 20 * mm, y, eur(line["total_cents"]))
        y -= 8 * mm
    c.line(110 * mm, y, w - 20 * mm, y)
    y -= 8 * mm
    for label, val in (("Subtotaal", invoice["subtotal_cents"]), (f"Btw {org['vat_rate_bps'] / 100:.0f}%", invoice["vat_cents"])):
        c.drawString(110 * mm, y, label)
        c.drawRightString(w - 20 * mm, y, eur(val))
        y -= 7 * mm
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(*teal)
    c.drawString(110 * mm, y - 2 * mm, "Totaal")
    c.drawRightString(w - 20 * mm, y - 2 * mm, eur(invoice["total_cents"]))
    c.setFillColorRGB(0.35, 0.42, 0.5)
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 18 * mm, "Depiqo (werknaam), introductieprijzen. Bedrijfs- en betaalgegevens worden toegevoegd zodra de entiteit is opgericht.")
    c.showPage()
    c.save()
    return buf.getvalue()
