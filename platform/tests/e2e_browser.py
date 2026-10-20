"""Browser test in Chromium: a manager creates a deposit, the tenant completes the journey on a phone.

    python3 run.py &   (with a freshly seeded database)
    python3 tests/e2e_browser.py [screenshot-dir]
"""
import os
import re
import sys
import time
from datetime import date

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import mfa  # noqa: E402  (TOTP codes for the two-factor step)

B = "http://127.0.0.1:5000"
PW = "Depiqo-demo-2026"
OUT = sys.argv[1] if len(sys.argv) > 1 else None


def shot(page, name):
    if OUT:
        page.screenshot(path=f"{OUT}/{name}.png", full_page=True)


with sync_playwright() as p:
    browser = p.chromium.launch()
    errors = []
    desk = browser.new_context(viewport={"width": 1440, "height": 900})
    m = desk.new_page()
    m.on("pageerror", lambda e: errors.append(str(e)))
    m.goto(B + "/login")
    shot(m, "01-login")
    m.fill("#email", "beheer@voorbeeldvastgoed.test")
    m.fill("#password", PW)
    m.click("button[type=submit]")
    expect(m.get_by_role("heading", name=re.compile("Welkom terug"))).to_be_visible()
    expect(m.get_by_role("heading", name="Vandaag te doen")).to_be_visible()
    expect(m.locator(".task-group h3").first).to_be_visible()
    shot(m, "02-dashboard")

    m.click("text=Nieuwe borg")
    m.fill("#address", "Prinsengracht 263")
    m.fill("#postcode", "1016 GV")
    m.fill("#city", "Amsterdam")
    m.fill("#tenant_name", "Kevin Testhuurder")
    m.fill("#tenant_email", "kevin@huurder.test")
    m.fill("#lease_start", date.today().isoformat())
    m.fill("#rent", "1.400,00")
    m.fill("#amount", "3.000,00")
    m.click("text=Opslaan en huurder uitnodigen")
    expect(m.locator(".flash.error")).to_contain_text("maximaal 2 maanden")
    m.fill("#amount", "2.800,00")
    shot(m, "03-nieuwe-borg")
    m.click("text=Opslaan en huurder uitnodigen")
    expect(m.locator(".flash.ok")).to_contain_text("uitnodiging verstuurd")
    shot(m, "04-dossier-uitgenodigd")
    deposit_url = m.url

    staff = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    staff.goto(B + "/admin/postvak")  # requires a staff login now
    staff.fill("#email", "staff@depiqo.test")
    staff.fill("#password", PW)
    staff.click("button[type=submit]")
    staff.goto(B + "/admin/mail")
    link = staff.locator("pre.mail a").first.get_attribute("href")
    assert "/t/" in link, link

    phone = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    t = phone.new_page()
    t.on("pageerror", lambda e: errors.append(str(e)))
    t.goto(link.replace("http://localhost:5000", B))
    shot(t, "05-huurder-uitnodiging")
    t.check("input[name=confirm_details]")
    t.fill("#password", "Mijn-eigen-wachtwoord-1")
    t.click("button[type=submit]")
    expect(t.get_by_role("heading", name="Bevestig je identiteit")).to_be_visible()
    t.fill("#full_name", "Kevin Testhuurder")
    t.fill("#birth_date", "1988-03-14")
    t.click("text=Bevestigen")
    expect(t.get_by_role("heading", name="Stort je borg")).to_be_visible()
    # Before payment the wallet never shows the obligation as money held: "Ontvangen" is a dash.
    received = t.locator(".fig").filter(has=t.locator("dt", has_text="Ontvangen")).locator("dd b")
    expect(received).to_have_text("—")
    expect(t.locator(".fig").filter(has=t.locator("dt", has_text="Vereiste borg")).locator("dd b")).to_have_text("€ 2.800,00")
    assert t.evaluate("document.documentElement.scrollWidth") <= 390
    shot(t, "06-huurder-storten")

    m.goto(deposit_url)
    m.click("text=Huurder stort")
    expect(m.locator(".badge").filter(has_text="Storting ontvangen")).to_be_visible()
    m.click("text=Bank bevestigt blokkering")
    expect(m.locator(".badge").filter(has_text="Zekerheid bevestigd").first).to_be_visible()
    m.click("text=Rente bijschrijven")
    shot(m, "07-dossier-zeker")

    t.reload()
    expect(t.locator(".badge").filter(has_text="Je borg staat veilig")).to_be_visible()
    expect(received).to_have_text("€ 2.800,00")
    shot(t, "08-huurder-veilig")

    # Two-factor authentication for this (non-demo) tenant, then a fresh login with a code
    t.click("text=Beveiliging van je account")
    t.click("text=Twee-stapsverificatie instellen")
    secret = t.locator("[data-totp-secret]").get_attribute("data-totp-secret")
    t.fill("#code", mfa.totp(secret))
    t.click("text=Bevestigen en aanzetten")
    expect(t.locator(".codes li")).to_have_count(10)
    shot(t, "08b-2fa-herstelcodes")
    t.click("text=Ik heb ze bewaard")
    t.click("button:has-text('Uitloggen')")
    t.fill("#email", "kevin@huurder.test")
    t.fill("#password", "Mijn-eigen-wachtwoord-1")
    t.click("button[type=submit]")
    expect(t.get_by_role("heading", name="Nog één stap.")).to_be_visible()
    t.fill("#code", mfa.totp(secret, time.time() + 30))  # the next step: the confirmation code may not be reused
    t.click("button[type=submit]")
    expect(t.locator(".badge").filter(has_text="Je borg staat veilig")).to_be_visible()

    # Existing dossier with a proposed settlement: Sanne agrees on her phone
    s = phone.new_page()
    s.goto(B + "/login")
    s.fill("#email", "sanne@huurder.test")
    s.fill("#password", PW)
    s.click("button[type=submit]")
    expect(s.get_by_role("heading", name="Eindafrekening")).to_be_visible()
    shot(s, "09-huurder-afrekening")
    s.on("dialog", lambda d: d.accept())
    s.click("button:has-text('Akkoord')")
    expect(s.locator(".flash.ok")).to_contain_text("akkoord")

    for path, name in (("/app/borgen", "10-borgen"), ("/app/team", "11-team"), ("/app/facturatie", "12-facturatie"),
                       ("/app/afstemming?alles=1", "12b-afstemming")):
        m.goto(B + path)
        shot(m, name)

    # Bulk import: preview with checks, then commit in one go
    m.on("dialog", lambda d: d.accept())
    m.goto(B + "/app/borgen/import")
    csv_text = ("\ufeffaddress;postcode;city;region;tenant_name;tenant_email;rent;amount;lease_start;holding;external_iban;evidence\r\n"
                "Singel 1;1012 VC;Amsterdam;NL;Tom Import;tom@huurder.test;1.000,00;2.000,00;01-02-2024;external;;declared\r\n"
                "Rue Neuve 2;1000;Brussel;BRU;Lea Import;lea@huurder.test;900,00;1.800,00;2023-07-01;external;;\r\n")
    m.set_input_files("#file", files=[{"name": "e2e.csv", "mimeType": "text/csv", "buffer": csv_text.encode("utf-8")}])
    m.click("button:has-text('Controleren')")
    expect(m.get_by_role("heading", name="Controleer je import")).to_be_visible()
    expect(m.locator("text=Alles klopt")).to_be_visible()
    expect(m.locator(".badge").filter(has_text="In orde")).to_have_count(2)
    shot(m, "12c-import-voorbeeld")
    m.click("button:has-text('Importeren')")
    expect(m.locator(".flash.ok")).to_contain_text("2 borgen geïmporteerd")
    expect(m.locator("text=Singel 1")).to_be_visible()
    expect(m.locator("tr", has_text="Singel 1").locator(".badge")).to_contain_text("Ontvangst verklaard door beheerder")
    m.goto(B + "/app/borgen?filter=alle")
    m.click("text=Vondelstraat 7-H")
    shot(m, "13-geschil")

    # 0.4.0: a deposit held at e-DEPO for a Belgian address. A landlord account in Flanders gets a live warning.
    m.goto(B + "/app/borgen/nieuw")
    m.fill("#address", "Sint-Pietersnieuwstraat 33")
    m.fill("#postcode", "9000")
    m.fill("#city", "Gent")
    m.select_option("#region", "VL")
    m.fill("#tenant_name", "Elise Testhuurder")
    m.fill("#tenant_email", "elise@huurder.test")
    m.fill("#lease_start", date.today().isoformat())
    m.fill("#rent", "850,00")
    m.fill("#amount", "2.550,00")
    m.check("input[name=holding][value=external]")
    m.select_option("#provider_kind", "verhuurder_rekening")
    expect(m.locator("[data-provider-warning]")).to_contain_text("geblokkeerde rekening op naam van de huurder")
    m.select_option("#provider_kind", "e_depo")
    expect(m.locator("[data-provider-warning]")).to_be_hidden()
    expect(m.locator("#guarantee_expires_on")).to_be_hidden()
    expect(m.locator("label[for=provider_reference]")).to_have_text("Dossiernummer (optioneel)")
    m.fill("#provider_name", "Deposito- en Consignatiekas")
    m.fill("#provider_reference", "EDP-2026-000777")
    shot(m, "17-nieuwe-borg-edepo")
    m.click("text=Opslaan en huurder uitnodigen")
    expect(m.locator(".flash.ok")).to_contain_text("uitnodiging verstuurd")
    expect(m.locator("#aanbieder")).to_contain_text("e-DEPO (Deposito- en Consignatiekas)")
    expect(m.locator("#aanbieder")).to_contain_text("EDP-2026-000777")
    expect(m.locator(".banner", has_text="bestaat alleen")).to_have_count(0)

    # Dashboard: where the deposits sit
    m.goto(B + "/app")
    where = m.locator("section", has=m.get_by_role("heading", name="Waar staan je borgen"))
    expect(where).to_be_visible()
    expect(where.locator("tr", has_text="e-DEPO").locator("td").nth(1)).to_have_text("2")  # the imported one and the new one
    expect(where.locator("tr", has_text="Aanbieder onbekend")).to_be_visible()
    shot(m, "18-dashboard-waar-staan-je-borgen")
    where.locator("a", has_text="e-DEPO").click()
    expect(m.locator("tr", has_text="Sint-Pietersnieuwstraat 33")).to_be_visible()
    expect(m.locator("#aanbieder")).to_have_value("e_depo")

    # Release paperwork after agreement (Stadswonen Gent, e-DEPO, tenant agreed with the settlement)
    gctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    gb = gctx.new_page()
    gb.on("pageerror", lambda e: errors.append(str(e)))
    gb.goto(B + "/login")
    gb.fill("#email", "beheer@stadswonen.test")
    gb.fill("#password", PW)
    gb.click("button[type=submit]")
    gb.goto(B + "/app/borgen?filter=alle&aanbieder=e_depo")
    gb.click("text=Korenmarkt 5 bus 3")
    expect(gb.locator(".release-steps")).to_be_visible()
    shot(gb, "19-edepo-akkoord")
    with gb.expect_download() as dl:
        gb.click("text=Vrijgaveformulier (PDF)")
    assert dl.value.suggested_filename.startswith("vrijgaveformulier-"), dl.value.suggested_filename
    with open(dl.value.path(), "rb") as fh:
        assert fh.read(5) == b"%PDF-"

    # The tenant downloads the same form in Depiqo Wallet
    sofie_ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, accept_downloads=True)
    sofie = sofie_ctx.new_page()
    sofie.on("pageerror", lambda e: errors.append(str(e)))
    sofie.goto(B + "/login")
    sofie.fill("#email", "sofie@huurder.test")
    sofie.fill("#password", PW)
    sofie.click("button[type=submit]")
    expect(sofie.get_by_role("heading", name="Waar staat je borg")).to_be_visible()
    with sofie.expect_download() as dl:
        sofie.click("text=Vrijgaveformulier (PDF)")
    with open(dl.value.path(), "rb") as fh:
        assert fh.read(5) == b"%PDF-"
    assert sofie.evaluate("document.documentElement.scrollWidth") <= 390

    # Finance confirms the release at the provider with proof: the dossier closes
    gb.on("dialog", lambda d: d.accept())
    gb.select_option("#kind", "vrijgave")
    gb.set_input_files("#file", files=[{"name": "vrijgave-edepo.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4 vrijgave e-DEPO"}])
    gb.click("button:has-text('Uploaden')")
    gb.select_option("#release_doc", index=1)
    gb.click("button:has-text('Vrijgave bij aanbieder bevestigd')")
    expect(gb.locator(".badge").filter(has_text="Vrijgegeven en gesloten")).to_be_visible()

    # A guarantee in the wallet: no money paid, a third party guarantees
    mila = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True).new_page()
    mila.on("pageerror", lambda e: errors.append(str(e)))
    mila.goto(B + "/login")
    mila.fill("#email", "mila@huurder.test")
    mila.fill("#password", PW)
    mila.click("button[type=submit]")
    expect(mila.locator("text=Je hebt geen geld gestort. Een derde staat garant.")).to_be_visible()
    assert mila.evaluate("document.documentElement.scrollWidth") <= 390
    shot(mila, "20-wallet-garantie")

    # 0.5.0: Depiqo Invest on a phone, as Kevin (identity verified for his deposit, two-step verification on).
    # His own phone session; the earlier phone context now belongs to Sanne.
    k = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True).new_page()
    k.on("pageerror", lambda e: errors.append(str(e)))
    k.goto(B + "/login")
    k.fill("#email", "kevin@huurder.test")
    k.fill("#password", "Mijn-eigen-wachtwoord-1")
    k.click("button[type=submit]")
    for attempt in range(3):
        k.fill("#code", mfa.totp(secret))
        k.click("button[type=submit]")
        if not k.get_by_role("heading", name="Nog één stap.").count():
            break
        time.sleep(31)  # a code may be used once: wait for the next step
    # 0.5.0: Depiqo Invest on a phone. Kevin's identity was checked for his deposit account, so the sandbox partner
    # activates his investment account right away. His deposit is never part of this.
    k.goto(B + "/wallet/beleggen")
    expect(k.get_by_role("heading", name="Beleggen met je eigen geld")).to_be_visible()
    expect(k.locator(".note.warn")).to_contain_text("Je kunt geld verliezen")
    expect(k.locator(".invest-note")).to_contain_text("nooit belegd")
    k.click("text=Start de toets")
    for key, value in (("experience", "soms"), ("funds", "pot"), ("risk", "beide"), ("spread", "kleiner"), ("horizon", "lang"),
                       ("loss", "ja"), ("drop", "wachten"), ("goal", "opbouwen")):
        k.check(f"input[name={key}][value={value}]")
    k.click("text=Toets afronden")
    expect(k.get_by_role("heading", name="Beleggen past bij je")).to_be_visible()
    k.click("text=Kies een portefeuille")
    k.fill("#bedrag", "500,00")
    k.click("button:has-text('Bereken')")
    neutraal = k.locator("form.portfolio", has=k.get_by_role("heading", name="Neutraal"))
    expect(neutraal.locator("tr.total")).to_contain_text("€ 2,21")   # 1 year: 0,25% service + 0,1925% fund costs on € 500
    expect(neutraal.locator("tr.total")).to_contain_text("€ 6,63")   # 3 years
    expect(neutraal).to_contain_text("Scenario's, geen voorspelling")
    assert k.evaluate("document.documentElement.scrollWidth") <= 390
    neutraal.locator("button").click()
    k.check("input[name=accept_partner]")
    k.check("input[name=accept_depiqo]")
    k.click("text=Rekening openen")
    expect(k.locator(".flash.ok")).to_contain_text("wordt geopend")
    expect(k.get_by_role("heading", name="Storten")).to_be_visible()
    k.fill("#dep_amount", "500,00")
    k.click("button:has-text('Simuleer storting')")
    expect(k.locator(".flash.ok")).to_contain_text("storting is binnen")
    k.fill("#buy_amount", "400,00")
    k.click("button:has-text('Kosten bekijken')")  # 0.5.2: costs in euro and the risk before every purchase
    expect(k.get_by_role("heading", name="Kosten op € 400,00")).to_be_visible()
    expect(k.locator("tr.total")).to_contain_text("€ 1,77")
    expect(k.locator(".note.warn")).to_contain_text("Je kunt geld verliezen")
    k.check("input[name=confirm]")
    k.click("button:has-text('Kooporder plaatsen')")
    expect(k.locator(".badge").filter(has_text="Wacht op koers")).to_be_visible()
    staff.goto(B + "/admin/beleggen")
    staff.click("button:has-text('Koersen een dag vooruitzetten')")
    expect(staff.locator(".flash.ok")).to_contain_text("Sandbox: koersen staan op")
    k.reload()
    expect(k.locator(".badge").filter(has_text="Uitgevoerd")).to_be_visible()
    expect(k.locator("svg.chart polyline.chart-value")).to_have_count(1)
    expect(k.locator("section", has=k.get_by_role("heading", name="Je fondsen"))).to_contain_text("Wereldwijde aandelen")
    assert k.evaluate("document.documentElement.scrollWidth") <= 390
    shot(k, "21-invest-overzicht")
    k.fill("#sell_amount", "100,00")
    k.click("button:has-text('Verkooporder plaatsen')")
    expect(k.locator(".flash.ok")).to_contain_text("verkooporder")
    # 0.5.2: withdrawals only to the tenant's own registered account; with 2FA on, a fresh code makes it usable at once
    for attempt in range(3):
        k.fill("#own_iban", "NL91 ABNA 0417 1643 00")
        k.fill("#own_code", mfa.totp(secret))
        k.click("button:has-text('Registreren')")
        if k.locator(".flash.ok").count():
            break
        time.sleep(31)  # this step's code was already used to log in: wait for the next one
    expect(k.locator(".flash.ok")).to_contain_text("Je rekeningnummer is geregistreerd")
    k.fill("#out_amount", "100,00")
    k.click("button:has-text('Opnemen')")
    expect(k.locator(".flash.ok")).to_contain_text("Je opname staat klaar")
    staff.goto(B + "/admin/beleggen")
    staff.click("button:has-text('Koersen een dag vooruitzetten')")
    k.reload()
    expect(k.locator("section", has=k.get_by_role("heading", name="Transacties"))).to_contain_text("Opgenomen naar")
    expect(k.locator("section", has=k.get_by_role("heading", name="Transacties"))).to_contain_text("Verkocht: Neutraal")

    st = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    st.goto(B + "/login")
    st.fill("#email", "staff@depiqo.test")
    st.fill("#password", PW)
    st.click("button[type=submit]")
    expect(st.get_by_role("heading", name="Depiqo-beheer")).to_be_visible()
    shot(st, "14-beheer")
    st.goto(B + "/admin/afstemming")
    expect(st.get_by_role("heading", name="Afstemming")).to_be_visible()
    expect(st.locator("text=Bankopdracht mislukt").first).to_be_visible()
    shot(st, "15-afstemming")
    st.goto(B + "/admin/unit-economics")
    expect(st.locator("text=Partnerkosten zijn aannames")).to_be_visible()
    shot(st, "16-unit-economics")
    browser.close()
    assert not errors, errors
    print("E2E OK")
