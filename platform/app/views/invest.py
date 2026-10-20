"""Depiqo Invest in the wallet (tenants) and in the back office (Depiqo staff).

Every tenant route answers 404 unless the person is a tenant, an organisation of theirs offers Invest
and an investment partner is available (fail closed). Property managers never reach these routes and
no Business page reads an Invest table. Staff see aggregates and accounts but cannot place orders.
"""
from functools import wraps

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .. import db, investing, services
from .. import states as S
from ..security import NO_ORG, audit, staff_required
from ..util import now_iso, parse_euros, today

bp = Blueprint("invest", __name__, url_prefix="/wallet/beleggen")
staff_bp = Blueprint("invest_admin", __name__, url_prefix="/admin/beleggen")


def invest_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not g.user:
            return redirect(url_for("auth.login", next=request.path))
        if not g.tenant_ids or investing.visibility(g.user["id"]) != "available":
            abort(404)
        return view(*args, **kwargs)
    return wrapper


def _ctx(**extra):
    p = investing.partner()
    return {"partner": p, "role_text": investing.role_text(p), "PORTFOLIOS": investing.PORTFOLIOS, "FUNDS": investing.FUNDS,
            "MIN_ORDER": investing.MIN_ORDER_CENTS, "fee_bps": investing.fee_bps(), **extra}


def _audit(action, data=None):
    audit(f"invest.{action}", f"user:{g.user['id']}", data, org_id=NO_ORG)  # never tied to an organisation


# ------------------------------------------------------------ tenant: onboarding

@bp.route("")
@invest_required
def index():
    acct = investing.account_for_user(g.user["id"])
    if acct and acct["status"] in ("pending", "active", "closed"):
        return overview(acct)
    appr = investing.latest_appropriateness(g.user["id"])
    return render_template("wallet/invest_intro.html", **_ctx(acct=acct, appr=appr, may_continue=investing.may_continue(appr)))


@bp.route("/toets", methods=["GET", "POST"])
@invest_required
def questionnaire():
    acct = investing.account_for_user(g.user["id"])
    if acct and acct["status"] != "draft":
        return redirect(url_for("invest.index"))
    if not investing.org_enabled_for(g.user["id"]):
        abort(404)
    error = None
    answers = request.form if request.method == "POST" else {}
    if request.method == "POST":
        try:
            a = investing.record_appropriateness(g.user["id"], request.form)
            _audit("appropriateness", {"result": a["result"], "score": a["score"]})
            return redirect(url_for("invest.result"))
        except investing.InvestError as exc:
            error = str(exc)
    return render_template("wallet/invest_test.html", **_ctx(QUESTIONS=investing.QUESTIONS, answers=answers, error=error))


@bp.route("/toets/uitslag", methods=["GET", "POST"])
@invest_required
def result():
    appr = investing.latest_appropriateness(g.user["id"])
    if not appr:
        return redirect(url_for("invest.questionnaire"))
    if request.method == "POST":
        if request.form.get("confirm") != "1":
            flash("Vink aan dat je de waarschuwing hebt gelezen en toch verder wilt.", "error")
            return redirect(url_for("invest.result"))
        try:
            investing.confirm_warning(g.user["id"])
            _audit("appropriateness_warning_confirmed")
        except investing.InvestError as exc:
            flash(str(exc), "error")
            return redirect(url_for("invest.result"))
        return redirect(url_for("invest.choose"))
    import json
    return render_template("wallet/invest_result.html", **_ctx(appr=appr, reasons=json.loads(appr["reasons_json"])))


@bp.route("/portefeuille", methods=["GET", "POST"])
@invest_required
def choose():
    acct = investing.account_for_user(g.user["id"])
    if not acct or not investing.may_continue(investing.latest_appropriateness(g.user["id"])):
        return redirect(url_for("invest.index"))
    if acct["status"] != "draft":
        return redirect(url_for("invest.index"))
    if request.method == "POST":
        try:
            investing.choose_portfolio(g.user["id"], request.form.get("portfolio"))
            _audit("portfolio_chosen", {"portfolio": request.form.get("portfolio")})
            return redirect(url_for("invest.terms"))
        except investing.InvestError as exc:
            flash(str(exc), "error")
    amount = parse_euros(request.args.get("bedrag")) or 100000
    amount = min(max(amount, investing.MIN_ORDER_CENTS), 10_000_000)
    fee = investing.fee_bps()
    options = [{"code": c, "p": p, "costs": investing.costs(amount, c, fee), "scenarios": investing.scenarios(amount, c, fee)}
               for c, p in investing.PORTFOLIOS.items()]
    return render_template("wallet/invest_choose.html", **_ctx(acct=acct, amount=amount, options=options))


@bp.route("/voorwaarden", methods=["GET", "POST"])
@invest_required
def terms():
    acct = investing.account_for_user(g.user["id"])
    if not acct or acct["status"] != "draft" or not acct["portfolio"]:
        return redirect(url_for("invest.index"))
    if request.method == "POST":
        try:
            investing.open_account(g.user["id"], request.form.get("accept_partner") == "1", request.form.get("accept_depiqo") == "1")
            _audit("account_opened", {"portfolio": acct["portfolio"]})
            flash("Je beleggingsrekening wordt geopend bij de partner.", "ok")
            return redirect(url_for("invest.index"))
        except investing.InvestError as exc:
            flash(str(exc), "error")
    return render_template("wallet/invest_terms.html", **_ctx(acct=acct, DEPIQO_TERMS=investing.DEPIQO_TERMS_VERSION, TERMS=investing.terms()))


# ------------------------------------------------------------ tenant: overview and actions

def overview(acct):
    s = investing.summary(acct) if acct["status"] in ("active", "closed") else None
    p = investing.partner()
    from .. import mfa
    return render_template(
        "wallet/invest_overview.html", offered=investing.org_enabled_for(g.user["id"]), two_factor=mfa.enabled(g.user),
        cooling_off_days=investing.COOLING_OFF.days, now_iso=now_iso(),
        **_ctx(acct=acct, s=s, chart=investing.chart(acct["id"]) if s else None, orders=investing.orders(acct["id"], limit=6),
               txs=investing.transactions(acct["id"], limit=10), withdrawals=investing.pending_withdrawals(acct["id"]),
               pay=p.deposit_instructions(acct) if acct["status"] == "active" else None,
               periods=investing.statement_periods(acct), costs=investing.costs(max(s["total"], 0) if s else 0, acct["portfolio"], investing.fee_bps())
               if acct["portfolio"] else None, others=[c for c in investing.PORTFOLIOS if c != acct["portfolio"]]))


ACTIONS = ("storten", "kopen", "verkopen", "opnemen", "wisselen", "rekening", "servicevergoeding")


@bp.route("/kopen")
@invest_required
def buy_confirm():
    """Before a purchase: the amount, the costs in euro for this amount and the risk, then an explicit confirmation."""
    acct = investing.account_for_user(g.user["id"])
    if not acct or acct["status"] != "active":
        return redirect(url_for("invest.index"))
    amount = parse_euros(request.args.get("bedrag"))
    if not amount or amount < investing.MIN_ORDER_CENTS:
        flash("Je koopt voor minimaal € 25.", "error")
        return redirect(url_for("invest.index"))
    rate = investing.summary(acct)["fee_rate_bps"]
    return render_template("wallet/invest_buy_confirm.html", **_ctx(acct=acct, amount=amount, costs=investing.costs(amount, acct["portfolio"], rate),
                                                                    scenarios=investing.scenarios(amount, acct["portfolio"], rate),
                                                                    s=investing.summary(acct)))


@bp.route("/wisselen")
@invest_required
def switch_confirm():
    """Before a switch: the new portfolio's costs and scenarios on the current value, the risk, then a confirmation."""
    acct = investing.account_for_user(g.user["id"])
    target = request.args.get("portefeuille")
    if not acct or acct["status"] != "active" or target not in investing.PORTFOLIOS or target == acct["portfolio"]:
        flash("Kies een andere portefeuille.", "error")
        return redirect(url_for("invest.index"))
    s = investing.summary(acct)
    base = max(s["total"], investing.MIN_ORDER_CENTS)
    return render_template("wallet/invest_switch_confirm.html", **_ctx(acct=acct, target=target, s=s, base=base,
                                                                       costs=investing.costs(base, target, s["fee_rate_bps"]),
                                                                       scenarios=investing.scenarios(base, target, s["fee_rate_bps"])))


@bp.route("/actie/<action>", methods=["POST"])
@invest_required
def action(action):
    if action not in ACTIONS:
        abort(404)
    acct = investing.account_for_user(g.user["id"])
    if not acct:
        abort(404)
    try:
        if action == "storten":
            investing.simulate_deposit(acct, parse_euros(request.form.get("amount")))
            flash("Sandbox: je storting is binnen bij de partner.", "ok")
        elif action == "kopen":
            if request.form.get("confirm") != "1":
                raise investing.InvestError("Bevestig dat je de kosten en het risico hebt gelezen.")
            investing.place_order(acct, "buy", parse_euros(request.form.get("amount")))
            flash("Je kooporder staat klaar. De partner voert hem uit tegen de volgende koers.", "ok")
        elif action == "verkopen":
            investing.place_order(acct, "sell", parse_euros(request.form.get("amount")), sell_all=request.form.get("all") == "1")
            flash("Je verkooporder staat klaar. De partner voert hem uit tegen de volgende koers.", "ok")
        elif action == "opnemen":
            investing.withdraw(acct, parse_euros(request.form.get("amount")))
            flash("Je opname staat klaar. De partner maakt het geld over naar je eigen rekening.", "ok")
        elif action == "wisselen":
            investing.switch_portfolio(acct, request.form.get("portfolio"), request.form.get("confirm") == "1")
            flash("Je portefeuille wordt gewisseld: eerst verkopen, daarna kopen. Tot dat klaar is, blijft je huidige portefeuille staan.", "ok")
        elif action == "rekening":
            usable = investing.register_own_iban(acct, g.user, request.form.get("iban"), request.form.get("code"))
            flash("Je rekeningnummer is geregistreerd." + ("" if usable <= now_iso() else f" Je kunt het gebruiken vanaf {investing._dt(usable)}.")
                  + " Je krijgt hierover een e-mail.", "ok")
        elif action == "servicevergoeding":
            if request.form.get("accept") != "1":
                raise investing.InvestError("Vink aan dat je akkoord gaat met de nieuwe servicevergoeding.")
            investing.accept_fee_change(acct)
            flash("Je nieuwe servicevergoeding geldt vanaf vandaag.", "ok")
        _audit(action)
    except investing.InvestError as exc:
        flash(str(exc), "error")
    return redirect(url_for("invest.index"))


@bp.route("/overzicht/<period>.pdf")
@invest_required
def statement(period):
    acct = investing.account_for_user(g.user["id"])
    if not acct or period not in investing.statement_periods(acct):
        abort(404)
    _audit("statement", {"period": period})
    return Response(investing.statement_pdf(acct, period, g.user["name"]), mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=beleggen-{acct['reference']}-{period}.pdf"})


@bp.route("/doorbeleggen/<pid>", methods=["POST"])
@invest_required
def payout_choice(pid):
    d = services.get_deposit(pid, tenant_ids=g.tenant_ids)
    if not d:
        abort(404)
    try:
        to_invest = request.form.get("destination") == "invest"
        if to_invest and request.form.get("confirm") != "1":
            raise investing.InvestError("Bevestig dat je jouw deel van de borg op je beleggingsrekening wilt ontvangen.")
        investing.choose_payout(d, g.user["id"], to_invest)
        _audit("payout_choice", {"deposit": pid, "invest": to_invest})
        flash("Je deel van de borg gaat naar je beleggingsrekening." if to_invest else "Je deel van de borg gaat naar je eigen rekening.", "ok")
    except investing.InvestError as exc:
        flash(str(exc), "error")
    return redirect(url_for("wallet.deposit", pid=pid))


# ------------------------------------------------------------ staff

@staff_bp.route("")
@staff_required
def home():
    orgs = db.all_("SELECT id, name, invest_enabled FROM organizations ORDER BY name")
    return render_template("admin/invest.html", ov=investing.staff_overview(), orgs=orgs, partner=investing.partner(),
                           fee_bps=investing.fee_bps(), PORTFOLIOS=investing.PORTFOLIOS)


@staff_bp.route("/<action>", methods=["POST"])
@staff_required
def staff_action(action):
    try:
        if action == "dag-vooruit":
            n = investing.advance_day(1)
            flash(f"Sandbox: koersen staan op {investing.invest_day().isoformat()}. {n} berichten van de partner verwerkt.", "ok")
        elif action == "servicekosten":
            n = investing.charge_fees_now()
            flash(f"Servicekosten verrekend: {n} {'rekening' if n == 1 else 'rekeningen'}.", "ok")
        elif action == "versturen":
            r = investing.dispatch()
            flash(f"Niets verstuurd. {r['blocked']}" if r["blocked"] else f"Opdrachten verstuurd: {r['sent']}. Mislukt: {r['failed']}.",
                  "error" if r["blocked"] or r["failed"] else "ok")
        elif action == "servicevergoeding":
            raw = (request.form.get("fee_pct") or "").replace(",", ".").strip()
            try:
                bps = int(round(float(raw) * 100))
            except ValueError:
                raise investing.InvestError("Vul een percentage in, bijvoorbeeld 0,25.")
            n = investing.set_fee_bps(bps, g.user["id"])
            flash(f"Servicevergoeding voor nieuwe rekeningen opgeslagen. {n} bestaande {'rekening krijgt' if n == 1 else 'rekeningen krijgen'} "
                  "een voorstel; die vergoeding geldt pas na akkoord van de huurder.", "ok")
        else:
            abort(404)
        audit(f"invest_admin.{action}", "invest", org_id=NO_ORG)
    except investing.InvestError as exc:
        flash(str(exc), "error")
    return redirect(url_for("invest_admin.home"))


@staff_bp.route("/rekeningen/<int:account_id>/activeren", methods=["POST"])
@staff_required
def activate(account_id):
    try:
        investing.activate_sandbox_account(account_id)
        audit("invest_admin.activate", f"invest_account:{account_id}", org_id=NO_ORG)
        flash("Sandbox: de partner heeft de rekening geactiveerd.", "ok")
    except investing.InvestError as exc:
        flash(str(exc), "error")
    return redirect(url_for("invest_admin.home"))


@staff_bp.route("/opdrachten/<int:instr_id>/opnieuw", methods=["POST"])
@staff_required
def retry(instr_id):
    try:
        investing.retry_instruction(instr_id)
        investing.dispatch(ids=[instr_id])
        audit("invest_admin.retry", f"invest_instruction:{instr_id}", org_id=NO_ORG)
        flash("Opdracht opnieuw verstuurd.", "ok")
    except investing.InvestError as exc:
        flash(str(exc), "error")
    return redirect(url_for("invest_admin.home"))


@staff_bp.route("/berichten/<int:event_id>/opnieuw", methods=["POST"])
@staff_required
def reprocess(event_id):
    try:
        result = investing.reprocess_event(event_id)
        audit("invest_admin.event_reprocessed", f"invest_event:{event_id}", {"result": result}, org_id=NO_ORG)
        flash("Bericht opnieuw verwerkt." if result == "processed" else "Bericht opnieuw bekeken, maar het geeft nog een fout.",
              "ok" if result == "processed" else "error")
    except investing.InvestError as exc:
        flash(str(exc), "error")
    return redirect(url_for("invest_admin.home"))


@staff_bp.route("/organisaties/<int:org_id>", methods=["POST"])
@staff_required
def toggle_org(org_id):
    org = db.one("SELECT * FROM organizations WHERE id = ?", (org_id,))
    if not org:
        abort(404)
    on = request.form.get("enabled") == "1"
    db.run("UPDATE organizations SET invest_enabled = ? WHERE id = ?", (1 if on else 0, org_id))
    audit("invest_admin.org_toggle", f"org:{org_id}", {"enabled": on}, org_id=org_id)
    flash(f"Beleggen voor huurders van {org['name']} staat {'aan' if on else 'uit'}.", "ok")
    return redirect(url_for("invest_admin.home"))
