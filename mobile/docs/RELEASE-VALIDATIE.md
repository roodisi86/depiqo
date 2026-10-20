# Release-validatie in GitHub Actions

Status op 20 oktober 2026: **alles staat klaar, maar niets hiervan heeft al gedraaid.** De workflows, flows en scripts zijn geschreven op een computer zonder npm-registry en zonder simulators. Wat daar wél kon, is gedaan (zie "Wat al lokaal is gecontroleerd"). De eerste run op GitHub is de eerste echte installatie, de eerste echte build en de eerste keer dat een scherm wordt getekend. Reken erop dat de eerste run fouten laat zien die je eerst moet oplossen; daarvoor is hij ook bedoeld.

## 1. De repository aanmaken en de eerste keer pushen

1. Op github.com: **New repository**. Naam bijvoorbeeld `depiqo`, **Private**, en vink niets aan (geen README, geen .gitignore, geen licentie).
2. Op je laptop, in de map met deze repository (er is al één commit, zonder remote):
   ```bash
   cd depiqo-repo
   git log --oneline            # één commit: "Depiqo: platform en app in één repository, met CI voor release-validatie"
   git remote add origin git@github.com:<jouw-account>/depiqo.git
   git branch -M main
   git push -u origin main
   ```
   (Met https in plaats van ssh: `https://github.com/<jouw-account>/depiqo.git`.)
3. Op GitHub, **Settings → Actions → General**:
   - Actions permissions: "Allow all actions and reusable workflows" (of minstens: acties van GitHub, `gradle/actions` en `reactivecircus/android-emulator-runner`).
   - Workflow permissions mag op "Read" blijven: alleen de job die de lockfile terugzet vraagt zelf schrijfrechten. Staat er een branch protection op `main` die pushes van GitHub Actions weigert, commit de lockfile dan met de hand (stap 5).
4. Optioneel, **Settings → Secrets and variables → Actions → Variables**: `STAGING_API_URL` = het https-adres van je staging-backend (zie §7). Alleen dan bouwt Android e2e ook een staging-APK.
5. De push start meteen **Platform**, **Mobile checks** en **Android e2e**. Als Mobile checks klaar is, zet je de lockfile in git, op één van twee manieren:
   - Actions → Mobile checks → **Run workflow**, vink **commit_lockfile** aan. De job "Commit lockfile" zet `mobile/package.json` en `mobile/package-lock.json` op de branch. (Een commit door GitHub Actions start zelf geen nieuwe workflows; push daarna nog iets of start ze met de hand.)
   - Of download het artifact `lockfile`, pak het uit in `mobile/`, en commit en push zelf.
   Vanaf dan gebruiken alle workflows `npm ci` en dezelfde versies.
6. **iOS e2e** start je met de hand: Actions → iOS e2e → Run workflow, kies `nl`, `large-dark`, `fr-en` of `all`.

Kosten: een privé-repository heeft een maandelijks aantal gratis minuten (bij een gratis account 2.000). Android e2e duurt ruwweg 30 minuten bouwen plus drie keer 30 tot 45 minuten emulator (parallel). macOS-minuten tellen tien keer zo zwaar; daarom draait iOS e2e alleen met de hand. Wil je iOS ook bij elke push naar `main`: haal in `.github/workflows/ios-e2e.yml` de `#` weg voor `push:` en `branches: [main]`.

## 2. Wat elke workflow bewijst

### Platform (`platform.yml`)
- **Unittests**: alle tests in `platform/tests` (267 bestaande plus 5 nieuwe in `test_mobile_contract.py`), één keer gewoon en één keer met `TZ=UTC` (termijnen rekenen met de Nederlandse kalenderdag; dit vangt fouten rond middernacht UTC). Met PyYAML en jsonschema geïnstalleerd, dus ook de controle van echte API-antwoorden tegen `openapi.yaml` (die wordt anders overgeslagen).
- **API-rooktest** (`tests/api_smoke.py`) tegen een echte server (gunicorn) met verse demodata.
- **Browsertest** (`tests/e2e_browser.py`, Playwright, Chromium zonder scherm) met schermafdrukken.
- Bewijst niet: iets over de app.

### Mobile checks (`mobile-checks.yml`)
- **`npm install`** zonder lockfile (later `npm ci`), daarna **`npx expo install --fix`**: zet alle Expo-onderdelen op de versies van SDK 53. Het resultaat (`package.json` + `package-lock.json`) is het artifact `lockfile`. Staat er al een lockfile in git en verandert `expo install --fix` toch iets, dan faalt de job: commit dan de nieuwe lockfile.
- **`npx expo-doctor`**: rapporteert problemen met versies en configuratie, maar laat de job niet falen (waarschuwing bovenaan de run, volledige tekst in `expo-doctor.txt`).
- **`npx tsc --noEmit`** met de echte typen van React Native, Expo en expo-router. Let op: de getypeerde routes van expo-router (`.expo/types`) worden pas door `expo start` gemaakt; zonder dat bestand zijn routes in CI gewoon tekst. Dat maakt de check iets losser voor routepaden, niet voor de rest.
- **`npx eslint .`** (config `eslint-config-expo`, plus `no-console` behalve in `src/lib/log.ts`).
- **`npx jest --ci`** met de echte `jest-expo`-preset. `jest.setup.ts` vervangt alleen `expo-secure-store` en `expo-crypto` door een geheugenversie: die hebben native code die in Node niet bestaat. Verder geen vervangers.
- **`node scripts/check-i18n.mjs`** en `validate-json.mjs` (talen gelijk, geen tokens in de testdata), en een controle dat alle teksten die de Maestro-flows gebruiken in nl, fr en en bestaan.
- Bewijst niet: dat de app bouwt of start.

### Android e2e (`android-e2e.yml`)
- **Bouw**: `expo prebuild` voor Android met `APP_ENV=development` en `EXPO_PUBLIC_API_URL=http://10.0.2.2:5000`, dan `./gradlew :app:assembleRelease`: een release-APK met het JavaScript erin (geen Metro nodig), getekend met de debug-sleutel. De workflow controleert na de prebuild in het gegenereerde `build.gradle` dat release getekend wordt en dat de taak `assembleRelease` bestaat, en na de bouw dat de APK de JS-bundel bevat, naar `10.0.2.2:5000` wijst, Invest bevat, geldig getekend is en (alleen in development) http toestaat.
- **Backend**: het platform uit `platform/`, verse demodata (`seed.py --reset`), `development` met sandbox, op `0.0.0.0:5000` (de emulator ziet de runner als `10.0.2.2`). Daarbovenop alleen voor CI (`.github/scripts/e2e_prepare.py`, met de functies van het platform zelf): 2FA voor `lars@huurder.test` en een verse uitnodigingslink voor Biltstraat 301. De gewone demodata voor development verandert niet.
- **Emulator**: Android 14 (API 34, google_apis, x86_64, Pixel 6), drie runs naast elkaar:
  - `nl`: alle flows in het Nederlands;
  - `large-dark`: Nederlands met lettergrootte 1,3 en donkere modus;
  - `fr-en`: alle flows in het Frans en daarna in het Engels.
- **Logcat**: tijdens de hele run opgenomen. De job faalt als de app crasht of als er een toegangs-, vernieuwings- of 2FA-token in de log staat. Die controle is exact: elke tekenreeks van tokenlengte in de log wordt gehasht en vergeleken met de tokens die de server tijdens de run uitgaf (`.github/scripts/scan_logs_for_tokens.py`).
- **Staging-APK**: alleen als `STAGING_API_URL` is gezet (moet met https beginnen); `APP_ENV=staging`, pakket `com.getdepiqo.app.staging`, geen http. Die kun je op een Android-telefoon installeren (sideloaden) om tegen staging te testen. De CI-APK (`apk-ci`) praat met `10.0.2.2` en werkt dus alleen in de emulator.

### iOS e2e (`ios-e2e.yml`)
- **Bouw**: `expo prebuild` voor iOS met `EXPO_PUBLIC_API_URL=http://127.0.0.1:5000`, `pod install`, `xcodebuild` in **Release** voor de simulator zonder ondertekening. Gecontroleerd: App Transport Security staat alleen lokaal netwerk toe en nooit "arbitrary loads", de bundel zit in de app, de app wijst naar `127.0.0.1:5000`.
- **Simulator**: iPhone 16 (of 15 als die er niet is), dezelfde flows, dezelfde varianten (lettergrootte via "extra-extra-large"), app-log met dezelfde tokencontrole, crashrapporten.

## 3. De artifacts lezen

Open de run → onderaan **Artifacts** → downloaden (zip).

- **`android-e2e-<variant>/report.html`**: overzicht per flow (geslaagd of de foutmelding van Maestro) met alle schermafdrukken. `report.md` staat ook in de samenvatting van de run.
- `maestro-<taal>/junit/*.xml`: per flow het resultaat. `maestro-<taal>/debug/<flow>/`: Maestro's eigen log en een schermafdruk op het moment van een fout. Begin bij een rode flow altijd met die laatste schermafdruk.
- `maestro-<taal>/screenshots/`: de schermafdrukken uit de flows, met namen als `a-02-amounts-mila-nl.png` (letter = flow, zie §4).
- `logcat-app.txt` (Android) of `app-log.txt` (iOS): wat de app logde. Al gecontroleerd op tokens; de volledige emulatorlog wordt niet bewaard.
- `backend/`: `seed.log`, `backend.log` (elke API-aanroep met status en duur) en `config.json`. Een 4xx of 5xx in `backend.log` op het moment dat een flow faalde, wijst meestal naar de oorzaak.
- **`android-build-logs`** / **`ios-build-logs`**: Gradle- of Xcode-log, het gegenereerde `build.gradle` / `Info.plist`, het samengevoegde manifest en de ingebouwde `app.config`.
- **`mobile-checks`**: `tsc.txt`, `eslint.txt`, `jest.txt` (+ `jest-results.json`), `expo-doctor.txt`, `expo-install-fix.txt` en `package.json.diff` (wat `expo install --fix` aan de versies veranderde).
- **`platform-results`**: `unittest.txt`, `unittest-tz-utc.txt`, `mobile-contract.txt`, `api-smoke.txt`, `browser-screens/`.

## 4. De Maestro-flows

Alle flows staan in `mobile/.maestro/flows/` en draaien via `mobile/.maestro/run-suite.sh`. Ze gebruiken testID's (taalonafhankelijk) en de echte teksten uit `src/i18n/locales/*.json` (`scripts/maestro-env.mjs` zet ze klaar). Na het inloggen kiest elke flow de taal van de run in Profiel. Geen enkele flow gaat akkoord, maakt bezwaar, accepteert een uitnodiging, plaatst een order of neemt geld op; elke run begint met verse demodata.

| Flow | Account | Wat wordt gecontroleerd |
|---|---|---|
| a. `01-login-deposits-amounts` | mila (garantie) | Inloggen zonder 2FA, borgenlijst, borg openen, de vier bedragen elk met eigen label; Ontvangen, Bevestigd geblokkeerd en Rente zijn "nog niet bekend" (op Android ook het "—" zelf), en Ontvangen is nooit het vereiste bedrag. |
| b. `02-login-2fa` | lars (2FA in CI) | Na het wachtwoord de tweede stap; de code wordt vlak voor de flow gemaakt uit het CI-geheim. |
| c. `03-invite-deeplink` | (niet ingelogd) | `depiqo://t/<token>` via `adb shell am start` of `xcrun simctl openurl`: verhuurder, adres en bedrag staan in beeld voordat er iets geaccepteerd kan worden. |
| d. `04-settlement-view` | sanne | Ontvangen toont het bedrag (bevestigd door de sandbox-bank); eindafrekening met de regel "Herstel badkamerdeur", knoppen akkoord en bezwaar zichtbaar maar niet aangeraakt. |
| e. `05-notifications-profile-language` | sanne | Meldingen, profiel, taal naar Frans en Engels met schermafdrukken, en terug. |
| f. `06-logout-protected` | thomas | Uitloggen; daarna leidt een link naar Beleggen en een herstart naar het inlogscherm. |
| g. `07-session-restore` | ella | App afsluiten en opnieuw starten: nog ingelogd (biometrie staat standaard uit). |
| h. `08-invest-visibility` | sofie, daan | Tab Beleggen ontbreekt bij sofie (haar verhuurder biedt het niet aan) en staat er bij daan, met de testbalk "SANDBOX"; geen order. |
| x. `09-wrong-password` | mila | Fout wachtwoord: de vertaalde foutmelding, niet ingelogd. |

### Wat er in de app-kopie is veranderd (alleen in deze repository)

- **testID's** (geen zichtbaar verschil, geen ander gedrag): `login-email`, `login-password`, `login-submit`, `mfa-code`, `mfa-submit`, tabknoppen `tab-deposits`, `tab-activity`, `tab-invest`, `tab-notifications`, `tab-profile` (via `tabBarButtonTestID`), `deposit-card`, `deposit-detail`, `open-settlement`, `settlement-screen`, `settlement-agree`, `settlement-dispute`, `notification-row`, `profile-screen`, `profile-logout`, taalknoppen `language-nl/fr/en` (nieuwe optionele prop `testID` op `Segmented` in `src/ui/form.tsx`), `invite-screen`, `invite-landlord`, `invite-address`, `invite-amount`, `invite-reference`, `invest-overview`. Al aanwezig: `amount-<sleutel>` en `env-banner`.
- **`app.config.ts`**:
  - Android: een kleine config-plugin zet `android:usesCleartextTraffic="true"`, **alleen bij `APP_ENV=development`**. Zonder dit weigert een release-build http naar `10.0.2.2`. Staging en productie laten het weg (Android staat dan geen http toe); de workflow controleert dat in het samengevoegde manifest.
  - iOS: App Transport Security staat nu expliciet op `NSAllowsLocalNetworking: true` en `NSAllowsArbitraryLoads: false` in development (was `NSAllowsArbitraryLoads: true`), en op beide `false` in staging en productie. Goed om te weten: iOS laat verbindingen naar een IP-adres (127.0.0.1, 192.168.x.x) altijd toe, ook zonder uitzondering; `NSAllowsLocalNetworking` gaat over namen als `laptop.local`. De echte grendel voor staging en productie blijft de https-controle in `app.config.ts` en `src/config/env.ts`. Je development-build op een iPhone met `http://192.168.1.20:5000` blijft dus werken.
  - Staging: het API-adres mag nu uit `EXPO_PUBLIC_API_URL` komen (voor de staging-APK uit `STAGING_API_URL`); zonder die variabele blijft het `https://staging.getdepiqo.com`. Het moet https zijn, anders weigert de config. Gevolg: staat `EXPO_PUBLIC_API_URL=http://...` nog in je terminal of in een `.env`, dan faalt een staging-build met een duidelijke melding. Haal hem dan weg.
- Nieuw: `scripts/maestro-env.mjs`, `.maestro/` en deze `docs/RELEASE-VALIDATIE.md`. De oude `mobile/.github/workflows/ci.yml` is opgegaan in `.github/workflows/mobile-checks.yml` (een workflow in een submap draait niet op GitHub).

### Wijzigingen in het platform (alleen in deze repository)

- Nieuwe test `tests/test_mobile_contract.py` (zie §5). Geen gedrag veranderd.
- `requirements.txt`: `tzdata` erbij (de tijdzone Europe/Amsterdam in een kale container). Nieuw `requirements-dev.txt` voor de tests (PyYAML, jsonschema, Playwright).
- `Dockerfile` luistert op `$PORT` en heeft een klein startscript (`deploy/entrypoint.sh`) dat een nieuw gekoppeld volume aan gebruiker `depiqo` geeft; `.dockerignore` houdt `instance/` en databases buiten de image; `fly.toml` voor staging.

## 5. De tien onderdelen van de release-opdracht: wat CI dekt

De nummering volgt de onderdelen zoals ze in de opdracht voor deze validatie staan; staat het bij jou anders genummerd, dan klopt de inhoud nog steeds.

| # | Onderdeel | In CI? | Hoe |
|---|---|---|---|
| 1 | Echte installatie met lockfile | Ja | Mobile checks: `npm install`, `expo install --fix`, artifact `lockfile`, optioneel terugzetten op de branch. |
| 2 | Typen, lint en tests met de echte bibliotheken | Ja | Mobile checks: `tsc`, `eslint`, `jest` met jest-expo, expo-doctor (meldt alleen). |
| 3 | Android-build | Ja | Android e2e: release-APK met bundel, getekend met de debug-sleutel. Voor Google Play is een build met EAS-credentials nodig (niet in CI). |
| 4 | iOS-build | Ja, voor de simulator | iOS e2e: Release voor de simulator, zonder ondertekening. Een ondertekende build voor een iPhone of TestFlight kan alleen met je Apple-account (EAS). |
| 5 | End-to-end tegen de backend | Ja | Maestro-flows a tot h en de foutflow, op Android (drie varianten) en iOS (met de hand). |
| 6 | Financiële juistheid | Ja | `tests/test_mobile_contract.py` (alle borgen van alle demo-huurders via `/api/v1`, tegen de regels van het platform zelf; geen route die borggeld vrijgeeft; akkoord via de app verplaatst geen geld) en de flows a en d (wat de app toont: "—" bij onbekend, nooit het vereiste bedrag als ontvangen). |
| 7 | Beveiliging en sessie | Grotendeels | 2FA, uitloggen, beschermde schermen, sessieherstel, geen tokens in de app-log (exacte controle), geen http in staging/productie. Niet in CI: schermafdruk-blokkering (FLAG_SECURE en de iOS-afscherming staan in development bewust uit), app-wisselaar, gejailbreakte toestellen. |
| 8 | Talen, grote tekst, donkere modus | Ja (emulator/simulator) | Matrix `nl`, `large-dark`, `fr-en`, met schermafdrukken om na te kijken. Of iets afgekapt of slecht leesbaar is, zie je alleen door de schermafdrukken te bekijken: daar faalt geen test op. |
| 9 | Toegankelijkheid, push, biometrie | Nee | Moet op echte toestellen, zie §6. |
| 10 | Distributie en staging | Nee (voorbereid) | Staging-backend: §7. TestFlight en Google Play interne test: `TESTFLIGHT-EN-PLAY.md`, met EAS-credentials. |

## 6. Wat jij (of een tester) op echte toestellen moet doen

- **VoiceOver (iPhone) en TalkBack (Android)**: elk scherm doorlopen. Labels en volgorde staan in de code; of het prettig voorleest, kan alleen een mens beoordelen. Begin met de borg (vier bedragen), de uitnodiging en de eindafrekening.
- **Pushmeldingen**: alleen op een echt toestel met een build die een EAS-project-ID heeft, met `PUSH_SEND=1` op de server. Emulators en simulators ontvangen geen betrouwbare Expo-push.
- **Face ID en vingerafdruk**: aanzetten in Profiel, app 60 seconden naar de achtergrond, terugkomen, ontgrendelen, en "wachtwoord gebruiken".
- **Schermafdrukken en app-wisselaar** in een staging-build (in development staan die blokkeringen bewust uit).
- **Universele links** (`https://app.getdepiqo.com/t/...`): vereisen de juiste bestanden op het domein en een ondertekende build.
- **TestFlight en Google Play (interne test)**: met je Apple- en Google-accounts en EAS, zie `TESTFLIGHT-EN-PLAY.md` en `STORE-CHECKLIST.md`.
- **Foto's toevoegen** (camera, HEIC op iPhone) en documenten delen.

## 7. Staging-backend

De staging-app en de staging-APK hebben een backend op internet nodig, met https. Voorbereid voor Fly.io (`platform/fly.toml`, `platform/Dockerfile`); Render of Railway kan ook (zie `platform/docs/DEPLOY.md`).

- **Altijd `DEPIQO_ENV=staging` met `DEPIQO_SANDBOX=1`.** Nooit `production` zonder echte bank- en beleggingspartner: productie draait geen sandbox, dus zonder partner gebeurt er niets financieels en antwoordt de API 503.
- **Eén machine met een volume op `/data`** voor SQLite en documenten. Dat is goed voor staging, niet voor productie met echt geld (dan PostgreSQL en objectopslag, zie `platform/docs/ARCHITECTUUR.md`).
- **Omgevingsvariabelen** (staging):
  - verplicht: `DEPIQO_ENV=staging`, `SECRET_KEY` (geheim, lang willekeurig), `BANK_WEBHOOK_SECRET` (geheim), `BASE_URL=https://<je-staging-adres>` (moet met https beginnen);
  - in `fly.toml`: `DEPIQO_SANDBOX=1`, `TRUST_PROXY=1`, `DATABASE_PATH=/data/depiqo.sqlite3`, `STORAGE_DIR=/data/storage`, `PUSH_SEND=0`, `PORT=8000`;
  - optioneel: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`; `APP_MIN_VERSION_IOS`, `APP_MIN_VERSION_ANDROID`, `SUPPORT_EMAIL`, `PRIVACY_URL`, `TERMS_URL`; voor deep links `APP_IOS_TEAM_ID`, `APP_BUNDLE_ID=com.getdepiqo.app.staging`, `ANDROID_SHA256_CERT`; voor push `EXPO_ACCESS_TOKEN` en `PUSH_SEND=1`. `REQUIRE_2FA_FOR_STAFF` staat in staging standaard aan.
- **Stappen met Fly.io** (eenmalig `fly auth login`), in `platform/`:
  ```bash
  fly launch --no-deploy --copy-config          # kies een eigen app-naam; pas BASE_URL in fly.toml daarop aan
  fly volumes create depiqo_staging_data --size 1 --region ams
  fly secrets set SECRET_KEY=$(openssl rand -hex 32) BANK_WEBHOOK_SECRET=$(openssl rand -hex 32)
  fly deploy
  fly ssh console -C "setpriv --reuid=depiqo --regid=depiqo --init-groups python3 seed.py --reset"
  curl https://<je-app>.fly.dev/api/v1/config     # "environment": "staging", "banner": "STAGING"
  ```
  Zet daarna `STAGING_API_URL=https://<je-app>.fly.dev` als repository-variabele (§1, stap 4).
- **Let op**: de demo-accounts hebben een bekend wachtwoord (`Depiqo-demo-2026`, staat in de README). Staging met demodata is dus voor iedereen met het adres te gebruiken. Zet er geen echte persoonsgegevens op en deel het adres alleen met testers. Bankopdrachten gaan in de sandbox meteen; wil je ook de outbox en push laten lopen, draai dan af en toe `fly ssh console -C "setpriv --reuid=depiqo --regid=depiqo --init-groups python3 run.py dispatch"` (een scheduler per minuut is voor staging niet ingericht).

## 8. Wat al lokaal is gecontroleerd, en wat niet

Gecontroleerd op de computer waar dit is gemaakt:

- Platform-tests in de kopie in deze repository, met de nieuwe contracttest: geslaagd (zie het rapport bij de oplevering). De contracttest is ook omgekeerd getest: een versie van het platform die het vereiste bedrag als "ontvangen" toont, laat hem falen.
- `e2e_prepare.py` op een verse seed, een 2FA-login met een code van `totp_now.py` via de API, de tokenscan (vindt een echt uitgegeven token, laat "[redacted]" door), het rapportscript, de controle op ondertekening van `build.gradle`, en `run-suite.sh` met een nep-Maestro (volgorde, deep link, foutafhandeling, exitcode).
- Alle workflows en flows zijn geldige YAML; shellscripts met `bash -n`; `node scripts/check-i18n.mjs` geslaagd.

Niet gecontroleerd (kon hier niet): elke stap die npm, Gradle, Xcode, een emulator, een simulator of Maestro nodig heeft. `actionlint` was niet beschikbaar. Dingen waarvan ik niet zeker ben en die de eerste run kunnen laten haken:

1. **`tabBarButtonTestID`**: de naam van de optie in React Navigation 7 (in v6 heette het `tabBarTestID`). Geeft `tsc` hier een fout, gebruik dan de naam die de typen noemen.
2. **De ingebouwde `app.config`** in de APK (`assets/app.config`) en in de iOS-app (`EXConstants.bundle/app.config`): zo schrijft expo-constants hem weg, maar de plek is niet gecontroleerd. De workflow faalt duidelijk als hij er niet is.
3. **Uitlog-bevestiging op iOS**: de knop in de systeemmelding heet hetzelfde als de knop op het profiel. De subflow `logout.yaml` probeert eerst de tweede treffer, daarna de enige. Op Android wordt de knop via `android:id/button1` gekozen.
4. **Het "—" zelf** wordt alleen op Android gecontroleerd (`childOf` de rij). Op iOS verbergt de toegankelijke rij de losse teksten; daar controleert de flow het voorgelezen label ("nog niet bekend").
5. **`hideKeyboard`** na het wachtwoord: werkt meestal; zo niet, dan wordt de inlogknop niet gevonden.
6. **De taal van het toestel** speelt geen rol: voor het inloggen gebruiken de flows alleen testID's, en daarna kiezen ze de taal in Profiel.
7. **De eerste `tsc`- en Jest-run** met de echte typen: zie `STATUS.md`, risico 2.
