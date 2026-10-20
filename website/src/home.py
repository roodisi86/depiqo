"""Homepage for /nl/ and /be/ (V4, human-first)."""
from components import (dashboard_mock, faq_html, icon, lead_form, phone_mock, plans_html, task_float, wallet_float)
from layout import AUD, CHECKED_NL, PAGES, REGIONS, photo

COPY = {
    "nl": {
        "title": "Depiqo | De waarborgsom digitaal geregeld, met rente voor de huurder",
        "desc": "Depiqo regelt de waarborgsom van borgverzoek tot terugbetaling. Voor vastgoedbeheerders, makelaars, verhuurders en huurders in Nederland. Nu in pilotfase.",
        "sub": "Depiqo regelt de waarborgsom van borgverzoek tot terugbetaling, naast je eigen beheersoftware en ook voor bestaande borgen. Huurders zien waar hun geld staat en krijgen er, via onze partnerbank, rente op.",
        "rule": "Maximaal 2 maanden kale huur. Terug binnen 14 dagen, of 30 dagen als er kosten worden verrekend.",
        "where_h": "Elke waarborgsom op één plek, waar hij ook staat.",
        "where_p": "Je hoeft niets te vervangen. Depiqo werkt naast je beheersoftware en volgt ook de borgen die je al hebt.",
        "where": [("home", "Op de rekening van de verhuurder", "Zo staat de meeste waarborgsom vandaag. Depiqo bewaakt termijnen en afrekening, met bewijs van ontvangst."),
                  ("bank", "Op een Depiqo-borgrekening", "Bij onze partnerbank, op naam van de huurder, met rente voor de huurder. Beschikbaar bij lancering."),
                  ("shield", "Via een borggarantie", "Een derde staat garant in plaats van een storting. Depiqo houdt certificaat en vervaldatum bij.")],
        "money_h": "Een waarborgsom hoeft niet stil te staan.",
        "money_p": "Staat de waarborgsom op de rekening van de verhuurder, dan levert hij de huurder meestal niets op. Met Depiqo staat het geld bij een bank, op naam van de huurder, en is de rente voor hem.",
        "faq": [
            ("Is Depiqo al beschikbaar?", "Depiqo werkt als prototype en we zoeken pilotpartners. De borgrekening met rente start zodra de partnerbank is gekozen en de juridische toetsing klaar is. Tot die tijd werken we met testdossiers."),
            ("Is Depiqo een bank?", "Nee. Depiqo maakt software. Het geld staat bij een gereguleerde bank, op naam van de huurder. Niet bij Depiqo en niet op de rekening van de beheerder."),
            ("Krijgt de huurder rente over de waarborgsom?", "De wet regelt dat niet. Op een Depiqo-borgrekening wel: de rente die de partnerbank uitkeert, is voor de huurder. Hoeveel dat is, hangt af van de bank. We tonen alleen rente die echt is bijgeschreven."),
            ("Wie beslist bij onenigheid over de afrekening?", "Huurder en verhuurder samen, of anders de rechter. Depiqo legt afspraken en bewijs vast, maar beslist nooit zelf."),
            ("Wat kost Depiqo?", "Voor huurders niets. Beheerders en makelaars betalen een abonnement vanaf € 99 per maand, inclusief 100 actieve dossiers. Op een Depiqo-borgrekening kost een extra dossier minder."),
            ("Kan ik beleggen via Depiqo?", "Ja, met eigen geld en naast je borg, via Depiqo Invest. Je kiest een defensieve, neutrale of offensieve portefeuille bij een vergunde beleggingspartner en ziet de kosten vooraf: 0,25% per jaar voor Depiqo plus de fondskosten. De borg zelf blijft op de geblokkeerde rekening, want de verhuurder moet erop kunnen rekenen. Depiqo Invest werkt nu in de testomgeving en gaat live zodra de beleggingspartner is aangesloten."),
        ],
    },
    "be": {
        "title": "Depiqo | De huurwaarborg digitaal geregeld, van aanvraag tot vrijgave",
        "desc": "Depiqo regelt de huurwaarborg van aanvraag tot vrijgave, volgens de regels in Vlaanderen en Brussel. Voor vastgoedbeheerders, immokantoren, verhuurders en huurders.",
        "sub": "Behoud je vastgoedsoftware en je huidige aanbieders. Met Depiqo volg je elke huurwaarborg op één plek, of hij nu bij e-DEPO, een bank of een verzekeraar staat, van aanvraag tot vrijgave.",
        "rule": "Vlaanderen: maximaal 3 maanden huur. Brussel: maximaal 2 maanden. Vrijgave met akkoord van beide partijen of een vonnis.",
        "where_h": "Elke huurwaarborg op één plek, waar hij ook staat.",
        "where_p": "Je hoeft niets te vervangen: niet je vastgoedsoftware en niet je aanbieders. Depiqo volgt elke waarborg en maakt de vrijgave klaar, ook voor de dossiers die je al hebt.",
        "where": [("doc", "Bij e-DEPO", "De gratis dienst van de Deposito- en Consignatiekas. Depiqo houdt het dossiernummer, de afrekening en het vrijgaveformulier bij."),
                  ("bank", "Op een geblokkeerde bankrekening", "Bij je eigen bank of bij onze partnerbank, op naam van de huurder."),
                  ("shield", "Via een verzekeraar of garantie", "Een kapitalisatiecontract of een borgstelling door een derde, met vervaldatum en certificaat in het dossier.")],
        "money_h": "Rente voor de huurder. Zonder papierwerk.",
        "money_p": "In België staat de huurwaarborg meestal al op een geblokkeerde rekening op naam van de huurder, met de rente voor hem. Depiqo maakt het openen, opvolgen en vrijgeven daarvan digitaal, en houdt het hele dossier bij elkaar.",
        "faq": [
            ("Is Depiqo al beschikbaar?", "Depiqo werkt als prototype en we zoeken pilotpartners in Vlaanderen en Brussel. De geblokkeerde rekening via Depiqo start zodra de partnerbank is gekozen. Tot die tijd werken we met testdossiers."),
            ("Is Depiqo een bank?", "Nee. Depiqo maakt software. De waarborg staat op een geblokkeerde rekening op naam van de huurder bij een erkende bank, of blijft waar hij nu staat."),
            ("Waarom Depiqo als e-DEPO gratis is?", "e-DEPO bewaart de waarborg, en dat doet het goed. Depiqo regelt het werk eromheen: aanvragen, opvolging, plaatsbeschrijving, eindafrekening, akkoord en vrijgave, voor honderden dossiers tegelijk. Staat de waarborg bij e-DEPO, je bank of een verzekeraar, dan volgt Depiqo het dossier daar en maakt het de vrijgave klaar."),
            ("Wie beslist bij onenigheid over de vrijgave?", "Huurder en verhuurder samen, of anders de vrederechter. Depiqo legt afspraken en bewijs vast, maar beslist nooit zelf."),
            ("Wat kost Depiqo?", "Voor huurders niets. Beheerders en immokantoren betalen een abonnement vanaf € 99 per maand, inclusief 100 actieve dossiers. Op een Depiqo-borgrekening kost een extra dossier minder."),
            ("Werkt Depiqo ook in Wallonië?", "Nog niet. We beginnen in Vlaanderen en Brussel. Wallonië heeft eigen regels en volgt later."),
        ],
    },
}


def build(ctx, region):
    c = COPY[region]
    t = REGIONS[region]
    L = ctx.link
    r = region
    term, terms, end = t["term"], t["terms"], t["end"]
    nl = r == "nl"

    aud_cards = ""
    aud_data = [
        ("huurders", "aud-huurder", "Een jonge vrouw draagt een verhuisdoos haar nieuwe, lichte appartement binnen", f"Je {term} is jouw geld. Zie waar het staat, wat het opbrengt en wanneer je het terugkrijgt."),
        ("verhuurders", "aud-verhuurder", "Een verhuurder bekijkt documenten aan een eettafel in een gerenoveerde woning", f"Zekerheid die door de bank is bevestigd, en een afrekening die je kunt onderbouwen."),
        ("makelaars", "aud-makelaar", "Een makelaar overhandigt in een trappenhuis de sleutels aan een nieuwe huurder", "Verstuur borgverzoeken bij het contract en zie direct wie al betaald heeft."),
        ("beheerders", "aud-beheerder", "Een vastgoedbeheerder werkt op een laptop in een licht kantoor", f"Alle {terms} in één overzicht, met termijnbewaking en een audittrail."),
    ]
    for key, slot, alt, text in aud_data:
        a = AUD[key][r]
        aud_cards += (f'<a class="aud-card reveal" href="{L(a["path"])}">{photo(ctx, slot, alt, "r-43")}'
                      f'<div class="aud-body"><h3>{a["label"]}</h3><p>{text}</p><span class="link-arrow">Voor {a["label"].lower()}</span></div></a>')
    partner_links = "".join(f'<a href="{L(AUD[k][r]["path"])}">{AUD[k][r]["label"]}</a>' for k in ("institutioneel", "banken", "verzekeraars", "beleggen", "software"))

    where_cards = "".join(f'<div class="card reveal">{icon(i)}<h3>{h}</h3><p>{p}</p></div>' for i, h, p in c["where"])
    demo = L(PAGES["home"][r] + "#demo")
    return f"""
<section class="hero" aria-labelledby="hero-title">
  <div class="wrap hero-grid">
    <div class="hero-copy">
      <span class="status-chip"><i></i>In pilotfase · {t['label']}</span>
      <h1 id="hero-title">Elke {term}. <span class="serif">Eén helder proces.</span></h1>
      <p class="lede">{c['sub']}</p>
      <div class="cta-row">
        <a class="btn btn-primary" href="{demo}">Plan een demo</a>
        <a class="btn btn-secondary" href="{L(PAGES['hoe'][r])}">Ontdek Depiqo</a>
      </div>
      <p class="hero-note">Huurder? <a href="{L(AUD['huurders'][r]['path'])}">Zo werkt het voor jou</a>. Depiqo is geen bank: het geld staat bij een gereguleerde partnerbank.</p>
    </div>
    <div class="hero-visual">
      {photo(ctx, "hero-nieuwe-woning", "Een jong stel staat met de sleutels in hun nieuwe, nog lege huurappartement aan de gracht, in warm daglicht", "r-45", eager=True)}
      {wallet_float(r)}
      {task_float(r)}
      <p class="demo-note">Productvoorbeeld met fictieve gegevens</p>
    </div>
  </div>
</section>

<section class="section tone-white" aria-labelledby="wat-t">
  <div class="wrap">
    <div class="section-head center"><p class="eyebrow">Wat is Depiqo?</p><h2 id="wat-t">Eén plek voor de {term}, voor iedereen die ermee te maken heeft.</h2><p>Een {term} is een groot bedrag voor een huurder en een klein dossier voor een beheerder. Depiqo maakt het voor allebei duidelijk.</p></div>
    <ol class="simple-steps">
      <li class="reveal"><h3>Aanvragen</h3><p>De beheerder of makelaar maakt de {term} aan bij het huurcontract. De huurder krijgt een uitnodiging die hij kan controleren: naam van de verhuurder, adres en bedrag.</p></li>
      <li class="reveal"><h3>Veilig stellen</h3><p>De huurder stort op een rekening op zijn eigen naam bij onze partnerbank. Pas als de bank de blokkering bevestigt, staat de {term} op ‘veilig’.</p></li>
      <li class="reveal"><h3>{end.capitalize()}</h3><p>Bij vertrek stelt de beheerder de afrekening op, met bewijs. De huurder gaat akkoord of betwist. Depiqo bewaakt de termijnen.</p></li>
    </ol>
  </div>
</section>

<section class="section tone-mint" aria-labelledby="waar-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Werkt met wat je al hebt</p><h2 id="waar-t">{c['where_h']}</h2><p>{c['where_p']}</p></div>
    <div class="grid-3">{where_cards}</div>
    <p class="fineprint">Bestaande borgen importeer je in één keer uit een Excel- of CSV-bestand. Koppelingen met beheersoftware bouwen we samen met de eerste klanten. Depiqo is geen partner van de genoemde soorten aanbieders, tenzij we dat uitdrukkelijk vermelden.</p>
  </div>
</section>

<section class="section tone-off" aria-labelledby="wie-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Voor wie</p><h2 id="wie-t">Herken je eigen ingang.</h2><p>Depiqo verbindt huurders, verhuurders en vastgoedprofessionals met de bank die het geld bewaart.</p></div>
    <div class="grid-4">{aud_cards}</div>
    <div class="partner-strip"><b>Ook voor</b>{partner_links}</div>
  </div>
</section>

<section class="section tone-white" aria-labelledby="geld-t">
  <div class="wrap split wide-right">
    <div class="split-copy">
      <p class="eyebrow">Financiële mogelijkheden</p>
      <h2 id="geld-t">{c['money_h']}</h2>
      <p>{c['money_p']}</p>
      <p class="small muted">We zijn duidelijk over wat er al is en wat nog komt. Elke optie heeft een status.</p>
    </div>
    <div class="opt-grid">
      <div class="opt reveal"><div class="row">{icon('bank')}<span class="badge b-launch">Bij lancering</span></div><h3>Borgrekening met rente</h3><p>Op naam van de huurder bij een gereguleerde partnerbank, geblokkeerd ten gunste van de verhuurder. De rente is voor de huurder.</p></div>
      <div class="opt reveal"><div class="row">{icon('doc')}<span class="badge b-live">Nu in prototype</span></div><h3>Transparante administratie</h3><p>Elk dossier met bedrag, status, documenten en een volledige historie. Voor huurder en beheerder hetzelfde beeld.</p></div>
      <div class="opt reveal"><div class="row">{icon('shield')}<span class="badge b-live">Nu in prototype</span></div><h3>Gecontroleerde zekerheid</h3><p>‘Veilig’ alleen na bevestiging van de bank. Regels per land en gewest, met controledatum.</p></div>
      <div class="opt reveal"><div class="row">{icon('chart')}<span class="badge b-launch">In testversie</span></div><h3>Beleggen met Depiqo Invest</h3><p>Met eigen geld, naast je {term}. Kies een defensieve, neutrale of offensieve portefeuille bij een vergunde beleggingspartner en volg de waarde in dezelfde app. De {term} zelf blijft op de geblokkeerde rekening.</p><small>Werkt in de testomgeving; live zodra de beleggingspartner is aangesloten. Beleggen kan geld kosten.</small></div>
    </div>
  </div>
</section>

<section class="section tone-sand" id="beheerders" aria-labelledby="beh-t">
  <div class="wrap split wide-right">
    <div class="split-copy">
      <p class="eyebrow">Voor vastgoedbeheerders en makelaars</p>
      <h2 id="beh-t">Van borgverzoek tot {end}. Alles in één workflow.</h2>
      <ul class="checks">
        <li>Eén overzicht van alle {terms}, per pand, huurder en status.</li>
        <li>Automatische herinneringen voor huurders die nog niet gestort hebben.</li>
        <li>Termijnbewaking per land en gewest, met waarschuwing vooraf.</li>
        <li>Eindafrekening met foto's en documenten, en een vastgelegd akkoord.</li>
        <li>Teamrollen: wie aanmaakt, mag niet zomaar uitbetalen.</li>
      </ul>
      <div class="cta-row"><a class="btn btn-primary" href="{demo}">Plan een demo</a><a class="link-arrow" href="{L(AUD['beheerders'][r]['path'])}">Meer voor beheerders</a></div>
    </div>
    <div class="mock-pair reveal">
      {dashboard_mock(r)}
    </div>
  </div>
</section>

<section class="section tone-navy" aria-labelledby="proces-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Het proces</p><h2 id="proces-t">Vijf stappen. Iedereen ziet dezelfde status.</h2></div>
    <ol class="process">
      <li class="reveal"><h3>Borgverzoek</h3><p>Aangemaakt bij het contract, met controle op het wettelijke maximum.</p></li>
      <li class="reveal"><h3>Controle en identiteit</h3><p>De huurder controleert verhuurder, adres en bedrag, en bevestigt wie hij is.</p></li>
      <li class="reveal"><h3>Storting en blokkering</h3><p>Op een rekening op naam van de huurder. ‘Veilig’ pas na bevestiging van de bank.</p></li>
      <li class="reveal"><h3>Afrekening</h3><p>Bij vertrek, met foto's en documenten. Akkoord of betwisting in de app.</p></li>
      <li class="reveal"><h3>{end.capitalize()}</h3><p>De bank betaalt uit volgens het akkoord of het vonnis. Het dossier sluit.</p></li>
    </ol>
    <p class="rule-note">{c['rule']} Gecontroleerd op {CHECKED_NL}. <a href="{L(PAGES['kennisbank'][r])}">Lees de regels</a></p>
  </div>
</section>

<section class="section tone-off" id="huurders" aria-labelledby="hu-t">
  <div class="wrap split">
    <div class="media-stack reveal">
      {photo(ctx, "huurder-woonkamer", "Een huurder zit ontspannen op de bank in een lichte woonkamer en kijkt op zijn telefoon", "r-45")}
    </div>
    <div class="split-copy">
      <p class="eyebrow">Voor huurders</p>
      <h2 id="hu-t">Je {term} is jouw geld. <span class="serif">Je ziet het ook.</span></h2>
      <p>Een {term} is vaak een van de grootste bedragen die je in één keer betaalt. In de Depiqo-wallet zie je altijd waar het staat, op wiens naam, wat het opbrengt en wanneer je het terugkrijgt.</p>
      <ul class="checks">
        <li>Je geld staat op jouw naam bij de bank, niet bij de verhuurder.</li>
        <li>De rente van de bank is voor jou.</li>
        <li>Afrekening met bewijs, en een knop om akkoord te gaan of te betwisten.</li>
        <li>Depiqo is gratis voor huurders.</li>
      </ul>
      <div class="cta-row"><a class="btn btn-secondary" href="{L(AUD['huurders'][r]['path'])}">Zo werkt het voor jou</a><a class="link-arrow" href="{L(r + '/echt-borgverzoek-herkennen.html')}">Een echt borgverzoek herkennen</a></div>
    </div>
  </div>
</section>

<section class="section tone-white" id="veiligheid" aria-labelledby="vei-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Veiligheid en vertrouwen</p><h2 id="vei-t">Wie doet wat met het geld?</h2><p>Bij duizenden euro's hoort een eerlijk antwoord. Dit is hoe het werkt, en wat nog niet bestaat.</p></div>
    <div class="trust">
      <div class="trust-item reveal">{icon('bank')}<div><h3>De bank houdt het geld aan</h3><p>Een gereguleerde partnerbank, op naam van de huurder. Depiqo houdt nooit geld aan. Die partnerbank kiezen we nog; tot dan werken we met testdossiers.</p></div></div>
      <div class="trust-item reveal">{icon('code')}<div><h3>Depiqo levert de software</h3><p>Aanvragen, statussen, termijnen, documenten, afrekening en de opdracht tot {end}. Alles met een audittrail.</p></div></div>
      <div class="trust-item reveal">{icon('lock')}<div><h3>Juridische blokkering</h3><p>De bank blokkeert de rekening ten gunste van de verhuurder. Vrijgeven kan alleen met akkoord van beide partijen of een rechterlijke beslissing.</p></div></div>
      <div class="trust-item reveal">{icon('shield')}<div><h3>Welke bescherming geldt</h3><p>Tegoeden bij een bank vallen onder het depositogarantiestelsel tot € 100.000 per persoon per bank. Beleggingen vallen daar niet onder; die bieden we daarom niet aan als borg.</p></div></div>
    </div>
    <p class="fineprint">Nog in ontwikkeling: de koppeling met de partnerbank, echte identiteitsverificatie en tweestapsverificatie. <a href="{L(PAGES['hoe'][r] + '#veiligheid')}">Alles over veiligheid en geldstromen</a></p>
  </div>
</section>

<section class="section tone-off" aria-labelledby="prijs-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Prijzen</p><h2 id="prijs-t">Een helder abonnement. Gratis voor huurders.</h2><p>Geen opstartkosten. Dossiers op een Depiqo-borgrekening kosten minder, omdat de bank een deel van het werk doet.</p></div>
    {plans_html(ctx, r, demo, compact=True)}
    <p class="fineprint">Prijzen excl. btw, introductietarief. Geen kosten tijdens de pilot. <a href="{L(PAGES['prijzen'][r])}">Bereken je prijs</a></p>
  </div>
</section>

<section class="section tone-white" aria-labelledby="faq-t">
  <div class="wrap split wide-right top">
    <div class="split-copy"><p class="eyebrow">Veelgestelde vragen</p><h2 id="faq-t">Goede vragen over je {term}.</h2><p>Staat je vraag er niet bij? Mail naar <a href="mailto:hallo@getdepiqo.com">hallo@getdepiqo.com</a>.</p></div>
    {faq_html(c['faq'])}
  </div>
</section>

<section class="section tone-sand" id="demo" aria-labelledby="demo-t">
  <div class="wrap demo-band">
    <div class="split-copy">
      <p class="eyebrow">Pilotprogramma</p>
      <h2 id="demo-t">Laat ons zien hoe jullie het nu doen.</h2>
      <p>In 30 minuten lopen we met jou door een {term} van begin tot eind, met jullie werkwijze als uitgangspunt. Daarna weet je of een pilot past.</p>
      {photo(ctx, "team-overleg", "Twee collega's van een vastgoedkantoor overleggen aan een tafel met een laptop", "r-32")}
    </div>
    {lead_form(r, "home", "demo", "vastgoedbeheerder")}
  </div>
</section>
"""
