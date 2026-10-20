# Changelog

## 0.6.1 — 20 oktober 2026
Acht bevindingen uit een onafhankelijke review van de API van 0.6.0 opgelost, elk met een regressietest in `tests/test_v061.py`; de probes van de reviewer zijn daar ook als tests opgenomen.
- **Opnamerekening en 2FA-code (hoog).** Wie een nieuw rekeningnummer met een code registreert, kan niet meer onbeperkt raden: dezelfde tellers als de tweede inlogstap (5 foute codes per 15 minuten, dan 429 in de app en een melding op de website). Alleen een code van 6 cijfers telt; een herstelcode wordt hier nooit meer verbruikt.
- **Account verwijderen (midden).** De kopie van een supportvraag in de supportmailbox wordt gewist (onderwerp en inhoud), ook de inlogpogingen van "wachtwoord vergeten". Offertes en de berichten over de beleggingsrekening blijven bewaard als vastlegging, zonder naam en e-mailadres. De uitleg in de app zegt nu precies wat er gebeurt.
- **Idempotentie bij uploads (midden).** Voor multipart telt de inhoud (velden en de SHA-256 van elk bestand), niet de ruwe body met een wisselende boundary; een herhaalde upload met dezelfde sleutel krijgt hetzelfde antwoord.
- **Invoer (laag).** Een cursor met een te groot, negatief of vreemd getal, of diep geneste JSON, geeft 400 in plaats van een serverfout. Een rare `Accept-Language` (q=nan of inf) wordt genegeerd.
- **Sandboxstorting (laag).** Buiten de sandbox bestaat het endpoint niet: 404 vóór elke andere controle, ook zonder login.
- **Tijdzone (laag).** Tijden in meldingen en e-mails gebruiken Europe/Amsterdam (zomer- en wintertijd), niet vast UTC+2. Dat geldt ook voor de datums op de website.
- **Pushtoken (laag).** Een token gaat alleen naar een ander account als de sessie waar hij bij hoorde is afgemeld; anders 409 `push_token_in_use`.
- **Pogingen tellen (laag).** Inloggen, de tweede stap (app en website), wachtwoord bij verwijderen en de code bij de opnamerekening reserveren de poging eerst en tellen daarna, zodat gelijktijdige verzoeken samen niet boven de limiet komen. De vijf pogingen per inlogpoging in de app worden met één voorwaardelijke update geclaimd.

## 0.6.0 — 20 oktober 2026
JSON-API voor de app van Depiqo voor huurders (React Native met Expo), onder `/api/v1`: 55 endpoints op 44 paden, beschreven in `docs/api/openapi.yaml` (OpenAPI 3.1) met een uitleg in `docs/api/README.md`. Alleen voor huurders (Wallet en Invest); beheerders en medewerkers houden de webapp.
- **Inloggen met tokens.** Toegangstoken 15 minuten, vernieuwingstoken 30 dagen, beide alleen gehasht opgeslagen. Elk vernieuwingstoken werkt één keer; een gebruikt token dat terugkomt, beëindigt de hele apparaatsessie (diefstaldetectie). Tweede stap met een code of herstelcode, dezelfde rate limits als de website. Apparaten met naam, platform, versie en laatst gezien, af te melden in de app en op de pagina Beveiliging. Wachtwoord resetten en 2FA wijzigen beëindigen ook de app-sessies. Medewerkers en leden van een organisatie zonder huurdersrol krijgen 403.
- **Geen cookies, geen CSRF.** De API leest de websessie nooit; een schrijvend verzoek met de webcookie maar zonder bearer-token wordt geweigerd.
- **Uitnodigingen** met de anti-phishingcontrole (verhuurder, adres, bedrag, kenmerk) en accepteren vanuit de app.
- **Borgen:** overzicht en detail met de vier bedragen (onbekend is `null` met uitleg), voortgang, waar de borg staat (ook garantie en vervaldatum), termijn, volgende stap, betaalgegevens en gebeurtenissen; identiteit, documenten (ook een foto van de camera), eindafrekening akkoord of bezwaar, vrijgaveformulier, doorbeleggen met dezelfde regels als 0.5.2.
- **Beleggen:** dezelfde functies als de wallet, geen tweede kopie van de regels. Een order kan alleen met een offerte (kosten in euro, scenario's, risico; 10 minuten geldig) en `risk_acknowledged: true`. Grafiek als reeksen per periode.
- **Idempotentie:** `Idempotency-Key` op elk schrijvend geldverzoek, verplicht bij orders, opnames en de sandboxstorting; 24 uur bewaard. Geen dubbele order of opname bij een herhaald verzoek.
- **Meldingen en push:** een meldingentabel gevuld door de bestaande gebeurtenissen; push via een outbox naar Expo, met alleen een vaste titel. In de sandbox `skipped`. `DeviceNotRegistered` zet de token uit.
- **Talen nl, fr en en** (`app/i18n.py`): foutmeldingen, meldingen, pushberichten en twee e-mails volgen `Accept-Language` of de taal van de gebruiker. Elke status en elk label heeft een vaste sleutel naast de Nederlandse tekst. Een test somt ontbrekende vertalingen op.
- **Support:** vragen uit de app met een limiet, een e-mail aan support en een pagina voor medewerkers (`/admin/support`) met antwoord als melding.
- **Geschiedenis:** gebeurtenissen per borg en één activiteitenlijst voor borg en beleggen.
- **Privacy:** gegevens downloaden als JSON en account verwijderen (anonimiseren); geweigerd zolang er een borg loopt of er geld op de beleggingsrekening staat, met uitleg wat blijft en waarom.
- **Omgevingen:** `DEPIQO_ENV` development, staging of production. Staging mag de sandbox gebruiken en toont STAGING; productie draait nooit een sandboxpartner. Zonder echte partner geeft elk geld- en beleggingsendpoint 503 `partner_unavailable`.
- **Deep links:** `/.well-known/apple-app-site-association` en `/.well-known/assetlinks.json` voor `/t/*` en `/app-link/*`, met de bestaande pagina's als terugval.
- Migratie 009. 246 tests (181 ongewijzigd, 65 nieuw in `tests/test_v060.py`), ook met `TZ=UTC`; rooktest `tests/api_smoke.py` tegen de draaiende server en de browsertest groen.

## 0.5.2 — 20 oktober 2026
Veertien bevindingen uit een onafhankelijke review van Depiqo Invest 0.5.0 opgelost, elk met een regressietest (181 tests, ook met `TZ=UTC`; browsertest groen).
- **Saldo nooit negatief (hoog).** Opgebouwde servicekosten die nog niet zijn verrekend, en het geld voor lopende orders en opnames, zijn niet beschikbaar voor kopen of opnemen. De partner int nooit meer dan het vrije geld plus de opbrengst van een verkoop; de rest schuift door. Een bericht dat het saldo onder nul zou brengen, wordt geweigerd.
- **Mislukt blijft mislukt (hoog).** Een medewerker kan een order of opname die de huurder als mislukt zag, niet meer opnieuw versturen. Opnieuw kan alleen voor servicekosten en een rekeningopening die nog wacht.
- **Doorbeleggen zonder dubbele creditering (hoog).** Kiezen en terugdraaien zijn één voorwaardelijke opdracht op de status van de borg; na de vrijgave-opdracht kan niets meer veranderen. De bestemming staat in de vrijgave-opdracht en alleen die telt bij de uitbetaling.
- **Doorbeleggen faalt dicht (hoog, ook M2).** Bij de start van de uitbetaling wordt gecontroleerd: partner, actieve rekening, Beleggen aan voor de organisatie van díe borg. Anders gaat het deel naar de eigen rekening, met auditregel, e-mail aan de huurder en een afwijking voor Depiqo. "Betaald" alleen als het geld in dezelfde transactie op de beleggingsrekening staat; anders "niet verwerkt" en zichtbaar voor Depiqo.
- **Wisselen (hoog).** De portefeuille verandert pas na de verkoop én het plaatsen van de nieuwe aankoop. Mislukte verkoop: niets verandert, de huurder krijgt een melding. Een aankoop die nog niet kan, blijft openstaan en wordt opnieuw geprobeerd; het bericht van de partner geeft geen fout meer.
- **Berichten voor een nog onbekende rekening (hoog).** Worden opnieuw verwerkt als de partner ze nog eens stuurt; medewerkers kunnen een bericht met een fout opnieuw laten verwerken.
- **Schakelaar per organisatie (M1).** Uit betekent: geen nieuwe rekeningen, aankopen, wissels of doorbeleggen. Bestaande beleggers houden toegang om te kijken, verkopen, opnemen en overzichten te downloaden.
- **Risico en kosten bij elke verbintenis (M3).** Kopen en wisselen via een controlepagina met kosten in euro, scenario's en een vinkje; risicowaarschuwing ook bij verkopen en doorbeleggen.
- **Servicevergoeding per rekening (M4).** Vastgelegd bij het akkoord. Een nieuw tarief geldt voor nieuwe rekeningen; bestaande rekeningen krijgen een voorstel en een e-mail en houden het oude tarief tot ze akkoord gaan, nooit met terugwerkende kracht.
- **Opnemen alleen naar de eigen rekening (M5).** Registreren met een verse 2FA-code (direct) of anders na 7 dagen; altijd een e-mail; de partner controleert de naam.
- **Berichten gecontroleerd (M6).** Bedrag van een uitvoering moet kloppen met stukken × koers, gehele positieve getallen, een echte datum binnen de looptijd. Een fout bericht verandert niets en geeft geen serverfout meer.
- **Gelijktijdige verzoeken (L1).** De saldocontrole gebeurt in dezelfde transactie als de reservering.
- **Auditlog (L2).** Invest-regels hebben nooit een organisatie, ook niet als de huurder lid is van een organisatie.
- Gecontroleerd: de CSV-export voor beheerders bevat niets van Invest.
- Migratie 008: tarief per rekening, voorstel en doorgeschoven servicekosten, wissel in uitvoering, eigen rekeningnummer, opnieuw te verwerken berichten, twee nieuwe uitkomsten voor doorbeleggen.

## 0.5.1 — 20 oktober 2026
- Datum: de app rekent met de kalenderdatum in Nederland en België (Europe/Amsterdam), niet met UTC. Wettelijke termijnen lopen nu op de lokale datum, en de tests gebruiken dezelfde functie. De tests slagen nu ook tussen 00:00 en 02:00.
- Nog open: tijdstempels worden in UTC opgeslagen; de maand van een nieuw dossier voor de facturatie volgt dat tijdstempel (verschil kan alleen rond middernacht op de laatste dag van de maand optreden).

## 0.5.0 — 20 oktober 2026
Depiqo Invest: huurders beleggen hun eigen geld bij een vergunde partner, los van hun borg (155 tests, browsertest groen).
- **Scheiding.** Eigen tabellen per persoon, nooit per organisatie. De borg wordt nooit belegd en nooit als onderpand gebruikt; elk Invest-scherm zegt dat. Enige brug: de expliciete keuze van de huurder om zijn deel van een terugbetaling op zijn beleggingsrekening te ontvangen.
- **Partner.** Interface `InvestmentPartner` (toets, rekening openen, stortinstructies, orders, opnames, servicekosten, koersen) met een sandboxpartner. Kiezen met `INVEST_PARTNER`; faalt dicht zoals de bank. Opdrachten via een eigen outbox (`invest_instructions`) met idempotentiesleutels, berichten via `/webhooks/invest/<partner>` met HMAC, eenmalig per event-id.
- **Wallet.** Tab Beleggen: risico en rol van Depiqo, kennis- en ervaringstoets (8 vragen, uitslag passend of niet passend, bij niet passend een waarschuwing en een extra bevestiging), drie modelportefeuilles met kosten in euro (1 en 3 jaar) en scenario's (geen voorspelling), voorwaarden met versie en tijdstip, rekening op eigen naam, storten (IBAN van de partner en kenmerk), kopen vanaf € 25, overzicht met waarde, inleg, vrij geld, resultaat, fondsen en een grafiek (SVG op de server, zonder script), orders, transacties, kosten, verkopen, opnemen naar eigen IBAN, wisselen van portefeuille, maandoverzichten als PDF.
- **Doorbeleggen.** Na akkoord kiest de huurder zelf waar zijn deel heen gaat. De vrijgave-opdracht aan de bank betaalt dan het deel van de huurder aan de klantengeldrekening van de partner met zijn kenmerk. De controle op de uitbetaalde bedragen uit 0.3 blijft; pas daarna komt de storting op de beleggingsrekening. Beheerders zien alleen "naar de rekening van de huurder".
- **Kosten.** Servicevergoeding 0,25% per jaar (instelbaar), elke dag opgebouwd over de waarde van de fondsen en per maand verrekend; fondskosten zitten in de koers. Unit economics toont belegd vermogen, actieve beleggers, servicekosten en marge na een aangenomen partnerprijs per rekening (€ 0,30).
- **Beheer.** Pagina Beleggen: totalen, rekeningen, uitslagen van de toets, mislukte opdrachten, Beleggen aan of uit per organisatie, sandboxklok. Medewerkers kunnen geen orders plaatsen.
- **Demo.** Vier beleggers (18 maanden geschiedenis, doorbeleggen gekozen, toets niet gehaald en toch door). Beleggen staat aan voor Voorbeeld Vastgoed BV.

## 0.4.0 — 19 oktober 2026
Eén plek voor alle huurwaarborgen, ongeacht waar ze staan (135 tests, browsertest groen).
- **Aanbieders van borgen elders.** Per borg de soort (rekening van verhuurder of beheerder, geblokkeerde rekening bij een bank, e-DEPO, kapitalisatiecontract bij verzekeraar tak 26, garantie of borgstelling door een derde, waarborg via OCMW, anders), de naam van de aanbieder, een referentie en bij een garantie de einddatum. Migratie 006; bestaande borgen elders staan als "aanbieder onbekend".
- **Regio's.** e-DEPO, OCMW en tak 26 alleen in België; een rekening van de verhuurder in Vlaanderen of Brussel krijgt een waarschuwing (Brussel: ook geen contanten). Waarschuwen, nooit blokkeren: live in het formulier, na opslaan, op het dossier en in het importvoorbeeld.
- **Zekerheid.** Garantie wordt `security_type` guarantee, de andere soorten "borg buiten Depiqo". Bij een garantie of het OCMW stort de huurder niets: geen betaalgegevens, geen betaalherinnering, "Ontvangen" blijft "—". Per soort toont de bewijsladder welk stuk past. Juridische zekerheid kan niet bij een rekening van de verhuurder.
- **Formulieren.** Nieuw dossier met de aanbieder; aparte pagina "Waar staat de borg" voor beheerder en vastgoedbeheerder zolang het dossier loopt, met auditlog. Na verificatie door Depiqo kan alleen de einddatum van een garantie nog veranderen.
- **Import en export.** Vier optionele kolommen, met Nederlandse kolomnamen en waarden ("rekening verhuurder", "e-DEPO", "tak 26", "garantie"). Het sjabloon heeft een derde voorbeeldrij (een garantie). De CSV-export heeft vier kolommen erbij.
- **Overzicht.** Blok "Waar staan je borgen" op het dashboard, filter "aanbieder" op de borgenlijst, twee nieuwe afwijkingen in de afstemming (geen aanbieder; garantie loopt binnen 60 dagen af of is verlopen).
- **Vrijgave.** Na akkoord of een afgesloten geschil een vrijgaveformulier (PDF, één pagina) voor beheerder en huurder, met handtekeningvakken en de opmerking dat e-DEPO, de bank en de verzekeraar een eigen procedure hebben. "Vrijgave bij aanbieder bevestigd" (financieel of beheerder) met bewijs sluit het dossier. Dit vervangt de klik "Terugbetaling registreren".
- **Wallet.** "Waar staat je borg" met de aanbieder in gewone taal; bij een garantie: "Je hebt geen geld gestort. Een derde staat garant. Bij schade kan die het bedrag op jou verhalen." met de einddatum.
- Prijzen en unit economics ongewijzigd: elke soort is een borg elders.
- Demodata: beide organisaties hebben een realistische mix van aanbieders, met algemene namen.

## 0.3.1 — 19 oktober 2026
Negen bevindingen uit een onafhankelijke review van 0.3.0 opgelost, elk met een regressietest (105 tests, browsertest groen).
- **Uitbetaling (hoog):** een bevestiging van de bank die binnenkomt voordat Depiqo het antwoord op de vrijgave-opdracht heeft vastgelegd, ging verloren en het dossier bleef op "uitbetaling loopt". De rekening staat nu in dezelfde transactie als de opdracht op "vrijgave aangevraagd". Een bankbericht dat om een timingreden is geweigerd (onbekende rekening, nog geen vrijgave-opdracht) wordt opnieuw verwerkt als de bank het nog eens stuurt. Depiqo-medewerkers kunnen een bankbericht met een fout opnieuw verwerken.
- **Sandbox uit:** een blokkering op een sandboxrekening telt niet meer als bevestigde zekerheid als de sandbox niet de actieve partner is. Label "SANDBOX, niet bevestigd", niet in de totalen van dashboard en afstemming, wel als afwijking in de afstemming.
- **Sessies en 2FA:** aanzetten of uitzetten van twee-stapsverificatie en nieuwe herstelcodes beëindigen alle andere sessies. Elke sessie onthoudt of de tweede stap is gedaan; de beheeromgeving vraagt dat per sessie als `REQUIRE_2FA_FOR_STAFF` aan staat.
- **Plangeschiedenis:** een planwijziging door Depiqo vanaf deze maand vervangt een eerder ingeplande wissel van de klant voor later.
- **Facturen uit 0.2:** facturen van € 0 en vervallen facturen stonden na migratie 004 als open of te laat. Migratie 005 zet ze op "niets te betalen"; een vervallen factuur heet "Vervallen" en kan niet op betaald.
- **Creditnota en betaling:** een gecrediteerde factuur kan niet meer op betaald, en een betaalde factuur crediteren wordt geweigerd tot de terugbetaling geregeld is.
- **Rekening openen na een fout:** een nieuwe identiteitscontrole na een mislukte opdracht verstuurt de opdracht opnieuw. De huurder ziet alleen "de bank opent nu je borgrekening" als dat ook zo is.
- **Opdrachten:** een time-out overschrijft nooit meer een opdracht die de bank al had bevestigd of aangenomen.
- **Import:** een extreem lang veld geeft een duidelijke melding in plaats van een serverfout. Maximale lengtes per kolom (adres 200, naam 120, e-mail 254, plaats 80 tekens en meer).

## 0.3.0 — 19 oktober 2026
Financiële correctheid en klaar voor een pilot (89 tests, browsertest groen).

Financieel
- Vier aparte bedragen in Wallet, op de kaarten in Wallet en op het dossier in Business: vereiste borg, ontvangen, bevestigd geblokkeerd en rente. Wat niet bevestigd is, staat als "—" met uitleg. De wallet toont het borgbedrag nooit meer als geld dat er staat.
- Bewijsniveaus voor borgen elders: verklaard door beheerder, bankdocument ontvangen, extern geverifieerd (alleen Depiqo, met notitie) en juridische zekerheid (alleen Depiqo, met blokkeringsattest of e-DEPO). Alleen geverifieerd en juridisch tellen mee als dekking. Alleen juridische zekerheid en een door de bank bevestigde blokkering zijn groen ("Zekerheid bevestigd"). Het bewijsniveau staat in lijsten, op het dashboard, in de afstemming, in de CSV-export en in de wallet.
- De status "zekerheid bevestigd" heet nu "zekerheid geregistreerd"; het label hangt af van het bewijs. Bestaande bevestigingen uit 0.2 zijn "verklaard" geworden.
- Bankpartner kiezen met `BANK_PARTNER`. Zonder partner faalt alles dicht: geen rekening, geen opdracht, geen bankbericht, en een duidelijke melding. Sandboxrekeningen hebben overal het label SANDBOX.
- Opdrachten aan de bank via een outbox met idempotentiesleutel, in dezelfde transactie als de statuswijziging. Versturen direct na de actie, met de knop "Opdrachten versturen" of `python3 run.py dispatch`; maximaal 5 pogingen.
- Een uitbetaling sluit pas als de bank precies de opgedragen bedragen voor huurder en verhuurder meldt. Een afwijking komt in de afstemming en het dossier blijft open.
- Afstemming voor Depiqo en voor beheerders en financieel medewerkers: verplichting, saldo, opdracht en bewijs per dossier, met afwijkingen.

Pilot
- Regels per versie: een dossier houdt het maximum en de termijnen van zijn regelversie.
- Plangeschiedenis: een factuur gebruikt het plan van de eerste dag van de maand; zelf wisselen geldt vanaf volgende maand. De oude waarschuwing over planwissels is weg.
- Facturen hebben een betaalstatus (open, betaald, te laat). Depiqo zet een factuur op betaald of maakt een creditnota; daarna kan de maand opnieuw worden gefactureerd.
- Unit economics voor Depiqo: omzet, aangenomen partnerkosten en marge per organisatie, met een waarschuwing bij negatieve marge per Depiqo-borgrekening.
- Bestaande borgen importeren uit CSV (sjabloon, voorbeeld met fouten per rij, alles of niets). Puntkomma, komma, BOM en Windows-1252 werken.
- Bulkacties op de borgenlijst: (opnieuw) uitnodigen, betaalherinnering sturen en selectie exporteren.
- "Vandaag te doen" op het dashboard: taken per soort met een directe actie, de meest dringende eerst.
- Twee-stapsverificatie met een authenticator-app en 10 herstelcodes. Melding voor beheerders en Depiqo-medewerkers; verplicht voor medewerkers met `REQUIRE_2FA_FOR_STAFF`.
- Communicatie per dossier: welke mails zijn verstuurd, aan wie, wanneer en of het lukte.
- Opgelost: het filter "Waar staat de borg" op de borgenlijst werkte niet (de waarde botste met een macronaam).

## 0.2.0 — 19 oktober 2026
Nieuw prijsmodel en een zekerheidsmodel per dossier (48 tests).
- Drie plannen. Essential: € 99 per maand, 100 actieve dossiers inbegrepen, extra € 0,75 (elders) of € 0,40 (Depiqo-borgrekening), € 5 per nieuw dossier. Professional: € 299, 500 inbegrepen, € 0,45 / € 0,25, € 3 per nieuw dossier. Enterprise op aanvraag, met eigen bedragen per organisatie.
- Nieuw dossier: geactiveerd in de factuurmaand en niet geannuleerd. Inbegrepen dossiers tellen nog steeds eerst voor borgen elders. Pilot blijft 100% korting.
- Factuurregels tonen apart: basis, inbegrepen, extra elders, extra Depiqo-borgrekening, nieuwe dossiers en pilotkorting.
- Facturatiepagina: huidig plan, vergelijking van de plannen, raming van deze en vorige maand. Een beheerder wisselt tussen Essential en Professional; dat komt in het auditlog.
- Beheeromgeving: plan per organisatie zichtbaar; een Depiqo-medewerker zet elk plan, ook Enterprise met eigen bedragen. Plan kiezen bij een nieuwe organisatie.
- Zekerheid per dossier: type, bewaarder, begunstigde, juridische blokkering bij de bank en dekking. Bankberichten houden dit bij (aangevraagd, actief, vrijgegeven; waarde volgt het saldo en de rente). Zichtbaar op de dossierpagina.
- Migratie 003 vult bestaande dossiers aan: borgen elders krijgen het juiste type, geblokkeerde Depiqo-rekeningen een actieve blokkering, uitbetaalde een vrijgegeven.
- Demodata: Voorbeeld Vastgoed BV op Professional (pilot), Stadswonen Gent op Essential. Teruggedateerde demodossiers tellen niet meer als nieuw in de huidige maand.

## 0.1.1 — 19 oktober 2026
Na een onafhankelijke beveiligingsreview (12 bevindingen, alle opgelost, 12 regressietests erbij; 37 tests):
- Sandbox-bankberichten alleen voor beheerder en financieel; alleen-lezen kan geen borg meer "veilig" zetten.
- Het demo-postvak (met reset- en uitnodigingslinks) is alleen nog voor Depiqo-medewerkers.
- Open redirect na inloggen gedicht; alleen lokale paden.
- Juridische blokkade: bankberichten tijdens de blokkade worden na opheffen alsnog verwerkt; geen blokkade meer tijdens een lopende uitbetaling.
- "Wachtwoord vergeten" heeft een eigen teller en kan niemand meer buitensluiten; een reset maakt alle oudere resetlinks ongeldig.
- Factuurperiode strikt JJJJ-MM en niet vóór de start van de organisatie; btw rondt half-omhoog af.
- Origin-controle exact; IP-adres achter een proxy via ProxyFix (niet meer te vervalsen via X-Forwarded-For).
- Productie vereist een https-BASE_URL; in ontwikkeling één vaste geheime sleutel voor alle workers.
- Uitnodigingslink verloopt op het exacte tijdstip; bankberichten met een ongeldig bedrag worden geweigerd; uitbetaling nooit hoger dan het saldo; dubbel gelijktijdig bankbericht geeft geen fout meer.
- Alleen-lezen en vastgoedbeheerders zien de maandkosten niet; CSV-export beschermt ook tegen tab en carriage return; geen tijdsverschil meer bij inloggen met een onbekend adres.

## 0.1.0 — 19 oktober 2026
Eerste werkende versie: Depiqo Business, Depiqo Wallet, beheeromgeving, sandbox-bank, facturatie volgens prijsmodel B (€ 49 incl. 50 dossiers, € 1 / € 0,50 per dossier), 25 tests en een browsertest.
