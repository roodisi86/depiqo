"""Fills a fresh database with a realistic demo portfolio.

    python seed.py --reset

Everything here is fictitious. All money movements go through the sandbox bank, using
the same code paths a real bank event would use.
"""
import io
import os
import sys
from datetime import date, timedelta

from werkzeug.datastructures import FileStorage

from app import billing, create_app, db, imports, investing, services
from app import states as S
from app.partners import SandboxBank, bank
from app.security import hash_password
from app.storage import save_upload
from app.util import add_months, now_iso, sha256, today, token

# Staging sets DEMO_PASSWORD (a secret) so the public staging server does not use the password from the README.
PASSWORD = os.environ.get("DEMO_PASSWORD") or "Depiqo-demo-2026"


def pdf_bytes(title, lines):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(60, 780, title)
    c.setFont("Helvetica", 11)
    for i, line in enumerate(lines):
        c.drawString(60, 750 - i * 18, line)
    c.drawString(60, 80, "Voorbeelddocument voor de Depiqo-demo. Niet echt.")
    c.save()
    return buf.getvalue()


def upload(d, kind, name, title, lines, by="user", uid=None):
    fs = FileStorage(stream=io.BytesIO(pdf_bytes(title, lines)), filename=name, content_type="application/pdf")
    return save_upload(fs, d, kind, by, uid)


def user(email, name, staff=False):
    return db.run("INSERT INTO users (email, name, password_hash, is_staff, created_at) VALUES (?, ?, ?, ?, ?)",
                  (email, name, hash_password(PASSWORD), 1 if staff else 0, now_iso()))


def member(uid, org, role):
    db.run("INSERT INTO memberships (user_id, org_id, role, created_at) VALUES (?, ?, ?, ?)", (uid, org, role, now_iso()))


def invite_and_accept(d, uid, password=PASSWORD):
    d = services.send_invite(d, uid)
    raw = token()
    db.run("UPDATE deposits SET invite_token_hash = ? WHERE id = ?", (sha256(raw), d["id"]))
    tenant_uid, d = services.accept_invite(raw, password=password)
    return tenant_uid, d


def bank_event(d, etype, amount=None):
    acct = services.account_for(d)
    partner = bank()
    services.handle_bank_event(partner.name, etype, partner.simulate(etype, acct, amount))
    return services.reload(d)


def secure(d, uid):
    tenant_uid, d = invite_and_accept(d, uid)
    if d["holding"] == "depiqo":
        tenant = db.one("SELECT * FROM tenants WHERE id = ?", (d["tenant_id"],))
        d = services.verify_identity(d, tenant_uid, tenant["name"], "1994-05-12")
        d = bank_event(d, "deposit.received", d["amount_cents"])
        d = bank_event(d, "account.blocked")
    else:
        d = services.confirm_external_receipt(d, uid)
    return tenant_uid, d


def months_interest(d, n):
    for _ in range(n):
        acct = services.account_for(d)
        bank_event(d, "interest.credited", max(1, round(acct["ledger_balance_cents"] * acct["interest_rate_bps"] / 10000 / 12)))
    return services.reload(d)


def new(org, uid, address, postcode, city, region, tenant, email, rent, amount, holding, start, end=None, iban=None,
        kind=None, provider=None, ref=None, expires=None):
    return services.create_deposit(org, uid, {
        "address": address, "postcode": postcode, "city": city, "region": region, "tenant_name": tenant, "tenant_email": email,
        "rent_cents": rent * 100, "amount_cents": amount * 100, "holding": holding, "lease_start": start, "lease_end": end,
        "external_iban": iban, "provider_kind": kind, "provider_name": provider, "provider_reference": ref,
        "guarantee_expires_on": expires})


def staff_evidence(d, level, staff_uid, note, doc=None):
    return services.set_evidence(services.reload(d), level, staff_uid, note, doc, staff=True)


# Provider columns with Dutch names, as a property manager would type them. Avenue Louise has no provider: it shows
# as "aanbieder onbekend" on the dashboard and in the reconciliation.
IMPORT_CSV = """address;postcode;city;region;tenant_name;tenant_email;rent;amount;lease_start;holding;external_iban;evidence;aanbieder;naam_aanbieder;referentie
Damrak 70-3;1012 LM;Amsterdam;NL;Yara Smits;yara@huurder.test;1.450,00;2.900,00;12-03-2023;external;NL91ABNA0417164300;declared;rekening verhuurder;Bank A;
Avenue Louise 120;1050;Brussel;BRU;Hugo Lambert;hugo@huurder.test;1.100,00;2.200,00;2024-06-01;external;;declared;;;
Nieuwstraat 4;9000;Gent;VL;Fien Maes;fien@huurder.test;780,00;2.340,00;2022-10-01;external;;declared;e-DEPO;Deposito- en Consignatiekas;EDP-2022-104417
"""


PASSEND = {"experience": "soms", "funds": "pot", "risk": "beide", "spread": "kleiner", "horizon": "lang", "loss": "ja",
           "drop": "wachten", "goal": "opbouwen"}
NIET_PASSEND = {"experience": "nooit", "funds": "weet_niet", "risk": "stijgt", "spread": "weet_niet", "horizon": "middel", "loss": "ja",
                "drop": "twijfel", "goal": "opbouwen"}


def uid_of(email):
    return db.scalar("SELECT id FROM users WHERE email = ?", (email,))


def invest_onboard(email, portfolio, answers=PASSEND, confirm=False):
    uid = uid_of(email)
    investing.record_appropriateness(uid, answers)
    if confirm:
        investing.confirm_warning(uid)
    investing.choose_portfolio(uid, portfolio)
    investing.open_account(uid, True, True)
    return investing.account_for_user(uid)


def invest_seed(org, staff):
    """Depiqo Invest demo: about 18 months of history for two tenants, run through the sandbox partner day by day
    (the same code paths as the app: instructions, events, daily fee accrual, monthly fee charges)."""
    db.run("UPDATE organizations SET invest_enabled = 1 WHERE id = ?", (org,))
    db.run("UPDATE invest_sandbox_clock SET offset_days = -548 WHERE id = 1")
    daan = invest_onboard("daan@huurder.test", "neutraal")        # identity checked for his deposit: active right away
    thomas = invest_onboard("thomas@huurder.test", "offensief")
    for acct, first in ((daan, 250000), (thomas, 300000)):
        investing.simulate_deposit(acct, first)
        investing.place_order(investing.account_for_user(acct["user_id"]), "buy", first)
    for days_left in range(547, -1, -1):
        investing.advance_day(1)
        day = investing.invest_day()
        if day.day == 1:                                       # a monthly transfer and a purchase
            for acct, monthly in ((daan, 15000), (thomas, 20000)):
                a = investing.account_for_user(acct["user_id"])
                investing.simulate_deposit(a, monthly)
                investing.place_order(a, "buy", min(monthly, investing.summary(a)["available"]))
        if days_left == 140:                                   # Daan sells a little and takes it out
            a = investing.account_for_user(daan["user_id"])
            investing.place_order(a, "sell", 30000)
        if days_left == 138:
            # Demo: Daan registered his own account long ago (in the app this needs a 2FA code or 7 days cooling-off).
            db.run("UPDATE invest_accounts SET own_iban = 'NL91ABNA0417164300', own_iban_registered_at = ?, own_iban_usable_from = ?, "
                   "own_iban_holder = 'Daan Visser' WHERE id = ?", (now_iso(), now_iso(), daan["id"]))
        if days_left == 137:
            a = investing.account_for_user(daan["user_id"])
            investing.withdraw(a, min(30000, investing.available_cents(a["id"])))  # the fee already owed stays
        if days_left == 60:                                    # Mohamed starts small, Defensief
            m = invest_onboard("mohamed@huurder.test", "defensief")
            investing.simulate_deposit(m, 30000)
            investing.place_order(investing.account_for_user(m["user_id"]), "buy", 25000)
        if days_left == 30:                                    # Iris fails the test, confirms the warning, waits for the partner
            i = invest_onboard("iris@huurder.test", "defensief", NIET_PASSEND, confirm=True)
            investing.activate_sandbox_account(i["id"])        # no identity check at Depiqo: the partner activates
            investing.simulate_deposit(investing.account_for_user(i["user_id"]), 20000)
    # Mohamed agreed with his settlement and chose to receive his share on his investment account.
    oudegracht = db.one("SELECT d.* FROM deposits d JOIN properties p ON p.id = d.property_id WHERE p.address = 'Oudegracht 140'")
    investing.choose_payout(oudegracht, uid_of("mohamed@huurder.test"), True)


def backdate(d, activated):
    db.run("UPDATE deposits SET activated_at = ?, created_at = ? WHERE id = ?", (activated, activated, d["id"]))
    return services.reload(d)  # the next transition must see activated_at, or it sets it to today


def main():
    app = create_app()
    if "--reset" in sys.argv:
        path = app.config["DATABASE_PATH"]
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.remove(path + suffix)
        storage = app.config["STORAGE_DIR"]
        for f in os.listdir(storage):
            os.remove(os.path.join(storage, f))
        app = create_app()
    with app.test_request_context("/"):
        t = today()
        first = t.replace(day=1)
        org = db.run("INSERT INTO organizations (name, registration_number, country, billing_email, pilot_until, plan, created_at) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?)",
                     ("Voorbeeld Vastgoed BV", "87654321", "NL", "facturen@voorbeeldvastgoed.test", add_months(t, 4).isoformat(),
                      "professional", f"{add_months(first, -4).isoformat()}T09:00:00+00:00"))
        admin = user("beheer@voorbeeldvastgoed.test", "Lotte Jansen")
        fin = user("finance@voorbeeldvastgoed.test", "Ruben Smit")
        viewer = user("kijker@voorbeeldvastgoed.test", "Eva Peeters")
        staff = user("staff@depiqo.test", "Depiqo Support", staff=True)
        member(admin, org, "admin")
        member(fin, org, "finance")
        member(viewer, org, "viewer")
        # Plan history: started on Essential, Professional from this month.
        org_row = db.one("SELECT * FROM organizations WHERE id = ?", (org,))
        billing.record_plan_change(org_row, "essential", None, add_months(first, -4), admin)
        billing.record_plan_change(org_row, "professional", None, first, admin)

        past = (t - timedelta(days=6)).isoformat()

        # 1. Sanne: settlement proposed, waiting for her answer
        d = new(org, admin, "Kerkstraat 12-2", "3512 BC", "Utrecht", "NL", "Sanne de Vries", "sanne@huurder.test", 1200, 2400, "depiqo", "2023-09-01", past)
        d = backdate(d, "2023-08-20T10:00:00+00:00")
        _, d = secure(d, admin)
        d = months_interest(d, 6)
        upload(d, "inspection", "plaatsbeschrijving-start.pdf", "Plaatsbeschrijving bij intrek", ["Kerkstraat 12-2, Utrecht", "Badkamerdeur: zonder schade"], uid=admin)
        d = services.start_move_out(d, admin, past)
        photo = upload(d, "photo", "badkamerdeur.pdf", "Foto badkamerdeur bij vertrek", ["Scheur in de deur, 20 cm"], uid=admin)
        quote = upload(d, "quote", "offerte-herstel-deur.pdf", "Offerte herstel badkamerdeur", ["Herstel en schilderen: EUR 185,00"], uid=admin)
        services.save_settlement(d, admin, [
            {"category": "damage", "description": "Herstel badkamerdeur", "amount_cents": 18500, "document_id": quote},
            {"category": "service_costs", "description": "Afrekening servicekosten 2026", "amount_cents": 6000, "document_id": None}])
        services.propose_settlement(d, admin)

        # 2. Agreed, ready for payout
        d = new(org, admin, "Oudegracht 140", "3511 AX", "Utrecht", "NL", "Mohamed el Amrani", "mohamed@huurder.test", 975, 1950, "depiqo", "2022-03-01", past)
        d = backdate(d, "2022-02-15T10:00:00+00:00")
        tu, d = secure(d, admin)
        d = months_interest(d, 4)
        d = services.start_move_out(d, admin, past)
        services.save_settlement(d, admin, [])
        d = services.propose_settlement(d, admin)
        services.tenant_agree(d, tu)

        # 3. External, disputed
        d = new(org, admin, "Vondelstraat 7-H", "1054 GA", "Amsterdam", "NL", "Julia Bakker", "julia@huurder.test", 2100, 4200, "external",
                "2021-06-01", (t - timedelta(days=12)).isoformat(), iban="NL91ABNA0417164300", kind="verhuurder_rekening", provider="Bank A")
        d = backdate(d, "2021-05-20T10:00:00+00:00")
        tu, d = secure(d, fin)
        # Declared six weeks ago and never proven: shows up in reconciliation.
        db.run("UPDATE deposits SET evidence_set_at = ? WHERE id = ?", (f"{(t - timedelta(days=42)).isoformat()}T10:00:00+00:00", d["id"]))
        db.run("UPDATE deposit_evidence SET at = ? WHERE deposit_id = ?", (f"{(t - timedelta(days=42)).isoformat()}T10:00:00+00:00", d["id"]))
        d = services.start_move_out(d, admin, (t - timedelta(days=12)).isoformat())
        doc = upload(d, "quote", "factuur-schilder.pdf", "Factuur schilderwerk", ["Woonkamer opnieuw schilderen: EUR 640,00"], uid=admin)
        services.save_settlement(d, admin, [{"category": "damage", "description": "Woonkamer opnieuw schilderen", "amount_cents": 64000, "document_id": doc}])
        d = services.propose_settlement(d, admin)
        services.tenant_dispute(d, tu, "De muren waren bij de start al verkleurd; zie de foto's bij de plaatsbeschrijving van 2021.")

        # 4.-5. Secured with interest, and one invited
        d = new(org, admin, "Laan van Meerdervoort 88", "2517 AN", "Den Haag", "NL", "Daan Visser", "daan@huurder.test", 1550, 3100, "depiqo", "2025-02-01")
        d = backdate(d, "2025-01-20T10:00:00+00:00")
        _, d = secure(d, admin)
        months_interest(d, 9)
        d = new(org, admin, "Biltstraat 301", "3572 AS", "Utrecht", "NL", "Noor Hendriks", "noor@huurder.test", 1375, 2750, "depiqo", (t + timedelta(days=20)).isoformat())
        services.send_invite(d, admin)

        # 6.-8. Belgium
        d = new(org, admin, "Kortrijksesteenweg 214", "9000", "Gent", "VL", "Lien Claes", "lien@huurder.test", 850, 2550, "depiqo", (t - timedelta(days=3)).isoformat())
        tu, d = invite_and_accept(d, admin)
        # Identity confirmed; the instruction to open the account waits in the outbox (pending).
        app.config["DISPATCH_INLINE"] = False
        services.verify_identity(d, tu, "Lien Claes", "1998-02-03")
        app.config["DISPATCH_INLINE"] = True
        d = new(org, admin, "Rue Haute 51", "1000", "Brussel", "BRU", "Thomas Dubois", "thomas@huurder.test", 950, 1900, "depiqo", "2024-09-01")
        d = backdate(d, "2024-08-25T10:00:00+00:00")
        _, d = secure(d, admin)
        months_interest(d, 12)
        d = new(org, admin, "Meir 38 bus 3", "2000", "Antwerpen", "VL", "Ella Wouters", "ella@huurder.test", 1100, 3300, "depiqo", "2023-04-01")
        d = backdate(d, "2023-03-20T10:00:00+00:00")
        _, d = secure(d, admin)
        d = months_interest(d, 8)
        services.start_move_out(d, admin, (t - timedelta(days=2)).isoformat())

        # 9.-12. Concept, closed, external secured and awaiting payment
        new(org, admin, "Herengracht 401", "1017 BP", "Amsterdam", "NL", "Bram de Groot", "bram@huurder.test", 1850, 3700, "depiqo", (t + timedelta(days=40)).isoformat())
        d = new(org, admin, "Nachtegaalstraat 22", "3581 AC", "Utrecht", "NL", "Femke Mulder", "femke@huurder.test", 1050, 2100, "depiqo", "2022-01-01", (t - timedelta(days=40)).isoformat())
        d = backdate(d, "2021-12-20T10:00:00+00:00")
        tu, d = secure(d, admin)
        d = months_interest(d, 3)
        d = services.start_move_out(d, admin, (t - timedelta(days=40)).isoformat())
        services.save_settlement(d, admin, [])
        d = services.propose_settlement(d, admin)
        d = services.tenant_agree(d, tu)
        d = services.start_payout(d, fin)
        bank_event(d, "payout.completed")
        d = new(org, admin, "Javastraat 90", "1094 HL", "Amsterdam", "NL", "Sem Bos", "sem@huurder.test", 1325, 2650, "external", "2024-11-01",
                iban="NL91ABNA0417164300", kind="verhuurder_rekening", provider="Bank A")
        d = backdate(d, "2024-10-20T10:00:00+00:00")
        tu, d = invite_and_accept(d, admin)
        proof = upload(d, "bankbewijs", "afschrift-borg-javastraat.pdf", "Bankafschrift", ["Bijschrijving EUR 2.650,00", "Omschrijving: borg Javastraat 90"], uid=fin)
        services.confirm_external_receipt(d, fin, proof)  # evidence level: document
        d = new(org, admin, "Weteringschans 12", "1017 SG", "Amsterdam", "NL", "Iris Vos", "iris@huurder.test", 1600, 3200, "external",
                (t + timedelta(days=10)).isoformat(), iban="NL91ABNA0417164300", kind="verhuurder_rekening", provider="Bank A")
        invite_and_accept(d, admin)

        # 13. External, verified by Depiqo staff
        d = new(org, admin, "Overtoom 310", "1054 JC", "Amsterdam", "NL", "Lars Dekker", "lars@huurder.test", 1500, 3000, "external", "2023-02-01",
                iban="NL91ABNA0417164300", kind="verhuurder_rekening", provider="Bank A")
        d = backdate(d, "2023-01-20T10:00:00+00:00")
        tu, d = invite_and_accept(d, admin)
        proof = upload(d, "bankbewijs", "afschrift-overtoom.pdf", "Bankafschrift", ["Bijschrijving EUR 3.000,00"], uid=fin)
        d = services.confirm_external_receipt(d, fin, proof)
        staff_evidence(d, "verified", staff, "Afschrift opgevraagd bij de beheerder en gecontroleerd op naam, bedrag en datum.", proof)

        # 14. Flanders, held elsewhere with a blocking certificate: legal security
        d = new(org, admin, "Lange Gasthuisstraat 20", "2000", "Antwerpen", "VL", "Nina Jacobs", "nina@huurder.test", 1000, 3000, "external", "2023-09-01",
                iban="BE68539007547034", kind="bank_geblokkeerd", provider="Bank A", ref="BE68 5390 0754 7034")
        d = backdate(d, "2023-08-20T10:00:00+00:00")
        tu, d = invite_and_accept(d, admin)
        d = services.confirm_external_receipt(d, fin)
        cert = upload(d, "blokkering", "blokkeringsattest-bank.pdf", "Attest geblokkeerde huurwaarborg", ["Rekening op naam van de huurder", "Geblokkeerd: EUR 3.000,00"], uid=fin)
        staff_evidence(d, "legal", staff, "Attest van de bank: rekening op naam van de huurder, geblokkeerd.", cert)

        # 15. Payout whose release instruction failed at the bank (sandbox failure): needs staff attention
        d = new(org, admin, "Stationsweg 3", "2312 AV", "Leiden", "NL", "Ruben Kok", "ruben.kok@huurder.test", 1000, 2000, "depiqo", "2022-05-01", (t - timedelta(days=9)).isoformat())
        d = backdate(d, "2022-04-20T10:00:00+00:00")
        tu, d = secure(d, admin)
        d = months_interest(d, 2)
        d = services.start_move_out(d, admin, (t - timedelta(days=9)).isoformat())
        services.save_settlement(d, admin, [])
        d = services.propose_settlement(d, admin)
        d = services.tenant_agree(d, tu)
        SandboxBank.failures = {"release"}
        d = services.start_payout(d, fin)
        release_id = db.scalar("SELECT id FROM bank_instructions WHERE deposit_id = ? AND kind = 'release'", (d["id"],))
        for _ in range(app.config["MAX_INSTRUCTION_ATTEMPTS"]):
            services.dispatch_instructions(ids=[release_id])  # only this one: Lien's open instruction stays pending
        SandboxBank.failures = set()

        # 15b. Rotterdam: a guarantee by a third party. The tenant paid nothing; the wallet says so.
        d = new(org, admin, "Witte de Withstraat 50", "3012 BR", "Rotterdam", "NL", "Mila Jansen", "mila@huurder.test", 1250, 2500, "external",
                "2025-03-01", "2027-02-28", kind="borggarantie", provider="Garantiefonds C", ref="GF-2025-0042", expires="2027-03-31")
        d = backdate(d, "2025-02-20T10:00:00+00:00")
        tu, d = invite_and_accept(d, admin)
        services.confirm_external_receipt(d, fin)

        # 16.-18. Existing deposits imported from a CSV file (held elsewhere, declared), no invitations
        batch_id = imports.create_batch(org, admin, "bestaande-borgen.csv", IMPORT_CSV.encode("utf-8-sig"))
        imports.commit_batch(db.one("SELECT * FROM import_batches WHERE id = ?", (batch_id,)), admin, send_invites=False)

        # Depiqo Invest (0.5.0): only for tenants of this organisation
        invest_seed(org, staff)

        # Invoice for last month (pilot: nothing to pay)
        org_row = db.one("SELECT * FROM organizations WHERE id = ?", (org,))
        billing.issue_invoice(org_row, add_months(first, -1).strftime("%Y-%m"))

        # A second organisation, to prove isolation
        org2 = db.run("INSERT INTO organizations (name, country, plan, vat_rate_bps, created_at) VALUES (?, ?, ?, ?, ?)",
                      ("Stadswonen Gent", "BE", "essential", 2100, f"{add_months(first, -2).isoformat()}T09:00:00+00:00"))
        other = user("beheer@stadswonen.test", "Pieter Maes")
        member(other, org2, "admin")
        org2_row = db.one("SELECT * FROM organizations WHERE id = ?", (org2,))
        billing.record_plan_change(org2_row, "essential", None, add_months(first, -2), staff)
        d = new(org2, other, "Veldstraat 10", "9000", "Gent", "VL", "An Jacobs", "an@huurder.test", 900, 2700, "depiqo", (t + timedelta(days=5)).isoformat())
        services.send_invite(d, other)
        # Invoices: two months ago open and overdue; last month credited by Depiqo (can be invoiced again).
        inv = billing.issue_invoice(org2_row, add_months(first, -2).strftime("%Y-%m"))
        issued = add_months(first, -1)
        db.run("UPDATE invoices SET issued_at = ?, due_at = ? WHERE id = ?",
               (f"{issued.isoformat()}T09:00:00+00:00", (issued + timedelta(days=14)).isoformat(), inv["id"]))
        inv = billing.issue_invoice(org2_row, add_months(first, -1).strftime("%Y-%m"))
        billing.credit_invoice(inv["id"], "Basisprijs dubbel gerekend: pilotafspraak", staff)

        # Stadswonen Gent keeps its current providers: e-DEPO, a blocked bank account, an insurer (tak 26) and a
        # guarantee that runs out soon. Provider names are generic on purpose.
        d = new(org2, other, "Sint-Jacobsnieuwstraat 12", "9000", "Gent", "VL", "Jonas Peeters", "jonas@huurder.test", 820, 2460, "external",
                "2024-02-01", kind="e_depo", provider="Deposito- en Consignatiekas", ref="EDP-2024-118734")
        d = backdate(d, "2024-01-20T10:00:00+00:00")
        tu, d = invite_and_accept(d, other)
        d = services.confirm_external_receipt(d, other)
        proof = upload(d, "blokkering", "bewijs-edepo-sint-jacobs.pdf", "Bewijs van e-DEPO", ["Huurwaarborg geregistreerd", "Dossier EDP-2024-118734"], uid=other)
        staff_evidence(d, "legal", staff, "Bewijs van e-DEPO gecontroleerd: dossiernummer, bedrag en naam van de huurder kloppen.", proof)

        d = new(org2, other, "Overpoortstraat 40", "9000", "Gent", "VL", "Lucas Willems", "lucas@huurder.test", 750, 2250, "external",
                "2024-09-01", kind="bank_geblokkeerd", provider="Bank A", ref="BE71 0961 2345 6769")
        d = backdate(d, "2024-08-20T10:00:00+00:00")
        tu, d = invite_and_accept(d, other)
        bank_doc = upload(d, "bankbewijs", "bevestiging-bank-overpoort.pdf", "Bevestiging van de bank", ["Geblokkeerde rekening op naam van de huurder", "EUR 2.250,00"], uid=other)
        services.confirm_external_receipt(d, other, bank_doc)

        d = new(org2, other, "Brabantdam 18", "9000", "Gent", "VL", "Emma Claeys", "emma@huurder.test", 980, 2940, "external",
                "2025-05-01", kind="verzekering_tak26", provider="Verzekeraar B", ref="K26-558812")
        d = backdate(d, "2025-04-20T10:00:00+00:00")
        tu, d = invite_and_accept(d, other)
        services.confirm_external_receipt(d, other)

        d = new(org2, other, "Dampoortstraat 7", "9000", "Gent", "VL", "Ruben De Smet", "ruben.desmet@huurder.test", 700, 2100, "external",
                "2025-01-01", "2028-12-31", kind="borggarantie", provider="Garantiefonds C", ref="GF-2025-0187",
                expires=(t + timedelta(days=40)).isoformat())
        d = backdate(d, "2024-12-20T10:00:00+00:00")
        tu, d = invite_and_accept(d, other)
        services.confirm_external_receipt(d, other)

        # e-DEPO, tenant moved out and agreed with the settlement: the release form is ready (Sofie can log in).
        d = new(org2, other, "Korenmarkt 5 bus 3", "9000", "Gent", "VL", "Sofie Martens", "sofie@huurder.test", 900, 2700, "external",
                "2022-09-01", (t - timedelta(days=10)).isoformat(), kind="e_depo", provider="Deposito- en Consignatiekas", ref="EDP-2022-077120")
        d = backdate(d, "2022-08-20T10:00:00+00:00")
        tu, d = invite_and_accept(d, other)
        d = services.confirm_external_receipt(d, other)
        proof = upload(d, "blokkering", "bewijs-edepo-korenmarkt.pdf", "Bewijs van e-DEPO", ["Huurwaarborg geregistreerd", "Dossier EDP-2022-077120"], uid=other)
        d = staff_evidence(d, "legal", staff, "Bewijs van e-DEPO gecontroleerd.", proof)
        d = services.start_move_out(d, other, (t - timedelta(days=10)).isoformat())
        quote = upload(d, "quote", "factuur-schoonmaak-korenmarkt.pdf", "Factuur eindschoonmaak", ["Eindschoonmaak keuken en badkamer: EUR 150,00"], uid=other)
        services.save_settlement(d, other, [{"category": "other", "description": "Eindschoonmaak keuken en badkamer", "amount_cents": 15000,
                                             "document_id": quote}])
        d = services.propose_settlement(d, other)
        services.tenant_agree(d, tu)
    print("Demo klaar. Inloggen met wachtwoord", PASSWORD)


if __name__ == "__main__":
    main()
