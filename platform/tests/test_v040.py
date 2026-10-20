"""Tests for version 0.4.0: the provider registry for deposits held elsewhere, the overview of where
deposits sit, and the release paperwork for external providers.

    python -m unittest discover -s tests -v
"""
import io
import os
import shutil
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.util import today as local_today  # noqa: E402
from app import billing, db, finance, imports, providers, release_form, services  # noqa: E402
from app import states as S  # noqa: E402
from app.util import today  # noqa: E402
import test_v030 as tv  # noqa: E402  (module import: its classes must not be collected twice)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENT = {"address": "Korenmarkt 1", "postcode": "9000", "city": "Gent", "region": "VL"}


class Base(tv.Base):
    def ext(self, kind="e_depo", where=GENT, **over):
        """A deposit held elsewhere, created through the form and invited. Returns (admin client, response, row)."""
        mgr = self.client("admin@a.test")
        fields = {"holding": "external", "provider_kind": kind, **where}
        fields.update(over)
        r = self.create(mgr, **fields)
        return mgr, r, self.row()

    def ext_agreed(self, kind="e_depo", where=GENT, **over):
        """Held elsewhere, receipt declared, moved out, settlement with EUR 150 agreed by the tenant."""
        mgr, _, d = self.ext(kind, where, **over)
        tenant = self.app.test_client()
        self.accept(tenant, self.invite_link())
        token = self.csrf(mgr)
        mgr.post(f"/app/borgen/{d['pid']}/ontvangst", data={"csrf_token": token})
        mgr.post(f"/app/borgen/{d['pid']}/vertrek", data={"move_out_date": local_today().isoformat(), "csrf_token": token})
        mgr.post(f"/app/borgen/{d['pid']}/afrekening-opslaan", data={"cat_0": "damage", "desc_0": "Gat in de muur", "amount_0": "150,00",
                                                                    "csrf_token": token})
        mgr.post(f"/app/borgen/{d['pid']}/afrekening-voorstellen", data={"csrf_token": token})
        tenant.post(f"/wallet/borg/{d['pid']}/akkoord", data={"csrf_token": self.csrf(tenant, f"/wallet/borg/{d['pid']}")})
        self.assertEqual(self.row(d["pid"])["status"], S.AGREED)
        return mgr, tenant, self.row(d["pid"])

    def audit_actions(self):
        with self.app.app_context():
            return [r["action"] for r in db.all_("SELECT action FROM audit_log ORDER BY id")]


# ====================================================================== 1. registry: validation and mapping

class ProviderRegistryTest(Base):
    def test_new_external_deposit_records_the_provider(self):
        mgr, r, d = self.ext("e_depo", provider_name="Deposito- en Consignatiekas", provider_reference="EDP-2026-1")
        self.assertEqual(r.status_code, 302)
        self.assertEqual((d["provider_kind"], d["provider_name"], d["provider_reference"], d["security_type"], d["custodian"], d["external_iban"]),
                         ("e_depo", "Deposito- en Consignatiekas", "EDP-2026-1", "external_account", "Deposito- en Consignatiekas", None))
        html = mgr.get(f"/app/borgen/{d['pid']}").get_data(as_text=True)
        for text in ("Waar staat de borg", "e-DEPO (Deposito- en Consignatiekas)", "EDP-2026-1", "Dossiernummer"):
            self.assertIn(text, html)

    def test_guarantee_maps_to_security_type_guarantee(self):
        _, _, d = self.ext("borggarantie", where={}, provider_name="Garantiefonds C", guarantee_expires_on="2030-01-31")
        self.assertEqual((d["provider_kind"], d["security_type"], d["guarantee_expires_on"], d["region"]),
                         ("borggarantie", "guarantee", "2030-01-31", "NL"))
        with self.ctx():
            self.assertEqual(services.payment_details(d), (None, None))  # the tenant transfers nothing
        self.assertEqual(providers.security_type_for("verhuurder_rekening"), "external_account")
        self.assertIsNone(providers.custodian_for("verhuurder_rekening", "Bank A"))

    def test_validation(self):
        mgr = self.client("admin@a.test")
        cases = (
            ({"provider_kind": "spaarpot"}, "Kies een geldige soort aanbieder"),
            ({"provider_kind": "borggarantie", "guarantee_expires_on": "2001-01-01"}, "langer lopen dan de start"),
            ({"provider_kind": "borggarantie", "guarantee_expires_on": "31-31-2030"}, "JJJJ-MM-DD"),
            ({"provider_kind": "verhuurder_rekening"}, "Vul het rekeningnummer in"),
            ({"provider_kind": "e_depo", "provider_reference": "x" * 61}, "maximaal 60 tekens"),
        )
        for fields, message in cases:
            r = self.create(mgr, holding="external", **{**GENT, **fields})
            self.assertEqual(r.status_code, 200, fields)
            self.assertIn(message, r.get_data(as_text=True), fields)
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM deposits"), 0)
        with self.ctx():
            problems = services.validate_new({"region": "NL", "rent_cents": 100000, "amount_cents": 200000, "lease_start": "2025-01-01",
                                              "holding": "depiqo", "provider_kind": "e_depo", "tenant_name": "T", "tenant_email": "t@t.test",
                                              "address": "A", "postcode": "1", "city": "B"})
        self.assertTrue(any("alleen in bij een borg die elders staat" in p for p in problems))
        self.assertIn("alleen in bij een garantie", providers.validate({"holding": "external", "provider_kind": "e_depo",
                                                                        "guarantee_expires_on": "2030-01-01"})[0])
        # In the form the expiry field is hidden for other kinds: a leftover value is dropped, not an error.
        r = self.create(mgr, holding="external", provider_kind="e_depo", guarantee_expires_on="2030-01-01", **GENT)
        self.assertEqual(r.status_code, 302)
        self.assertIsNone(self.row()["guarantee_expires_on"])
        # Dutch names are accepted wherever a kind is typed
        self.assertEqual([providers.parse_kind(v) for v in ("e-DEPO", "Tak 26", "rekening verhuurder", "Garantie", "", "spaarpot")],
                         ["e_depo", "verzekering_tak26", "verhuurder_rekening", "borggarantie", None, False])

    def test_no_provider_keeps_the_0_3_behaviour(self):
        mgr = self.client("admin@a.test")
        r = self.create(mgr, holding="external", tenant_email="y@huurder.test", address="Elders 2")
        self.assertIn("Vul het rekeningnummer in", r.get_data(as_text=True))
        self.create(mgr, holding="external", external_iban="NL91ABNA0417164300", tenant_email="z@huurder.test", address="Elders 3")
        d = self.row()
        self.assertEqual((d["provider_kind"], d["security_type"]), (None, "external_account"))


# ====================================================================== 1. region warnings (never block)

class RegionWarningTest(Base):
    def test_rules(self):
        w = providers.region_warnings
        self.assertEqual(w("VL", "e_depo"), [])
        self.assertEqual(w("NL", "verhuurder_rekening"), [])
        for kind in ("e_depo", "ocmw", "verzekering_tak26"):
            self.assertIn("bestaat alleen in België", w("NL", kind)[0])
        self.assertIn("geblokkeerde rekening op naam van de huurder", w("VL", "verhuurder_rekening")[0])
        self.assertNotIn("contanten", w("VL", "verhuurder_rekening")[0])
        self.assertIn("contanten ook niet toegestaan", w("BRU", "verhuurder_rekening")[0])

    def test_warning_shown_but_deposit_created(self):
        mgr, r, d = self.ext("e_depo", where={})  # e-DEPO for a Dutch address
        self.assertEqual(r.status_code, 302)
        self.assertEqual((d["provider_kind"], d["region"]), ("e_depo", "NL"))
        page = mgr.get(r.headers["Location"]).get_data(as_text=True)
        self.assertIn('class="flash warn"', page)
        self.assertIn("bestaat alleen in België", page)
        self.assertIn('class="banner warn"', page)  # and it stays on the deposit page
        form = mgr.get("/app/borgen/nieuw").get_data(as_text=True)
        self.assertIn('data-warn-nl="e-DEPO (Deposito- en Consignatiekas) bestaat alleen in België', form)  # live hint in the form
        self.assertIn("Bijvoorbeeld de naam van de bank of verzekeraar.", form)

    def test_guarantee_ending_before_the_lease(self):
        self.assertEqual(providers.guarantee_warnings({"guarantee_expires_on": "2030-01-01", "lease_end": "2029-01-01"}), [])
        self.assertIn("voor het einde van de huur", providers.guarantee_warnings({"guarantee_expires_on": "2029-01-01", "lease_end": "2030-01-01"})[0])


# ====================================================================== 2. edit (admin and manager, audited)

class ProviderEditTest(Base):
    def test_permissions_and_audit(self):
        mgr, _, d = self.ext("e_depo")
        url = f"/app/borgen/{d['pid']}/aanbieder"
        for email, code in (("admin@a.test", 200), ("manager@a.test", 200), ("finance@a.test", 403), ("viewer@a.test", 403)):
            self.assertEqual(self.client(email).get(url).status_code, code, email)
        self.assertEqual(self.client("admin@b.test").get(url).status_code, 404)
        m = self.client("manager@a.test")
        r = m.post(url, data={"provider_kind": "bank_geblokkeerd", "provider_name": "Bank A", "provider_reference": "BE71 0961 2345 6769",
                              "csrf_token": self.csrf(m)})
        self.assertEqual(r.status_code, 302)
        d = self.row(d["pid"])
        self.assertEqual((d["provider_kind"], d["provider_name"], d["custodian"]), ("bank_geblokkeerd", "Bank A", "Bank A"))
        self.assertIn("deposit.provider_updated", self.audit_actions())
        with self.app.app_context():
            ev = db.one("SELECT message FROM deposit_events WHERE deposit_id = ? AND type = 'provider'", (d["id"],))
        self.assertIn("soort: e-DEPO wordt Geblokkeerde rekening", ev["message"])
        v = self.client("viewer@a.test")
        self.assertEqual(v.post(url, data={"provider_kind": "anders", "csrf_token": self.csrf(v)}).status_code, 403)
        self.assertEqual(self.row(d["pid"])["provider_kind"], "bank_geblokkeerd")

    def test_only_while_running_and_only_external(self):
        mgr, _, d = self.ext("e_depo")
        with self.ctx():
            services.cancel(services.reload(d), None, "test")
        r = mgr.post(f"/app/borgen/{d['pid']}/aanbieder", data={"provider_kind": "anders", "csrf_token": self.csrf(mgr)}, follow_redirects=True)
        self.assertIn("alleen aan bij een lopende borg", r.get_data(as_text=True))
        self.assertEqual(self.row(d["pid"])["provider_kind"], "e_depo")
        self.create(mgr, tenant_email="dep@huurder.test", address="Depiqo 1")
        dep = self.row()
        with self.ctx():
            with self.assertRaises(services.WorkflowError):
                services.update_provider(dep, None, {"provider_kind": "e_depo"})

    def test_verified_evidence_locks_the_provider(self):
        mgr, _, d = self.ext("e_depo")
        self.accept(self.app.test_client(), self.invite_link())
        mgr.post(f"/app/borgen/{d['pid']}/ontvangst", data={"csrf_token": self.csrf(mgr)})
        with self.ctx():
            services.set_evidence(services.reload(d), "verified", self.uid("staff@depiqo.test"), "Gecontroleerd bij de aanbieder.", staff=True)
        url = f"/app/borgen/{d['pid']}/aanbieder"
        r = mgr.post(url, data={"provider_kind": "anders", "csrf_token": self.csrf(mgr)})
        self.assertIn("Depiqo heeft het bewijs voor deze aanbieder geverifieerd", r.get_data(as_text=True))
        self.assertEqual(self.row(d["pid"])["provider_kind"], "e_depo")

    def test_guarantee_expiry_can_be_extended(self):
        mgr, _, d = self.ext("borggarantie", where={}, guarantee_expires_on="2030-01-31")
        mgr.post(f"/app/borgen/{d['pid']}/aanbieder", data={"provider_kind": "borggarantie", "guarantee_expires_on": "2031-01-31",
                                                           "csrf_token": self.csrf(mgr)})
        self.assertEqual(self.row(d["pid"])["guarantee_expires_on"], "2031-01-31")


# ====================================================================== 2. import and export

def provider_csv(rows):
    header = "address;postcode;city;region;tenant_name;tenant_email;rent;amount;lease_start;holding;external_iban;aanbieder;naam_aanbieder;referentie;garantie_tot"
    return ("﻿" + "\r\n".join([header, *(";".join(r) for r in rows)]) + "\r\n").encode("utf-8")


class ImportProviderTest(Base):
    ROWS = [
        ("Korenmarkt 1", "9000", "Gent", "VL", "A", "a@huurder.test", "900", "2700", "2024-01-01", "external", "", "e-DEPO", "Deposito- en Consignatiekas", "EDP-1", ""),
        ("Meir 2", "2000", "Antwerpen", "VL", "B", "b@huurder.test", "900", "2700", "2024-01-01", "elders", "", "Tak 26", "Verzekeraar B", "K26-1", ""),
        ("Damrak 3", "1012 LM", "Amsterdam", "NL", "C", "c@huurder.test", "1000", "2000", "2024-01-01", "external", "NL91ABNA0417164300", "rekening verhuurder", "Bank A", "", ""),
        ("Coolsingel 4", "3011 AD", "Rotterdam", "NL", "D", "d@huurder.test", "1000", "2000", "2024-01-01", "external", "", "garantie", "Garantiefonds C", "GF-1", "31-12-2027"),
        ("Kerkstraat 5", "1017 GA", "Amsterdam", "NL", "E", "e@huurder.test", "1000", "2000", "2024-01-01", "external", "", "e-depo", "", "", ""),
        ("Rue Haute 6", "1000", "Brussel", "BRU", "F", "f@huurder.test", "900", "1800", "2024-01-01", "external", "", "verhuurder", "", "", ""),
    ]

    def test_aliases_values_and_warnings(self):
        with self.ctx():
            rows = imports.parse(provider_csv(self.ROWS), self.org)
        self.assertEqual([r["errors"] for r in rows], [[]] * 6)
        self.assertEqual([r["data"]["provider_kind"] for r in rows],
                         ["e_depo", "verzekering_tak26", "verhuurder_rekening", "borggarantie", "e_depo", "verhuurder_rekening"])
        self.assertEqual((rows[3]["data"]["guarantee_expires_on"], rows[0]["data"]["provider_reference"]), ("2027-12-31", "EDP-1"))
        self.assertEqual([bool(r["warnings"]) for r in rows], [False, False, False, False, True, True])  # warn, never block
        self.assertIn("contanten", rows[5]["warnings"][0])

    def test_invalid_values_are_errors(self):
        bad = [
            ("Laan 1", "1000 AA", "Amsterdam", "NL", "A", "a@huurder.test", "1000", "2000", "2024-01-01", "external", "", "spaarpot", "", "", ""),
            ("Laan 2", "1000 AA", "Amsterdam", "NL", "B", "b@huurder.test", "1000", "2000", "2024-01-01", "external", "", "e_depo", "", "", "2027-01-01"),
            ("Laan 3", "1000 AA", "Amsterdam", "NL", "C", "c@huurder.test", "1000", "2000", "2024-01-01", "external", "", "garantie", "", "", "morgen"),
            ("Laan 4", "1000 AA", "Amsterdam", "NL", "D", "d@huurder.test", "1000", "2000", "2024-01-01", "depiqo", "", "e_depo", "", "", ""),
        ]
        with self.ctx():
            rows = imports.parse(provider_csv(bad), self.org)
        errors = [" ".join(r["errors"]) for r in rows]
        self.assertIn("Aanbieder: onbekende soort", errors[0])
        self.assertIn("alleen in bij een garantie", errors[1])
        self.assertIn("Garantie tot", errors[2])
        self.assertIn("alleen in bij een borg die elders staat", errors[3])

    def test_commit_and_preview(self):
        a = self.client("admin@a.test")
        r = a.post("/app/borgen/import", data={"file": (io.BytesIO(provider_csv(self.ROWS)), "borgen.csv"), "csrf_token": self.csrf(a)},
                   content_type="multipart/form-data")
        preview = a.get(r.headers["Location"]).get_data(as_text=True)
        for text in ("Aanbieder", "e-DEPO", "Verzekeraar (tak 26)", "Garantiefonds C", 'class="warns"', "Dat houdt de import niet tegen"):
            self.assertIn(text, preview)
        with self.app.app_context():
            batch = db.one("SELECT * FROM import_batches")
        a.post(f"/app/borgen/import/{batch['id']}/bevestigen", data={"csrf_token": self.csrf(a)})
        with self.app.app_context():
            got = {r["address"]: r for r in db.all_("SELECT d.*, p.address FROM deposits d JOIN properties p ON p.id = d.property_id")}
        self.assertEqual(len(got), 6)
        self.assertEqual((got["Coolsingel 4"]["security_type"], got["Coolsingel 4"]["guarantee_expires_on"], got["Coolsingel 4"]["status"]),
                         ("guarantee", "2027-12-31", S.SECURED))
        self.assertEqual((got["Korenmarkt 1"]["provider_kind"], got["Korenmarkt 1"]["custodian"]), ("e_depo", "Deposito- en Consignatiekas"))

    def test_template_has_the_provider_columns(self):
        header = imports.template_csv().splitlines()[0]
        for col in ("provider_kind", "provider_name", "provider_reference", "guarantee_expires_on"):
            self.assertIn(col, header)

    def test_export_columns(self):
        mgr, _, d = self.ext("e_depo", provider_name="Deposito- en Consignatiekas", provider_reference="EDP-9")
        lines = mgr.get("/app/export.csv").get_data(as_text=True).splitlines()
        header = lines[0].lstrip("﻿").split(";")
        self.assertEqual(header[7:11], ["aanbieder_soort", "aanbieder", "referentie_aanbieder", "garantie_tot"])
        self.assertEqual(header[-1], "sandbox")
        row = lines[1].split(";")
        self.assertEqual(row[7:10], ["e_depo", "Deposito- en Consignatiekas", "EDP-9"])


# ====================================================================== 3. overview, list filter, reconciliation

class OverviewTest(Base):
    def make(self, kind, amount, status=S.SECURED, evidence="declared", n=[0], **extra):
        n[0] += 1
        with self.ctx():
            d = services.create_deposit(self.org, self.uid("admin@a.test"), {
                "address": f"Weg {n[0]}", "postcode": "9000", "city": "Gent", "region": "VL", "tenant_name": "T",
                "tenant_email": f"t{n[0]}@huurder.test", "rent_cents": 100000, "amount_cents": amount, "holding": "external" if kind != "depiqo" else "depiqo",
                "lease_start": "2024-01-01", "external_iban": "BE68539007547034" if kind in (None, "verhuurder_rekening") else None,
                "provider_kind": None if kind == "depiqo" else kind, **extra})
            db.run("UPDATE deposits SET status = ?, evidence_level = ? WHERE id = ?",
                   (status, evidence if kind != "depiqo" else None, d["id"]))
            return services.reload(d)

    def test_grouping(self):
        self.make("e_depo", 200000, evidence="legal")
        self.make("e_depo", 250000)
        self.make("borggarantie", 300000)
        self.make(None, 100000)
        self.make("depiqo", 150000)
        self.make("e_depo", 290000, status=S.CLOSED)   # not running: not counted
        self.make("e_depo", 290000, status=S.CONCEPT)  # not running: not counted
        with self.ctx():
            rows, totals = providers.overview(self.org)
        got = {r["key"]: (r["n"], r["total"], r["declared"]) for r in rows}
        self.assertEqual(got, {"depiqo": (1, 150000, None), "e_depo": (2, 450000, 1), "borggarantie": (1, 300000, 1), "onbekend": (1, 100000, 1)})
        self.assertEqual([r["key"] for r in rows], ["depiqo", "e_depo", "borggarantie", "onbekend"])
        self.assertEqual((totals["n"], totals["total"], totals["declared"]), (5, 1000000, 3))
        html = self.client("viewer@a.test").get("/app").get_data(as_text=True)
        for text in ("Waar staan je borgen", "e-DEPO", "Garantie", "Aanbieder onbekend", "aanbieder=e_depo"):
            self.assertIn(text, html)

    def test_list_filter(self):
        self.make("e_depo", 200000)
        self.make("ocmw", 200000)
        self.make(None, 200000)
        v = self.client("viewer@a.test")
        html = v.get("/app/borgen?filter=alle&aanbieder=e_depo").get_data(as_text=True)
        self.assertIn("Weg ", html)
        self.assertEqual(html.count('class="tag prov"'), 1)
        self.assertIn(">e-DEPO<", html)
        html = v.get("/app/borgen?filter=alle&aanbieder=onbekend").get_data(as_text=True)
        self.assertEqual(html.count("Aanbieder onbekend</span>"), 1)
        html = v.get("/app/borgen?filter=alle&aanbieder=niet-bestaand").get_data(as_text=True)
        self.assertEqual(html.count('class="rowlink"'), 3)  # an unknown value filters nothing

    def test_reconciliation(self):
        soon = self.make("borggarantie", 200000, guarantee_expires_on=(today() + timedelta(days=30)).isoformat())
        late = self.make("borggarantie", 200000, guarantee_expires_on=(today() - timedelta(days=3)).isoformat())
        fine = self.make("borggarantie", 200000, guarantee_expires_on=(today() + timedelta(days=200)).isoformat())
        unknown = self.make(None, 200000)
        done = self.make("borggarantie", 200000, status=S.CLOSED, guarantee_expires_on=(today() - timedelta(days=3)).isoformat())
        with self.ctx():
            rows, totals = finance.reconciliation(org_id=self.org, only_exceptions=True)
            _, place_totals = providers.overview(self.org)
        by = {r["d"]["reference"]: r["exceptions"] for r in rows}
        self.assertIn("Garantie verloopt over 30 dagen", by[soon["reference"]][0])
        self.assertIn("Garantie verlopen op", by[late["reference"]][0])
        self.assertNotIn(fine["reference"], by)
        self.assertNotIn(done["reference"], by)
        self.assertIn("Borg elders zonder aanbieder", by[unknown["reference"]][0])
        self.assertEqual(place_totals["expiring"], 2)
        html = self.client("finance@a.test").get("/app/afstemming").get_data(as_text=True)
        self.assertIn("Garantie verloopt over 30 dagen", html)


# ====================================================================== 4. release paperwork

class ReleaseFormTest(Base):
    def test_only_after_agreement_and_only_held_elsewhere(self):
        mgr, _, d = self.ext("e_depo")
        self.assertEqual(mgr.get(f"/app/borgen/{d['pid']}/vrijgaveformulier.pdf").status_code, 404)
        _, dep = self.to_agreed()  # Depiqo account: the bank releases, no form
        self.assertEqual(mgr.get(f"/app/borgen/{dep['pid']}/vrijgaveformulier.pdf").status_code, 404)

    def test_pdf_has_the_key_fields(self):
        mgr, tenant, d = self.ext_agreed("e_depo", provider_name="Deposito- en Consignatiekas", provider_reference="EDP-2026-777")
        r = mgr.get(f"/app/borgen/{d['pid']}/vrijgaveformulier.pdf")
        self.assertEqual((r.status_code, r.mimetype), (200, "application/pdf"))
        self.assertTrue(r.data.startswith(b"%PDF-"))
        with self.ctx():
            f = release_form.data_for(d)
            raw = release_form.build(d, compress=False).decode("latin-1")
        self.assertEqual((f["to_tenant"], f["to_landlord"], f["obligation"]), (185000, 15000, 200000))
        for text in ("Vrijgaveformulier huurwaarborg", "Tess Huurder", "Org A", "Korenmarkt 1, 9000 Gent", d["reference"],
                     "e-DEPO \\(Deposito- en Consignatiekas\\)", "EDP-2026-777", "2.000,00", "1.850,00", "150,00", "Handtekening",
                     "eigen procedure", "Akkoord van de huurder met de eindafrekening"):
            self.assertIn(text, raw, text)
        self.assertIn("deposit.release_form", self.audit_actions())
        with self.app.app_context():
            self.assertTrue(db.scalar("SELECT COUNT(*) FROM deposit_events WHERE deposit_id = ? AND message LIKE 'Vrijgaveformulier%'", (d["id"],)))

    def test_who_may_download(self):
        mgr, tenant, d = self.ext_agreed("e_depo")
        url = f"/app/borgen/{d['pid']}/vrijgaveformulier.pdf"
        self.assertEqual(self.client("viewer@a.test").get(url).status_code, 200)  # deposit.view
        self.assertEqual(self.client("admin@b.test").get(url).status_code, 404)   # other organisation
        wurl = f"/wallet/borg/{d['pid']}/vrijgaveformulier.pdf"
        r = tenant.get(wurl)
        self.assertEqual((r.status_code, r.data[:5]), (200, b"%PDF-"))
        self.assertIn("Vrijgaveformulier (PDF)", tenant.get(f"/wallet/borg/{d['pid']}").get_data(as_text=True))
        # another tenant of the same organisation cannot download it
        self.create(mgr, holding="external", provider_kind="e_depo", tenant_email="ander@huurder.test", address="Andere 1", **{
            k: v for k, v in GENT.items() if k != "address"})
        other = self.app.test_client()
        self.accept(other, self.invite_link())
        self.assertEqual(other.get(wurl).status_code, 404)
        self.assertEqual(self.client("admin@a.test").get(wurl).status_code, 403)  # staff of the org use the business route

    def test_basis_after_a_resolved_dispute(self):
        mgr, tenant, d = self.ext_agreed("e_depo")
        with self.ctx():
            text, _ = services.release_basis(services.reload(d))
        self.assertEqual(text, "Akkoord van de huurder met de eindafrekening")
        mgr2 = self.client("admin@a.test")
        self.create(mgr2, holding="external", provider_kind="bank_geblokkeerd", tenant_email="g@huurder.test", address="Geschil 1",
                    **{k: v for k, v in GENT.items() if k != "address"})
        g = self.row()
        t = self.app.test_client()
        self.accept(t, self.invite_link())
        token = self.csrf(mgr2)
        mgr2.post(f"/app/borgen/{g['pid']}/ontvangst", data={"csrf_token": token})
        mgr2.post(f"/app/borgen/{g['pid']}/vertrek", data={"move_out_date": local_today().isoformat(), "csrf_token": token})
        mgr2.post(f"/app/borgen/{g['pid']}/afrekening-opslaan", data={"cat_0": "damage", "desc_0": "Muur", "amount_0": "500", "csrf_token": token})
        mgr2.post(f"/app/borgen/{g['pid']}/afrekening-voorstellen", data={"csrf_token": token})
        t.post(f"/wallet/borg/{g['pid']}/betwisten", data={"reason": "Dit was er al bij de start van de huur.",
                                                          "csrf_token": self.csrf(t, f"/wallet/borg/{g['pid']}")})
        doc = self.upload(mgr2, g, "agreement", "akkoord.pdf")
        mgr2.post(f"/app/borgen/{g['pid']}/geschil-afsluiten", data={"kind": "agreement", "landlord_amount": "200", "document_id": doc,
                                                                     "csrf_token": token})
        with self.ctx():
            g = services.reload(g)
            self.assertEqual(g["status"], S.AGREED)
            self.assertEqual(services.release_basis(g)[0], "Akkoord tussen huurder en verhuurder na een geschil")
            self.assertEqual(release_form.data_for(g)["to_landlord"], 20000)


class ReleaseConfirmTest(Base):
    def test_confirmation_needs_proof_and_the_right_role(self):
        mgr, tenant, d = self.ext_agreed("e_depo")
        m = self.client("manager@a.test")
        self.assertEqual(m.post(f"/app/borgen/{d['pid']}/vrijgave", data={"csrf_token": self.csrf(m)}).status_code, 403)
        fin = self.client("finance@a.test")
        r = fin.post(f"/app/borgen/{d['pid']}/vrijgave", data={"csrf_token": self.csrf(fin)}, follow_redirects=True)
        self.assertIn("Voeg eerst het bewijs van de aanbieder toe", r.get_data(as_text=True))
        # the old shortcut ("Terugbetaling registreren") is wrapped: it needs the same proof
        fin.post(f"/app/borgen/{d['pid']}/uitbetalen", data={"csrf_token": self.csrf(fin)})
        self.assertEqual(self.row(d["pid"])["status"], S.AGREED)
        wrong = self.upload(fin, d, "bankbewijs", "afschrift.pdf")
        r = fin.post(f"/app/borgen/{d['pid']}/vrijgave", data={"document_id": wrong, "csrf_token": self.csrf(fin)}, follow_redirects=True)
        self.assertIn("juiste soort", r.get_data(as_text=True))
        proof = self.upload(fin, d, "vrijgave", "vrijgave-edepo.pdf")
        fin.post(f"/app/borgen/{d['pid']}/vrijgave", data={"document_id": proof, "csrf_token": self.csrf(fin)})
        d = self.row(d["pid"])
        self.assertEqual((d["status"], d["release_document_id"], d["eligible_value_cents"], d["asset_value_cents"]), (S.CLOSED, proof, 0, 0))
        self.assertIn("deposit.vrijgave", self.audit_actions())
        with self.app.app_context():
            ev = db.one("SELECT message, data_json FROM deposit_events WHERE deposit_id = ? AND to_status = ?", (d["id"], S.CLOSED))
        self.assertIn("Vrijgave bij aanbieder bevestigd (e-DEPO", ev["message"])
        self.assertIn('"huurder":185000', ev["data_json"])
        html = fin.get(f"/app/borgen/{d['pid']}").get_data(as_text=True)
        self.assertIn("Vrijgegeven en gesloten", html)
        self.assertIn("Bewijs van vrijgave", html)
        self.assertEqual(fin.get(f"/app/borgen/{d['pid']}/vrijgaveformulier.pdf").status_code, 200)  # kept for the record
        self.assertIn("Vrijgegeven", tenant.get(f"/wallet/borg/{d['pid']}").get_data(as_text=True))

    def test_not_for_a_depiqo_account(self):
        _, d = self.to_agreed()
        with self.ctx():
            with self.assertRaisesRegex(services.WorkflowError, "bevestigt de bank"):
                services.confirm_external_release(services.reload(d), None, None)

    def test_legal_not_possible_on_the_landlords_account(self):
        mgr, _, d = self.ext("verhuurder_rekening", where={}, external_iban="NL91ABNA0417164300")
        self.accept(self.app.test_client(), self.invite_link())
        mgr.post(f"/app/borgen/{d['pid']}/ontvangst", data={"csrf_token": self.csrf(mgr)})
        doc = self.upload(mgr, d, "blokkering", "attest.pdf")
        with self.ctx():
            with self.assertRaisesRegex(services.WorkflowError, "niet juridisch geblokkeerd"):
                services.set_evidence(services.reload(d), "legal", self.uid("staff@depiqo.test"), "x", doc, staff=True)
            d = services.set_evidence(services.reload(d), "verified", self.uid("staff@depiqo.test"), "Afschrift gecontroleerd.", staff=True)
        self.assertEqual(d["evidence_level"], "verified")


# ====================================================================== 5. wallet and 6. billing

class WalletGuaranteeTest(Base):
    def test_guarantee_text_and_no_payment(self):
        mgr, _, d = self.ext("borggarantie", where={}, provider_name="Garantiefonds C", provider_reference="GF-1",
                             guarantee_expires_on=(today() + timedelta(days=30)).isoformat())
        tenant = self.app.test_client()
        self.accept(tenant, self.invite_link())
        html = tenant.get(f"/wallet/borg/{d['pid']}").get_data(as_text=True)
        for text in ("Waar staat je borg", "Je hebt geen geld gestort. Een derde staat garant. Bij schade kan die het bedrag op jou verhalen.",
                     "Garantiefonds C", "GF-1", "Garantie geldig tot", "Je borg wordt geregeld", "Je garantie loopt binnenkort af"):
            self.assertIn(text, html)
        self.assertNotIn("Stort je borg", html)
        with self.ctx():
            figs = {f["key"]: f for f in services.balances(services.reload(d))}
            self.assertIsNone(figs["received"]["value"])
            self.assertIn("Geen geld gestort", figs["received"]["note"])
            with self.assertRaisesRegex(services.WorkflowError, "stort de huurder niets"):
                services.send_payment_reminder(services.reload(d), None)

    def test_provider_shown_for_other_kinds(self):
        mgr, _, d = self.ext("verzekering_tak26", provider_name="Verzekeraar B", provider_reference="K26-1")
        tenant = self.app.test_client()
        self.accept(tenant, self.invite_link())
        html = tenant.get(f"/wallet/borg/{d['pid']}").get_data(as_text=True)
        self.assertIn("In een kapitalisatiecontract op jouw naam bij een verzekeraar", html)
        self.assertIn("Verzekeraar B", html)
        self.assertNotIn("Een derde staat garant", html)


class BillingUnchangedTest(Base):
    def test_every_provider_kind_is_billed_as_held_elsewhere(self):
        for i, kind in enumerate(providers.KINDS):
            self.ext(kind, where={**GENT, "address": f"Gent {i}"}, tenant_email=f"b{i}@huurder.test",
                     external_iban="BE68539007547034" if providers.needs_iban(kind) else "")
        with self.ctx():
            counts = billing.active_counts(self.org, today().strftime("%Y-%m"))
        self.assertEqual(counts, {"external": len(providers.KINDS), "depiqo": 0})


# ====================================================================== migration 006

class Migration006Test(Base):
    def test_existing_external_deposits_stay_unknown(self):
        src = os.path.join(ROOT, "migrations")
        old_dir = os.path.join(self.tmp, "m6")
        os.makedirs(old_dir)
        import glob
        for f in sorted(glob.glob(os.path.join(src, "*.sql"))):
            if os.path.basename(f)[:3] < "006":
                shutil.copy(f, old_dir)
        path = os.path.join(self.tmp, "old6.sqlite3")
        db.migrate(path, old_dir)
        conn = db.connect(path)
        conn.execute("INSERT INTO organizations (id, name, created_at) VALUES (1, 'Oud BV', '2026-03-15T10:00:00+00:00')")
        conn.execute("INSERT INTO properties (id, org_id, address, postcode, city, region, created_at) VALUES (1, 1, 'A 1', '9000', 'Gent', 'VL', '2026-01-01')")
        conn.execute("INSERT INTO tenants (id, org_id, name, email, created_at) VALUES (1, 1, 'T', 't@t.test', '2026-01-01')")
        conn.execute("INSERT INTO deposits (id, pid, reference, org_id, property_id, tenant_id, region, holding, rent_cents, amount_cents, status, "
                     "lease_start, rule_version, created_at, updated_at, security_type) VALUES (1, 'p1', 'DPQ-001-00001', 1, 1, 1, 'VL', 'external', "
                     "100000, 200000, 'secured', '2026-01-01', '2026-10-18', '2026-01-01', '2026-01-01', 'external_account')")
        conn.close()
        shutil.copy(os.path.join(src, "006_provider_registry.sql"), old_dir)
        db.migrate(path, old_dir)
        conn = db.connect(path)
        row = conn.execute("SELECT provider_kind, provider_name, guarantee_expires_on, release_document_id, security_type FROM deposits").fetchone()
        self.assertEqual(tuple(row), (None, None, None, None, "external_account"))
        with self.assertRaises(Exception):
            conn.execute("UPDATE deposits SET provider_kind = 'spaarpot' WHERE id = 1")  # CHECK constraint
        conn.close()


if __name__ == "__main__":
    unittest.main()
