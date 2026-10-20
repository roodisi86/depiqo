# Depiqo platform

Werkend platform voor digitale huurborgen. Positie: **behoud je vastgoedsoftware en je huidige aanbieders, en beheer alle huurwaarborgen, ongeacht waar ze staan, op één plek.** Onderdelen: **Depiqo Business** voor vastgoedbeheerders, **Depiqo Wallet** voor huurders en een **beheeromgeving** voor Depiqo zelf. Alle bankfuncties lopen via een **sandbox-bank**; er wordt geen echt geld verwerkt.

## Snel starten

Vereist: Python 3.11 of nieuwer.

```bash
pip install -r requirements.txt
python3 seed.py --reset        # demo-organisatie met 12 dossiers in alle statussen
python3 run.py                 # http://127.0.0.1:5000
```

Demo-accounts (wachtwoord voor allemaal: `Depiqo-demo-2026`):

| Rol | E-mail |
|---|---|
| Beheerder organisatie | beheer@voorbeeldvastgoed.test |
| Financieel medewerker | finance@voorbeeldvastgoed.test |
| Alleen lezen | kijker@voorbeeldvastgoed.test |
| Huurder (afrekening ligt klaar) | sanne@huurder.test |
| Huurder met een garantie (geen geld gestort) | mila@huurder.test |
| Huurder bij e-DEPO, vrijgaveformulier klaar | sofie@huurder.test |
| Belegger Neutraal, 18 maanden geschiedenis | daan@huurder.test |
| Belegger Offensief, 18 maanden geschiedenis | thomas@huurder.test |
| Belegger met doorbeleggen gekozen bij zijn terugbetaling | mohamed@huurder.test |
| Belegger die de toets niet haalde en toch doorging | iris@huurder.test |
| Huurder zonder beleggingsrekening (om het begin te zien) | sanne@huurder.test |
| Depiqo-medewerker | staff@depiqo.test |
| Beheerder van een tweede organisatie | beheer@stadswonen.test |

Uitnodigings- en resetmails lees je als Depiqo-medewerker (`staff@depiqo.test`) onder Beheer → Mail (`/admin/mail`). De demo-accounts hebben twee-stapsverificatie uit; zet het aan onder Beveiliging om het te proberen.

De demo bevat borgen bij elke soort aanbieder: Voorbeeld Vastgoed BV heeft Depiqo-borgrekeningen, borgen op de rekening van de verhuurder, een geblokkeerde bankrekening, e-DEPO (geïmporteerd), een garantie en één borg waarvan de aanbieder nog onbekend is. Stadswonen Gent heeft e-DEPO (één met akkoord, klaar voor het vrijgaveformulier), een geblokkeerde bankrekening, een verzekeraar (tak 26) en een garantie die binnen 60 dagen afloopt. Namen van aanbieders zijn bewust algemeen ("Bank A", "Verzekeraar B", "Garantiefonds C").

De demo bevat ook elk bewijsniveau (verklaard, bankbewijs, geverifieerd, juridisch zeker), een opdracht die nog bij de bank moet (Kortrijksesteenweg), een mislukte uitbetalingsopdracht (Stationsweg), drie geïmporteerde borgen, plangeschiedenis en facturen (open, te laat, gecrediteerd).

## Depiqo Invest (0.5.0, sandbox)

Huurders beleggen met hun eigen geld bij een vergunde beleggingspartner, los van hun borg. Hun borg wordt nooit belegd en nooit als onderpand gebruikt. Depiqo geeft geen advies: het verwijst door en toont het overzicht. In de demo is de partner de **Sandbox-beleggingspartner**.

- In Depiqo Wallet staat naast "Mijn borg" een tab **Beleggen** (alleen voor huurders van een organisatie waarvoor Depiqo dit aanzette; in de demo Voorbeeld Vastgoed BV). Stappen: risico en rol van Depiqo, kennis- en ervaringstoets, portefeuille kiezen met kosten in euro en scenario's, voorwaarden, rekening openen, storten, kopen, overzicht met grafiek, verkopen, opnemen, wisselen, maandoverzichten.
- **Sandbox:** in je overzicht staat "Simuleer storting". Orders, opnames en servicekosten voert de partner uit als zijn klok een dag vooruit gaat: als Depiqo-medewerker onder Beheer → Beleggen, knop "Koersen een dag vooruitzetten". Daar staan ook "Servicekosten verrekenen", rekeningen activeren en de servicevergoeding (standaard 0,25% per jaar). Koersen zijn een vaste, herhaalbare reeks per fonds vanaf januari 2023.
- **Doorbeleggen:** na akkoord over de eindafrekening van een Depiqo-borgrekening kiest de huurder in de wallet of zijn deel naar zijn eigen rekening of naar zijn beleggingsrekening gaat. Zie Oudegracht 140 (mohamed@huurder.test). De beheerder ziet alleen "naar de rekening van de huurder".
- **Opnemen** kan alleen naar je eigen, geregistreerde rekening: met twee-stapsverificatie en een verse code direct, anders na 7 dagen (daan@huurder.test heeft er al een). Kopen en wisselen gaan via een controlepagina met de kosten in euro en de risico's.
- Zonder partner (`INVEST_PARTNER` leeg, of sandbox uit) is Beleggen verborgen en weigeren alle routes; de wallet toont "Nog niet beschikbaar".

## API voor de app (0.6.0)

JSON-API onder `/api/v1` voor de app voor huurders (Wallet en Invest), met bearer-tokens, meldingen, push via Expo, drie talen (nl, fr, en) en support. Specificatie in `docs/api/openapi.yaml`, uitleg met voorbeelden en het overzicht scherm per endpoint in `docs/api/README.md`.

```bash
curl -s localhost:5000/api/v1/config
python3 tests/api_smoke.py   # rooktest tegen de draaiende demo (daan@huurder.test)
```

Supportvragen uit de app beantwoordt een Depiqo-medewerker onder Beheer → Support (`/admin/support`). Apparaten waarop de huurder in de app is ingelogd, staan op de pagina Beveiliging.

## Wat werkt

- Inloggen, wachtwoord vergeten, sessies, rollen (beheerder, vastgoedbeheerder, financieel, alleen lezen) en strikte scheiding tussen organisaties.
- Team uitnodigen, rollen wijzigen, toegang intrekken.
- Borgdossier aanmaken met controle op het wettelijk maximum per regio (NL, Vlaanderen, Brussel), regels versiebeheerd met controledatum.
- Huurder uitnodigen via een eenmalige link; huurder controleert verhuurder, adres en bedrag, maakt een account en bevestigt zijn identiteit.
- Depiqo-borgrekening via de sandbox-bank: rekening op naam van de huurder, storting, blokkering, rente. **"Zekerheid bevestigd" (groen) volgt alleen op een bankbevestiging of aangetoonde juridische zekerheid.**
- Vier aparte bedragen per borg: vereiste borg, ontvangen, bevestigd geblokkeerd, rente. Wat niet bevestigd is, staat als "—".
- **Aanbieders van borgen elders (0.4.0):** per borg de soort (rekening van verhuurder of beheerder, geblokkeerde bankrekening, e-DEPO, verzekeraar tak 26, garantie of borgstelling, OCMW, anders), de naam van de aanbieder, een referentie en bij een garantie de einddatum. Waarschuwingen per regio, nooit blokkerend. In het formulier, op een aparte pagina "Waar staat de borg", in de CSV-import (ook met Nederlandse namen) en in de export.
- **"Waar staan je borgen"** op het dashboard: aantal, verplichting en hoeveel alleen verklaard per plek; filter "aanbieder" op de borgenlijst; afstemming meldt borgen zonder aanbieder en garanties die binnen 60 dagen aflopen.
- **Vrijgave bij een aanbieder:** na akkoord een vrijgaveformulier als PDF (voor beheerder en huurder), daarna "Vrijgave bij aanbieder bevestigd" met bewijs. Dat sluit het dossier.
- Borgen elders met bewijsniveaus: verklaard door beheerder, bankbewijs, extern geverifieerd (Depiqo), juridische zekerheid (Depiqo, met attest of e-DEPO).
- Bankpartner via `BANK_PARTNER`; zonder partner faalt alles dicht. Opdrachten aan de bank via een outbox met idempotentiesleutel (`python3 run.py dispatch`). Een uitbetaling sluit pas als de bank de juiste bedragen meldt.
- Afstemming (dossier, bank, opdracht, bewijs) voor Depiqo en voor financieel medewerkers.
- Bestaande borgen importeren uit CSV, bulkacties (uitnodigen, herinneren, exporteren), actiecentrum "Vandaag te doen", communicatie per dossier.
- Twee-stapsverificatie (TOTP) met herstelcodes.
- Vertrek, eindafrekening per regel met bewijsstukken, akkoord of betwisting door de huurder, uitkomst van een geschil vastleggen (akkoord of vonnis, met document). Depiqo beslist nooit zelf.
- Termijnbewaking: NL 14 of 30 dagen, Brussel 2 maanden, Vlaanderen intern streefdoel.
- Uitbetaling via vrijgave-opdracht aan de bank, met verdeling huurder en verhuurder.
- Juridische blokkade, annuleren, documenten (PDF, JPG, PNG; type gecontroleerd op inhoud), audittrail per dossier en een auditlog.
- Facturatie met drie plannen (zie hieronder), pilotkorting en facturen als PDF. Plangeschiedenis: een factuur gebruikt het plan van de eerste dag van de maand. Een beheerder wisselt zelf tussen Essential en Professional (vanaf volgende maand); Enterprise zet een Depiqo-medewerker. Betaalstatus en creditnota's.
- Zekerheid per dossier: type, bewaarder, begunstigde, status van de blokkering bij de bank en dekking. De bankberichten houden dit bij.
- Beheeromgeving: organisaties met plan en pilot, Enterprise-prijzen met ingangsmaand, eerste beheerder uitnodigen, afstemming, bankopdrachten versturen en opnieuw proberen, bewijs verifiëren, facturen (betaald, crediteren), unit economics met aannames voor partnerkosten, verstreken termijnen, bankberichten met fouten, uitgaande mail, auditlog.
- Webhook voor bankberichten met HMAC-handtekening en idempotentie.
- CSV-export met bescherming tegen formule-injectie.

## Prijzen

Bedragen per organisatie per maand, zonder btw. Huurders betalen nooit.

| Plan | Basis | Inbegrepen actieve dossiers | Extra dossier, borg elders | Extra dossier, Depiqo-borgrekening | Per nieuw dossier |
|---|---|---|---|---|---|
| Essential | € 99 | 100 | € 0,75 | € 0,40 | € 5,00 |
| Professional | € 299 | 500 | € 0,45 | € 0,25 | € 3,00 |
| Enterprise | op aanvraag | op maat | op maat | op maat | op maat |

- **Actief**: het dossier liep ergens in de maand (uitnodiging verstuurd, niet geannuleerd, niet gesloten vóór de maand).
- **Nieuw**: het dossier werd in die maand geactiveerd en is niet geannuleerd.
- De inbegrepen dossiers tellen eerst voor borgen die elders staan, want die zijn duurder.
- Pilotorganisaties krijgen een kortingsregel van 100%.
- Enterprise-bedragen staan per organisatie in de database; een leeg veld volgt Professional.

Voorbeeld: 900 actieve dossiers (360 elders, 540 op een Depiqo-borgrekening) en 30 nieuwe. Essential: € 99 + € 195 + € 216 + € 150 = € 660. Professional: € 299 + € 0 + € 100 + € 90 = € 489.

## Testen

```bash
pip install -r requirements-dev.txt     # test-extra's: PyYAML en jsonschema (OpenAPI-controle), Playwright (browsertest)
python3 -m unittest discover -s tests -v   # alle tests (zie CHANGELOG voor het aantal). Regels, statussen, facturatie, zekerheid, outbox, import, 2FA, aanbieders, vrijgave, beleggen, volledige flow, beveiliging
python3 seed.py --reset && python3 run.py &     # daarna:
python3 tests/e2e_browser.py /tmp/screens      # browsertest in Chromium (Playwright), met schermafdrukken
```

`tests/test_mobile_contract.py` controleert de bedragen die de app via `/api/v1` krijgt tegen de regels van het platform, voor alle demo-huurders, en dat geen API-route borggeld vrijgeeft. In de monorepo draait alles ook in GitHub Actions (`.github/workflows/platform.yml`).

## Live zetten (zonder echt geld)

Zie `docs/DEPLOY.md`. Kort: een Python-host (Render, Fly.io, Railway), een vaste schijf voor de database en documenten, `DEPIQO_ENV=staging` voor een demo of pilot met de sandbox (de app toont STAGING) of `DEPIQO_ENV=production` met echte partners (productie draait nooit de sandbox), een eigen `SECRET_KEY` en `BANK_WEBHOOK_SECRET`, SMTP voor e-mail, en `gunicorn "run:app"`. Laat `python3 run.py dispatch` elke minuut draaien (bank en beleggingspartner). Voor Invest met een echte partner: `INVEST_PARTNER` en `INVEST_WEBHOOK_SECRET`. In productie moeten Depiqo-medewerkers 2FA aanzetten (`REQUIRE_2FA_FOR_STAFF`).

## Mappen

```
app/                 applicatie
  security.py        sessies, CSRF, rollen, rate limiting, audit
  rules.py           regels per regio, per versie (nu 2026-10-18)
  states.py          statusmachine, bewijsniveaus en labels
  services.py        alle workflows; elke statuswijziging via transition(); outbox voor bankopdrachten
  partners.py        bank-, identiteits- en mailadapters; keuze van de bankpartner (fail-closed)
  billing.py         plannen, plangeschiedenis, prijzen, facturen en creditnota's
  finance.py         afstemming en unit economics
  providers.py       aanbieders van borgen elders: soorten, regiowaarschuwingen, overzicht
  release_form.py    vrijgaveformulier (PDF) voor een borg bij een aanbieder
  investing.py       Depiqo Invest: partnerinterface, sandboxpartner, portefeuilles, toets, orders, kosten, overzichten
  imports.py         CSV-import van bestaande borgen
  mfa.py             twee-stapsverificatie (TOTP) en herstelcodes
  storage.py         documentopslag
  api/               JSON-API voor de app (0.6.0): auth, borgen, beleggen, meldingen, support
  apitokens.py       tokens en apparaatsessies voor de app
  notify.py          meldingen en push-outbox (Expo)
  i18n.py            teksten in nl, fr en en voor de app
  views/             auth, business, wallet, admin, webhooks, deep links, support
  templates/, static/
migrations/          SQL-schema
tests/               unit- en flowtests, browsertest
docs/                architectuur, beveiliging, deploy, open punten; docs/api: OpenAPI-specificatie en uitleg
seed.py              demodata
```
