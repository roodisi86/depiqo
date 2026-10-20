"""Provider registry for deposits held elsewhere (holding = 'external').

Depiqo's position: keep your property software and your current providers, and manage every
deposit, wherever it is held, in one place. This module knows the kinds of places where a
deposit can sit, in which regions each kind exists (Depiqo warns, it never blocks), how each
kind maps to the security model, which proof fits which evidence level, and it builds the
"Waar staan je borgen" overview.

Nothing here changes a deposit's status. The evidence rules of 0.3 are unchanged: only
'verified' and 'legal' count as coverage. One addition: money on the landlord's own account is
never legally locked, so 'legal' is refused for provider_kind 'verhuurder_rekening'.
"""
import re
from datetime import timedelta

from . import db
from . import states as S
from .util import date_nl, parse_date, today

BE = ("VL", "BRU")
ALL_REGIONS = ("NL", "VL", "BRU")

# Order is the order on screens.
PROVIDER_KINDS = {
    "verhuurder_rekening": {
        "label": "Rekening van verhuurder of beheerder", "short": "Rekening verhuurder",
        "tenant": "Op een rekening van je verhuurder of beheerder",
        "regions": ALL_REGIONS, "reference_label": "Rekeningnummer of kenmerk",
        "document_proof": "Bankafschrift met de bijschrijving",
        "legal_proof": None,
    },
    "bank_geblokkeerd": {
        "label": "Geblokkeerde rekening bij een bank", "short": "Geblokkeerde rekening",
        "tenant": "Op een geblokkeerde rekening op jouw naam bij een bank",
        "regions": ALL_REGIONS, "reference_label": "Rekeningnummer",
        "document_proof": "Bevestiging van de bank dat de rekening is geopend",
        "legal_proof": "Blokkeringsattest van de bank",
    },
    "e_depo": {
        "label": "e-DEPO (Deposito- en Consignatiekas)", "short": "e-DEPO",
        "tenant": "Bij de Deposito- en Consignatiekas (e-DEPO), een dienst van de overheid",
        "regions": BE, "reference_label": "Dossiernummer",
        "document_proof": "Betalingsbevestiging van e-DEPO",
        "legal_proof": "Bewijs van e-DEPO dat de waarborg er staat",
    },
    "verzekering_tak26": {
        "label": "Kapitalisatiecontract bij verzekeraar (tak 26)", "short": "Verzekeraar (tak 26)",
        "tenant": "In een kapitalisatiecontract op jouw naam bij een verzekeraar",
        "regions": BE, "reference_label": "Contractnummer",
        "document_proof": "Bevestiging van het contract",
        "legal_proof": "Certificaat van de verzekeraar met de inpandgeving",
    },
    "borggarantie": {
        "label": "Garantie of borgstelling door een derde", "short": "Garantie",
        "tenant": "Een derde staat garant. Je hebt geen geld gestort.",
        "regions": ALL_REGIONS, "reference_label": "Certificaatnummer",
        "document_proof": "Kopie van het garantiecertificaat",
        "legal_proof": "Origineel garantiecertificaat ten gunste van de verhuurder",
    },
    "ocmw": {
        "label": "Waarborg via OCMW of lokaal bestuur", "short": "OCMW",
        "tenant": "Via het OCMW of je lokaal bestuur",
        "regions": BE, "reference_label": "Dossiernummer",
        "document_proof": "Brief of beslissing van het OCMW",
        "legal_proof": "Waarborgattest of borgstellingsbrief van het OCMW",
    },
    "anders": {
        "label": "Anders", "short": "Anders",
        "tenant": "Bij een andere partij",
        "regions": ALL_REGIONS, "reference_label": "Referentie",
        "document_proof": "Bewijs van de aanbieder",
        "legal_proof": "Attest dat de borg juridisch geblokkeerd is",
    },
}
KINDS = tuple(PROVIDER_KINDS)
GUARANTEE_KINDS = ("borggarantie", "ocmw")      # a guarantee or a promise to pay: may have an expiry date
NO_TENANT_PAYMENT = ("borggarantie", "ocmw")    # the tenant does not transfer money to anyone
UNKNOWN_LABEL = "Elders, aanbieder onbekend"
EXPIRY_WARN_DAYS = 60
MAX_NAME = 120
MAX_REFERENCE = 60


def label(kind, short=False):
    if kind in PROVIDER_KINDS:
        return PROVIDER_KINDS[kind]["short" if short else "label"]
    return UNKNOWN_LABEL


def security_type_for(kind):
    """The security model of 0.2: a guarantee is a guarantee, everything else is an external account."""
    return "guarantee" if kind == "borggarantie" else "external_account"


def custodian_for(kind, name):
    """Who holds the security. Empty for the landlord's own account (shown as 'verhuurder of beheerder')."""
    if kind == "verhuurder_rekening":
        return None
    return (name or "").strip() or None


def region_warnings(region, kind):
    """Plain-Dutch warnings. They never block: the manager knows the contract, Depiqo only points out the rules."""
    if kind not in PROVIDER_KINDS:
        return []
    out = []
    if region not in PROVIDER_KINDS[kind]["regions"]:
        out.append(f"{label(kind)} bestaat alleen in België. Controleer of dit klopt voor een woning in Nederland.")
    if kind == "verhuurder_rekening" and region in BE:
        text = ("In België moet een huurwaarborg in geld op een geblokkeerde rekening op naam van de huurder staan. "
                "Een rekening van de verhuurder volstaat niet.")
        if region == "BRU":
            text += " In Brussel is een waarborg in contanten ook niet toegestaan."
        out.append(text)
    return out


def guarantee_warnings(deposit_like):
    """A guarantee that ends before the lease does is a risk for the landlord."""
    exp = parse_date(_get(deposit_like, "guarantee_expires_on"))
    end = parse_date(_get(deposit_like, "lease_end"))
    if exp and end and exp < end:
        return [f"De garantie loopt af op {date_nl(exp)}, voor het einde van de huur op {date_nl(end)}."]
    return []


def warnings_for(d):
    """All warnings for one deposit (row or dict)."""
    if _get(d, "holding") != "external":
        return []
    return region_warnings(_get(d, "region"), _get(d, "provider_kind")) + guarantee_warnings(d)


def evidence_hint(kind, level):
    """What proves a given evidence level for this kind of provider (shown on the evidence ladder)."""
    p = PROVIDER_KINDS.get(kind)
    if not p:
        return None
    if level == "document":
        return p["document_proof"]
    if level == "legal":
        return p["legal_proof"] or "Niet mogelijk: geld op een rekening van de verhuurder is niet juridisch geblokkeerd."
    return None


def legal_possible(kind):
    return kind not in PROVIDER_KINDS or PROVIDER_KINDS[kind]["legal_proof"] is not None


# ---------------------------------------------------------------- input

def _norm(value):
    v = (value or "").strip().lower()
    v = re.sub(r"[()]", " ", v)
    v = re.sub(r"[\s_\-]+", " ", v)
    return v.strip()


_ALIASES = {
    "verhuurder_rekening": ("rekening verhuurder", "rekening van verhuurder", "rekening van de verhuurder", "verhuurder",
                            "rekening beheerder", "beheerder", "derdenrekening", "eigen rekening", "landlord"),
    "bank_geblokkeerd": ("geblokkeerde rekening", "geblokkeerde bankrekening", "bank", "bank geblokkeerd", "geblokkeerd",
                         "huurwaarborgrekening", "waarborgrekening", "blocked account"),
    "e_depo": ("edepo", "e depo", "deposito en consignatiekas", "consignatiekas", "dck"),
    "verzekering_tak26": ("tak 26", "tak26", "verzekeraar", "verzekering", "kapitalisatiecontract", "verzekering tak 26",
                          "verzekeraar tak 26"),
    "borggarantie": ("garantie", "borgstelling", "bankgarantie", "huurgarantie", "waarborggarantie", "guarantee"),
    "ocmw": ("ocmw", "cpas", "lokaal bestuur", "waarborg via ocmw", "ocmw waarborg"),
    "anders": ("overig", "andere", "ander", "other"),
}
_LOOKUP = {}
for _kind, _p in PROVIDER_KINDS.items():
    for _alias in (_kind, _p["label"], _p["short"], *_ALIASES.get(_kind, ())):
        _LOOKUP[_norm(_alias)] = _kind


def parse_kind(value):
    """Code, Dutch label or a common Dutch name -> kind code. '' -> None. Unknown -> False."""
    if not (value or "").strip():
        return None
    return _LOOKUP.get(_norm(value), False)


def clean_fields(form, region=None):
    """Reads provider fields from a form or dict. Returns (fields, errors). Dates as ISO strings."""
    errors = []
    raw_kind = form.get("provider_kind") or ""
    kind = parse_kind(raw_kind)
    if kind is False:
        errors.append("Kies een geldige soort aanbieder.")
        kind = None
    name = " ".join((form.get("provider_name") or "").split())
    ref = " ".join((form.get("provider_reference") or "").split())
    if len(name) > MAX_NAME:
        errors.append(f"Naam van de aanbieder: maximaal {MAX_NAME} tekens.")
    if len(ref) > MAX_REFERENCE:
        errors.append(f"Referentie bij de aanbieder: maximaal {MAX_REFERENCE} tekens.")
    for value in (name, ref):
        if value[:1] in ("=", "+", "@"):
            errors.append("Formules zijn niet toegestaan in de gegevens van de aanbieder.")
            break
    exp_raw = (form.get("guarantee_expires_on") or "").strip()
    exp = None
    if exp_raw:
        try:
            exp = parse_date(exp_raw)
        except ValueError:
            exp = None
        if not exp:
            errors.append("Vervaldatum van de garantie: gebruik JJJJ-MM-DD.")
    return {"provider_kind": kind, "provider_name": name[:MAX_NAME] or None, "provider_reference": ref[:MAX_REFERENCE] or None,
            "guarantee_expires_on": exp.isoformat() if exp else None}, errors


def validate(data):
    """Checks on the provider fields of a new or edited deposit. Returns a list of problems."""
    errors = []
    kind = data.get("provider_kind")
    if kind and kind not in PROVIDER_KINDS:
        errors.append("Kies een geldige soort aanbieder.")
    if data.get("holding") != "external" and (kind or data.get("provider_name") or data.get("provider_reference")
                                               or data.get("guarantee_expires_on")):
        errors.append("Een aanbieder vul je alleen in bij een borg die elders staat.")
    exp = data.get("guarantee_expires_on")
    if exp:
        if kind not in GUARANTEE_KINDS:
            errors.append("Een vervaldatum vul je alleen in bij een garantie of een waarborg via het OCMW.")
        start = parse_date(data.get("lease_start"))
        if start and parse_date(exp) <= start:
            errors.append("De garantie moet langer lopen dan de start van de huur.")
    return errors


def needs_iban(kind):
    """The tenant transfers money to an account the landlord knows: the landlord's own account, or not known yet."""
    return kind in (None, "", "verhuurder_rekening")


# ---------------------------------------------------------------- read models

def expiry_info(d, on=None):
    """(days_left, date) for a guarantee with an expiry date on a dossier that still runs, else None."""
    exp = parse_date(_get(d, "guarantee_expires_on"))
    if not exp or _get(d, "status") in (S.CLOSED, S.CANCELLED, S.CONCEPT):
        return None
    return (exp - (on or today())).days, exp


def overview(org_id):
    """'Waar staan je borgen': per place, the number of running dossiers, the total obligation and how many
    are only declared by the manager. Running = the statuses counted as active on the dashboard."""
    statuses = tuple(S.ACTIVE)
    ph = ",".join("?" * len(statuses))
    rows = db.all_(
        f"SELECT holding, provider_kind, COUNT(*) AS n, COALESCE(SUM(amount_cents), 0) AS total, "
        f"SUM(CASE WHEN evidence_level = 'declared' THEN 1 ELSE 0 END) AS declared "
        f"FROM deposits WHERE org_id = ? AND status IN ({ph}) GROUP BY holding, provider_kind", (org_id, *statuses))
    by_key = {}
    for r in rows:
        key = "depiqo" if r["holding"] == "depiqo" else (r["provider_kind"] or "onbekend")
        item = by_key.setdefault(key, {"n": 0, "total": 0, "declared": 0})
        item["n"] += r["n"]
        item["total"] += r["total"]
        item["declared"] += r["declared"] or 0
    out = []
    for key in ("depiqo", *KINDS, "onbekend"):
        if key not in by_key:
            continue
        lbl = "Depiqo-borgrekening" if key == "depiqo" else ("Aanbieder onbekend" if key == "onbekend" else label(key, short=True))
        full = "Depiqo-borgrekening bij de partnerbank" if key == "depiqo" else (UNKNOWN_LABEL if key == "onbekend" else label(key))
        out.append({"key": key, "label": lbl, "full": full, **by_key[key], "declared": None if key == "depiqo" else by_key[key]["declared"]})
    totals = {"n": sum(r["n"] for r in out), "total": sum(r["total"] for r in out),
              "declared": sum(r["declared"] or 0 for r in out)}
    cutoff = (today() + timedelta(days=EXPIRY_WARN_DAYS)).isoformat()
    totals["expiring"] = db.scalar(
        f"SELECT COUNT(*) FROM deposits WHERE org_id = ? AND holding = 'external' AND guarantee_expires_on IS NOT NULL "
        f"AND guarantee_expires_on <= ? AND status IN ({ph})", (org_id, cutoff, *statuses))
    return out, totals


def _get(row, key):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None
