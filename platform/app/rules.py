"""Regional rules for rental deposits, versioned.

Every deposit stores the rule version it was created under (deposits.rule_version). A rule
change gets a new entry in RULESETS; existing deposits keep the version they started with,
so their maximum amount and their return deadline do not change afterwards. New deposits use
RULE_VERSION. Each region records when its rules were last checked against official sources.
These rules support the workflow; they are not legal advice and must be reviewed by counsel
before live use.
"""
from dataclasses import dataclass
from datetime import date, timedelta

from .util import add_months, eur, parse_date

RULE_VERSION = "2026-10-18"   # version for new deposits


class UnknownRuleVersion(KeyError):
    pass


@dataclass(frozen=True)
class RegionRules:
    code: str
    name: str
    term: str
    max_months: int
    max_months_before_2019: int | None
    rent_basis: str
    statutory_deadline: bool
    interest_owner: str
    release_note: str
    checked_on: str
    sources: tuple
    # Return deadline after the end of the lease. Exactly one of these applies:
    return_days: tuple | None = None      # (without deductions, with deductions)
    return_months: int | None = None      # calendar months after the tenant left
    deadline_note: str = ""


@dataclass(frozen=True)
class RuleSet:
    version: str
    regions: dict
    internal_target_days: int   # used where the law sets no deadline (Flanders); shown as such


RULESETS = {
    "2026-10-18": RuleSet(
        version="2026-10-18",
        internal_target_days=30,
        regions={
            "NL": RegionRules(
                code="NL", name="Nederland", term="waarborgsom", max_months=2, max_months_before_2019=None,
                rent_basis="kale huur (zonder servicekosten)",
                statutory_deadline=True,
                interest_owner="Volgens afspraak; op een Depiqo-borgrekening voor de huurder",
                release_note="Terug binnen 14 dagen na het einde van de huur, of binnen 30 dagen als kosten worden verrekend.",
                checked_on="2026-10-18",
                sources=("https://www.volkshuisvestingnederland.nl/onderwerpen/huren-en-wonen/huurbescherming-en-huurcontracten/waarborgsom",),
                return_days=(14, 30),
            ),
            "VL": RegionRules(
                code="VL", name="Vlaanderen", term="huurwaarborg", max_months=3, max_months_before_2019=2,
                rent_basis="maandhuur",
                statutory_deadline=False,
                interest_owner="Huurder",
                release_note="Vrijgave pas na het einde van de huur, met akkoord van beide partijen of een beslissing van de vrederechter.",
                checked_on="2026-10-18",
                sources=("https://www.vlaanderen.be/huurprijs-en-huurwaarborg/huurwaarborg",),
            ),
            "BRU": RegionRules(
                code="BRU", name="Brussel", term="huurwaarborg", max_months=2, max_months_before_2019=None,
                rent_basis="maandhuur zonder lasten",
                statutory_deadline=True,
                interest_owner="Huurder",
                release_note="Terug binnen 2 maanden nadat de huurder de woning verlaten heeft. Cash is niet toegestaan.",
                checked_on="2026-10-18",
                sources=("https://be.brussels/nl/huisvesting/wijziging-van-de-huurwetgeving-november-2024",),
                return_months=2,
                deadline_note="nadat de huurder de woning verlaten heeft",
            ),
        },
    ),
    # A future version is added here as a new key, e.g. "2027-01-01": RuleSet(...). Never edit an
    # existing version in place: deposits created under it must keep their behaviour.
}

# Current rules, for screens that are not about one existing deposit (new deposit, settings).
REGIONS = RULESETS[RULE_VERSION].regions
INTERNAL_TARGET_DAYS = RULESETS[RULE_VERSION].internal_target_days


def ruleset(version=None):
    version = version or RULE_VERSION
    try:
        return RULESETS[version]
    except KeyError:
        raise UnknownRuleVersion(f"Onbekende regelversie: {version}") from None


def region_rules(region, version=None):
    return ruleset(version).regions[region]


def _version_of(deposit):
    try:
        return deposit["rule_version"]
    except (KeyError, IndexError):
        return None


def for_deposit(deposit):
    """The region rules under which this deposit was created."""
    return region_rules(deposit["region"], _version_of(deposit))


def max_amount_cents(region, rent_cents, lease_start, version=None):
    r = region_rules(region, version)
    months = r.max_months
    start = parse_date(lease_start)
    if r.max_months_before_2019 and start and start < date(2019, 1, 1):
        months = r.max_months_before_2019
    return rent_cents * months, months


def validate_deposit(region, rent_cents, amount_cents, lease_start, lease_end=None, version=None):
    """Returns a list of problems in plain Dutch. Empty list = valid."""
    errors = []
    rs = ruleset(version)
    if region not in rs.regions:
        return ["Kies Nederland, Vlaanderen of Brussel."]
    if not rent_cents or rent_cents <= 0:
        errors.append("Vul de huur in.")
    if not amount_cents or amount_cents <= 0:
        errors.append("Vul het borgbedrag in.")
    start = parse_date(lease_start)
    end = parse_date(lease_end)
    if not start:
        errors.append("Vul de ingangsdatum van het huurcontract in.")
    if start and end and end <= start:
        errors.append("De einddatum moet na de ingangsdatum liggen.")
    if rent_cents and amount_cents and start:
        cap, months = max_amount_cents(region, rent_cents, start, rs.version)
        if amount_cents > cap:
            r = rs.regions[region]
            errors.append(f"In {r.name} is de {r.term} maximaal {months} maanden {r.rent_basis}: {eur(cap)}.")
    return errors


def deadline(deposit, has_deductions):
    """The date by which the deposit must be returned, and whether that date is statutory.

    deposit needs: region, lease_end, move_out_date and (optionally) rule_version.
    Returns (date or None, is_statutory: bool, explanation: str).
    """
    rs = ruleset(_version_of(deposit))
    r = rs.regions[deposit["region"]]
    end = parse_date(deposit["move_out_date"]) or parse_date(deposit["lease_end"])
    if not end:
        return None, False, "Nog geen einddatum bekend."
    if r.statutory_deadline and r.return_days:
        days = r.return_days[1] if has_deductions else r.return_days[0]
        reason = f"{days} dagen bij verrekening" if has_deductions else f"{days} dagen zonder verrekening"
        return end + timedelta(days=days), True, f"Wettelijke termijn: {reason} na het einde van de huur."
    if r.statutory_deadline and r.return_months:
        return add_months(end, r.return_months), True, \
            f"Wettelijke termijn: {r.return_months} maanden {r.deadline_note or 'na het einde van de huur'}."
    return end + timedelta(days=rs.internal_target_days), False, \
        f"Geen wettelijke termijn in {r.name}; intern streefdoel {rs.internal_target_days} dagen na vertrek."


def settlement_allowed(deposit, on_date):
    """Release agreements may only be made after the lease ends (enforced for all regions, required in VL)."""
    end = parse_date(deposit["move_out_date"]) or parse_date(deposit["lease_end"])
    return bool(end) and on_date >= end
