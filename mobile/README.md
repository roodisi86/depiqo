# Depiqo Wallet: de app voor huurders

Dit is de app van Depiqo voor huurders, voor iPhone en Android. De huurder ziet hier zijn borg, waar die staat, wat er nog moet gebeuren, de eindafrekening, documenten, meldingen en (als dat aan staat) Depiqo Invest.

De app praat alleen met de bestaande Depiqo-API (`/api/v1` van het platform in `depiqo-platform`). Alle regels blijven op de server. De app verplaatst nooit borggeld: daar bestaat geen endpoint voor en de app verzint er geen.

> **Eerlijk vooraf.** Deze code is geschreven op een computer zonder toegang tot de npm-registry en zonder iPhone- of Android-simulator. De app is dus nog **nooit geïnstalleerd, gebouwd of op een telefoon gestart**. Wat wel is gecontroleerd en wat niet, staat precies in [`docs/STATUS.md`](docs/STATUS.md). Begin daar.

## Wat de app doet

- **Inloggen** met e-mail en wachtwoord, met twee-stapsverificatie (code uit de app of een herstelcode). Tokens staan alleen in de beveiligde opslag van de telefoon (Keychain op iPhone, Keystore op Android).
- **Ontgrendelen met Face ID of vingerafdruk** (zelf aan te zetten in Profiel). Inloggen met wachtwoord blijft altijd mogelijk.
- **Uitnodiging openen** via de link uit de e-mail (`https://app.getdepiqo.com/t/...` of `depiqo://t/...`). De app toont eerst groot de verhuurder, het adres, het bedrag en het kenmerk, zodat de huurder kan controleren of het klopt (bescherming tegen phishing).
- **Mijn borg**: per borg de status en **vier aparte bedragen**: Vereiste borg, Ontvangen, Bevestigd geblokkeerd (juridische zekerheid) en Rente. Is een bedrag niet bekend, dan staat er "—" met de uitleg van de server, nooit het vereiste bedrag.
- **Waar staat de borg** (Depiqo-rekening of een aanbieder elders, met referentie, bewijsniveau en bij een garantie de einddatum), de **voortgang**, **termijnen**, **wat nu te doen**, en de **betaalgegevens** met kopieerknoppen voor IBAN en kenmerk.
- **Documenten** openen en delen, en een **foto toevoegen** (camera of fotobibliotheek), alleen met de soorten die de server toestaat.
- **Eindafrekening**: de regels met bewijsstukken, akkoord gaan of bezwaar maken (met verplichte uitleg). Het **vrijgaveformulier** (PDF) voor een borg die elders staat.
- **Doorbeleggen**: kiezen waar je deel heen gaat, alleen als de server die keuze aanbiedt.
- **Geschiedenis** per borg en één tijdlijn met alles.
- **Hulp**: een vraag stellen aan Depiqo en de antwoorden lezen.
- **Meldingen** in de app, en **pushmeldingen** (de app vraagt pas toestemming als de huurder daarvoor kiest). Op het vergrendelscherm staat alleen een korte vaste titel, nooit een bedrag.
- **Drie talen**: Nederlands (standaard), Frans en Engels. Te wisselen in Profiel.
- **Privacy**: meldingen per soort aan of uit, al je gegevens downloaden (JSON), links naar privacyverklaring en voorwaarden, en een account laten verwijderen (met uitleg en de redenen als het nog niet kan).
- **Depiqo Invest** (alleen als `/config` het aanbiedt én `/me` zegt dat de huurder er recht op heeft): overzicht met grafiek, portefeuilles met kosten en scenario's, de kennis- en ervaringstoets, voorwaarden, rekening openen, storten, kopen, verkopen en wisselen via een **risicoscherm met de kosten vooraf**, orders, opnemen naar de eigen rekening, maandoverzichten en akkoord op een nieuwe servicevergoeding. Antwoordt de server `partner_unavailable`, dan toont de app alleen "Nog niet beschikbaar".
- **Testbalk**: in staging en in de sandbox staat bovenaan een gele balk, zodat niemand gesimuleerde bedragen voor echt aanziet.

## Projectstructuur

```
depiqo-mobile/
  app/                        De schermen. Elk bestand is een scherm (expo-router).
    _layout.tsx               Basis: lettertype, taal, sessie, testbalk, vergrendeling, meldingen
    (auth)/login.tsx, mfa.tsx Inloggen en de tweede stap
    t/[token].tsx             Uitnodiging (werkt zonder inloggen)
    (app)/(tabs)/             De vijf tabbladen: borg, geschiedenis, beleggen, meldingen, profiel
    (app)/deposit/[pid]/      Borg: detail, documenten, eindafrekening, geschiedenis, identiteit, doorbeleggen
    (app)/investing/          Beleggen: toets, voorwaarden, portefeuilles, storten, kopen/verkopen, risico, orders, opnemen, overzichten, vergoeding
    (app)/support/            Hulp: lijst, nieuwe vraag, gesprek
    (app)/settings/           Apparaten, privacy, account verwijderen
  src/
    api/                      De verbinding met de server: client.ts (tokens, vernieuwen), schemas.ts (controle van elk antwoord), endpoints.ts (alle endpoints)
    auth/                     Sessie, veilige opslag, ontgrendelen met biometrie
    i18n/locales/             nl.json, fr.json, en.json: alle teksten
    lib/                      Rekenen en opmaak: bedragen, data, deep links, Invest aan/uit
    notifications/            Pushmeldingen
    ui/                       Knoppen, kaarten, kleuren (huisstijl van de website), grafiek, logo
  fixtures/                   Echte antwoorden van de server (tokens weggelaten), voor de tests
  scripts/                    check-i18n.mjs, validate-json.mjs, generate-assets.mjs, capture-fixtures.mjs
  assets/                     Tijdelijke iconen en splash (vervangen voor de stores)
  docs/                       TESTEN, TESTFLIGHT-EN-PLAY, STORE-CHECKLIST, SECURITY-PRIVACY, STATUS
  app.config.ts               Instellingen per omgeving (naam, bundel-ID, API-adres, links)
  eas.json                    Bouwprofielen voor Expo Application Services (EAS)
```

## Eenmalig: je laptop klaarmaken

Je hebt nodig: een Mac of Windows-pc, [Node.js 22](https://nodejs.org) (LTS), en de code van deze map.

1. Open een terminal in de map `depiqo-mobile`.
2. Installeer alles:
   ```bash
   npm install
   npx expo install --fix
   ```
   De tweede opdracht zet de versies van alle Expo-onderdelen gelijk aan Expo SDK 53. **Doe dit altijd eerst**: de versienummers in `package.json` zijn met de hand gekozen, zonder internettoegang.
3. Controleer of alles klopt:
   ```bash
   npm run check
   ```
   Dat doet vijf controles: teksten in drie talen, JSON-bestanden, TypeScript, lint en de tests. Zie [`docs/STATUS.md`](docs/STATUS.md) voor wat je de eerste keer kunt verwachten.

## De server op je laptop bereikbaar maken voor je telefoon

Op je telefoon betekent `localhost` de telefoon zelf. De app moet dus het IP-adres van je laptop in je wifi-netwerk gebruiken.

1. Start de server in `depiqo-platform` zo, dat hij ook vanaf je wifi bereikbaar is (`python3 run.py` luistert alleen op je laptop zelf):
   ```bash
   cd ../depiqo-platform
   python3 seed.py --reset          # alleen als je verse demogegevens wilt
   python3 -m flask --app run:app run --host 0.0.0.0 --port 5000
   ```
   Doe dit alleen op een vertrouwd netwerk (thuis of kantoor), niet op openbare wifi.
2. Zoek het IP-adres van je laptop:
   - Mac: `ipconfig getifaddr en0` (bijvoorbeeld `192.168.1.20`)
   - Windows: `ipconfig`, kijk bij "IPv4-adres"
3. Telefoon en laptop moeten op hetzelfde wifi-netwerk zitten.

## Snel kijken met Expo Go

Expo Go is een gratis app uit de App Store en Google Play waarmee je de app zonder bouwen kunt openen. Handig om schermen te bekijken, maar niet alles werkt:

| Werkt in Expo Go | Werkt niet in Expo Go |
|---|---|
| Inloggen, borg, documenten, eindafrekening, Invest, talen | Pushmeldingen op Android (Expo SDK 53) |
| Foto maken en kiezen | Face ID op iPhone (Expo Go gebruikt dan de toegangscode) |
| Ontgrendelen met vingerafdruk op Android | Universele links (`https://app.getdepiqo.com/t/...`) |

Stappen:

1. Installeer **Expo Go** op je telefoon (versie voor SDK 53).
2. Start de app op je laptop, met het IP-adres van je laptop:
   ```bash
   EXPO_PUBLIC_API_URL=http://192.168.1.20:5000 npx expo start --go
   ```
   Op Windows (PowerShell): `$env:EXPO_PUBLIC_API_URL="http://192.168.1.20:5000"; npx expo start --go`
3. Scan de QR-code: op iPhone met de Camera-app, op Android in Expo Go.
4. Log in met een demo-account (zie hieronder).

## Een development build op je eigen telefoon (alle functies)

Een development build is je eigen versie van de app, met Face ID, push en deep links. Je bouwt hem één keer in de cloud van Expo (EAS); daarna laad je wijzigingen gewoon vanaf je laptop.

1. Maak een gratis account op [expo.dev](https://expo.dev) en log in:
   ```bash
   npx eas-cli login
   npx eas-cli init
   ```
   `eas init` maakt een project en toont een **project-ID**. Zet die in `app.config.ts` bij `EAS_PROJECT_ID` (vervang `''` door je ID tussen aanhalingstekens), of zet hem als omgevingsvariabele `EAS_PROJECT_ID`. Zonder project-ID werken pushmeldingen niet.
2. **iPhone**: je hebt een Apple Developer-account nodig (99 dollar per jaar; voor de stores het account van de onderneming, zie [`docs/STORE-CHECKLIST.md`](docs/STORE-CHECKLIST.md)). Registreer je telefoon:
   ```bash
   npx eas-cli device:create
   ```
   Open de link op je iPhone en volg de stappen. Zet daarna op de iPhone **Instellingen > Privacy en beveiliging > Ontwikkelaarsmodus** aan.
3. Bouw de development build:
   ```bash
   npx eas-cli build --profile development --platform ios
   npx eas-cli build --profile development --platform android
   ```
   Als de bouw klaar is, toont EAS een QR-code en een link. Open die op je telefoon en installeer "Depiqo Dev".
4. Start de app vanaf je laptop:
   ```bash
   EXPO_PUBLIC_API_URL=http://192.168.1.20:5000 npx expo start --dev-client
   ```
   Open "Depiqo Dev" op je telefoon; die vindt je laptop vanzelf (of scan de QR-code).

Je hoeft alleen opnieuw te bouwen als er een nieuw native onderdeel bij komt of als `app.config.ts` verandert. Gewone codewijzigingen zie je meteen.

## Omgevingen wisselen

Er zijn drie versies van de app, naast elkaar te installeren:

| `APP_ENV` | Naam op de telefoon | Bundel-ID | Server |
|---|---|---|---|
| `development` (standaard) | Depiqo Dev (icoon met DEV) | `com.getdepiqo.app.dev` | `EXPO_PUBLIC_API_URL`, standaard `http://localhost:5000` |
| `staging` | Depiqo Staging (icoon met STG) | `com.getdepiqo.app.staging` | `https://staging.getdepiqo.com` |
| `production` | Depiqo | `com.getdepiqo.app` | `https://app.getdepiqo.com` |

- Lokaal: zet `APP_ENV` vóór de opdracht, bijvoorbeeld `APP_ENV=staging npx expo start --dev-client`. Let op: een development build van "Depiqo Dev" heeft de bundel-ID van development; voor een echte staging-app bouw je het profiel `preview`.
- In de cloud: de bouwprofielen in `eas.json` zetten `APP_ENV` zelf: `development` (dev), `preview` (staging) en `production` (stores). Zie [`docs/TESTFLIGHT-EN-PLAY.md`](docs/TESTFLIGHT-EN-PLAY.md).
- Staging en productie werken alleen met `https`. De app weigert te starten als dat niet zo is.
- De gele testbalk komt van de server (`/config` zegt STAGING of SANDBOX). In een dev- of staging-build staat er ook een balk zolang de server nog niet heeft geantwoord.

## Demo-accounts (lokale server)

Wachtwoord voor allemaal: `Depiqo-demo-2026`.

| Account | Wat je ziet |
|---|---|
| `sanne@huurder.test` | Eindafrekening ligt klaar (akkoord of bezwaar), nog geen beleggingsrekening (het begin van Invest) |
| `mila@huurder.test` | Borg via een garantie: geen geld gestort, "Ontvangen —" |
| `sofie@huurder.test` | Borg bij e-DEPO, akkoord, vrijgaveformulier klaar |
| `daan@huurder.test` | Belegger (Neutraal) met 18 maanden geschiedenis en een geregistreerde rekening |
| `thomas@huurder.test` | Belegger (Offensief) |
| `mohamed@huurder.test` | Doorbeleggen gekozen bij zijn terugbetaling |
| `iris@huurder.test` | Haalde de toets niet en ging toch door |

Twee-stapsverificatie staat bij de demo-accounts uit. Zet het aan op de website onder Beveiliging om de tweede stap te testen.

## Controles en tests

```bash
npm run check:i18n    # zelfde sleutels en {plaatshouders} in nl, fr en en; elke tekst die de code gebruikt bestaat
npm run check:json    # alle JSON-bestanden geldig, geen tokens in de testdata
npm run typecheck     # TypeScript (strict)
npm run lint          # ESLint (onder andere: geen console.log)
npm test              # Jest: API-client, schema's tegen echte antwoorden, bedragen, talen, Invest aan/uit, deep links
npm run check         # alles hierboven
```

De testdata in `fixtures/` komt van de echte server. Opnieuw ophalen (tegen je lokale server):

```bash
npm run fixtures
```

Bij elke push naar GitHub draait dezelfde reeks automatisch (`.github/workflows/mobile-checks.yml` in de hoofdmap van de repository), plus builds en end-to-end-tests: zie [`docs/RELEASE-VALIDATIE.md`](docs/RELEASE-VALIDATIE.md).

## Regels die in de code vastliggen

- Vier bedragen, strikt gescheiden; onbekend is "—" met uitleg, nooit het vereiste bedrag (`src/lib/amounts.ts`).
- Elke geldactie stuurt een `Idempotency-Key`: één per handeling, dezelfde bij opnieuw proberen (`src/api/idempotency.ts`, `src/hooks/mutations.ts`). Knoppen staan uit zolang een verzoek loopt.
- Eén vernieuwing van de sessie tegelijk; een hergebruikt vernieuwingstoken logt uit (`src/api/client.ts`).
- Gesimuleerde gegevens nooit als echt: testbalk uit `/config`, en bij sandbox-rekeningen en de sandbox-partner een extra melding.
- Geen tokens of persoonsgegevens in logs (`src/lib/log.ts`, `src/lib/redact.ts`, lintregel `no-console`).

## Verder lezen

- [`docs/STATUS.md`](docs/STATUS.md): wat er is, wat nog nooit is gedraaid, de risico's en wat je eerst controleert.
- [`docs/TESTEN.md`](docs/TESTEN.md): testplan per scherm, met afvinklijst.
- [`docs/TESTFLIGHT-EN-PLAY.md`](docs/TESTFLIGHT-EN-PLAY.md): bouwen en verspreiden naar testers.
- [`docs/STORE-CHECKLIST.md`](docs/STORE-CHECKLIST.md): publiceren in de App Store en Google Play voor een financiële app.
- [`docs/SECURITY-PRIVACY.md`](docs/SECURITY-PRIVACY.md): beveiliging en privacy.
