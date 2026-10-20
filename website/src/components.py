"""Reusable building blocks: icons, product mocks, pricing, FAQ and forms."""
from html import escape

from layout import REGIONS, mark

# ---------------------------------------------------------------- icons (24px stroke, currentColor)
_I = {
    "shield": '<path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z"/><path d="M9 12l2 2 4-4"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "doc": '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4M10 12h5M10 16h5"/>',
    "bank": '<path d="M4 10l8-5 8 5M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3.5 20h17"/>',
    "users": '<circle cx="9" cy="8.5" r="3"/><path d="M3.5 19c.6-3 2.8-4.8 5.5-4.8s4.9 1.8 5.5 4.8"/><circle cx="17" cy="9.5" r="2.4"/><path d="M15.5 14.4c2.3.1 4.2 1.7 4.8 4.6"/>',
    "chart": '<path d="M4 20V4M4 20h16"/><path d="M8 16v-4M12 16V8M16 16v-6"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="M11 12l8-8M16 7l2 2M14 9l2 2"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "coins": '<ellipse cx="12" cy="7" rx="7" ry="3"/><path d="M5 7v5c0 1.7 3.1 3 7 3s7-1.3 7-3V7"/><path d="M5 12v5c0 1.7 3.1 3 7 3s7-1.3 7-3v-5"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "home": '<path d="M4 11l8-6 8 6v9H4z"/><path d="M10 20v-5h4v5"/>',
    "scale": '<path d="M12 4v16M6 20h12M5 8h14"/><path d="M5 8l-2.5 6a3 3 0 0 0 5 0L5 8zM19 8l-2.5 6a3 3 0 0 0 5 0L19 8z"/>',
    "phone": '<rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 18h2"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
    "code": '<path d="M9 8l-4 4 4 4M15 8l4 4-4 4"/>',
    "umbrella": '<path d="M3 12a9 9 0 0 1 18 0z"/><path d="M12 12v6a2 2 0 0 0 4 0"/>',
    "spark": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M18 6l-2.5 2.5M8.5 15.5L6 18"/>',
}


def icon(name):
    return (f'<span class="icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{_I[name]}</svg></span>')


# ---------------------------------------------------------------- product mocks (fictitious data)

def wallet_float(region, amount="€ 2.400,00"):
    t = REGIONS[region]
    status = "Zekerheid bevestigd" if region == "be" else "Borg veilig gesteld"
    return f"""<div class="float-card wallet-card" aria-hidden="true">
  <div class="w-top"><span class="brand">{mark()}depiqo</span><span>Jouw {t['term']}</span></div>
  <strong>{amount}</strong>
  <span class="badge b-ok">{status}</span>
  <div class="w-line"><span>Staat bij</span><b>Partnerbank, op jouw naam</b></div>
  <div class="w-line"><span>Rente</span><b>Voor jou, via de bank</b></div>
</div>"""


def task_float(region):
    if region == "nl":
        return """<div class="float-card task-card" aria-hidden="true"><span class="tick">✓</span><div><b>Storting bevestigd door de bank</b><span>Kerkstraat 12-2 · zojuist</span></div></div>"""
    return """<div class="float-card task-card" aria-hidden="true"><span class="tick">✓</span><div><b>Waarborg geblokkeerd door de bank</b><span>Meir 38 bus 3 · zojuist</span></div></div>"""


def dashboard_mock(region, title="Depiqo Business · overzicht"):
    if region == "nl":
        rows = [("Kerkstraat 12-2", "€ 2.400", '<span class="badge b-ok">Veilig gesteld</span>', "—"),
                ("Laan v. Meerdervoort 88", "€ 3.100", '<span class="badge b-wait">Wacht op storting</span>', "herinnerd"),
                ("Oudegracht 140", "€ 1.950", '<span class="badge b-info">Afrekening voorgesteld</span>', "nog 9 dagen"),
                ("Vondelstraat 7-H", "€ 4.200", '<span class="badge b-alert">Betwist</span>', "nog 3 dagen")]
        k = [("312", "Actieve borgen"), ("7", "Wachten op storting"), ("4", "Termijn binnen 7 dagen")]
        dh = "Termijn"
    else:
        rows = [("Kortrijksesteenweg 214", "€ 2.550", '<span class="badge b-ok">Zekerheid bevestigd</span>', "—"),
                ("Rue Haute 51", "€ 1.900", '<span class="badge b-wait">Wacht op storting</span>', "herinnerd"),
                ("Meir 38 bus 3", "€ 3.300", '<span class="badge b-info">Akkoord gevraagd</span>', "huurder"),
                ("Elsensesteenweg 12", "€ 2.100", '<span class="badge b-alert">Vrijgave vraagt actie</span>', "dag 54")]
        k = [("284", "Actieve waarborgen"), ("6", "Wachten op storting"), ("3", "Vrijgave vraagt actie")]
        dh = "Actie"
    trs = "".join(f"<tr><td>{a}</td><td class=\"num\">{b}</td><td>{s}</td><td>{d}</td></tr>" for a, b, s, d in rows)
    kp = "".join(f'<div class="kpi"><b>{a}</b><span>{b}</span></div>' for a, b in k)
    return f"""<div class="app-window" role="img" aria-label="Voorbeeld van het overzicht in Depiqo Business met fictieve dossiers">
  <div class="app-bar"><span class="dots" aria-hidden="true"><span></span><span></span><span></span></span>{title}</div>
  <div class="app-body">
    <div class="kpis">{kp}</div>
    <div class="table-scroll"><table class="table"><thead><tr><th>Adres</th><th>Bedrag</th><th>Status</th><th>{dh}</th></tr></thead><tbody>{trs}</tbody></table></div>
  </div>
</div>"""


def phone_mock(region, compact=False):
    t = REGIONS[region]
    end = t["end"]
    nl = region == "nl"
    status = "Borg veilig gesteld" if nl else "Zekerheid bevestigd"
    extra = "" if compact else f"""
    <div class="row-card"><span>Rente tot nu toe</span><b>€ 14,20 · voorbeeld</b></div>
    <div class="row-card"><span>Documenten</span><b>Contract, plaatsbeschrijving</b></div>"""
    return f"""<div class="phone" role="img" aria-label="Voorbeeld van de Depiqo-wallet voor huurders, met fictieve gegevens">
  <div class="phone-head"><small>Jouw {t['term']}</small><strong>€ 2.400,00</strong><span class="badge b-ok">{status}</span></div>
  <div class="phone-body">
    <div class="row-card"><span>Woning</span><b>{'Kerkstraat 12-2' if nl else 'Meir 38 bus 3'}</b></div>
    <div class="row-card"><span>Staat bij</span><b>Partnerbank, op jouw naam</b></div>{extra}
    <ul class="steps-mini" aria-label="Voortgang"><li class="done"><i></i>Uitnodiging gecontroleerd</li><li class="done"><i></i>{'Storting bevestigd door de bank' if nl else 'Waarborg geblokkeerd door de bank'}</li><li class="now"><i></i>Huur loopt</li><li><i></i>{end.capitalize()}</li></ul>
  </div>
</div>"""


def invest_mock(region):
    t = REGIONS[region]
    return f"""<div class="phone" role="img" aria-label="Voorbeeld van Depiqo Invest in de wallet, met fictieve bedragen">
  <div class="phone-head"><small>Depiqo Invest · naast je {t['term']}</small><strong>€ 1.268,40</strong><span class="badge b-ok">+ € 68,40 sinds start</span></div>
  <div class="phone-body">
    <div class="row-card"><span>Portefeuille</span><b>Neutraal · 50% aandelen</b></div>
    <div class="row-card"><span>Ingelegd</span><b>€ 1.200,00</b></div>
    <div class="row-card"><span>Kosten per jaar</span><b>0,25% + fondskosten</b></div>
    <div class="row-card"><span>Je borg</span><b>Apart, op de borgrekening</b></div>
    <p class="small muted">Bij de vergunde beleggingspartner. De waarde kan dalen.</p>
  </div>
</div>"""


def settlement_mock(region):
    nl = region == "nl"
    T = REGIONS[region]["Term"]
    return f"""<div class="app-window" role="img" aria-label="Voorbeeld van een eindafrekening met fictieve bedragen">
  <div class="app-bar"><span class="dots" aria-hidden="true"><span></span><span></span><span></span></span>Eindafrekening · {'Oudegracht 140' if nl else 'Meir 38 bus 3'}</div>
  <div class="app-body">
    <div class="table-scroll"><table class="table"><tbody>
      <tr><td>{T}</td><td class="num">€ 1.950,00</td></tr>
      <tr><td>Schade deur badkamer (foto's, offerte)</td><td class="num">− € 185,00</td></tr>
      <tr><td>Achterstallige servicekosten</td><td class="num">− € 60,00</td></tr>
      <tr><td><b>Terug naar de huurder</b></td><td class="num"><b>€ 1.705,00</b></td></tr>
    </tbody></table></div>
    <div class="row"><span class="badge b-ok">Verhuurder akkoord</span><span class="badge b-wait">Huurder: nog niet gereageerd</span></div>
    <p class="small muted">{'Met verrekening: uiterlijk 30 dagen na het einde van de huur terugbetalen.' if nl else 'De vrijgave gebeurt na akkoord van beide partijen. Bij betwisting beslist de vrederechter, niet Depiqo.'}</p>
  </div>
</div>"""


INVEST_FEE = "0,25%"

# ---------------------------------------------------------------- pricing (single source of truth)
PLANS = [
    {"key": "essential", "name": "Essential", "base": 99, "included": 100, "ext": "0,75", "dpq": "0,40", "new": "5",
     "for": "Voor makelaars en kleinere beheerders, tot een paar honderd huurwoningen.",
     "features": ["Borgverzoeken, statussen en herinneringen", "Termijnbewaking per land en gewest", "Eindafrekening, akkoord en geschil", "Huurderswallet inbegrepen", "Export naar je boekhouding"]},
    {"key": "professional", "name": "Professional", "base": 299, "included": 500, "ext": "0,45", "dpq": "0,25", "new": "3",
     "for": "Voor vastgoedbeheerders met grotere portefeuilles en meerdere teams.", "featured": True,
     "features": ["Alles uit Essential", "Teamrollen en vier-ogenprincipe bij uitbetaling", "Rapportages en audittrail per pand", "Bulkacties en import van bestaande borgen", "Geselecteerde integraties met beheersoftware"]},
    {"key": "enterprise", "name": "Enterprise", "base": None,
     "for": "Voor woningcorporaties, institutionele verhuurders en softwarepartners.",
     "features": ["Prijs op basis van volume en integratie", "API en white-label", "Migratie van bestaande borgportefeuilles", "SLA, eigen onboarding en support", "Afspraken over gegevensverwerking"]},
]


def plans_html(ctx, region, link_demo, compact=False):
    t = REGIONS[region]
    cards = ""
    for p in PLANS:
        feat = "".join(f"<li>{f}</li>" for f in p["features"][: 3 if compact else 5])
        ribbon = '<span class="ribbon">Aanbevolen voor beheerders</span>' if p.get("featured") else ""
        if p["base"] is not None:
            price = f'<div class="price"><b>€ {p["base"]}</b><span>per maand, excl. btw</span></div>'
            rows = (f'<div class="price-rows"><div><span>Actieve dossiers inbegrepen</span><b>{p["included"]}</b></div>'
                    f'<div><span>Extra dossier, borg elders</span><b>€ {p["ext"]} p/m</b></div>'
                    f'<div><span>Extra dossier, Depiqo-borgrekening</span><b>€ {p["dpq"]} p/m</b></div>'
                    f'<div><span>Per nieuw dossier</span><b>€ {p["new"]} eenmalig</b></div></div>')
            btn = f'<a class="btn {"btn-primary" if p.get("featured") else "btn-secondary"}" href="{link_demo}">Plan een demo</a>'
        else:
            price = '<div class="price"><b>Op maat</b></div>'
            rows = '<div class="price-rows"><div><span>Vanaf</span><b>ca. 2.500 dossiers</b></div><div><span>Integratie en API</span><b>inbegrepen</b></div><div><span>Contract</span><b>jaarlijks</b></div></div>'
            btn = f'<a class="btn btn-secondary" href="{link_demo}">Vraag een offerte aan</a>'
        cards += (f'<div class="plan{" featured" if p.get("featured") else ""}">{ribbon}<h3>{p["name"]}</h3><p class="for">{p["for"]}</p>'
                  f'{price}{rows}<ul class="checks">{feat}</ul>{btn}</div>')
    tenant = f"""<div class="tenant-band">
  <div class="price"><b>€ 0</b><span>voor huurders</span></div>
  <p><b>Huurders betalen niets</b> voor hun {t['term']} via Depiqo. Rente op een Depiqo-borgrekening is voor de huurder. Kiest een huurder zelf voor Depiqo Invest, beleggen naast de borg, dan betaalt hij 0,25% per jaar plus de fondskosten, en ziet hij dat vooraf.</p>
  <span class="badge b-ok">Altijd gratis</span>
</div>"""
    return f'<div class="plans">{cards}</div>{tenant}'


# ---------------------------------------------------------------- FAQ

def faq_html(qas):
    return '<div class="faq">' + "".join(f"<details><summary>{q}</summary><p>{a}</p></details>" for q, a in qas) + "</div>"


# ---------------------------------------------------------------- forms
# One form per contact flow, so leads arrive with the right label and follow-up.
FORM_KINDS = {
    "demo": {"name": "demo-aanvraag", "button": "Plan een demo", "title": "Plan een demo van 30 minuten"},
    "verhuurder": {"name": "verhuurder-aanvraag", "button": "Vraag toegang aan", "title": "Gebruik Depiqo als verhuurder"},
    "partner": {"name": "partner-aanvraag", "button": "Plan een gesprek", "title": "Bespreek een partnership"},
}


def _field(pid, label, name, kind="text", required=True, error="", full=False, auto="", options=None, hint=""):
    req = f' data-required data-error="{escape(error)}"' if required else ""
    a = f' autocomplete="{auto}"' if auto else ""
    if options is not None:
        opts = "".join(f'<option value="{escape(v)}"{" selected" if sel else ""}>{escape(lbl)}</option>' for v, lbl, sel in options)
        ctl = f'<select id="{pid}" name="{name}"{req}>{opts}</select>'
    elif kind == "textarea":
        ctl = f'<textarea id="{pid}" name="{name}"{req}></textarea>'
    else:
        ctl = f'<input id="{pid}" name="{name}" type="{kind}"{a}{req}>'
    h = f'<span class="hint">{hint}</span>' if hint else ""
    err = f'<span class="error" id="{pid}-err"></span>' if required else ""
    return f'<div class="field{" full" if full else ""}"><label for="{pid}">{label}{"" if required else " (optioneel)"}</label><div class="input-wrap">{ctl}</div>{h}{err}</div>'


def lead_form(region, key, kind="demo", audience="vastgoedbeheerder", partner_type=""):
    k = FORM_KINDS[kind]
    p = f"f-{key}"
    nl = region == "nl"
    regio_opts = [("", "Kies", False), ("Nederland", "Nederland", nl), ("Vlaanderen", "Vlaanderen", not nl), ("Brussel", "Brussel", False), ("Meerdere", "Meerdere", False)]
    hidden = (f'<input type="hidden" name="form-name" value="{k["name"]}">'
              f'<input type="hidden" name="doelgroep" value="{escape(audience)}">'
              f'<input type="hidden" name="regio-site" value="{region}">')
    if partner_type:
        hidden += f'<input type="hidden" name="partnertype" value="{escape(partner_type)}">'
    fields = _field(f"{p}-name", "Voor- en achternaam", "naam", error="Vul je naam in.", auto="name")
    if kind == "demo":
        fields += _field(f"{p}-company", "Organisatie", "organisatie", error="Vul de naam van je organisatie in.", auto="organization")
        fields += _field(f"{p}-email", "Zakelijk e-mailadres", "email", "email", error=f"Vul een geldig e-mailadres in, zoals naam@bedrijf.{'nl' if nl else 'be'}.", full=True, auto="email")
        fields += _field(f"{p}-units", "Huurwoningen in beheer", "woningen", error="Kies een aantal.",
                         options=[("", "Kies", False), ("minder dan 100", "minder dan 100", False), ("100 tot 500", "100 tot 500", False), ("500 tot 2.500", "500 tot 2.500", False), ("meer dan 2.500", "meer dan 2.500", False)])
        fields += _field(f"{p}-region", "Land of gewest", "regio", error="Kies een land of gewest.", options=regio_opts)
        fields += _field(f"{p}-system", "Huidige beheersoftware", "systeem", required=False, full=True)
    elif kind == "verhuurder":
        fields += _field(f"{p}-email", "E-mailadres", "email", "email", error="Vul een geldig e-mailadres in.", auto="email")
        fields += _field(f"{p}-units", "Aantal huurwoningen", "woningen", error="Kies een aantal.",
                         options=[("", "Kies", False), ("1", "1", False), ("2 tot 5", "2 tot 5", False), ("6 tot 20", "6 tot 20", False), ("meer dan 20", "meer dan 20", False)])
        fields += _field(f"{p}-region", "Land of gewest", "regio", error="Kies een land of gewest.", options=regio_opts)
        fields += _field(f"{p}-msg", "Je vraag", "vraag", "textarea", required=False, full=True)
    else:
        fields += _field(f"{p}-company", "Organisatie", "organisatie", error="Vul de naam van je organisatie in.", auto="organization")
        fields += _field(f"{p}-email", "Zakelijk e-mailadres", "email", "email", error="Vul een geldig e-mailadres in.", auto="email")
        fields += _field(f"{p}-role", "Functie", "functie", required=False, auto="organization-title")
        fields += _field(f"{p}-msg", "Waar wil je het over hebben?", "bericht", "textarea", required=False, full=True)
    consent = (f'<div class="full"><label class="consent" for="{p}-consent"><input type="checkbox" id="{p}-consent" name="toestemming" value="ja" data-required data-error="Geef toestemming zodat we contact kunnen opnemen.">'
               f'Depiqo mag mijn gegevens gebruiken om contact met mij op te nemen over deze aanvraag. Ik kan dit altijd intrekken.</label><span class="error" id="{p}-consent-err"></span></div>')
    return f"""<form class="form" name="{k['name']}" method="POST" data-netlify="true" netlify-honeypot="bot-field" data-lead novalidate>
  <h3>{k['title']}</h3>
  {hidden}<p class="hp"><label>Laat dit leeg <input name="bot-field" tabindex="-1" autocomplete="off"></label></p>
  {fields}{consent}
  <div class="full"><button class="btn btn-primary" type="submit">{k['button']}</button></div>
  <p class="form-status" role="status" hidden></p>
</form>"""
