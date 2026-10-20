# Open punten en testresultaten

## Getest (20 oktober 2026, versie 0.6.1)

- **267 geautomatiseerde tests geslaagd**, gewoon en met `TZ=UTC`: de 246 van 0.6.0 (geen aangepast) en 21 regressietests in `tests/test_v061.py`, één of meer per bevinding uit de review van de API en de probes van de reviewer. Rooktest en browsertest groen.
- Keuze: de vaste tijdzone (UTC+2) is ook op de website vervangen door Europe/Amsterdam, niet alleen in de app-teksten.

## Getest (20 oktober 2026, versie 0.6.0)

- **246 geautomatiseerde tests geslaagd**, gewoon en met `TZ=UTC`: de 181 van 0.5.2 (geen aangepast) en 65 nieuwe in `tests/test_v060.py`: inloggen, tweede stap met code en herstelcode, rotatie en hergebruik van vernieuwingstokens, verlopen tokens, blokkade gedeeld met de website, medewerkers en beheerders geweigerd, alleen-cookie geweigerd, apparaten in app en web, uitnodigingen, elk borgendpoint (ook 404 voor de borg van een ander), uploads, afrekening, vrijgaveformulier, doorbeleggen, onboarding Invest, offerte en order (met en zonder bevestiging, verlopen, gebruikt), idempotentie, opnamerekening, meldingen en push-outbox, talen en ontbrekende vertalingen, support, activiteit, export en verwijderen, omgevingen en 503 in productie zonder partner, deep links, en de specificatie (paden in beide richtingen en echte antwoorden tegen de schema's).
- **Rooktest** `tests/api_smoke.py` tegen de draaiende demo: geslaagd (inloggen als Daan, borgen, offerte, order, dezelfde Idempotency-Key geeft hetzelfde antwoord, meldingen, fout in het Frans, uitloggen).
- **Browsertest** groen, ongewijzigd.

## Keuzes in 0.6.0

- **Ondoorzichtige tokens in plaats van JWT.** Elk verzoek kijkt in de database; afmelden werkt daardoor meteen. Bij veel verkeer kan een korte cache per token.
- **Een herhaald vernieuwingstoken beëindigt de sessie,** ook als de app zelf twee keer tegelijk vernieuwt. Geen respijtperiode; de app moet vernieuwen in één keer.
- **Idempotentie bewaart alleen geslaagde antwoorden.** Na een fout voert een nieuwe poging met dezelfde sleutel de actie opnieuw uit; de eerste poging veranderde niets.
- **Accepteren van een uitnodiging heeft geen Idempotency-Key** (er is dan nog geen gebruiker). De uitnodiging is zelf eenmalig; na een verloren antwoord logt de huurder in met het gekozen wachtwoord.
- **Wachtwoord vergeten blijft op de website** (`/config` geeft de link).
- **Labels blijven Nederlands** in de antwoorden, met een vaste sleutel ernaast. Foutmeldingen en meldingen vertaalt de server (nl, fr, en). Vrije teksten van services (de precieze reden) komen in het Frans en Engels als `detail` in het Nederlands mee.
- **Huurders uploaden** foto, plaatsbeschrijving of overig, zoals op de website.
- **Een order vraagt altijd een offerte,** ook verkopen en wisselen; wisselen is een offerte met `side: switch`.
- **Staging** heeft dezelfde verplichte geheimen en https als productie. Een gehoste demo of pilot met de sandbox draait nu op `DEPIQO_ENV=staging` in plaats van productie met `DEPIQO_SANDBOX=1`.

## Open na 0.6.0

- **Privacyverklaring en voorwaarden:** de links in `/config` (`PRIVACY_URL`, `TERMS_URL`) wijzen naar pagina's op getdepiqo.com die nog geschreven moeten worden.
- **Account verwijderen bij de partner:** de beleggingsrekening wordt in Depiqo gesloten; de partner moet de rekening aan zijn kant sluiten (opdracht in het partnercontract).
- **E-mails in het Frans en Engels:** alleen de mails over het opnamerekeningnummer en het voorstel voor de servicevergoeding zijn vertaald. Mails over de borg gaan via de verhuurder naar het e-mailadres van de huurder, vaak voordat er een account en taalkeuze is; die blijven Nederlands.
- **Push in productie** vraagt een Expo-account (`EXPO_ACCESS_TOKEN` aanbevolen) en `PUSH_SEND=1`; ontvangstbewijzen worden opgehaald door `run.py dispatch`.
- **Deep links:** `APP_IOS_TEAM_ID` en `ANDROID_SHA256_CERT` invullen zodra de app is ondertekend.
- **Activiteit:** beleggingstransacties staan op het tijdstip van boeken; in de demo staat de historie daardoor op het moment van de seed.

## Getest (20 oktober 2026, versie 0.5.2)

- **181 geautomatiseerde tests geslaagd**, gewoon en met `TZ=UTC`: de 155 van 0.5.1 (twee aangepast omdat het gedrag bewust veranderde: kopen vraagt een bevestiging na de kostenpagina, opnemen kan alleen naar een geregistreerde eigen rekening) en 26 regressietests in `tests/test_v052.py`, één of meer per bevinding uit de review van 0.5.0 (H1 tot H6, M1 tot M6, L1, L2) en een test dat de CSV-export niets van Invest bevat. De probes van de reviewer reproduceren geen van de defecten meer.
- **Browsertest** groen. Gevonden en opgelost: in 0.5.0 liep de Invest-stap in de browsertest onbedoeld als Sanne (de telefoonsessie was intussen van haar). Nu als Kevin in een eigen sessie, met 2FA, de kostenpagina vóór de aankoop en het registreren van zijn eigen rekening met een code.

## Review van 0.5.0 (20 oktober 2026)

Veertien bevindingen, alle opgelost; zie `CHANGELOG.md` (0.5.2). Bewust zo gekozen:
- **Mislukt is definitief** voor orders en opnames. Een medewerker kan ze niet opnieuw versturen; de huurder plaatst zelf een nieuwe.
- **Afkoelperiode van 7 dagen** voor een nieuw opnamerekeningnummer zonder 2FA. Een terugbetaling naar de vorige rekening tijdens die periode kan niet; dat is de prijs van de bescherming.
- **Servicekosten die niet geïnd konden worden,** schuiven door. Een rekening die leeg is, bouwt niets meer op (alleen over fondsen), dus de rest blijft klein.
- **Afwijkingen bij doorbeleggen** ziet alleen Depiqo (afstemming in de beheeromgeving en de pagina Beleggen), nooit de beheerder van de borg.

## Getest (20 oktober 2026, versie 0.5.0)

- **155 geautomatiseerde tests geslaagd**: de 135 van 0.4.0 (geen aangepast) en 20 nieuwe in `tests/test_v050.py`: toetslogica en de extra bevestiging bij niet passend, kostenvoorbeelden 1 en 3 jaar, scenario's, herhaalbare koersen, verdeling en afronding, uitvoering tegen de volgende koers, verkopen, opnemen, limieten, wisselen, falen zonder partner of sandbox, de schakelaar per organisatie, privacy (beheerders 404 op elke Invest-route, niets op dossierpagina's), medewerkers kunnen geen orders plaatsen, doorbeleggen met bedragcontrole, opbouw en verrekening van servicekosten, maandoverzicht als PDF, webhook-handtekening en idempotentie, migratie 007.
- **Browsertest** groen, met erbij op een telefoon: Beleggen openen, toets, Neutraal kiezen met kosten, voorwaarden, rekening openen, € 500 storten (sandbox), € 400 kopen, een dag vooruit (medewerker), positie en grafiek, € 100 verkopen en € 100 opnemen.

## Keuzes in 0.5.0

- **Eigen outbox voor de beleggingspartner** (`invest_instructions`), zelfde patroon als de bank. Zie `ARCHITECTUUR.md`.
- **Rekening per persoon**, niet per huurdersrecord of organisatie. Een huurder met borgen bij twee beheerders heeft één beleggingsrekening.
- **De sandboxpartner gebruikt het grootboek van Depiqo als zijn eigen boek.** Een echte partner is de bron van waarheid; dan volgt het grootboek alleen zijn berichten.
- **Servicevergoeding alleen over de fondsen**, niet over vrij geld. Bij te weinig vrij geld verkoopt de partner naar rato.
- **Sandboxactivering:** een huurder die zijn identiteit al bevestigde voor een Depiqo-borgrekening, krijgt de rekening direct; anders activeert een medewerker hem in de sandbox (zoals na de controle van de partner).
- **Doorbeleggen alleen bij een Depiqo-borgrekening.** Bij een borg elders betaalt de aanbieder uit; Depiqo kan die niet sturen.

## Gevonden tijdens het testen van 0.5.0 (niet nieuw)


## Open voor Invest (vóór echt geld)

- **Na de review van 0.5.0:** de naamcontrole op een opnamerekening en de opvolging van een `unrecorded` doorbelegging (partner meldt de storting niet) moeten met een echte partner worden afgesproken. Een voorstel voor een nieuwe servicevergoeding heeft nog geen einddatum; leg vast wat er gebeurt als een huurder nooit reageert.

- **Vergunde partner:** contract met een beleggingsonderneming met vergunning (AFM in Nederland, FSMA in België), klantengeldrekening, API volgens het contract in `ARCHITECTUUR.md`, prijsafspraak per rekening.
- **Rol van Depiqo bevestigen:** alleen doorverwijzen (geen vergunning, geen advies), of verbonden agent of andere vorm onder de vergunning van de partner. Dat bepaalt welke teksten, welk toezicht en welke vergoeding mogen. Juridisch advies nodig, ook over de servicevergoeding (inducements) en over marketing binnen een huurproduct.
- **Essentiële-informatiedocumenten (EID/KID)** per fonds tonen vóór elke aankoop, en de kosten- en lastenopgave volgens MiFID II (ex ante en jaarlijks ex post) van de partner.
- **Passendheidstoets** is van de partner: vragen, drempels en de waarschuwing laten vaststellen door de partner; Depiqo toont alleen. Ook periodiek herhalen en de doelgroep per product (product governance).
- **Belasting:** jaaropgave van de partner (Box 3 in Nederland; in België de taks op effectenrekeningen en roerende voorheffing waar van toepassing). Depiqo geeft geen belastingadvies.
- **Fondsen en koersen:** echte fondsen met ISIN, koersen en lopende kosten van de partner in plaats van de sandboxreeks; scenario's volgens de methode van de EID's.
- **Doorbeleggen:** juridisch toetsen dat een vrijgave aan een derde rekening op naam van de huurder mag (in België vraagt dat het akkoord van beide partijen of de vrederechter, zoals elke vrijgave), en dat de bank de IBAN en het kenmerk van de partner accepteert.
- **Privacy:** antwoorden op de toets zijn financiële gegevens; bewaartermijn en inzage vastleggen (DPIA).
- **Herstelregeling:** het depositogarantiestelsel geldt niet; uitleggen welk beleggerscompensatiestelsel de partner heeft.


## Getest (19 oktober 2026, versie 0.4.0)

- **135 geautomatiseerde tests geslaagd**: de 105 van 0.3.1 (één aangepast omdat het gedrag bewust veranderde: het importsjabloon heeft een derde voorbeeldrij) en 30 nieuwe in `tests/test_v040.py`: registratie en afbeelding op het zekerheidsmodel, validatie, regiowaarschuwingen die niet blokkeren, wijzigen (rechten, alleen lopend, auditlog, slot na verificatie), import met Nederlandse namen en fouten, export, overzicht per plek, lijstfilter, afstemming (garantie verloopt, verlopen, geen aanbieder), vrijgaveformulier (alleen na akkoord, alleen elders, inhoud van de PDF, wie mag downloaden, basis na een geschil), bevestiging (rol, bewijs van de juiste soort, sluiten, niet bij een Depiqo-rekening), juridisch niet bij een rekening van de verhuurder, wallettekst bij een garantie, facturatie ongewijzigd, migratie 006.
- **Browsertest** groen op verse demodata, met erbij: nieuwe borg bij e-DEPO voor een adres in Gent (live waarschuwing bij "rekening verhuurder"), het blok "Waar staan je borgen" en het filter, vrijgaveformulier downloaden als beheerder en als huurder, vrijgave bevestigen met bewijs, wallet van een garantie op een telefoon.

## Keuzes in 0.4.0

- **Geen backfill van de aanbieder.** Bestaande borgen elders staan als "aanbieder onbekend" tot iemand het invult. Raden zou een bewering zonder bron zijn.
- **Waarschuwen, niet blokkeren.** Regio en aanbieder passen soms niet bij de standaardregels (oude contracten, uitzonderingen). De beheerder beslist; Depiqo toont de regel.
- **Geen nieuwe status voor de vrijgave.** De aanvraag bij de aanbieder gebeurt buiten Depiqo. Het dossier blijft op "akkoord" tot het bewijs er is; dan sluit het via de gewone overgang. Zie `ARCHITECTUUR.md`.
- **Verborgen velden tellen niet.** Een IBAN bij een garantie of een einddatum bij een andere soort dan garantie of OCMW, ingevuld en daarna verborgen, wordt niet bewaard.

## Open na 0.4.0

- Echte koppelingen met aanbieders (status van e-DEPO, attesten van banken en verzekeraars) in plaats van handmatig bewijs.
- Een vrijgaveformulier in het Frans voor Brussel.
- Een taak in "Vandaag te doen" als een garantie bijna afloopt (nu in de afstemming en op het dashboard).
- Bewijs bij een garantie heet nog "bankbewijs" in de documentsoorten; een eigen soort "garantiecertificaat" is netter.

## Getest (19 oktober 2026, versie 0.3.1)

- **105 geautomatiseerde tests geslaagd**: de 89 van 0.3.0 (twee aangepast omdat het gedrag bewust veranderde: de rekening staat direct op "vrijgave aangevraagd", en een gecrediteerde factuur kan niet op betaald) en 16 regressietests voor de negen bevindingen uit de review van 0.3.0 (`tests/test_v031.py`). De probes van de reviewer reproduceren geen van de negen meer.
- **Browsertest** opnieuw groen op verse demodata.

## Review van 0.3.0 (19 oktober 2026)

Negen bevindingen, alle opgelost; zie `CHANGELOG.md` (0.3.1). Bewust nog niet gedaan:
- **Eerste koppeling van de authenticator-app** hoort bij het accepteren van een uitnodiging voor medewerkers en beheerders, zodat een account nooit zonder tweede stap bestaat. Nu gebeurt het na de eerste login onder Beveiliging (en medewerkers worden nog via de shell aangemaakt).
- **Terugbetaling van een betaalde factuur** vastleggen, zodat een betaalde factuur gecrediteerd kan worden. Nu wordt dat geweigerd.

## Eerder getest (versie 0.3.0)

- **89 geautomatiseerde tests geslaagd**: de 48 van versie 0.2 (drie aangepast omdat het gedrag bewust veranderde: een verklaring telt niet meer als dekking, een uitbetaling moet de betaalde bedragen melden, de migratietest van 003 gebruikt alleen 001 en 002) en 41 nieuwe:
  - vier bedragen: "—" vóór de storting, cijfers volgen de bank, borg elders zonder bewijs, kaarten in de wallet;
  - bewijsniveaus: verklaard is niet groen, document vraagt een bankbewijs, alleen Depiqo verifieert (met notitie) en bevestigt juridische zekerheid (met attest), nooit omlaag;
  - partner: sandbox uit betekent geen partner, onbekende partner, echte adapter weigert sandboxrekeningen, SANDBOX-label;
  - outbox: opdracht in dezelfde transactie, geen opdracht zonder statuswijziging, nieuwe pogingen tot mislukt en opnieuw, één rekening per sleutel, betaalde bedragen moeten kloppen, `run.py dispatch`;
  - afstemming: afwijkingen en rechten; regelversies met een nepversie; plangeschiedenis, creditnota en betaalstatus; unit economics en aannames;
  - import: voorbeeld en commit, fouten per rij blokkeren, formaten en limieten, uitnodigingen; bulkacties; actiecentrum; 2FA (RFC 6238-testvectoren, venster en hergebruik, inloggen, herstelcodes, rate limiting, reset, verplichting voor medewerkers, uitzetten); communicatielog; migratie 004.
- **Browsertest in Chromium (Playwright)**: de flow van 0.2 plus: actiecentrum, wallet toont "—" bij "Ontvangen" vóór de storting en het bedrag erna, 2FA aanzetten voor een nieuwe huurder en inloggen met een code, afstemming, CSV-import met voorbeeld en bevestiging, afstemming en unit economics in de beheeromgeving. Geen JavaScript-fouten.

## Keuzes in 0.3.0

- **Geen nieuwe statussen voor bewijs.** `secured` heet "zekerheid geregistreerd"; het label volgt het bewijs. Zie `ARCHITECTUUR.md`.
- **Import is alles of niets.** Zolang één rij een fout heeft, wordt er niets geïmporteerd. Via import kan alleen bewijsniveau "verklaard"; hogere niveaus vragen bewijs per dossier.
- **Na identificatie wacht het dossier op de bank.** Het openen van de rekening is een opdracht in de outbox. Met de sandbox gaat dat direct.
- **Een planwijziging door de klant geldt vanaf volgende maand.** Een Depiqo-medewerker kan een wijziging vanaf de lopende maand laten ingaan.

## Prijsmodel

- **Negatieve marge per Depiqo-borgrekening** met de aangenomen partnerkosten (€ 0,50 per rekening per maand): Essential rekent € 0,40 en Professional € 0,25 per extra dossier. Prijzen of partnerafspraak herzien zodra er offertes zijn. Zie Unit economics in de beheeromgeving.
- **Prijzen zijn nog niet gevalideerd** met klanten. De bedragen staan op één plek (`PLANS` in `app/billing.py`).
- **Enterprise** heeft nog geen contractdatum of looptijd.
- **Zekerheid:** verpande beleggingsrekening bestaat alleen als type. Garantie is sinds 0.4.0 in gebruik voor borgen elders.

## Volgende ronde (bewust niet in 0.3.0)

1. **PostgreSQL** in plaats van SQLite (zie `ARCHITECTUUR.md` voor de stappen).
2. **Objectopslag en virusscan** voor documenten in plaats van de lokale schijf.
3. **Frans** (Brussel) en Engels.
4. **Productcatalogus en portefeuille-adapter** voor een verpande beleggingsrekening (fase 3).
5. **Echte partneradapters** (Banqup, Korfine, Certo of een bank) volgens de interface in `ARCHITECTUUR.md`.
6. **Betalingen innen** voor facturen (incasso of betaallink). Nu zet Depiqo een factuur handmatig op betaald.

## Ook nog open

- TOTP-sleutels versleuteld opslaan; 2FA verplicht maken voor beheerders van organisaties (nu een melding).
- De dispatcher automatisch laten draaien (cron of een worker) in productie; nu na elke actie en via knop of `run.py dispatch`.
- Een payout-afwijking oplossen in de beheeromgeving (nu zichtbaar in de afstemming, oplossen gaat buiten de app).
- Bulkimport van borgen met een Depiqo-borgrekening voor bestaande huurders (nu een concept per dossier).

## Niet getest

- Echte e-mailaflevering via SMTP (de code is er, getest met de uitgaande mail in de beheeromgeving).
- Belasting met veel gebruikers tegelijk; meerdere workers die tegelijk opdrachten versturen (de claim is optimistisch, maar niet onder last getest).
- Andere browsers dan Chromium; schermlezers.
- 2FA met een echte authenticator-app (getest met dezelfde berekening als de app).

## Nodig vóór echt geld

1. **Partnerbank:** contract, rekeningstructuur op naam van de huurder met blokkering of pandrecht, kosten per rekening, API of bestandsuitwisseling. Daarna een echte `BankPartner`-adapter.
2. **Juridisch advies** op de vier vragen in het businessdocument, en de regels per regio laten bevestigen.
3. **Identiteitsverificatie** via de bank of een partij als iDIN of itsme in plaats van de sandbox.
4. **Beveiliging:** zie `BEVEILIGING.md` (versleutelde TOTP-sleutels, lokale fonts, virusscan, back-ups, pentest, DPIA).
5. **PostgreSQL** en objectopslag in plaats van SQLite en lokale schijf.
6. **Facturen:** bedrijfsgegevens, btw-regels voor Belgische klanten (verlegging), betaalverwerking.
