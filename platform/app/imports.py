"""Bulk import of existing deposits from a CSV file (Excel export).

Flow: upload -> parse and validate every row -> preview with errors per row -> commit.
The commit runs in one transaction: either every row is imported or none. Invitations, if
chosen, are sent after the commit, one by one, so a mail problem never undoes the import.

Accepts UTF-8 (with or without BOM) and Windows-1252, and ',' ';' or tab as separator
(Dutch Excel writes ';'). At most IMPORT_MAX_ROWS rows and IMPORT_MAX_BYTES bytes.
"""
import csv
import io
import json
import re
from datetime import date

from flask import current_app

from . import db, providers, services
from . import states as S
from .util import dumps, now_iso, parse_euros, valid_email, valid_iban

COLUMNS = ("address", "postcode", "city", "region", "tenant_name", "tenant_email", "rent", "amount", "lease_start",
           "holding", "external_iban", "evidence", "provider_kind", "provider_name", "provider_reference", "guarantee_expires_on")
REQUIRED = ("address", "postcode", "city", "region", "tenant_name", "tenant_email", "rent", "amount", "lease_start", "holding")
ALIASES = {"adres": "address", "plaats": "city", "regio": "region", "huurder": "tenant_name", "naam_huurder": "tenant_name",
           "email": "tenant_email", "e-mail": "tenant_email", "email_huurder": "tenant_email", "huur": "rent", "borg": "amount",
           "start_huur": "lease_start", "ingangsdatum": "lease_start", "waar": "holding", "iban": "external_iban", "bewijs": "evidence",
           # 0.4.0: provider registry (all optional)
           "aanbieder": "provider_kind", "soort_aanbieder": "provider_kind", "waar_staat_de_borg": "provider_kind", "soort": "provider_kind",
           "naam_aanbieder": "provider_name", "aanbieder_naam": "provider_name",
           "referentie": "provider_reference", "referentie_aanbieder": "provider_reference", "kenmerk_aanbieder": "provider_reference",
           "dossiernummer": "provider_reference", "certificaatnummer": "provider_reference",
           "garantie_tot": "guarantee_expires_on", "vervaldatum_garantie": "guarantee_expires_on", "geldig_tot": "guarantee_expires_on"}
HOLDING_ALIASES = {"external": "external", "elders": "external", "depiqo": "depiqo", "depiqo-borgrekening": "depiqo"}
TEXT_FIELDS = ("address", "postcode", "city", "tenant_name", "tenant_email", "external_iban", "provider_name", "provider_reference")
# Longest accepted value per column. Longer is an error on that row (and stored shortened for the preview).
MAX_LEN = {"address": 200, "postcode": 12, "city": 80, "region": 5, "tenant_name": 120, "tenant_email": 254, "rent": 20,
           "amount": 20, "lease_start": 20, "holding": 30, "external_iban": 34, "evidence": 20,
           "provider_kind": 60, "provider_name": providers.MAX_NAME, "provider_reference": providers.MAX_REFERENCE, "guarantee_expires_on": 20}
LABELS = {"address": "Adres", "postcode": "Postcode", "city": "Plaats", "region": "Regio", "tenant_name": "Huurder",
          "tenant_email": "E-mail", "rent": "Huur", "amount": "Borg", "lease_start": "Start huur", "holding": "Waar",
          "external_iban": "IBAN", "evidence": "Bewijs", "provider_kind": "Aanbieder", "provider_name": "Naam aanbieder",
          "provider_reference": "Referentie aanbieder", "guarantee_expires_on": "Garantie tot"}


class ImportProblem(Exception):
    """The whole file is refused (size, encoding, header, too many rows)."""


def template_csv():
    rows = [COLUMNS,
            ("Kerkstraat 1", "1017 GA", "Amsterdam", "NL", "Anna de Boer", "anna@voorbeeld.nl", "1.250,00", "2.500,00", "2023-05-01",
             "external", "NL91ABNA0417164300", "declared", "verhuurder_rekening", "", "", ""),
            ("Meir 10 bus 2", "2000", "Antwerpen", "VL", "Bart Peeters", "bart@voorbeeld.be", "950,00", "2.850,00", "01-09-2024",
             "external", "", "declared", "e-DEPO", "Deposito- en Consignatiekas", "EDP-2024-000123", ""),
            ("Coolsingel 40", "3011 AD", "Rotterdam", "NL", "Chris Smit", "chris@voorbeeld.nl", "1.100,00", "2.200,00", "2025-02-01",
             "external", "", "declared", "garantie", "Garantiefonds C", "GF-2025-0001", "2027-01-31")]
    out = io.StringIO()
    csv.writer(out, delimiter=";", lineterminator="\r\n").writerows(rows)
    return "﻿" + out.getvalue()


def decode(data):
    if len(data) > current_app.config["IMPORT_MAX_BYTES"]:
        raise ImportProblem(f"Het bestand is groter dan {current_app.config['IMPORT_MAX_BYTES'] // (1024 * 1024)} MB.")
    if not data.strip():
        raise ImportProblem("Het bestand is leeg.")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportProblem("Het bestand is geen tekstbestand (CSV).")


def _delimiter(header_line):
    counts = {d: header_line.count(d) for d in (";", ",", "\t")}
    best = max(counts, key=counts.get)
    return best if counts[best] else ";"


def _date(value):
    v = value.strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", v) or None
    try:
        if m:
            return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", v)
        if m:
            return date(int(m[3]), int(m[2]), int(m[1])).isoformat()
    except ValueError:
        return None
    return None


def _clean(value):
    v = (value or "").strip()
    if v.startswith("'") and v[1:2] in ("=", "+", "-", "@"):
        v = v[1:]  # our own export guard, read back
    return v


def parse(data, org_id):
    """Returns a list of rows: dict(line, values, errors, data). Raises ImportProblem for the whole file."""
    text = decode(data)
    lines = text.splitlines()
    if not lines:
        raise ImportProblem("Het bestand is leeg.")
    reader = csv.reader(io.StringIO(text), delimiter=_delimiter(lines[0]))
    try:
        header = next(reader)
    except StopIteration:
        raise ImportProblem("Het bestand is leeg.") from None
    except csv.Error:
        raise ImportProblem("Het bestand kon niet worden gelezen: de kopregel is ongeldig. Gebruik het sjabloon.") from None
    names = []
    for h in header:
        key = h.strip().lower().replace(" ", "_")
        names.append(ALIASES.get(key, key))
    missing = [c for c in REQUIRED if c not in names]
    if missing:
        raise ImportProblem("Deze kolommen ontbreken: " + ", ".join(missing) + ". Gebruik het sjabloon.")
    max_rows = current_app.config["IMPORT_MAX_ROWS"]
    existing = {(r["address"].lower(), r["postcode"].replace(" ", "").upper(), r["email"].lower()) for r in db.all_(
        "SELECT p.address, p.postcode, t.email FROM deposits d JOIN properties p ON p.id = d.property_id JOIN tenants t ON t.id = d.tenant_id "
        "WHERE d.org_id = ? AND d.status NOT IN (?, ?)", (org_id, S.CLOSED, S.CANCELLED))}
    seen = set()
    rows = []
    try:
        for line_no, raw in enumerate(reader, start=2):
            if not any((c or "").strip() for c in raw):
                continue
            if len(rows) >= max_rows:
                raise ImportProblem(f"Het bestand heeft meer dan {max_rows} rijen. Splits het in delen.")
            values = {name: _clean(raw[i]) if i < len(raw) else "" for i, name in enumerate(names) if name in COLUMNS}
            rows.append(_validate_row(line_no, values, existing, seen))
    except csv.Error:
        raise ImportProblem("Het bestand kon niet worden gelezen: een veld is veel te lang of een aanhalingsteken is niet afgesloten. "
                            "Controleer het bestand of gebruik het sjabloon.") from None
    if not rows:
        raise ImportProblem("Het bestand bevat geen rijen onder de kopregel.")
    return rows


def _validate_row(line_no, v, existing, seen):
    errors = []
    for field, limit in MAX_LEN.items():
        if len(v.get(field, "")) > limit:
            errors.append(f"{LABELS[field]}: maximaal {limit} tekens.")
            v[field] = v[field][:limit] + "…"
    for field in TEXT_FIELDS:
        if v.get(field, "")[:1] in ("=", "+", "@"):
            errors.append(f"{LABELS[field]}: formules zijn niet toegestaan.")
    for field in REQUIRED:
        if not v.get(field):
            errors.append(f"{LABELS[field]} ontbreekt.")
    region = v.get("region", "").upper()
    holding = HOLDING_ALIASES.get(v.get("holding", "").lower())
    if v.get("holding") and not holding:
        errors.append("Waar: kies external of depiqo.")
    email = v.get("tenant_email", "").lower()
    if email and not valid_email(email):
        errors.append("E-mail: geen geldig adres.")
    rent = parse_euros(v.get("rent")) if v.get("rent") else None
    amount = parse_euros(v.get("amount")) if v.get("amount") else None
    if v.get("rent") and rent is None:
        errors.append("Huur: geen geldig bedrag.")
    if v.get("amount") and amount is None:
        errors.append("Borg: geen geldig bedrag.")
    lease_start = _date(v.get("lease_start", "")) if v.get("lease_start") else None
    if v.get("lease_start") and not lease_start:
        errors.append("Start huur: gebruik JJJJ-MM-DD of DD-MM-JJJJ.")
    iban = re.sub(r"\s+", "", v.get("external_iban", "")).upper() or None
    if iban and not valid_iban(iban):
        errors.append("IBAN klopt niet.")
    prov, prov_errors = providers.clean_fields({**v, "guarantee_expires_on": _date(v.get("guarantee_expires_on", "")) or v.get("guarantee_expires_on")})
    if v.get("provider_kind") and prov["provider_kind"] is None:
        errors.append("Aanbieder: onbekende soort. Gebruik een code of een Nederlandse naam uit het sjabloon, zoals e_depo of rekening verhuurder.")
        prov_errors = [e for e in prov_errors if "soort aanbieder" not in e]
    errors += [e.replace("Vervaldatum van de garantie: gebruik JJJJ-MM-DD.", "Garantie tot: gebruik JJJJ-MM-DD of DD-MM-JJJJ.") for e in prov_errors]
    evidence = (v.get("evidence") or "declared").lower()
    if evidence != "declared":
        errors.append("Bewijs: via import kan alleen 'declared'. Een hoger niveau zet je per dossier, met bewijs.")
    data = {"address": v.get("address", ""), "postcode": v.get("postcode", ""), "city": v.get("city", ""), "region": region,
            "tenant_name": v.get("tenant_name", ""), "tenant_email": email, "rent_cents": rent or 0, "amount_cents": amount or 0,
            "holding": holding or "", "lease_start": lease_start, "lease_end": None, "external_iban": iban, "existing": True, **prov}
    if not errors:
        errors += services.validate_new(data)
    warnings = providers.warnings_for({**data, "region": region}) if not errors else []
    key = (data["address"].lower(), data["postcode"].replace(" ", "").upper(), email)
    if key in seen:
        errors.append("Deze woning en huurder staan al eerder in het bestand.")
    elif key in existing:
        errors.append("Deze borg staat al in Depiqo.")
    seen.add(key)
    return {"line": line_no, "values": v, "errors": errors, "warnings": warnings, "data": data}


def create_batch(org_id, user_id, filename, data):
    rows = parse(data, org_id)
    errors = sum(1 for r in rows if r["errors"])
    return db.run("INSERT INTO import_batches (org_id, user_id, filename, status, row_count, error_count, rows_json, created_at) "
                  "VALUES (?, ?, ?, 'preview', ?, ?, ?, ?)",
                  (org_id, user_id, (filename or "import.csv")[:120], len(rows), errors, dumps(rows), now_iso()))


def get_batch(batch_id, org_id):
    b = db.one("SELECT * FROM import_batches WHERE id = ? AND org_id = ?", (batch_id, org_id))
    if not b:
        return None, []
    return b, json.loads(b["rows_json"])


def commit_batch(batch, user_id, send_invites=False):
    """Imports every row in one transaction. Refuses when any row has an error.
    External deposits: SECURED with evidence 'declared', activated on the lease start (billing).
    Depiqo deposits: concept (the tenant still has to open the account and pay)."""
    if batch["status"] != "preview":
        raise services.WorkflowError("Deze import is al verwerkt of geannuleerd.")
    rows = parse_stored(batch)
    if any(r["errors"] for r in rows):
        raise services.WorkflowError("Er staan nog fouten in het bestand. Pas het bestand aan en upload het opnieuw.")
    created = []
    with db.transaction():
        claimed = db.get_db().execute("UPDATE import_batches SET status = 'committed', committed_at = ?, send_invites = ? WHERE id = ? AND status = 'preview'",
                                      (now_iso(), 1 if send_invites else 0, batch["id"])).rowcount
        if claimed != 1:
            raise services.WorkflowError("Deze import is al verwerkt.")
        for r in rows:
            data = {**r["data"], "import_batch_id": batch["id"]}
            d = services.create_deposit(batch["org_id"], user_id, data)
            if d["holding"] == "external":
                d = services.transition(
                    d, S.SECURED, "user", "Bestaande borg geïmporteerd; ontvangst verklaard door de beheerder", user_id,
                    extra_sets={"evidence_level": "declared", "evidence_set_at": now_iso(),
                                "security_type": providers.security_type_for(d["provider_kind"]),
                                "asset_value_cents": d["amount_cents"], "eligible_value_cents": None,
                                "activated_at": f"{d['lease_start']}T00:00:00+00:00"})
                services._record_evidence(d, "declared", user_id, f"Import {batch['filename']}", None, False)
            created.append(d)
        db.run("UPDATE import_batches SET imported_count = ? WHERE id = ?", (len(created), batch["id"]))
    invited = 0
    if send_invites:
        for d in created:
            try:
                services.send_invite(services.reload(d), user_id)
                invited += 1
            except services.WorkflowError:
                pass
    return len(created), invited


def parse_stored(batch):
    """Re-validates the stored rows against the current database (another user may have added a deposit since)."""
    rows = json.loads(batch["rows_json"])
    existing = {(r["address"].lower(), r["postcode"].replace(" ", "").upper(), r["email"].lower()) for r in db.all_(
        "SELECT p.address, p.postcode, t.email FROM deposits d JOIN properties p ON p.id = d.property_id JOIN tenants t ON t.id = d.tenant_id "
        "WHERE d.org_id = ? AND d.status NOT IN (?, ?)", (batch["org_id"], S.CLOSED, S.CANCELLED))}
    seen = set()
    return [_validate_row(r["line"], r["values"], existing, seen) for r in rows]
