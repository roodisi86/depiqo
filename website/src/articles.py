"""SEO landing pages. Every legal statement is tied to a source in `sources`.
Checked on 18 October 2026. Re-check before every publication."""

SRC = {
    "vh_borg": ("Volkshuisvesting Nederland — Waarborgsom", "https://www.volkshuisvestingnederland.nl/onderwerpen/huren-en-wonen/huurbescherming-en-huurcontracten/waarborgsom"),
    "vh_wgv": ("Volkshuisvesting Nederland — Landelijke regels van goed verhuurderschap", "https://www.volkshuisvestingnederland.nl/onderwerpen/huren-en-wonen/wet-goed-verhuurderschap/landelijke-regels-van-goed-verhuurderschap"),
    "rijk": ("Rijksoverheid — Nieuwe regels voor verhuurders en verhuurbemiddelaars per 1 juli 2023", "https://www.rijksoverheid.nl/onderwerpen/woning-verhuren/vraag-en-antwoord/nieuwe-regels-voor-verhuurders-en-verhuurbemiddelaars-1-juli-2023"),
    "vl": ("Vlaanderen.be — Huurwaarborg", "https://www.vlaanderen.be/huurprijs-en-huurwaarborg/huurwaarborg"),
    "wikifin": ("Wikifin (FSMA) — Wat is de huurwaarborg?", "https://www.wikifin.be/nl/woning-en-hypothecaire-lening/woning-huren-verhuren/wat-de-huurwaarborg"),
    "bru": ("be.brussels — Wijziging van de huurwetgeving (november 2024)", "https://be.brussels/nl/huisvesting/wijziging-van-de-huurwetgeving-november-2024"),
    "jubel": ("Jubel.be — Brusselse huisvesting: waakzaamheid vereist voor verhuurders (12 juli 2024)", "https://www.jubel.be/brusselse-huisvesting-waakzaamheid-vereist-voor-verhuurders"),
}

ARTICLES = []


def art(**kw):
    ARTICLES.append(kw)


# ---------------------------------------------------------------- NEDERLAND
art(
    path="nl/waarborgsom.html", region="nl", kind="article",
    crumb="Waarborgsom",
    title="Waarborgsom huurwoning: maximum, terugbetaling en regels | Depiqo",
    desc="Hoe hoog mag de waarborgsom zijn en wanneer moet hij terug? De regels sinds 1 juli 2023: maximaal twee maanden kale huur, terug binnen 14 of 30 dagen.",
    h1="Waarborgsom voor een huurwoning: de regels in Nederland",
    lede="Sinds 1 juli 2023 gelden landelijke regels voor de waarborgsom. Hier lees je hoe hoog de borg mag zijn, wanneer hij terug moet en wat een verhuurder mag verrekenen.",
    summary=["Maximaal twee maanden <strong>kale</strong> huur.",
             "Terug binnen 14 dagen als er niets te verrekenen is.",
             "Terug binnen 30 dagen als de verhuurder kosten verrekent.",
             "Normale slijtage mag niet van de borg af."],
    sections=[
        ("wat", "Wat is een waarborgsom?",
         "<p>De waarborgsom, vaak kortweg borg genoemd, is een bedrag dat de huurder aan het begin van de huur betaalt. Het dient als zekerheid voor de verhuurder: als de huurder bij vertrek schade achterlaat of nog huur verschuldigd is, kan de verhuurder dat met de borg verrekenen. Is er niets te verrekenen, dan krijgt de huurder het volledige bedrag terug.</p>"
         "<p>In België heet hetzelfde de <em>huurwaarborg</em>, maar daar gelden andere regels. Lees daarvoor <a href=\"{be/huurwaarborg.html}\">de huurwaarborg in België</a>.</p>"),
        ("maximum", "Hoe hoog mag de waarborgsom zijn?",
         "<p>Sinds 1 juli 2023 mag de waarborgsom voor een woning <strong>maximaal twee maanden kale huur</strong> zijn. Kale huur is de huurprijs zonder servicekosten en zonder kosten voor gas, water en licht.</p>"
         "<p><strong>Voorbeeld.</strong> De totale huur is € 1.350 per maand, waarvan € 150 servicekosten. De kale huur is € 1.200. De borg mag dan maximaal € 2.400 zijn.</p>"
         "<p>Is de borg hoger? Dan kan de huurder na het ingaan van de huur de rechter vragen de borg te verlagen. Wat te veel is betaald, moet de verhuurder terugbetalen. Voor bedrijfsruimte gelden deze regels niet.</p>"),
        ("terug", "Wanneer moet de waarborgsom terug?",
         "<p>De wet noemt twee termijnen na het einde van de huur:</p>"
         "<ul><li><strong>14 dagen</strong> als de huurder de woning volgens de afspraken en zonder schade heeft achtergelaten.</li>"
         "<li><strong>30 dagen</strong> als de verhuurder kosten aftrekt. Het restbedrag moet dan binnen 30 dagen terug.</li></ul>"
         "<p>Voor beheerders betekent dit: de eindinspectie en de afrekening moeten snel na het vertrek klaar zijn. Lees meer in <a href=\"{nl/waarborgsom-terugkrijgen.html}\">waarborgsom terugkrijgen</a>.</p>"),
        ("verrekenen", "Wat mag een verhuurder verrekenen?",
         "<div class=\"compare-scroll\"><table class=\"compare\"><thead><tr><th>Mag wel verrekend worden</th><th>Mag niet verrekend worden</th></tr></thead><tbody>"
         "<tr><td>Schade aan de woning door de huurder</td><td>Normale slijtage</td></tr>"
         "<tr><td>Achterstallige huur</td><td>Schade door slecht of achterstallig onderhoud van de verhuurder</td></tr>"
         "<tr><td>Achterstallige servicekosten</td><td></td></tr>"
         "<tr><td>Een achterstallige energieprestatievergoeding</td><td></td></tr></tbody></table></div>"
         "<p>Een goede verrekening is onderbouwd: een opleverrapport, foto's van bij het begin en het einde van de huur, en een offerte of factuur voor het herstel.</p>"),
        ("rente", "Krijgt de huurder rente over de waarborgsom?",
         "<p>De landelijke regels zeggen niets over rente op de waarborgsom. Of de huurder rente krijgt, hangt af van de afspraken in het huurcontract en van waar het geld staat. Dat is anders dan in België, waar de rente op een geblokkeerde huurwaarborgrekening voor de huurder is.</p>"),
        ("geschil", "Wat als huurder en verhuurder het oneens zijn?",
         "<p>Komen huurder en verhuurder er samen niet uit, dan kan de huurder een melding doen bij de gemeente, die toeziet op de regels van goed verhuurderschap, of naar de rechter stappen. De Huurcommissie behandelt geschillen over de borg niet.</p>"),
        ("beheerders", "Wat betekent dit voor vastgoedbeheerders?",
         "<p>Voor een beheerder met honderden huurders is elke borg een klein dossier met een vaste deadline. De risico's zitten in drie dingen: een te hoge borg vragen, een termijn missen en een verrekening die je niet kunt onderbouwen. <a href=\"{nl/waarborgsom-voor-verhuurders.html}\">Lees hoe je de waarborgsom als beheerder goed regelt.</a></p>"),
    ],
    sources=["vh_borg", "vh_wgv", "rijk"],
    related=[("nl/waarborgsom-terugkrijgen.html", "Waarborgsom terugkrijgen", "Termijnen, stappen en wat je doet als de borg niet terugkomt."),
             ("nl/waarborgsom-voor-verhuurders.html", "Waarborgsom voor verhuurders", "Een werkwijze die past bij de regels.")],
    alt="be/huurwaarborg.html",
)

art(
    path="nl/waarborgsom-terugkrijgen.html", region="nl", kind="article",
    crumb="Waarborgsom terugkrijgen", parent=("Waarborgsom", "nl/waarborgsom.html"),
    title="Waarborgsom terugkrijgen: termijnen en stappen | Depiqo",
    desc="Je borg moet binnen 14 dagen terug, of binnen 30 dagen als er kosten worden verrekend. Zo krijg je je waarborgsom terug en dit doe je als dat niet gebeurt.",
    h1="Waarborgsom terugkrijgen: zo werkt het",
    lede="Na het einde van je huur heeft de verhuurder een vaste termijn om je borg terug te betalen. Met een goede oplevering en een paar foto's voorkom je de meeste discussies.",
    summary=["Zonder kosten: borg terug binnen 14 dagen.",
             "Met verrekening: restbedrag terug binnen 30 dagen.",
             "Vraag om een opleverrapport en maak zelf foto's.",
             "Geen geld? Herinner schriftelijk, meld bij de gemeente of stap naar de rechter."],
    sections=[
        ("termijnen", "Hoe snel moet de borg terug?",
         "<p>Als je de woning volgens de afspraken en zonder schade achterlaat, moet de verhuurder de waarborgsom <strong>binnen 14 dagen</strong> terugbetalen. Trekt de verhuurder kosten af, dan moet het restbedrag <strong>binnen 30 dagen</strong> op je rekening staan.</p>"
         "<p>Kosten die de verhuurder mag aftrekken zijn schade die jij hebt veroorzaakt, achterstallige huur en achterstallige servicekosten of energieprestatievergoeding. Normale slijtage mag niet van je borg af.</p>"),
        ("stappen", "Stappen om je borg zonder discussie terug te krijgen",
         "<ol class=\"check-steps\">"
         "<li><strong>Zoek je beginsituatie op.</strong> Het opleverrapport en de foto's van bij de start van de huur zijn je beste bewijs.</li>"
         "<li><strong>Plan de eindinspectie.</strong> Loop samen met de verhuurder of beheerder door de woning en laat afspraken op papier zetten.</li>"
         "<li><strong>Maak zelf foto's.</strong> Fotografeer elke ruimte op de dag dat je de sleutels inlevert, met datum.</li>"
         "<li><strong>Geef je rekeningnummer schriftelijk door.</strong> Zo kan de verhuurder niet zeggen dat hij niet wist waar het geld heen moest.</li>"
         "<li><strong>Vraag om een onderbouwde afrekening.</strong> Wordt er iets ingehouden, vraag dan om een overzicht met foto's en een offerte of factuur.</li></ol>"),
        ("niet-terug", "Wat als je de borg niet terugkrijgt?",
         "<p>Stuur eerst een schriftelijke herinnering met de datum waarop de termijn verliep en een nieuwe uiterste datum. Helpt dat niet, dan kun je een melding doen bij de gemeente, die toeziet op de regels van goed verhuurderschap. Je kunt ook naar de kantonrechter. De Huurcommissie behandelt geschillen over de borg niet.</p>"
         "<div class=\"callout\"><strong>Let op bij oudere contracten.</strong> Voor huurcontracten die vóór 1 augustus 2003 zijn ingegaan, gelden andere regels voor de staat waarin je de woning moet achterlaten. Kijk dan goed in je contract.</div>"),
        ("depiqo", "Hoe Depiqo hierbij helpt",
         "<p>Gebruikt je verhuurder of beheerder Depiqo, dan zie je in de app waar je borg staat, wanneer de termijn verloopt en welke kosten er eventueel worden voorgesteld. Je kunt akkoord gaan of betwisten, met het bewijs erbij. Depiqo beslist zelf niet over een geschil.</p>"),
    ],
    sources=["vh_borg", "rijk"],
    related=[("nl/waarborgsom.html", "Waarborgsom: de regels", "Maximum, verrekening en rente."),
             ("nl/echt-borgverzoek-herkennen.html", "Een echt borgverzoek herkennen", "Zo voorkom je dat je je borg aan een oplichter betaalt.")],
    alt="be/huurwaarborg-vrijgeven.html",
)

art(
    path="nl/waarborgsom-voor-verhuurders.html", region="nl", kind="article",
    crumb="Waarborgsom voor verhuurders", parent=("Waarborgsom", "nl/waarborgsom.html"),
    title="Waarborgsom beheren als verhuurder of vastgoedbeheerder | Depiqo",
    desc="Een werkwijze voor verhuurders en vastgoedbeheerders die de waarborgsom correct willen regelen: van maximum en administratie tot terugbetaling binnen 14 of 30 dagen.",
    h1="De waarborgsom beheren als verhuurder of vastgoedbeheerder",
    lede="De regels voor de waarborgsom zijn kort, maar in een portefeuille van honderden woningen wordt elke borg een dossier met een deadline. Zo houd je dat beheersbaar.",
    summary=["Controleer het maximum bij elk nieuw contract: twee maanden kale huur.",
             "Leg de beginsituatie vast met foto's en een opleverrapport.",
             "Plan de eindinspectie zo dat je binnen 14 of 30 dagen kunt terugbetalen.",
             "Onderbouw elke verrekening met bewijs."],
    sections=[
        ("start", "Bij de start van de huur",
         "<ul><li><strong>Bereken het maximum op de kale huur.</strong> Servicekosten tellen niet mee. Een te hoge borg kan de huurder via de rechter laten verlagen.</li>"
         "<li><strong>Leg de beginsituatie vast.</strong> Een opleverrapport met foto's per ruimte, ondertekend door de huurder, is later je belangrijkste bewijs.</li>"
         "<li><strong>Registreer de ontvangst.</strong> Noteer per huurder het bedrag, de datum van ontvangst en waar het geld staat.</li></ul>"),
        ("administratie", "Tijdens de huur: de administratie",
         "<p>De wet verplicht niet om de waarborgsom op een aparte rekening te zetten. Toch kiezen veel beheerders daarvoor, omdat het geld van huurders dan niet vermengd raakt met het eigen vermogen. Het maakt ook de controle door een accountant eenvoudiger.</p>"
         "<p>Houd per dossier bij: huurder, adres, bedrag, startdatum, verwachte einddatum en eventuele wijzigingen in de huur.</p>"),
        ("einde", "Aan het einde: terugbetalen binnen de termijn",
         "<p>De termijn loopt vanaf het einde van de huur: 14 dagen als je niets verrekent, 30 dagen als je wel kosten aftrekt. Plan de eindinspectie daarom op of vlak na de laatste huurdag, niet weken later.</p>"
         "<div class=\"compare-scroll\"><table class=\"compare\"><thead><tr><th>Moment</th><th>Wat je doet</th><th>Deadline</th></tr></thead><tbody>"
         "<tr><td>Opzegging ontvangen</td><td>Eindinspectie plannen, huurder informeren</td><td>Zo snel mogelijk</td></tr>"
         "<tr><td>Laatste huurdag</td><td>Eindinspectie met foto's, sleutels in</td><td>Dag 0</td></tr>"
         "<tr><td>Geen kosten</td><td>Volledige borg terugbetalen</td><td>Binnen 14 dagen</td></tr>"
         "<tr><td>Wel kosten</td><td>Afrekening met bewijs sturen, restbedrag betalen</td><td>Binnen 30 dagen</td></tr></tbody></table></div>"),
        ("verrekenen", "Verrekenen zonder discussie",
         "<p>Je mag schade, achterstallige huur, achterstallige servicekosten en een achterstallige energieprestatievergoeding verrekenen. Normale slijtage en gevolgen van achterstallig onderhoud door de verhuurder niet. Zet elke post apart in de afrekening, met een foto en een offerte of factuur.</p>"),
        ("depiqo", "Hoe Depiqo dit proces ondersteunt",
         "<p>Depiqo Business zet elke waarborgsom in één overzicht, met de status, het bedrag en de volgende actie. Je ziet welke termijnen binnenkort verlopen, stelt een eindafrekening op met bewijs en legt het akkoord van de huurder vast. Depiqo is in ontwikkeling; <a href=\"{nl/pilot.html}\">lees over het pilotprogramma</a>.</p>"),
    ],
    sources=["vh_borg", "vh_wgv", "rijk"],
    related=[("nl/waarborgsom.html", "Waarborgsom: de regels", "Maximum, termijnen en verrekening."),
             ("nl/pilot.html", "Pilotprogramma", "Test Depiqo met je eigen proces.")],
    alt=None,
)

# ---------------------------------------------------------------- BELGIË
art(
    path="be/huurwaarborg.html", region="be", kind="article",
    crumb="Huurwaarborg",
    title="Huurwaarborg in België: regels per gewest | Depiqo",
    desc="Hoeveel mag de huurwaarborg zijn en hoe moet hij gesteld worden? De regels voor Vlaanderen en Brussel naast elkaar: maximum, vormen en vrijgave.",
    h1="Huurwaarborg in België: de regels per gewest",
    lede="In België bepaalt het gewest de regels voor de huurwaarborg. Vlaanderen en Brussel verschillen in maximum, toegestane vormen en termijnen.",
    summary=["Vlaanderen: maximaal 3 maanden huur (contracten vanaf 1 januari 2019).",
             "Brussel: maximaal 2 maanden huur zonder lasten.",
             "De waarborg hoort op een rekening op naam van de huurder, niet op die van de verhuurder.",
             "Vrijgave alleen met akkoord van beide partijen of een rechterlijke beslissing."],
    sections=[
        ("wat", "Wat is een huurwaarborg?",
         "<p>De huurwaarborg is een zekerheid voor de verhuurder dat de huurder zijn verplichtingen nakomt. Anders dan in Nederland mag de verhuurder het geld in België niet zelf bijhouden. Het staat op een geblokkeerde rekening op naam van de huurder of wordt via een andere wettelijke vorm gesteld.</p>"
         "<p>Zoek je de Nederlandse regels? Lees dan <a href=\"{nl/waarborgsom.html}\">waarborgsom in Nederland</a>.</p>"),
        ("vergelijking", "Vlaanderen en Brussel naast elkaar",
         "<div class=\"compare-scroll\"><table class=\"compare\"><thead><tr><th></th><th>Vlaanderen</th><th>Brussel</th></tr></thead><tbody>"
         "<tr><th scope=\"row\">Maximum</th><td>3 maanden huur (contracten vanaf 1 januari 2019)</td><td>2 maanden huur, zonder lasten</td></tr>"
         "<tr><th scope=\"row\">Vormen</th><td>Geblokkeerde rekening op naam van de huurder, zakelijke zekerheid (obligatie of kapitalisatiebon), tussenkomst OCMW, of met akkoord van de verhuurder een persoonlijke borg</td><td>Geïndividualiseerde rekening op naam van de huurder bij een door de FSMA erkende instelling, bankwaarborg via het OCMW, progressief opgebouwde bankwaarborg of zakelijke zekerheid. Persoonlijke borg alleen bij studentenhuur.</td></tr>"
         "<tr><th scope=\"row\">Cash betalen</th><td>Niet de bedoeling: storten op een rekening op naam van de huurder</td><td>Niet toegestaan</td></tr>"
         "<tr><th scope=\"row\">Teruggave</th><td>Na akkoord van beide partijen of een vonnis</td><td>Binnen 2 maanden nadat de huurder de woning verlaten heeft</td></tr></tbody></table></div>"
         "<p>Meer detail per gewest: <a href=\"{be/huurwaarborg-vlaanderen.html}\">huurwaarborg in Vlaanderen</a> en <a href=\"{be/huurwaarborg-brussel.html}\">huurwaarborg in Brussel</a>.</p>"),
        ("rekening", "De geblokkeerde huurwaarborgrekening",
         "<p>De meest gebruikte vorm is een geblokkeerde rekening op naam van de huurder bij een bank. Geen van beide partijen kan tijdens de huur zomaar over het geld beschikken. De interesten op die rekening zijn voor de huurder. Wikifin, het educatieve platform van de FSMA, waarschuwt uitdrukkelijk: stort de huurwaarborg nooit zomaar op de rekening van de eigenaar.</p>"),
        ("vrijgave", "Hoe komt de huurwaarborg vrij?",
         "<p>De bank geeft de waarborg pas vrij op basis van een akkoord van huurder en verhuurder, of van een beslissing van de vrederechter. <a href=\"{be/huurwaarborg-vrijgeven.html}\">Lees hoe de vrijgave stap voor stap werkt.</a></p>"),
        ("wallonie", "En Wallonië?",
         "<p>Wallonië heeft eigen regels. Depiqo richt zich voorlopig op Vlaanderen en Brussel, en deze pagina behandelt Wallonië daarom niet.</p>"),
    ],
    sources=["vl", "bru", "jubel", "wikifin"],
    related=[("be/huurwaarborg-vlaanderen.html", "Huurwaarborg Vlaanderen", "Maximum, vormen en vrijgave."),
             ("be/huurwaarborg-brussel.html", "Huurwaarborg Brussel", "De regels sinds november 2024.")],
    alt="nl/waarborgsom.html",
)

art(
    path="be/huurwaarborg-vlaanderen.html", region="be", kind="article",
    crumb="Vlaanderen", parent=("Huurwaarborg", "be/huurwaarborg.html"),
    title="Huurwaarborg Vlaanderen: maximum, vormen en vrijgave | Depiqo",
    desc="De huurwaarborg in Vlaanderen: maximaal drie maanden huur voor contracten vanaf 2019, vier toegestane vormen en vrijgave alleen met akkoord of vonnis.",
    h1="Huurwaarborg in Vlaanderen",
    lede="Het Vlaamse Woninghuurdecreet regelt de huurwaarborg voor huurcontracten die vanaf 1 januari 2019 zijn gesloten. Voor oudere contracten gelden de vroegere regels.",
    summary=["Maximaal 3 maanden huur voor contracten vanaf 1 januari 2019.",
             "Vier vormen, die je niet mag combineren.",
             "Het geld staat op naam van de huurder, niet van de verhuurder.",
             "Vrijgave na akkoord van beide partijen of na tussenkomst van de vrederechter."],
    sections=[
        ("maximum", "Hoeveel mag de huurwaarborg zijn?",
         "<p>Voor huurcontracten vanaf 1 januari 2019 mag de verhuurder een waarborg van <strong>maximaal drie maanden huur</strong> vragen. Voor contracten van vóór 2019 was dat twee maanden, of drie maanden bij betaling in schijven via een bankwaarborg.</p>"),
        ("vormen", "Welke vormen zijn toegestaan?",
         "<ul><li><strong>Een geblokkeerde bankrekening</strong> op naam van de huurder.</li>"
         "<li><strong>Een zakelijke zekerheidstelling</strong>, zoals een obligatie of kapitalisatiebon, op naam van de huurder.</li>"
         "<li><strong>Een tussenkomst van het OCMW</strong> via een standaardcontract met een financiële instelling.</li>"
         "<li><strong>Een persoonlijke borgstelling</strong> door een persoon of organisatie, alleen met instemming van de verhuurder.</li></ul>"
         "<p>Deze vormen mogen niet worden gecombineerd. Zet de verhuurder de waarborg niet op een geblokkeerde rekening, dan is hij de huurder de gemiddelde marktrente op het bedrag verschuldigd.</p>"),
        ("rente", "Wie krijgt de rente?",
         "<p>Bij een geblokkeerde rekening op naam van de huurder komt de rente de huurder toe. Hoeveel dat is, hangt af van de bank.</p>"),
        ("vrijgave", "Vrijgave aan het einde van de huur",
         "<p>Pas als de huur beëindigd is, kan de waarborg worden vrijgegeven: in onderling akkoord tussen huurder en verhuurder, of na tussenkomst van de vrederechter. Een akkoord dat al bij de start van de huur is getekend, volstaat niet. <a href=\"{be/huurwaarborg-vrijgeven.html}\">Lees hoe de vrijgave in de praktijk verloopt.</a></p>"),
        ("depiqo", "Hoe Depiqo hierbij helpt",
         "<p>Depiqo Business houdt per dossier bij welke vorm is gekozen, wanneer de bank de waarborg heeft bevestigd en wie nog akkoord moet geven bij de vrijgave. De status “Zekerheid bevestigd” verschijnt pas na bevestiging door de bank, niet al bij een betaalopdracht.</p>"),
    ],
    sources=["vl", "wikifin"],
    related=[("be/huurwaarborg-brussel.html", "Huurwaarborg Brussel", "De verschillen met Vlaanderen."),
             ("be/huurwaarborg-vrijgeven.html", "Huurwaarborg vrijgeven", "Akkoord, vonnis en termijnen.")],
    alt=None,
)

art(
    path="be/huurwaarborg-brussel.html", region="be", kind="article",
    crumb="Brussel", parent=("Huurwaarborg", "be/huurwaarborg.html"),
    title="Huurwaarborg Brussel: de regels sinds november 2024 | Depiqo",
    desc="In Brussel is de huurwaarborg maximaal twee maanden huur zonder lasten, mag hij niet cash worden betaald en moet hij binnen twee maanden na vertrek terug.",
    h1="Huurwaarborg in Brussel",
    lede="Brussel heeft zijn huurregels in 2024 aangepast. Sinds november 2024 gelden strengere regels voor de huurwaarborg, onder meer over cash en de termijn van teruggave.",
    summary=["Maximaal 2 maanden huur, zonder lasten.",
             "Niet meer cash aan de verhuurder overhandigen.",
             "Terugbetaling binnen 2 maanden nadat de huurder vertrokken is.",
             "Persoonlijke borg alleen nog bij studentenhuur."],
    sections=[
        ("maximum", "Hoeveel mag de huurwaarborg zijn?",
         "<p>De huurwaarborg mag niet meer bedragen dan <strong>twee maanden huur, zonder lasten</strong>.</p>"),
        ("vormen", "Welke vormen zijn toegestaan?",
         "<ul><li>Een geïndividualiseerde rekening op naam van de huurder bij een door de FSMA erkende financiële instelling.</li>"
         "<li>Een bankwaarborg volgens het standaardcontract van het OCMW.</li>"
         "<li>Een bankwaarborg waarmee de huurder de waarborg geleidelijk opbouwt.</li>"
         "<li>Een zakelijke zekerheidstelling op naam van de huurder.</li></ul>"
         "<p>Een persoonlijke borg is alleen nog toegestaan bij studentenhuurcontracten. Cash betalen aan de verhuurder mag niet meer, onder meer om bewijsproblemen te voorkomen.</p>"),
        ("terug", "Binnen welke termijn moet de waarborg terug?",
         "<p>De verhuurder moet de waarborg <strong>binnen twee maanden</strong> nadat de huurder de woning verlaten heeft terugbetalen. Bij een laattijdige teruggave riskeert de verhuurder een bijkomende vergoeding per maand vertraging. Laat de precieze berekening voor jouw situatie nakijken, omdat bronnen die verschillend omschrijven.</p>"),
        ("beheerders", "Wat betekent dit voor beheerders?",
         "<p>Voor een beheerder is de termijn van twee maanden de belangrijkste wijziging. De eindafrekening en het akkoord van beide partijen moeten ruim binnen die periode rond zijn, anders loopt de verhuurder een financieel risico. Depiqo Business toont per dossier hoeveel dagen er nog over zijn.</p>"),
    ],
    sources=["bru", "jubel"],
    related=[("be/huurwaarborg-vlaanderen.html", "Huurwaarborg Vlaanderen", "De verschillen met Brussel."),
             ("be/huurwaarborg-vrijgeven.html", "Huurwaarborg vrijgeven", "Akkoord, vonnis en termijnen.")],
    alt=None,
)

art(
    path="be/huurwaarborg-vrijgeven.html", region="be", kind="article",
    crumb="Huurwaarborg vrijgeven", parent=("Huurwaarborg", "be/huurwaarborg.html"),
    title="Huurwaarborg vrijgeven: akkoord, vonnis en termijnen | Depiqo",
    desc="Zo komt de huurwaarborg vrij aan het einde van de huur: plaatsbeschrijving, afrekening, akkoord van huurder en verhuurder of een beslissing van de vrederechter.",
    h1="De huurwaarborg vrijgeven: zo gaat het",
    lede="De bank geeft een huurwaarborg alleen vrij met een akkoord van huurder en verhuurder of een beslissing van de vrederechter. Een goede plaatsbeschrijving maakt dat akkoord veel eenvoudiger.",
    summary=["Vrijgave pas na het einde van de huur.",
             "Nodig: een akkoord van beide partijen of een vonnis.",
             "In Brussel moet de waarborg binnen 2 maanden na vertrek terug.",
             "Bij onenigheid beslist de vrederechter."],
    sections=[
        ("stappen", "De vrijgave in vijf stappen",
         "<ol class=\"check-steps\">"
         "<li><strong>Plaatsbeschrijving bij vertrek.</strong> Vergelijk de staat van de woning met de plaatsbeschrijving bij intrek.</li>"
         "<li><strong>Eindafrekening.</strong> De verhuurder zet eventuele schade of openstaande bedragen op een rij, met bewijs.</li>"
         "<li><strong>Akkoord.</strong> Huurder en verhuurder ondertekenen een akkoord over de verdeling van de waarborg. Dat akkoord moet dateren van na het einde van de huur.</li>"
         "<li><strong>Bank.</strong> De bank betaalt uit volgens het akkoord: aan de huurder, aan de verhuurder of verdeeld.</li>"
         "<li><strong>Geen akkoord?</strong> Dan beslist de vrederechter, en de bank volgt die beslissing.</li></ol>"),
        ("termijnen", "Termijnen per gewest",
         "<p>In <strong>Brussel</strong> moet de verhuurder de waarborg binnen twee maanden na het vertrek van de huurder terugbetalen; te laat terugbetalen kan een extra vergoeding kosten. In <strong>Vlaanderen</strong> komt de waarborg vrij na akkoord of vonnis; maak daarom vooraf afspraken over het moment van de eindafrekening.</p>"),
        ("tips", "Tips voor huurders en beheerders",
         "<ul><li>Maak foto's met datum bij intrek en vertrek.</li>"
         "<li>Leg elke inhouding apart vast, met een offerte of factuur.</li>"
         "<li>Teken geen akkoord over de vrijgave vóór het einde van de huur.</li></ul>"),
        ("depiqo", "Hoe Depiqo hierbij helpt",
         "<p>Met Depiqo stelt de beheerder de eindafrekening op met bewijsstukken, ziet de huurder die in de app en geven beide partijen digitaal akkoord of geven ze aan dat ze het oneens zijn. Depiqo beslist nooit zelf over een geschil.</p>"),
    ],
    sources=["vl", "bru", "jubel", "wikifin"],
    related=[("be/huurwaarborg.html", "Huurwaarborg in België", "De regels per gewest."),
             ("be/echt-borgverzoek-herkennen.html", "Een echt borgverzoek herkennen", "Bescherm jezelf tegen fraude.")],
    alt="nl/waarborgsom-terugkrijgen.html",
)

# ---------------------------------------------------------------- PHISHING (both regions)
for r, term in (("nl", "waarborgsom"), ("be", "huurwaarborg")):
    art(
        path=f"{r}/echt-borgverzoek-herkennen.html", region=r, kind="article",
        crumb="Een echt borgverzoek herkennen",
        title=f"Een echt borgverzoek herkennen: fraude met je {term} voorkomen",
        desc=f"Een {term} betaal je maar één keer. Zo controleer je of een borgverzoek echt van Depiqo en je verhuurder komt, en wat je doet als je twijfelt.",
        h1="Hoe herken ik een echt borgverzoek van Depiqo?",
        lede=f"Oplichters gebruiken nep-sms'jes en nagemaakte websites om huurders hun {term} te laten storten. Met deze controles weet je zeker dat je verzoek echt is.",
        summary=["Depiqo vraagt je nooit om te betalen via alleen een sms-link.",
                 "Je ziet in het portaal altijd de naam van je verhuurder en het adres van de woning.",
                 "Twijfel je? Bel je verhuurder op een nummer dat je zelf opzoekt.",
                 "Depiqo werkt nog niet met live betalingen. Een betaalverzoek van Depiqo vandaag is dus nep."],
        sections=[
            ("nu", "Belangrijk: Depiqo is nog in ontwikkeling",
             "<div class=\"callout\"><strong>Depiqo verwerkt op dit moment geen betalingen.</strong> Krijg je nu een verzoek om je borg via Depiqo te betalen, dan is dat niet echt. Betaal niet en meld het bij je verhuurder.</div>"),
            ("controles", "Vijf controles voordat je betaalt",
             "<ol class=\"check-steps\">"
             "<li><strong>Je verwachtte het verzoek.</strong> Je hebt een huurcontract getekend of bent in gesprek met de verhuurder of beheerder.</li>"
             "<li><strong>Je opent het portaal zelf.</strong> Typ het adres getdepiqo.com zelf in je browser in plaats van op een link in een sms te tikken.</li>"
             "<li><strong>De gegevens kloppen.</strong> In het portaal staan de naam van je verhuurder of beheerder, het adres van de woning en het bedrag uit je contract.</li>"
             "<li><strong>Het bedrag past bij de regels.</strong> " + ("In Nederland is de borg maximaal twee maanden kale huur." if r == "nl" else "In Vlaanderen maximaal drie maanden huur, in Brussel maximaal twee maanden huur.") + "</li>"
             "<li><strong>Je betaalt nooit aan een privépersoon.</strong> " + ("Het geld gaat naar de rekening die in het portaal staat, nooit naar een rekening die iemand je per bericht stuurt." if r == "nl" else "De waarborg komt op een rekening op naam van jou, de huurder, en nooit op de privérekening van iemand anders.") + "</li></ol>"),
            ("signalen", "Signalen van fraude",
             "<ul><li>Haast: “betaal vandaag, anders gaat de woning naar iemand anders”.</li>"
             "<li>Een webadres dat net anders is, zoals extra woorden of een andere extensie.</li>"
             "<li>Een verzoek om je inloggegevens of een code van je bank.</li>"
             "<li>Een rekeningnummer dat verandert ten opzichte van eerdere berichten.</li></ul>"),
            ("twijfel", "Twijfel je? Zo ga je te werk",
             "<p>Betaal niet. Bel je verhuurder of beheerder op een nummer dat je zelf opzoekt, niet op het nummer uit het bericht. Heb je al betaald aan een rekening die niet klopt, neem dan meteen contact op met je bank en doe aangifte bij de politie.</p>"),
        ],
        sources=[],
        related=[(f"{r}/index.html", "Over Depiqo", "Wat Depiqo is en hoe het werkt."),
                 (("nl/waarborgsom.html" if r == "nl" else "be/huurwaarborg.html"), "De regels", f"Wat mag er gevraagd worden als {term}?")],
        alt=("be/echt-borgverzoek-herkennen.html" if r == "nl" else "nl/echt-borgverzoek-herkennen.html"),
    )
