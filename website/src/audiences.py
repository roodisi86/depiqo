"""Audience landing pages ("Voor wie"). Each page answers four questions for one audience:
what is Depiqo for me, what do I gain, how does it work, what does it cost."""
from html import escape

from components import (PLANS, dashboard_mock, faq_html, icon, lead_form, phone_mock, settlement_mock)
from layout import APP_LOGIN, AUD, CHECKED_NL, PAGES, REGIONS, photo


def _flow_bank(region):
    t = REGIONS[region]
    return f"""<div class="flow" role="img" aria-label="Schema: huurder, Depiqo en partnerbank">
  <div class="flow-node"><h3>Huurder en beheerder</h3><ul><li>Uitnodiging en controle</li><li>Afrekening en akkoord</li><li>Eén status voor iedereen</li></ul></div>
  <div class="flow-arrow" aria-hidden="true">→</div>
  <div class="flow-node key"><h3>Depiqo</h3><ul><li>Onboarding en documenten</li><li>Regels per land en gewest</li><li>Opdrachten via API</li></ul></div>
  <div class="flow-arrow" aria-hidden="true">→</div>
  <div class="flow-node"><h3>Partnerbank</h3><ul><li>Rekening op naam van de huurder</li><li>Blokkering en rente</li><li>Uitbetaling bij {t['end']}</li></ul></div>
</div>"""


def _api_mock():
    return """<div class="app-window" role="img" aria-label="Voorbeeld van een webhookbericht van Depiqo">
  <div class="app-bar"><span class="dots" aria-hidden="true"><span></span><span></span><span></span></span>POST /jouw-systeem/webhooks/depiqo</div>
  <div class="app-body"><pre class="code">{
  "type": "deposit.secured",
  "reference": "DPQ-001-00013",
  "property": "Prinsengracht 263",
  "amount_cents": 280000,
  "holding": "depiqo",
  "secured_at": "2026-10-19T09:41:00Z"
}</pre><p class="small muted">Voorbeeld. De publieke API is gepland; in de pilot werken we met export en gerichte koppelingen.</p></div>
</div>"""


def _time_calc(region):
    t = REGIONS[region]
    return f"""<div class="calc">
  <form class="calc-fields" data-calc onsubmit="return false" aria-label="Rekentool tijdsbesteding">
    <div class="field"><label for="c-new">Nieuwe huurcontracten per jaar</label><div class="input-wrap"><input id="c-new" inputmode="numeric" value="220"><span>per jaar</span></div></div>
    <div class="field"><label for="c-end">Beëindigde huurcontracten per jaar</label><div class="input-wrap"><input id="c-end" inputmode="numeric" value="200"><span>per jaar</span></div></div>
    <div class="field"><label for="c-min-new">Tijd per nieuwe {t['term']}</label><div class="input-wrap"><input id="c-min-new" inputmode="numeric" value="45"><span>min</span></div><span class="hint">Inclusief controle en nabellen</span></div>
    <div class="field"><label for="c-min-end">Tijd per {t['end']}</label><div class="input-wrap"><input id="c-min-end" inputmode="numeric" value="90"><span>min</span></div><span class="hint">Inclusief afrekening en overleg</span></div>
    <div class="field full"><label for="c-pct">Verwachte tijdsbesparing</label><div class="input-wrap"><input id="c-pct" inputmode="numeric" value="50"><span>%</span></div><span class="hint">Jouw eigen inschatting</span></div>
  </form>
  <div class="result" aria-live="polite">
    <div class="line"><span>Tijd per jaar nu</span><b id="r-before">465 uur</b></div>
    <div class="line"><span>Mogelijke besparing</span><b id="r-saved">233 uur</b></div>
    <div class="line"><span>Omgerekend</span><b id="r-fte">0,15 fte</b></div>
    <div><span class="small">Werkdagen van 8 uur terug per jaar</span><div class="big" id="r-days">29</div></div>
    <small>Berekening: (nieuwe contracten × minuten per nieuwe {t['term']} + beëindigingen × minuten per {t['end']}) ÷ 60, maal je besparing. Fte op basis van 1.600 productieve uren per jaar. Een indicatie op basis van jouw aannames, geen gemeten resultaat.</small>
  </div>
</div>"""


# ---------------------------------------------------------------- content per audience

def content(key, region):
    t = REGIONS[region]
    term, terms, Term, end = t["term"], t["terms"], t["Term"], t["end"]
    nl = region == "nl"
    pro = PLANS[1]
    ess = PLANS[0]

    if key == "huurders":
        return dict(
            title=f"{Term} via Depiqo: zie waar je geld staat | Voor huurders",
            desc=f"Je {term} op jouw naam bij een bank, met de rente voor jou. Zie in de Depiqo-wallet waar je geld staat en wanneer je het terugkrijgt. Gratis voor huurders.",
            eyebrow="Voor huurders",
            h1=(f"Je {term} is jouw geld. <span class=\"serif\">Zie waar het staat.</span>" if nl else f"Je {term} staat op jouw naam. <span class=\"serif\">Volg hem in één app.</span>"),
            lede=f"Met Depiqo staat je {term} op een rekening op jouw naam bij een bank. Je ziet wat het oplevert, wat er gebeurt bij vertrek en wanneer je het terugkrijgt. Je betaalt er niets voor.",
            hero=("huurder-verhuisdozen", "Een jong stel pakt verhuisdozen uit in hun nieuwe, lichte huurwoning", "cool"),
            cta_primary=("Ontdek je mogelijkheden", "#mogelijkheden"), cta_secondary=("Een echt verzoek herkennen", f"{region}/echt-borgverzoek-herkennen.html"),
            problem_h=f"Vier vragen die huurders over hun {term} stellen.",
            problem_p="En die je vaak pas bij vertrek beantwoord krijgt.",
            problems=[("home", "Waar staat mijn geld?", "Vaak op de rekening van de verhuurder of het kantoor. Je ziet het niet meer tot je vertrekt." if nl else "Op een geblokkeerde rekening, maar via welke bank en hoe je die volgt, is vaak onduidelijk."),
                      ("coins", "Levert het iets op?", "In Nederland regelt de wet geen rente op de waarborgsom. Meestal krijg je niets." if nl else "De rente is voor jou, maar je ziet zelden hoeveel het is."),
                      ("clock", "Wanneer krijg ik het terug?", "Binnen 14 dagen, of 30 dagen als er kosten worden verrekend. Maar wie houdt dat bij?" if nl else "Pas na akkoord van beide partijen of een vonnis. In Brussel binnen twee maanden na vertrek."),
                      ("scale", "Wat als ik het oneens ben?", "Zonder overzicht van de afrekening en het bewijs is het moeilijk om iets te betwisten.")],
            sol_h="Alles over je borg, in één wallet.",
            sol_bullets=[f"Je {term} staat op jouw naam bij een gereguleerde partnerbank.", "De rente die de bank uitkeert, is voor jou.", "Je ziet de afrekening met foto's en documenten.", "Je gaat akkoord of betwist met één knop, met je reden erbij.", "Je ziet altijd de volgende stap en de termijn."],
            visual="phone",
            steps=[("Controleer de uitnodiging", "Je ziet eerst de naam van de verhuurder, het adres en het bedrag. Klopt iets niet? Dan stop je."),
                   ("Bevestig wie je bent", "Eenmalig, via de bank. Zo kan niemand op jouw naam een rekening openen."),
                   ("Stort op je eigen rekening", "Op jouw naam bij de partnerbank. Niet naar een particulier rekeningnummer."),
                   ("Tijdens de huur", "Je ziet je saldo, de rente en je documenten."),
                   (f"{end.capitalize()}", "Je krijgt de afrekening, reageert in de app en de bank betaalt uit.")],
            benefits=[("€ 0", "Depiqo is gratis voor huurders. Geen abonnement, geen kosten per storting."),
                      ("Op jouw naam", "Het geld staat bij een bank, niet bij Depiqo en niet bij de verhuurder."),
                      ("+ € 147", f"Voorbeeld: € 2.400 drie jaar tegen 2% rente, vóór belasting. De echte rente hangt af van de bank en kan veranderen.")],
            extra=_tenant_options(region),
            price_h="Wat kost het?",
            price_p=f"Niets. Depiqo verdient aan het abonnement dat beheerders en makelaars betalen. Kies je later zelf voor een extra dienst, zoals beleggen met eigen geld naast je {term}, dan zie je de kosten vooraf en kies je zelf.",
            faq=[(f"Moet ik Depiqo gebruiken als mijn verhuurder dat vraagt?", f"Je verhuurder kiest hoe de {term} wordt geregeld, binnen de wettelijke regels. Via Depiqo staat het geld op jouw naam bij een bank, wat voor jou meestal gunstiger is dan op de rekening van de verhuurder."),
                 ("Hoe herken ik een echt verzoek van Depiqo?", "Een echt verzoek komt van het Depiqo-domein, noemt je verhuurder, het adres en het bedrag, en vraagt nooit om je bankcode. Je stort altijd op een rekening op je eigen naam."),
                 ("Wat gebeurt er met mijn geld als Depiqo stopt?", "Je geld staat niet bij Depiqo, maar bij de bank op jouw naam. Het blijft daar, ook als Depiqo zou stoppen. De bank betaalt uit volgens het akkoord of een vonnis."),
                 ("Kan ik mijn borg beleggen?", f"Niet de {term} zelf: die blijft op de geblokkeerde rekening, want de verhuurder moet erop kunnen rekenen. Met eigen geld kun je wel beleggen, naast je borg, via Depiqo Invest en een vergunde beleggingspartner. Bij de terugbetaling kun je ook kiezen om je borg door te beleggen. Beleggen kan geld kosten.")],
            cta="tenant",
            related=[(f"{region}/echt-borgverzoek-herkennen.html", "Een echt borgverzoek herkennen", "Zo voorkom je fraude"),
                     ("nl/waarborgsom-terugkrijgen.html" if nl else "be/huurwaarborg-vrijgeven.html", "Waarborgsom terugkrijgen" if nl else "Huurwaarborg vrijgeven", "Termijnen en wat je kunt doen"),
                     (PAGES["hoe"][region] + "#veiligheid", "Veiligheid en geldstromen", "Wie houdt het geld aan")],
        )

    if key == "verhuurders":
        return dict(
            title=f"{Term} regelen als verhuurder: zekerheid zonder gedoe | Depiqo",
            desc=f"De {term} goed regelen als verhuurder: zekerheid bevestigd door de bank, een onderbouwde afrekening en geen geld op je eigen rekening.",
            eyebrow="Voor verhuurders",
            h1=f"Zekerheid over de {term}. <span class=\"serif\">Zonder het geld zelf te bewaren.</span>",
            lede=f"Je wilt zeker weten dat de {term} er is als het nodig is, en een afrekening die standhoudt. Met Depiqo bevestigt de bank de zekerheid en houd je het dossier compleet.",
            hero=("verhuurder-inspectie", "Een verhuurder fotografeert een muur terwijl hij met de huurder door de lege woning loopt, tijdens de eindinspectie", ""),
            cta_primary=("Bekijk de oplossing", "#oplossing"), cta_secondary=("Vraag toegang aan", "#aanvraag"),
            problem_h="Waar het bij verhuurders vaak misgaat.",
            problem_p="Niet bij de start, maar bij het einde van de huur.",
            problems=[("coins", "Geld van de huurder op je eigen rekening", "Je moet het apart houden, terugbetalen en verantwoorden. Dat is werk en risico." if nl else "De waarborg moet op een geblokkeerde rekening op naam van de huurder. Openen en vrijgeven gaat vaak nog op papier."),
                      ("clock", "Termijnen die snel verlopen", "Sinds 1 juli 2023: terug binnen 14 dagen, of 30 dagen bij verrekening." if nl else "In Brussel moet de waarborg binnen twee maanden na vertrek terug, anders volgt een sanctie."),
                      ("doc", "Een afrekening zonder bewijs", "Zonder foto's, plaatsbeschrijving en offerte wordt een inhouding snel een discussie.")],
            sol_h="Wat Depiqo voor jou regelt.",
            sol_bullets=[f"Het borgverzoek met controle op het maximum: {'2 maanden kale huur' if nl else '3 maanden in Vlaanderen, 2 in Brussel'}.", "‘Zekerheid bevestigd’ pas na een bericht van de bank.", "Begin- en eindsituatie met foto's in het dossier.", "Een afrekening die de huurder ziet, met akkoord of betwisting.", f"Herinneringen vóór de wettelijke termijn voor {end}."],
            visual="settlement",
            steps=[("Maak het verzoek aan", "Adres, huur en bedrag. Depiqo controleert het maximum."), ("De huurder stort", "Op een rekening op zijn naam, geblokkeerd voor jou."), ("Leg de start vast", "Contract en plaatsbeschrijving in het dossier."), ("Reken af bij vertrek", "Met bewijs. De huurder reageert in de app."), ("De bank betaalt uit", "Volgens het akkoord. Het dossier sluit.")],
            benefits=[("Bevestigd", "Zekerheid door de bank bevestigd, niet alleen een betaalopdracht."), ("0 euro", "geld van huurders op je eigen rekening."), ("1 dossier", "met contract, foto's, afrekening en akkoord, voor als het ooit nodig is.")],
            extra="",
            price_h="Wat kost het?",
            price_p=f"Verhuur je via een makelaar of beheerder die Depiqo gebruikt? Dan zit Depiqo in hun dienst. Verhuur je zelf een paar woningen? In de pilot openen we een beperkt aantal plaatsen voor particuliere verhuurders. Het tarief voor kleine verhuurders maken we bekend bij de lancering. Voor de huurder is Depiqo altijd gratis.",
            faq=[(f"Mag ik de {term} op mijn eigen rekening houden?", "In Nederland verbiedt de wet dat niet, maar je moet het bedrag wel binnen de termijnen terugbetalen en kunnen onderbouwen wat je inhoudt. Via Depiqo staat het geld apart, op naam van de huurder." if nl else "Nee. In Vlaanderen en Brussel staat een waarborg in geld op een geblokkeerde rekening op naam van de huurder, of in een andere wettelijke vorm."),
                 ("Wat als de huurder niet reageert op de afrekening?", f"Depiqo herinnert de huurder en houdt de termijn bij. Komt er geen akkoord, dan beslist de {'rechter' if nl else 'vrederechter'}. Depiqo beslist nooit zelf."),
                 ("Wat mag ik inhouden?", "Schade door de huurder, achterstallige huur en servicekosten. Normale slijtage niet." if nl else "Schade en openstaande bedragen volgens het huurcontract en de plaatsbeschrijving. Normale slijtage niet.")],
            cta="verhuurder",
            related=[("nl/waarborgsom-voor-verhuurders.html" if nl else "be/huurwaarborg.html", "De regels voor verhuurders" if nl else "De huurwaarborg in België", "Maximum, termijnen, verrekenen"),
                     (AUD["makelaars"][region]["path"], AUD["makelaars"][region]["label"], "Verhuren via een kantoor"), (PAGES["prijzen"][region], "Prijzen", "Abonnementen en wat gratis is")],
        )

    if key == "makelaars":
        who = "makelaars" if nl else "immokantoren"
        return dict(
            title=("Waarborgsom voor makelaars: geregeld bij het contract | Depiqo" if nl else "Huurwaarborg voor immokantoren: digitaal tot de sleutels | Depiqo"),
            desc=(f"Voor verhuurmakelaars: verstuur het borgverzoek bij het contract, zie wie gestort heeft en draag een compleet dossier over. Geen geld via je eigen rekening." if nl else "Voor immokantoren: vraag de huurwaarborg digitaal aan, volg de bevestiging van de bank en geef de sleutels pas als de zekerheid er is."),
            eyebrow="Voor makelaars" if nl else "Voor immokantoren",
            h1=(f"De borg geregeld <span class=\"serif\">voordat de sleutels over gaan.</span>"),
            lede=(f"Je verhuurt de woning, en de borg hoort daarbij. Met Depiqo verstuur je het borgverzoek bij het contract, zie je wanneer de bank de storting bevestigt en draag je een compleet dossier over aan verhuurder of beheerder." if nl else "Een waarborgaanvraag, wachten op de bank, een attest voor de sleutels. Met Depiqo vraag je de huurwaarborg digitaal aan en zie je meteen wanneer de bank de zekerheid bevestigt."),
            hero=("makelaar-sleutels", "Een makelaar overhandigt in de hal van een herenhuis de sleutels aan een nieuwe huurder", ""),
            cta_primary=("Plan een demo", "#aanvraag"), cta_secondary=("Bekijk de prijzen", PAGES["prijzen"][region]),
            problem_h="Waar de tijd van een verhuurkantoor naartoe gaat.",
            problem_p="Niet naar het verhuren zelf, maar naar het najagen eromheen.",
            problems=[("phone", "Nabellen over de storting", "Is de borg al binnen? Huurders, verhuurders en collega's vragen het allemaal aan jou."),
                      ("coins", "Geld via de kantoorrekening" if nl else "Papier en wachten op de bank", "Innen en doorstorten kost administratie en brengt risico mee." if nl else "Formulieren, handtekeningen en een bezoek aan de bank voordat de rekening open is."),
                      ("key", "Sleutels zonder zekerheid", "Onder tijdsdruk gaan de sleutels soms over voordat de borg er echt is.")],
            sol_h="Eén borgverzoek. Iedereen ziet de status.",
            sol_bullets=["Borgverzoek in een paar stappen, met controle op het wettelijke maximum.", "De huurder krijgt een herkenbare uitnodiging en stort op zijn eigen rekening.", "Je ziet direct wanneer de bank de storting en blokkering bevestigt.", "Automatische herinneringen, zodat jij niet hoeft te bellen.", "Overdracht van het dossier aan verhuurder of beheerder, met historie."],
            visual="dashboard",
            steps=[("Contract getekend", "Je maakt de borg aan bij het contract."), ("Uitnodiging", "De huurder controleert en bevestigt zijn identiteit."), ("Storting", "Op een rekening op naam van de huurder bij de partnerbank."), ("Bevestiging", "De bank bevestigt. Jij geeft de sleutels."), ("Overdracht", "Het dossier gaat naar verhuurder of beheerder.")],
            benefits=[("Direct", "zie je wanneer de bank de storting bevestigt."), ("0", "stortingen via je kantoorrekening."), ("1 status", "voor huurder, verhuurder en kantoor.")],
            extra="",
            price_h="Wat kost het?",
            price_p=f"Essential kost € {ess['base']} per maand, inclusief {ess['included']} actieve dossiers. Per nieuw dossier betaal je € {ess['new']} eenmalig. Draag je een dossier over aan een beheerder die zelf Depiqo gebruikt, dan telt het daar verder. Huurders betalen niets.",
            faq=[("Kan ik Depiqo gebruiken naast mijn huidige software?", "Ja. In de pilot werk je in Depiqo en exporteer je naar je eigen systeem. Koppelingen bouwen we in de volgorde die pilotpartners nodig hebben."),
                 ("Wie is eigenaar van het dossier na de verhuur?", "De verhuurder of de beheerder die hij aanwijst. Jij draagt het dossier over; de historie blijft bewaard."),
                 ("Wat als de huurder niet stort?", "Depiqo herinnert de huurder automatisch en laat je zien wie nog moet storten. Zonder bevestiging van de bank staat de borg niet op ‘veilig’.")],
            cta="demo", audience="makelaar",
            related=[(AUD["beheerders"][region]["path"], "Voor vastgoedbeheerders", "Als je ook beheert"), (PAGES["prijzen"][region], "Prijzen", "Essential en Professional"),
                     (r_kb(region), "De regels", f"Maximum en termijnen {t['where']}")],
        )

    if key == "beheerders":
        return dict(
            title=(f"Software voor waarborgsommen voor vastgoedbeheerders | Depiqo" if nl else "Software voor huurwaarborgen voor vastgoedbeheerders | Depiqo"),
            desc=f"Alle {terms} in één platform: borgverzoeken, termijnbewaking, eindafrekening, teamrollen en audittrail. Voor vastgoedbeheerders.",
            eyebrow="Voor vastgoedbeheerders",
            h1=f"Alle {terms}. <span class=\"serif\">Eén overzicht, geen gemiste termijnen.</span>",
            lede=f"Honderden {terms}, elk met een eigen begin, einde en wettelijke termijn. Depiqo zet ze in één werkstroom, zodat je team ziet wat er vandaag moet gebeuren en de huurder ziet waar zijn geld staat.",
            hero=("beheerder-laptop", "Een vastgoedbeheerder werkt aan een laptop in een licht kantoor met planten", "cool"),
            cta_primary=("Bereken je voordeel", "#rekentool"), cta_secondary=("Plan een demo", "#aanvraag"),
            problem_h=f"Waarom de {term} meer tijd kost dan nodig.",
            problem_p="Elke borg is een klein financieel dossier. Toch loopt het vaak via mails, Excel en de bank.",
            problems=[("clock", "Termijnen in je hoofd of in Excel", "14 of 30 dagen na het einde van de huur. Eén vergeten dossier is te laat." if nl else "Vrijgave na akkoord of vonnis; in Brussel binnen twee maanden. Dossiers blijven open liggen."),
                      ("phone", "Nabellen en zoeken", "Wie heeft gestort, waar is de plaatsbeschrijving, wie keurde de afrekening goed?"),
                      ("coins", "Geld en administratie", "Borgen op de eigen rekening of verspreid over banken, met handmatige afstemming." if nl else "Rekeningen bij verschillende banken en e-DEPO, met attesten op papier.")],
            sol_h="Depiqo Business: van borgverzoek tot " + end + ".",
            sol_bullets=[f"Dashboard met wat vandaag aandacht vraagt, gesorteerd op termijn.", "Borgverzoeken met controle op het maximum en automatische herinneringen.", "Eindafrekening met foto's en documenten, akkoord of betwisting van de huurder.", "Teamrollen: beheerder, financieel, alleen lezen. Uitbetalen alleen door financieel.", "Audittrail en CSV-export; koppelingen met beheersoftware in Professional."],
            visual="dashboard",
            steps=[("Importeer of maak aan", "Nieuwe borgen bij het contract; bestaande borgen in bulk."), ("Volg de status", "Uitnodiging, identiteit, storting, bevestiging door de bank."), ("Bewaak termijnen", "Waarschuwingen per land en gewest, ruim vooraf."), ("Reken af", "Met bewijs, akkoord of betwisting in hetzelfde dossier."), (end.capitalize(), "Opdracht aan de bank, met vier-ogenprincipe.")],
            benefits=[("1 overzicht", "van alle dossiers, gesorteerd op wat vandaag moet gebeuren."), ("100%", "van de dossiers met een volledige historie: wie deed wat, wanneer."), ("0", "termijnen die ongemerkt verlopen, door waarschuwingen vooraf.")],
            extra=f'<section class="section tone-white" id="rekentool" aria-labelledby="calc-t"><div class="wrap"><div class="section-head"><p class="eyebrow">Rekentool</p><h2 id="calc-t">Hoeveel tijd kost de {term} je team nu?</h2><p>Vul je eigen aantallen in. De uitkomst is een indicatie op basis van jouw aannames.</p></div>{_time_calc(region)}</div></section>',
            price_h="Wat kost het?",
            price_p=f"Professional kost € {pro['base']} per maand, inclusief {pro['included']} actieve dossiers. Daarboven € {pro['ext']} per dossier per maand, of € {pro['dpq']} als de borg op een Depiqo-borgrekening staat. Per nieuw dossier € {pro['new']} eenmalig. Kleinere portefeuille? Essential begint bij € {ess['base']}.",
            faq=[("Hoe lang duurt de invoering?", "In de pilot start je met nieuwe dossiers zodra je account is ingericht. Bestaande borgen importeren we samen uit een export van je beheersoftware."),
                 ("Moeten bestaande borgen naar een Depiqo-borgrekening?", "Nee. Je kunt ze in Depiqo volgen terwijl ze blijven waar ze staan. Alleen nieuwe borgen kunnen, als je dat wilt, op een Depiqo-borgrekening."),
                 ("Wie mag uitbetalen?", "Alleen gebruikers met de rol financieel of beheerder. Een vastgoedbeheerder kan een afrekening opstellen, maar niet zelf uitbetalen."),
                 ("Waar staan onze gegevens?", "In de EU. Je data blijft van jou. Voor de pilot werken we met testgegevens of, na afspraak, met geanonimiseerde dossiers.")],
            cta="demo", audience="vastgoedbeheerder",
            related=[(PAGES["prijzen"][region], "Prijzen en rekentool", "Wat Depiqo jou kost"), (AUD["software"][region]["path"], "Integraties en API", "Koppelen met je beheersoftware"), (PAGES["pilot"][region], "Pilotprogramma", "Test met je eigen proces")],
        )

    if key == "institutioneel":
        return dict(
            title=("Waarborgsommen voor woningcorporaties | Depiqo" if nl else "Huurwaarborgen voor institutionele verhuurders | Depiqo"),
            desc=("Voor woningcorporaties: alle waarborgsommen transparant en toegankelijk, met audittrail, migratie van bestaande borgen en integratie." if nl else "Voor institutionele verhuurders en studentenhuisvesting in Vlaanderen en Brussel: één werkwijze voor alle huurwaarborgen, met audittrail."),
            eyebrow="Voor woningcorporaties" if nl else "Voor institutionele verhuurders",
            h1=f"Duizenden {terms}. <span class=\"serif\">Eén verantwoorde werkwijze.</span>",
            lede=(f"Corporaties en grote verhuurders werken met publieke verantwoording, veel huurders en strenge eisen aan gegevens. Depiqo geeft één werkwijze voor alle {terms}, met een volledige audittrail en een wallet die ook voor kwetsbare huurders begrijpelijk is." if nl else "Institutionele verhuurders, studentenhuisvesting en grote portefeuilles werken met veel huurders, meerdere gewesten en strenge eisen aan rapportering. Depiqo geeft één werkwijze voor alle huurwaarborgen."),
            hero=("institutioneel-gebouw", "Een modern woongebouw met balkons in een Nederlandse of Belgische stad, in middaglicht", "cool"),
            cta_primary=("Plan een kennismaking", "#aanvraag"), cta_secondary=("Bekijk Enterprise", PAGES["prijzen"][region] + "#enterprise"),
            problem_h="Wat schaal moeilijk maakt.",
            problem_p=("Of en hoeveel borg een corporatie vraagt, verschilt per corporatie. Waar het gebeurt, telt elk dossier." if nl else "Voor sociale huur gelden eigen regels; die nemen we per organisatie door."),
            problems=[("chart", "Verantwoording", "Toezicht, accountant en bestuur willen zien dat elk dossier volgens de regels liep."),
                      ("users", "Veel teams, veel locaties", "Verschillende werkwijzen per regio of team maken fouten en vragen."),
                      ("lock", "Gegevens en privacy", "Persoonsgegevens, documenten en bewaartermijnen vragen strakke afspraken.")],
            sol_h="Gebouwd voor verantwoording.",
            sol_bullets=["Audittrail per dossier en een auditlog per organisatie.", "Rollen, vier-ogenprincipe en scheiding tussen teams en entiteiten.", "Migratie van bestaande borgportefeuilles, niet alleen nieuwe contracten.", "Een wallet in eenvoudige taal, bruikbaar met schermlezer.", "Integratie met je beheersysteem via API en webhooks."],
            visual="dashboard",
            steps=[("Verkenning", "Je huidige proces, systemen en eisen."), ("Inrichting", "Rollen, entiteiten, regels en integratie."), ("Migratie", "Bestaande borgen in bulk, met controle."), ("Pilot", "Eén regio of team, met meetpunten."), ("Uitrol", "Alle teams, met SLA en vaste contactpersoon.")],
            benefits=[("1 werkwijze", "voor alle teams, regio's en entiteiten."), ("Volledig", "spoor van wie wat deed, voor accountant en toezicht."), ("B1", "taalniveau als doel voor alle huurdersteksten.")],
            extra="",
            price_h="Wat kost het?",
            price_p="Enterprise is maatwerk op basis van volume, integratie en ondersteuning, met een jaarcontract. Huurders betalen niets.",
            faq=[("Kunnen jullie onze bestaande borgen overnemen?", "Ja. We importeren bestaande dossiers in bulk en volgen ze in Depiqo, ook als het geld blijft waar het staat."),
                 ("Voldoet Depiqo aan de AVG?", "We verwerken alleen wat nodig is, in de EU, met een verwerkersovereenkomst. Voor de lancering doen we een DPIA en een externe pentest."),
                 ("Is de wallet toegankelijk?", "Dat is het doel: eenvoudige taal, goede contrasten en bruikbaar met toetsenbord en schermlezer. We testen dit met huurders in de pilot.")],
            cta="demo", audience="institutioneel",
            related=[(AUD["software"][region]["path"], "Integraties en API", "Koppelen met je systemen"), (PAGES["prijzen"][region] + "#enterprise", "Enterprise", "Maatwerk en SLA"), (PAGES["hoe"][region] + "#veiligheid", "Veiligheid", "Geldstromen en gegevens")],
        )

    if key == "banken":
        return dict(
            title=f"Voor banken: de {term} als depositoproduct | Depiqo",
            desc=f"Depiqo brengt {terms} van vastgoedbeheerders naar een partnerbank: rekeningen op naam van de huurder, blokkering, rente en vrijgave via API.",
            eyebrow="Voor banken en financiële instellingen",
            h1=f"Maak van de {term} <span class=\"serif\">een schaalbaar depositoproduct.</span>",
            lede=f"Elke {term} is een deposito op naam van een huurder, voor gemiddeld een paar jaar. Depiqo brengt die deposito's via vastgoedbeheerders naar één partnerbank, en regelt de onboarding, documenten en vrijgave eromheen.",
            hero=("bank-overleg", "Twee financiële professionals bespreken een uitgeprint schema in een licht, modern kantoor", "cool"),
            cta_primary=("Bespreek een partnership", "#aanvraag"), cta_secondary=("Bekijk de architectuur", "#oplossing"),
            problem_h="Waarom dit voor een bank interessant is.",
            problem_p="En waarom het zonder platform zelden schaalt.",
            problems=[("users", "Nieuwe, jonge klanten", "Huurders openen een rekening op een belangrijk moment: hun nieuwe woning."),
                      ("coins", "Stabiele tegoeden", f"Een {term} staat er meestal zolang de huur loopt. Opnames gebeuren alleen bij {end}."),
                      ("doc", "Maar veel handwerk", "Openen, blokkeren en vrijgeven per huurder kost een bank veel tijd zonder digitale keten.")],
            sol_h="Wat Depiqo doet, en wat de bank doet.",
            sol_bullets=["Depiqo: distributie via beheerders, uitnodiging, documenten, regels per regio, afrekening en akkoord.", "Bank: rekening op naam van de huurder, identificatie, blokkering ten gunste van de verhuurder, rente en uitbetaling.", "Koppeling: API of bestandsuitwisseling, met ondertekende berichten en idempotente verwerking.", "Depiqo houdt nooit geld aan en is geen betaalinstelling."],
            visual="flow",
            steps=[("Verkenning", "Productfit, juridische vorm en volumes."), ("Technische scope", "API of bestanden, identificatie, rapportage."), ("Pilot", "Eén beheerder, beperkt aantal rekeningen."), ("Evaluatie", "Kosten per rekening, operationele last, klantbeleving."), ("Opschalen", "Meer beheerders, meer regio's.")],
            benefits=[("3,5 mln", "huurwoningen in Nederland (JLL, 2025).") if nl else ("2 gewesten", "Vlaanderen en Brussel, met de geblokkeerde rekening op naam van de huurder als vaste vorm."), ("2 à 3 jaar", "typische looptijd van een borg, als indicatie."), ("0", "contant geld of papieren attesten in het proces.")],
            extra="",
            price_h="Het commerciële model",
            price_p="Huurders betalen niets. Beheerders betalen Depiqo een abonnement. Tussen bank en Depiqo bespreken we een vergoeding per rekening of een distributievergoeding. Depiqo rekent in zijn plannen niet op die vergoeding, zodat het product ook zonder werkt.",
            faq=[("Welke juridische vorm heeft de rekening?", "Een rekening op naam van de huurder, geblokkeerd ten gunste van de verhuurder. De precieze vorm per land en gewest leggen we samen met de bank en onze advocaten vast." if nl else "Een geblokkeerde rekening op naam van de huurder, zoals de Vlaamse en Brusselse regels voorzien."),
                 ("Wie doet de identificatie?", "De bank, volgens haar eigen KYC-proces. Depiqo levert de gegevens aan en toont de status."),
                 ("Is er exclusiviteit?", "Te bespreken per land. We beginnen met één partnerbank per markt.")],
            cta="partner", partner_type="bank",
            related=[(AUD["verzekeraars"][region]["path"], "Voor verzekeraars", "Garanties en risico"), (AUD["software"][region]["path"], "Software en API", "Hoe de koppeling werkt"), (PAGES["hoe"][region] + "#veiligheid", "Geldstromen", "Wie houdt het geld aan")],
        )

    if key == "verzekeraars":
        return dict(
            title=f"Voor verzekeraars: garanties voor de {term} | Depiqo",
            desc=f"Depiqo zoekt verzekeraars en garantiepartners voor borggaranties en bescherming van zekerheden, met distributie via vastgoedbeheerders {t['where']}.",
            eyebrow="Voor verzekeraars en garantiepartners",
            h1=f"Nieuwe distributie <span class=\"serif\">voor financiële zekerheid.</span>",
            lede=f"Niet elke huurder kan of wil een {term} in één keer storten. Een garantie kan dat oplossen, als er een verzekeraar is die het risico draagt. Depiqo brengt de distributie, de documenten en de claimsworkflow.",
            hero=("verzekeraar-gesprek", "Een adviseur en een klant bespreken documenten aan een ronde tafel in een licht kantoor", ""),
            cta_primary=("Bespreek risicoproducten", "#aanvraag"), cta_secondary=("Wat we zoeken", "#oplossing"),
            problem_h="Waar een garantiepartner het verschil maakt.",
            problem_p="In Nederland en België bestaan al borggaranties. Depiqo wil ze naast een gewone storting aanbieden, zodat huurder en beheerder kunnen kiezen.",
            problems=[("coins", "De drempel van de borg", "Twee of drie maanden huur vooraf is voor veel huurders een groot bedrag, naast de eerste huur en de verhuizing."),
                      ("shield", "Zekerheid voor de verhuurder", "Een garantie moet even betrouwbaar zijn als geld op een geblokkeerde rekening."),
                      ("doc", "Claims zonder dossier", "Zonder plaatsbeschrijving, afrekening en akkoord is een claim moeilijk te beoordelen.")],
            sol_h="Wat Depiqo kan bieden.",
            sol_bullets=["Distributie via vastgoedbeheerders en makelaars, op het moment van het huurcontract.", "Een volledig dossier per huurder: contract, plaatsbeschrijving, afrekening, akkoord.", "Een claimsworkflow met termijnen en bewijs.", "Geaggregeerde, geanonimiseerde inzichten, alleen met toestemming en binnen de AVG.", "Duidelijke rollen: de verzekeraar draagt het risico, Depiqo bemiddelt niet zonder de juiste vergunning."],
            visual="settlement",
            steps=[("Verkenning", "Welk product, welke markt, welke huurders."), ("Productontwerp", "Dekking, premie, acceptatie en juridische vorm."), ("Vergunning en rollen", "Wie bemiddelt, wie adviseert, wie draagt risico."), ("Pilot", "Beperkte groep beheerders en huurders."), ("Uitrol", "Na evaluatie van claims en klantbeleving.")],
            benefits=[("Toekomst", "Garanties zijn nog niet beschikbaar in Depiqo. We zoeken de juiste partner."), ("1 dossier", "per huurder, met alles wat een claim nodig heeft."), ("B2B2C", "distributie: één beheerder brengt honderden huurders.")],
            extra="",
            price_h="Het commerciële model",
            price_p="De huurder of verhuurder betaalt een premie aan de risicodrager. Depiqo kan een distributie- of servicevergoeding ontvangen, voor zover de regels dat toestaan en altijd transparant voor de klant.",
            faq=[("Wanneer komt dit beschikbaar?", "Nog niet gepland. Eerst lanceren we de borgrekening met een bank. Garanties volgen alleen met een partner die het risico draagt."),
                 ("Mag Depiqo verzekeringen verkopen?", "Niet zonder de juiste vergunning. Daarom werken we met een vergunde partner en leggen we de rollen vooraf vast."),
                 ("Kan een garantie belegde zekerheden beschermen?", "Dat is een van de vragen die we willen onderzoeken: een garantie die een verhuurder dekt als een verpande beleggingsrekening in waarde daalt.")],
            cta="partner", partner_type="verzekeraar",
            related=[(AUD["banken"][region]["path"], "Voor banken", "De borgrekening"), (AUD["beleggen"][region]["path"], "Voor beleggingsplatformen", "Beleggen apart van de borg"), (PAGES["producten"][region], "Producten", "Wat er is en wat komt")],
        )

    if key == "beleggen":
        return dict(
            title=f"Voor beleggingsplatformen: beleggen naast de {term} | Depiqo",
            desc=f"Depiqo Invest: huurders beleggen vrijwillig met eigen geld naast hun {term}, via een vergunde partner. Nu in testversie; we zoeken de partner.",
            eyebrow="Voor beleggingsplatformen",
            h1=f"Beleggen naast de {term}. <span class=\"serif\">Nooit met de borg zelf.</span>",
            lede=f"Huurders die hun {term} op een rekening zien groeien, krijgen vaak ook interesse in sparen en beleggen. Depiqo zoekt een vergunde beleggingspartner om dat verantwoord en vrijwillig aan te bieden, apart van de borg.",
            hero=("beleggen-telefoon", "Een huurder bekijkt aan de keukentafel haar telefoon, met een kop koffie in de hand", ""),
            cta_primary=("Bespreek een integratie", "#aanvraag"), cta_secondary=("Onze uitgangspunten", "#oplossing"),
            problem_h="Waarom we de borg zelf niet beleggen.",
            problem_p="Een verhuurder moet op het volle bedrag kunnen rekenen, ook als de beurs daalt.",
            problems=[("chart", "Koersrisico", "Een portefeuille van € 2.500 is na een daling van 20% nog € 2.000 waard. Dat tekort dekt niemand vanzelf."),
                      ("scale", "Wettelijke vorm", f"De regels voor de {term} gaan uit van geld of specifieke vormen van zekerheid, niet van een vrije beleggingsrekening."),
                      ("lock", "Vergunningen", "Orders doorgeven, adviseren en vermogensbeheer vragen een vergunning. Depiqo doet dat niet zelf.")],
            sol_h="Wat Depiqo Invest doet.",
            sol_bullets=["Vrijwillig beleggen met eigen geld, naast de borg, in de Depiqo-wallet.", "Eerst een kennis- en ervaringstoets; bij onvoldoende kennis een duidelijke waarschuwing.", "Drie portefeuilles met spreiding: defensief, neutraal en offensief. Geen losse aandelen.", "Kosten vooraf in euro's: 0,25% per jaar voor Depiqo plus de fondskosten van de partner.", "Bij de terugbetaling van de borg: de keuze om het bedrag door te beleggen.", "Orders, bewaring en de wettelijke toetsen bij de vergunde partner. Depiqo geeft geen advies."],
            visual="phone",
            steps=[("Verkenning", "Productfit, doelgroep en vergunningsrollen."), ("Technische scope", "Rekeningen, orders, rapportage en kosten via API."), ("Juridische toets", "Per land: wat mag, wat niet."), ("Pilot", "Kleine groep huurders, eigen geld, duidelijke risicotekst."), ("Evaluatie", "Gebruik, kosten en klantbegrip.")],
            benefits=[("Testversie", "De volledige beleggingsflow werkt in de Depiqo-testomgeving, met een gesimuleerde partner."), ("Eigen geld", "Alleen vrijwillig, naast de borg, nooit de borg zelf."), ("Vooraf", "zichtbare kosten, en een vergelijking met sparen.")],
            extra="",
            price_h="Het commerciële model",
            price_p="Een transparante vergoeding op het belegde vermogen of een vaste dienstvergoeding, betaald door de huurder die er zelf voor kiest. Bij kleine bedragen is dit beperkt, daarom zien we beleggen als aanvullende dienst, niet als kern van Depiqo.",
            faq=[("Waarom geen ETF's als huurwaarborg?", "Omdat de waarde kan dalen onder het borgbedrag. Een verpande portefeuille kan alleen met een buffer of een garantie van een derde, en dat kost geld. We onderzoeken het, maar beloven het niet."),
                 ("Wie draagt de vergunning?", "De beleggingspartner. Depiqo toont de dienst in de wallet en verwijst door, binnen de rol die de regels toestaan."),
                 ("Welke producten?", "Eerst eenvoudige, gespreide producten met lage kosten. Geen losse aandelen.")],
            cta="partner", partner_type="beleggingsplatform",
            related=[(AUD["huurders"][region]["path"], "Voor huurders", "Wat de huurder ziet"), (AUD["verzekeraars"][region]["path"], "Voor verzekeraars", "Garanties op zekerheden"), (PAGES["producten"][region], "Producten", "Status per product")],
        )

    if key == "software":
        return dict(
            title=f"Voor softwarepartners: de {term} via API | Depiqo",
            desc=f"Integreer de {term} in je vastgoedbeheersoftware: borgverzoeken, statussen en vrijgave via API en webhooks, of als white-labelmodule. {t['where'].capitalize()}.",
            eyebrow="Voor vastgoedsoftware en API-partners",
            h1=f"De {term} in je eigen product. <span class=\"serif\">Zonder zelf een bank te koppelen.</span>",
            lede=f"Je klanten beheren huurcontracten in jouw software. De {term} hoort erbij, maar vraagt banken, regels en termijnen. Depiqo levert die keten als API of als module, zodat je klanten niet naar een tweede systeem hoeven.",
            hero=("software-team", "Een klein softwareteam werkt samen aan een groot scherm in een licht kantoor", "cool"),
            cta_primary=("Ontdek de API", "#oplossing"), cta_secondary=("Bespreek een integratie", "#aanvraag"),
            problem_h=f"Waarom de {term} zelden goed in beheersoftware zit.",
            problem_p="Het lijkt een veld in het contract. In werkelijkheid is het een financieel proces.",
            problems=[("bank", "Bankkoppelingen", "Rekeningen, blokkering en vrijgave per bank bouwen is duur en traag."),
                      ("scale", "Regels per regio", "Maxima, termijnen en vormen verschillen per land en gewest, en veranderen."),
                      ("users", "Twee systemen", "Beheerders willen niet nog een systeem naast hun beheersoftware.")],
            sol_h="Wat je via Depiqo krijgt.",
            sol_bullets=["REST-API voor borgverzoeken, statussen, documenten en afrekeningen.", "Ondertekende webhooks bij elke statuswijziging.", "Regels per land en gewest, met versie en controledatum.", "White-labelwallet voor huurders, of een ingebedde flow.", "Sandbox met gesimuleerde bankberichten om tegen te ontwikkelen."],
            visual="api",
            steps=[("Kennismaking", "Je product, je klanten en hun proces."), ("Sandbox", "Toegang tot de testomgeving met voorbeelddossiers."), ("Integratie", "API en webhooks, of de module in je interface."), ("Pilot", "Met een gezamenlijke klant."), ("Lancering", "Gezamenlijke propositie en afspraken over omzet.")],
            benefits=[("Nu", "CSV-export en een sandbox in het prototype."), ("Gepland", "Publieke API en webhooks, in de volgorde die partners nodig hebben."), ("Partner", "Omzetdeling of inkoop, per partner af te spreken.")],
            extra="",
            price_h="Het commerciële model",
            price_p="Je klant betaalt via jou of rechtstreeks het Depiqo-abonnement. Voor softwarepartners spreken we een omzetdeling of inkoopprijs af, afhankelijk van wie de klant beheert.",
            faq=[("Is de API al beschikbaar?", "De publieke API is gepland. In de pilot werken we met export en gerichte koppelingen, en bouwen we de API samen met de eerste partners."),
                 ("Hoe zit het met beveiliging?", "Webhooks zijn ondertekend met HMAC en worden één keer verwerkt. Toegang loopt via sleutels per organisatie met rechten per rol."),
                 ("Kunnen we het onder onze eigen naam aanbieden?", "Ja, als white-label. De bankpartner en de wettelijke informatie blijven wel zichtbaar voor de huurder.")],
            cta="partner", partner_type="software",
            related=[(AUD["beheerders"][region]["path"], "Voor vastgoedbeheerders", "Wat je klanten zien"), (AUD["banken"][region]["path"], "Voor banken", "De bankkant van de keten"), (PAGES["producten"][region], "Producten", "Business, Wallet en API")],
        )
    raise KeyError(key)


def r_kb(region):
    return "nl/waarborgsom.html" if region == "nl" else "be/huurwaarborg.html"


def _tenant_options(region):
    t = REGIONS[region]
    return f"""<section class="section tone-white" id="mogelijkheden" aria-labelledby="mog-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Je mogelijkheden</p><h2 id="mog-t">Wat je met je {t['term']} kunt.</h2><p>Sparen op je borg, en beleggen met eigen geld ernaast. Allebei in dezelfde app.</p></div>
    <div class="opt-grid">
      <div class="opt"><div class="row">{icon('bank')}<span class="badge b-launch">Bij lancering</span></div><h3>Sparen op je borgrekening</h3><p>Je {t['term']} staat op jouw naam bij de partnerbank. De rente die de bank uitkeert, is voor jou. Geen risico op koersverlies; tegoeden vallen onder de depositogarantie.</p><small>De rente hangt af van de bank en kan veranderen.</small></div>
      <div class="opt"><div class="row">{icon('chart')}<span class="badge b-launch">In testversie</span></div><h3>Beleggen met Depiqo Invest</h3><p>Met eigen geld, naast je {t['term']}. Je beantwoordt eerst een paar vragen over je kennis en doelen, kiest een portefeuille (defensief, neutraal of offensief) en ziet de kosten vooraf. De vergunde beleggingspartner bewaart je beleggingen op jouw naam. Bij de terugbetaling van je borg kun je kiezen om dat bedrag door te beleggen.</p><small>Hogere mogelijke opbrengst, maar je kunt ook geld verliezen. Kosten: 0,25% per jaar voor Depiqo plus fondskosten. Live zodra de partner is aangesloten.</small></div>
    </div>
  </div>
</section>"""


# ---------------------------------------------------------------- render

def build(ctx, region, key):
    c = content(key, region)
    a = AUD[key][region]
    L = ctx.link
    t = REGIONS[region]
    slot, alt, tone = c["hero"]

    def href(x):
        return x if x.startswith("#") else L(x)

    crumbs = (f'<nav class="crumbs" aria-label="Kruimelpad"><ol><li><a href="{L(PAGES["home"][region])}">Depiqo</a></li>'
              f'<li>{"Partners" if AUD[key]["group"] == "partners" else "Voor wie"}</li><li aria-current="page">{a["label"]}</li></ol></nav>')
    problems = "".join(f'<div class="card reveal">{icon(i)}<h3>{h}</h3><p>{p}</p></div>' for i, h, p in c["problems"])
    cols = "grid-4" if len(c["problems"]) == 4 else "grid-3"
    bullets = "".join(f"<li>{b}</li>" for b in c["sol_bullets"])
    visual = {"phone": lambda: f'<div class="center-mock">{phone_mock(region)}</div>', "dashboard": lambda: dashboard_mock(region),
              "settlement": lambda: settlement_mock(region), "flow": lambda: _flow_bank(region), "api": _api_mock}[c["visual"]]()
    steps = "".join(f'<li class="reveal"><h3>{h}</h3><p>{p}</p></li>' for h, p in c["steps"])
    benefits = "".join(f'<div class="benefit reveal"><b>{b}</b><p>{p}</p></div>' for b, p in c["benefits"])
    related = "".join(f'<a href="{L(p)}">{escape(n)}<span>{escape(d)}</span></a>' for p, n, d in c["related"])

    if c["cta"] == "tenant":
        cta_block = f"""<section class="section tone-sand" id="aanvraag" aria-labelledby="cta-t">
  <div class="wrap demo-band">
    <div class="split-copy">
      <p class="eyebrow">Heb je een uitnodiging gekregen?</p>
      <h2 id="cta-t">Open de link uit je e-mail. <span class="serif">En controleer eerst.</span></h2>
      <ul class="checks">
        <li>Het webadres begint met het officiële Depiqo-domein.</li>
        <li>Je ziet de naam van je verhuurder, het adres en het bedrag. Kloppen die?</li>
        <li>Je stort alleen op een rekening op jouw eigen naam.</li>
        <li>Depiqo vraagt nooit om je bankcode of een betaling via een link in een sms.</li>
      </ul>
      <div class="cta-row"><a class="btn btn-primary" href="{APP_LOGIN}">Inloggen in je wallet</a><a class="link-arrow" href="{L(region + '/echt-borgverzoek-herkennen.html')}">Twijfel je? Lees dit eerst</a></div>
    </div>
    <div class="center-mock">{phone_mock(region, compact=True)}</div>
  </div>
</section>"""
    else:
        audience = c.get("audience", key)
        cta_title = {"demo": "Plan een demo", "verhuurder": "Vraag toegang aan", "partner": "Plan een gesprek"}[c["cta"]]
        cta_block = f"""<section class="section tone-sand" id="aanvraag" aria-labelledby="cta-t">
  <div class="wrap demo-band">
    <div class="split-copy">
      <p class="eyebrow">Volgende stap</p>
      <h2 id="cta-t">{cta_title}.</h2>
      <p>{_cta_text(c['cta'], key, t)}</p>
      <ul class="checks"><li>Reactie binnen twee werkdagen.</li><li>Geen kosten of verplichtingen.</li><li>We gebruiken je gegevens alleen voor deze aanvraag.</li></ul>
    </div>
    {lead_form(region, key, c['cta'], audience, c.get('partner_type', ''))}
  </div>
</section>"""

    return f"""
<section class="page-hero has-photo" aria-labelledby="ph-t">
  <div class="wrap">
    <div class="copy">
      {crumbs}
      <p class="eyebrow">{c['eyebrow']}</p>
      <h1 id="ph-t">{c['h1']}</h1>
      <p class="lede">{c['lede']}</p>
      <div class="cta-row"><a class="btn btn-primary" href="{href(c['cta_primary'][1])}">{c['cta_primary'][0]}</a><a class="btn btn-secondary" href="{href(c['cta_secondary'][1])}">{c['cta_secondary'][0]}</a></div>
    </div>
    {photo(ctx, slot, alt, "r-43", tone=tone, eager=True)}
  </div>
</section>

<section class="section tone-white" aria-labelledby="pr-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">De uitdaging</p><h2 id="pr-t">{c['problem_h']}</h2><p>{c['problem_p']}</p></div>
    <div class="{cols}">{problems}</div>
  </div>
</section>

<section class="section tone-off" id="oplossing" aria-labelledby="so-t">
  <div class="wrap split wide-right">
    <div class="split-copy"><p class="eyebrow">Wat Depiqo doet</p><h2 id="so-t">{c['sol_h']}</h2><ul class="checks">{bullets}</ul></div>
    <div class="reveal">{visual}<p class="demo-note">Voorbeeld met fictieve gegevens</p></div>
  </div>
</section>

<section class="section tone-white" aria-labelledby="st-t">
  <div class="wrap">
    <div class="section-head"><p class="eyebrow">Hoe het werkt</p><h2 id="st-t">In {len(c['steps'])} stappen.</h2></div>
    <ol class="process">{steps}</ol>
  </div>
</section>

<section class="section tone-mint tight" aria-label="Voordelen">
  <div class="wrap"><div class="benefit-band">{benefits}</div></div>
</section>
{c['extra']}
<section class="section tone-off" aria-labelledby="pp-t">
  <div class="wrap split top">
    <div class="split-copy"><p class="eyebrow">Prijs</p><h2 id="pp-t">{c['price_h']}</h2><p>{c['price_p']}</p><a class="link-arrow" href="{L(PAGES['prijzen'][region])}">Alle prijzen</a></div>
    <div class="split-copy"><p class="eyebrow">Veelgestelde vragen</p>{faq_html(c['faq'])}</div>
  </div>
</section>
{cta_block}
<section class="section tone-white tight" aria-labelledby="rl-t">
  <div class="wrap"><h2 id="rl-t" class="h3-like">Lees verder</h2><div class="related-links">{related}</div><p class="fineprint">Depiqo is in ontwikkeling. Informatie gecontroleerd op {CHECKED_NL}; geen juridisch of financieel advies.</p></div>
</section>
"""


def _cta_text(kind, key, t):
    if kind == "demo":
        return f"In 30 minuten lopen we met jou door een {t['term']} van begin tot eind, met jullie werkwijze als uitgangspunt."
    if kind == "verhuurder":
        return "Laat weten hoeveel woningen je verhuurt. We nemen contact op als er een plaats in de pilot vrij is."
    return {"banken": "Een verkennend gesprek over productfit, juridische vorm en de technische keten.",
            "verzekeraars": "Een verkennend gesprek over borggaranties, risicoverdeling en de rollen van elke partij.",
            "beleggen": "Een verkennend gesprek over vrijwillig beleggen naast de borg, binnen jullie vergunning.",
            "software": "Een technische kennismaking en toegang tot de sandbox."}.get(key, "Een verkennend gesprek.")


def meta(region, key):
    c = content(key, region)
    return c["title"], c["desc"], c["faq"]
