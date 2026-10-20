"""Producten, Prijzen, Hoe het werkt and Pilot pages."""
import json

from components import (PLANS, invest_mock, dashboard_mock, faq_html, icon, lead_form, phone_mock, plans_html, settlement_mock)
from layout import AUD, CHECKED_NL, PAGES, REGIONS, photo


def _crumbs(ctx, region, label):
    return (f'<nav class="crumbs" aria-label="Kruimelpad"><ol><li><a href="{ctx.link(PAGES["home"][region])}">Depiqo</a></li>'
            f'<li aria-current="page">{label}</li></ol></nav>')


# ---------------------------------------------------------------- Prijzen

PRICE_FAQ = [
    ("Wat is een actief dossier?", "Een borg vanaf het moment dat de uitnodiging naar de huurder gaat, tot het dossier is gesloten. Concepten en geannuleerde dossiers tellen niet mee."),
    ("Wat is een nieuw dossier?", "Een dossier waarvan de uitnodiging in die maand is verstuurd. De eenmalige vergoeding dekt de onboarding: uitnodiging, identiteitscontrole en het openen van het dossier."),
    ("Waarom is een Depiqo-borgrekening goedkoper?", "Omdat de bank de storting en blokkering bevestigt en er minder handwerk is voor jouw team en voor ons. En omdat de huurder er rente op krijgt; dat willen we stimuleren."),
    ("Welke dossiers vallen onder de inbegrepen aantallen?", "Eerst de dossiers waarvan de borg elders staat, omdat die per stuk duurder zijn. Zo betaal je altijd het laagste bedrag."),
    ("Betalen huurders iets?", "Nee. Huurders betalen nooit voor hun borg via Depiqo. Kiest een huurder later zelf voor een extra dienst, zoals beleggen naast de borg, dan ziet hij de kosten vooraf."),
    ("Hoe verdient Depiqo geld?", "Met het abonnement van beheerders en makelaars. Daarnaast kan een partnerbank Depiqo een vergoeding betalen per rekening. We rekenen in onze plannen niet op die vergoeding, en we verdienen nooit aan de borg van de huurder zelf."),
]


def prijzen(ctx, region):
    t = REGIONS[region]
    L = ctx.link
    demo = L(PAGES["home"][region] + "#demo")
    data = json.dumps([{k: p[k] for k in ("key", "name", "base", "included", "ext", "dpq", "new")} for p in PLANS if p["base"]]).replace('"', "&quot;")
    compare_rows = [
        ("Actieve dossiers inbegrepen", "100", "500", "Op maat"),
        ("Borgverzoeken, statussen en herinneringen", "✓", "✓", "✓"),
        ("Termijnbewaking per land en gewest", "✓", "✓", "✓"),
        ("Eindafrekening, akkoord en geschil", "✓", "✓", "✓"),
        ("Huurderswallet", "✓", "✓", "✓, ook white-label"),
        ("Teamrollen en vier-ogenprincipe", "Basis", "✓", "✓"),
        ("Rapportages per pand en entiteit", "—", "✓", "✓"),
        ("Bulkimport bestaande borgen", "—", "✓", "✓, met begeleiding"),
        ("Integratie met beheersoftware", "Export", "Geselecteerd", "API en webhooks"),
        ("Support", "E-mail", "E-mail en telefoon", "Vaste contactpersoon, SLA"),
    ]
    trs = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d in compare_rows)
    return f"""
<section class="page-hero" aria-labelledby="ph-t">
  <div class="wrap copy">
    {_crumbs(ctx, region, "Prijzen")}
    <p class="eyebrow">Prijzen</p>
    <h1 id="ph-t">Een helder abonnement. <span class="serif">Gratis voor huurders.</span></h1>
    <p class="lede">Je betaalt per maand voor het platform, met een vast aantal actieve dossiers inbegrepen. Staat de {t['term']} op een Depiqo-borgrekening, dan kost een extra dossier minder. Geen opstartkosten en geen kosten tijdens de pilot.</p>
  </div>
</section>

<section class="section tone-off" aria-label="Abonnementen">
  <div class="wrap">
    {plans_html(ctx, region, demo)}
    <p class="fineprint">Alle prijzen excl. btw. Introductietarief, geldig voor organisaties die in de pilotfase starten. Externe kosten van de partnerbank zijn voor rekening van Depiqo, niet van de huurder.</p>
  </div>
</section>

<section class="section tone-white" id="rekentool" aria-labelledby="calc-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Rekentool</p><h2 id="calc-t">Wat kost Depiqo voor jouw portefeuille?</h2><p>Vul je aantallen in. We rekenen beide abonnementen uit en tonen het voordeligste.</p></div>
    <div class="calc">
      <form class="calc-fields" data-price-calc data-plans="{data}" onsubmit="return false" aria-label="Rekentool prijzen">
        <div class="field full"><label for="p-active">Actieve {t['terms']}</label><div class="input-wrap"><input id="p-active" inputmode="numeric" value="900"><span>dossiers</span></div></div>
        <div class="field"><label for="p-share">Op een Depiqo-borgrekening</label><div class="input-wrap"><input id="p-share" inputmode="numeric" value="60"><span>%</span></div><span class="hint">De rest staat elders, bijvoorbeeld {'bij jullie zelf' if region == 'nl' else 'bij je bank of e-DEPO'}</span></div>
        <div class="field"><label for="p-new">Nieuwe dossiers per maand</label><div class="input-wrap"><input id="p-new" inputmode="numeric" value="30"><span>per maand</span></div></div>
      </form>
      <div class="result" aria-live="polite">
        <div class="line" data-plan-line="essential"><span>Essential</span><b id="p-essential">€ 660</b></div>
        <div class="line" data-plan-line="professional"><span>Professional</span><b id="p-professional">€ 489</b></div>
        <div><span class="small">Voordeligste abonnement per maand, excl. btw</span><div class="big" id="p-best">€ 489</div></div>
        <div class="line"><span>Gemiddeld per actief dossier</span><b id="p-per">€ 0,54</b></div>
        <small id="p-explain">Professional: € 299 basis, 500 dossiers inbegrepen (eerst de dossiers elders), 400 extra op een Depiqo-borgrekening à € 0,25 en 30 nieuwe dossiers à € 3.</small>
      </div>
    </div>
  </div>
</section>

<section class="section tone-off" id="enterprise" aria-labelledby="cmp-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Vergelijken</p><h2 id="cmp-t">Wat zit in welk abonnement?</h2></div>
    <div class="table-scroll"><table class="status-table"><thead><tr><th>Functie</th><th>Essential</th><th>Professional</th><th>Enterprise</th></tr></thead><tbody>{trs}</tbody></table></div>
    <p class="fineprint">Enterprise is voor woningcorporaties, institutionele verhuurders en softwarepartners, vanaf ongeveer 2.500 dossiers. <a href="{L(AUD['institutioneel'][region]['path'])}">Meer over Enterprise</a></p>
  </div>
</section>

<section class="section tone-white" aria-labelledby="faq-t">
  <div class="wrap split wide-right top">
    <div class="split-copy"><p class="eyebrow">Veelgestelde vragen</p><h2 id="faq-t">Over prijzen en hoe Depiqo verdient.</h2><p>We vinden dat je moet weten waar ons geld vandaan komt, zeker bij een product dat over jouw geld gaat.</p></div>
    {faq_html(PRICE_FAQ)}
  </div>
</section>

<section class="section tone-sand" id="aanvraag" aria-labelledby="cta-t">
  <div class="wrap demo-band">
    <div class="split-copy"><p class="eyebrow">Persoonlijke businesscase</p><h2 id="cta-t">Reken het samen met ons door.</h2><p>We maken een businesscase met jouw aantallen: tijd, kosten en wat huurders aan rente krijgen.</p></div>
    {lead_form(region, "prijzen", "demo", "prijzen")}
  </div>
</section>
"""


# ---------------------------------------------------------------- Producten

def producten(ctx, region):
    t = REGIONS[region]
    L = ctx.link
    products = [
        ("Depiqo Business", "b-live", "Nu in prototype", "Voor beheerders en makelaars",
         f"Het platform voor alle {t['terms']}: borgverzoeken, termijnbewaking, eindafrekening, teamrollen, audittrail en facturatie.",
         dashboard_mock(region), AUD["beheerders"][region]["path"]),
        ("Depiqo Wallet", "b-live", "Nu in prototype", "Voor huurders, gratis",
         f"De huurder controleert de uitnodiging, bevestigt zijn identiteit, ziet zijn {t['term']} en rente, en reageert op de afrekening.",
         f'<div class="center-mock">{phone_mock(region)}</div>', AUD["huurders"][region]["path"]),
        ("Depiqo-borgrekening", "b-launch", "Bij lancering", "Via een gereguleerde partnerbank",
         f"Een rekening op naam van de huurder, geblokkeerd ten gunste van de verhuurder. De rente is voor de huurder. Vrijgave via Depiqo, na akkoord of vonnis.",
         settlement_mock(region), AUD["banken"][region]["path"]),
        ("Depiqo Invest", "b-launch", "In testversie", "Voor huurders, vrijwillig",
         f"Beleggen met eigen geld, naast de {t['term']}. Kennistoets, drie portefeuilles, kosten vooraf, waarde en resultaat in de wallet, en de keuze om de terugbetaalde borg door te beleggen. Orders en bewaring bij een vergunde beleggingspartner. Live zodra die partner is aangesloten.",
         f'<div class="center-mock">{invest_mock(region)}</div>', AUD["beleggen"][region]["path"]),
    ]
    rows = ""
    for i, (name, badge, status, who, text, visual, link) in enumerate(products):
        rows += f"""<section class="section {'tone-white' if i % 2 == 0 else 'tone-off'}" aria-labelledby="p{i}">
  <div class="wrap split{' wide-right' if i % 2 == 0 else ''}">
    <div class="split-copy"><div class="row"><span class="badge {badge}">{status}</span><span class="small muted">{who}</span></div><h2 id="p{i}">{name}</h2><p>{text}</p><a class="link-arrow" href="{L(link)}">Meer hierover</a></div>
    <div class="reveal">{visual}<p class="demo-note">Voorbeeld met fictieve gegevens</p></div>
  </div>
</section>"""
    later = [
        ("code", "Depiqo API", "b-launch", "Gepland", "REST-API en ondertekende webhooks voor beheersoftware. In de pilot: export en gerichte koppelingen.", AUD["software"][region]["path"]),
        ("umbrella", "Borggaranties", "b-future", "Onderzoek", "Een alternatief voor een storting, met een verzekeraar die het risico draagt. Alleen met een vergunde partner.", AUD["verzekeraars"][region]["path"]),
    ]
    cards = "".join(f'<div class="opt{" future" if b == "b-future" else ""} reveal"><div class="row">{icon(ic)}<span class="badge {b}">{s}</span></div><h3>{n}</h3><p>{p}</p><a class="link-arrow" href="{L(link)}">Lees meer</a></div>'
                    for ic, n, b, s, p, link in later)
    status_rows = [
        ("Borgverzoeken, statussen, termijnen", "Prototype", "Werkt met testdossiers"),
        ("Eindafrekening, akkoord en geschil", "Prototype", "Werkt met testdossiers"),
        ("Huurderswallet", "Prototype", "Werkt met testdossiers"),
        ("Facturatie volgens het prijsmodel", "Prototype", "Werkt, nog zonder betaalkoppeling"),
        ("Rekening, blokkering en rente bij de bank", "Bij lancering", "Na keuze van de partnerbank"),
        ("Identiteitsverificatie", "Bij lancering", "Via de bank of een erkende dienst"),
        ("Publieke API", "Gepland", "Met de eerste softwarepartners"),
        ("Depiqo Invest (beleggen naast de borg)", "Prototype", "Werkt met een gesimuleerde beleggingspartner; live met een vergunde partner"),
        ("Borggaranties", "Toekomst", "Alleen met een vergunde risicodrager, na juridische toetsing"),
    ]
    trs = "".join(f"<tr><td>{a}</td><td><span class=\"badge {'b-live' if b == 'Prototype' else 'b-launch' if b in ('Bij lancering', 'Gepland') else 'b-future'}\">{b}</span></td><td>{c}</td></tr>" for a, b, c in status_rows)
    return f"""
<section class="page-hero" aria-labelledby="ph-t">
  <div class="wrap copy">
    {_crumbs(ctx, region, "Producten")}
    <p class="eyebrow">Producten</p>
    <h1 id="ph-t">Vier producten rond de {t['term']}. <span class="serif">En een eerlijke planning.</span></h1>
    <p class="lede">Depiqo Business voor beheerders, de Depiqo Wallet voor huurders, de Depiqo-borgrekening bij een partnerbank en Depiqo Invest om naast je borg te beleggen. Bij elk product staat wat er nu werkt en wat nog komt.</p>
  </div>
</section>
{rows}
<section class="section tone-white" aria-labelledby="later-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Daarna</p><h2 id="later-t">Wat we nog bouwen, en onder welke voorwaarden.</h2></div>
    <div class="grid-2">{cards}</div>
  </div>
</section>
<section class="section tone-off" aria-labelledby="status-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Productstatus</p><h2 id="status-t">Wat werkt er vandaag?</h2><p>Bijgewerkt op {CHECKED_NL}.</p></div>
    <div class="table-scroll"><table class="status-table"><thead><tr><th>Onderdeel</th><th>Status</th><th>Toelichting</th></tr></thead><tbody>{trs}</tbody></table></div>
    <div class="cta-row" style="margin-top:28px"><a class="btn btn-primary" href="{L(PAGES['home'][region] + '#demo')}">Plan een demo</a><a class="btn btn-secondary" href="{L(PAGES['prijzen'][region])}">Bekijk de prijzen</a></div>
  </div>
</section>
"""


# ---------------------------------------------------------------- Hoe het werkt

def hoe(ctx, region):
    t = REGIONS[region]
    L = ctx.link
    nl = region == "nl"
    steps = [
        ("Borgverzoek", "Beheerder of makelaar", f"Maakt de {t['term']} aan bij het contract. Depiqo controleert het wettelijke maximum en stuurt de huurder een uitnodiging."),
        ("Controle en identiteit", "Huurder", "Controleert naam van de verhuurder, adres en bedrag, en bevestigt zijn identiteit via de bank."),
        ("Storting en blokkering", "Huurder en bank", "De huurder stort op een rekening op zijn naam. De bank meldt de storting en blokkeert de rekening ten gunste van de verhuurder. Pas dan: ‘veilig’."),
        ("Tijdens de huur", "Iedereen", "Het dossier bevat contract en plaatsbeschrijving. De huurder ziet saldo en rente."),
        ("Afrekening", "Beheerder en huurder", "Bij vertrek stelt de beheerder de afrekening op met bewijs. De huurder gaat akkoord of betwist. Bij een geschil beslist de " + ("rechter" if nl else "vrederechter") + "."),
        (t["end"].capitalize(), "Financieel medewerker en bank", "Een financieel medewerker geeft de opdracht; de bank betaalt huurder en verhuurder volgens het akkoord. Het dossier sluit."),
    ]
    st = "".join(f'<li class="reveal"><h3>{h}</h3><p><b>{w}.</b> {p}</p></li>' for h, w, p in steps)
    if nl:
        rules = [("Nederland", [("Maximum", "2 maanden kale huur"), ("Terug zonder verrekening", "binnen 14 dagen"), ("Terug met verrekening", "binnen 30 dagen"), ("Sinds", "1 juli 2023")], "nl/waarborgsom.html")]
    else:
        rules = [("Vlaanderen", [("Maximum", "3 maanden huur"), ("Vorm", "o.a. geblokkeerde rekening op naam van de huurder"), ("Vrijgave", "akkoord van beide partijen of vonnis"), ("Rente", "voor de huurder")], "be/huurwaarborg-vlaanderen.html"),
                 ("Brussel", [("Maximum", "2 maanden huur zonder lasten"), ("Cash", "niet toegestaan"), ("Terug", "binnen 2 maanden na vertrek"), ("Sinds", "november 2024")], "be/huurwaarborg-brussel.html")]
    rc = "".join(f'<div class="card"><h3>{n}</h3><dl class="facts">{"".join(f"<dt>{a}</dt><dd>{b}</dd>" for a, b in f)}</dl><a class="link-arrow" href="{L(p)}">De volledige regels</a></div>' for n, f, p in rules)
    return f"""
<section class="page-hero has-photo" aria-labelledby="ph-t">
  <div class="wrap">
    <div class="copy">
      {_crumbs(ctx, region, "Hoe het werkt")}
      <p class="eyebrow">Hoe het werkt</p>
      <h1 id="ph-t">Van borgverzoek tot {t['end']}. <span class="serif">Stap voor stap.</span></h1>
      <p class="lede">Wie doet wat, waar staat het geld en wat gebeurt er als het misgaat. Zonder vakjargon.</p>
    </div>
    {photo(ctx, "hoe-huurder-verhuurder", "Een huurder en een verhuurder in gesprek in de keuken van een gerenoveerd appartement", "r-43", eager=True)}
  </div>
</section>

<section class="section tone-white" aria-labelledby="st-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Het proces</p><h2 id="st-t">Zes stappen, met voor elke stap een eigenaar.</h2></div>
    <ol class="process six">{st}</ol>
  </div>
</section>

<section class="section tone-off" id="geldstromen" aria-labelledby="gs-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Geldstromen</p><h2 id="gs-t">Het geld gaat nooit via Depiqo.</h2><p>De huurder stort rechtstreeks bij de bank, op een rekening op zijn naam. Depiqo stuurt opdrachten en toont statussen, maar raakt het geld niet aan.</p></div>
    <div class="flow" role="img" aria-label="Schema van de geldstroom: huurder, partnerbank, verhuurder; Depiqo levert de software">
      <div class="flow-node"><h3>Huurder</h3><ul><li>Stort de {t['term']}</li><li>Krijgt de rente</li><li>Gaat akkoord of betwist</li></ul></div>
      <div class="flow-arrow" aria-hidden="true">→</div>
      <div class="flow-node key"><h3>Partnerbank</h3><ul><li>Rekening op naam van de huurder</li><li>Geblokkeerd voor de verhuurder</li><li>Betaalt uit bij {t['end']}</li></ul></div>
      <div class="flow-arrow" aria-hidden="true">→</div>
      <div class="flow-node"><h3>Verhuurder</h3><ul><li>Begunstigde van de blokkering</li><li>Ontvangt het afgesproken deel</li><li>Ziet de status via Depiqo</li></ul></div>
    </div>
    <p class="fineprint">Staat de {t['term']} elders, {'bijvoorbeeld bij de verhuurder' if nl else 'bijvoorbeeld bij een andere bank of bij e-DEPO'}? Dan volgt Depiqo het dossier en bevestigt een financieel medewerker de ontvangst.</p>
  </div>
</section>

<section class="section tone-white" id="veiligheid" aria-labelledby="vei-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Veiligheid</p><h2 id="vei-t">Hoe we het geld en de gegevens beschermen.</h2></div>
    <div class="trust">
      <div class="trust-item">{icon('bank')}<div><h3>Geld bij een gereguleerde bank</h3><p>Op naam van de huurder. Tegoeden vallen onder het depositogarantiestelsel tot € 100.000 per persoon per bank. De partnerbank kiezen we nog.</p></div></div>
      <div class="trust-item">{icon('shield')}<div><h3>‘Veilig’ alleen na de bank</h3><p>Een betaalopdracht is niet genoeg. De status volgt pas op een ondertekend bericht van de bank.</p></div></div>
      <div class="trust-item">{icon('users')}<div><h3>Rollen en vier ogen</h3><p>Wie een afrekening opstelt, kan niet zelf uitbetalen. Elke actie staat in de audittrail.</p></div></div>
      <div class="trust-item">{icon('lock')}<div><h3>Gegevens in de EU</h3><p>Versleutelde verbindingen, documenten buiten de webserver, sessies die verlopen. Voor de lancering: tweestapsverificatie, DPIA en een externe pentest.</p></div></div>
      <div class="trust-item">{icon('phone')}<div><h3>Bescherming tegen fraude</h3><p>Uitnodigingen tonen verhuurder, adres en bedrag. Depiqo vraagt nooit om je bankcode. <a href="{L(region + '/echt-borgverzoek-herkennen.html')}">Zo herken je een echt verzoek</a>.</p></div></div>
      <div class="trust-item">{icon('scale')}<div><h3>Depiqo beslist niet</h3><p>Bij onenigheid beslissen huurder en verhuurder samen, of de {'rechter' if nl else 'vrederechter'}. Depiqo legt alleen vast.</p></div></div>
    </div>
  </div>
</section>

<section class="section tone-off" aria-labelledby="rg-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Regels</p><h2 id="rg-t">De regels die Depiqo toepast.</h2><p>Elke regel heeft een versie en een controledatum. Gecontroleerd op {CHECKED_NL}.</p></div>
    <div class="grid-{2 if len(rules) == 2 else 2}">{rc}</div>
  </div>
</section>

<section class="section tone-sand tight" aria-labelledby="next-t">
  <div class="wrap split">
    <div class="split-copy"><h2 id="next-t">Zien hoe het werkt met jouw dossiers?</h2><p>Een demo van 30 minuten, met jullie werkwijze als uitgangspunt.</p></div>
    <div class="cta-row"><a class="btn btn-primary" href="{L(PAGES['home'][region] + '#demo')}">Plan een demo</a><a class="btn btn-secondary" href="{L(AUD['huurders'][region]['path'])}">Ik ben huurder</a></div>
  </div>
</section>
"""


# ---------------------------------------------------------------- Pilot

def pilot(ctx, region):
    t = REGIONS[region]
    L = ctx.link
    return f"""
<section class="page-hero has-photo" aria-labelledby="ph-t">
  <div class="wrap">
    <div class="copy">
      {_crumbs(ctx, region, "Pilotprogramma")}
      <p class="eyebrow">Pilotprogramma</p>
      <h1 id="ph-t">Test Depiqo <span class="serif">met je eigen proces.</span></h1>
      <p class="lede">We zoeken vastgoedbeheerders en verhuurkantoren {t['where']} die Depiqo willen testen en mee willen bepalen wat we eerst bouwen.</p>
      <div class="cta-row"><a class="btn btn-primary" href="#aanvraag">Meld je aan</a></div>
    </div>
    {photo(ctx, "team-overleg", "Twee collega's van een vastgoedkantoor overleggen aan een tafel met een laptop", "r-43", eager=True)}
  </div>
</section>
<section class="section tone-white"><div class="wrap">
  <div class="grid-2">
    <div class="card"><h3>Wat het prototype nu kan</h3><ul class="checks"><li>Borgdossiers aanmaken en volgen per status</li><li>Termijnen bewaken per land en gewest</li><li>Eindafrekening met bewijs, akkoord of betwisting</li><li>Teamrollen, audittrail en export</li><li>Facturatie volgens het prijsmodel</li></ul></div>
    <div class="card"><h3>Wat we samen testen</h3><ul class="checks"><li>Past de werkwijze bij jullie proces?</li><li>Hoeveel tijd kost een {t['term']} nu, en straks?</li><li>Welke koppeling met je beheersoftware is het belangrijkst?</li><li>Wat huurders willen zien in de wallet</li></ul></div>
    <div class="card"><h3>Wat afhangt van partners</h3><p>Stortingen, bankbevestigingen, rente en identiteitscontrole werken pas live met een gereguleerde partnerbank. Tijdens de pilot werken we met testdossiers.</p></div>
    <div class="card"><h3>Kosten en gegevens</h3><p>Geen kosten tijdens de pilot. We werken met testgegevens of, na afspraak, met geanonimiseerde dossiers. Je data blijft van jou.</p></div>
  </div>
</div></section>
<section class="section tone-sand" id="aanvraag" aria-labelledby="cta-t">
  <div class="wrap demo-band">
    <div class="split-copy"><p class="eyebrow">Aanmelden</p><h2 id="cta-t">Plan een kennismaking van 30 minuten.</h2><p>We laten het prototype zien met jouw proces als uitgangspunt en bespreken of een pilot past.</p></div>
    {lead_form(region, "pilot", "demo", "pilot")}
  </div>
</section>
"""
