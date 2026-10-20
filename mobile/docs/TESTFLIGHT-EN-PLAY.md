# Bouwen en verspreiden: EAS, TestFlight en Google Play (interne test)

Je bouwt de app in de cloud van Expo (EAS Build) en zet hem daarna bij testers via TestFlight (iPhone) en de interne testtrack van Google Play (Android). Je hebt geen Mac nodig om te bouwen.

> Nog niet gedaan: geen van deze stappen is uitgevoerd. De eerste bouw zal waarschijnlijk iets laten zien dat moet worden aangepast (zie `docs/STATUS.md`).

## 0. Wat je nodig hebt

| Wat | Waarom | Kosten |
|---|---|---|
| Expo-account (expo.dev), liefst een organisatie "Depiqo" | EAS Build en Submit, pushmeldingen | Gratis tot een bepaald aantal builds per maand; daarna een abonnement |
| Apple Developer Program, **als organisatie** (met D-U-N-S-nummer) | TestFlight en App Store | 99 USD per jaar |
| Google Play Console, **als organisatie** | Interne test en Play Store | Eenmalig 25 USD |
| Toegang tot de DNS en de server van `app.getdepiqo.com` | Universele links (`/t/...`) | |

Waarom als organisatie: een financiële app moet in beide stores onder de naam van de onderneming staan (zie `STORE-CHECKLIST.md`). Een D-U-N-S-nummer vraag je gratis aan via Apple (duurt enkele dagen tot twee weken).

## 1. Eenmalig: EAS koppelen

```bash
npm install
npx expo install --fix
npx eas-cli login
npx eas-cli init
```

- Zet de project-ID uit `eas init` in `app.config.ts` bij `EAS_PROJECT_ID` (of als omgevingsvariabele in je terminal en in elk profiel van `eas.json` onder `env`).
- Zet je Expo-organisatie in `EXPO_OWNER` of vul `owner` in `app.config.ts` in.
- `eas.json` bewaart het buildnummer op de servers van Expo (`appVersionSource: remote`) en verhoogt het zelf bij elke productiebouw.

## 2. De drie bouwprofielen

| Profiel | Omgeving | Voor wie | Opdracht |
|---|---|---|---|
| `development` | `APP_ENV=development`, "Depiqo Dev" | Jij en ontwikkelaars, met je laptop als server | `npx eas-cli build -p ios --profile development` |
| `preview` | `APP_ENV=staging`, "Depiqo Staging", server `staging.getdepiqo.com` | Interne testers zonder store (Android als APK, iPhone via geregistreerde toestellen) | `npx eas-cli build -p all --profile preview` |
| `production` | `APP_ENV=production`, "Depiqo", server `app.getdepiqo.com` | TestFlight, Play interne test en later de stores | `npx eas-cli build -p all --profile production` |

- **iPhone en `development`/`preview`**: alleen toestellen die je registreert met `npx eas-cli device:create` (maximaal 100 per jaar). De tester opent de link, installeert een profiel en daarna de app. Op iOS 16 en nieuwer moet Ontwikkelaarsmodus aan.
- **Android en `preview`**: een APK. Stuur de link; de tester staat "installeren uit onbekende bron" toe.
- EAS vraagt bij de eerste iOS-bouw om in te loggen bij Apple en maakt certificaten en profielen voor je aan. Kies "laat EAS het beheren". Voor Android maakt EAS een upload-sleutel. **Bewaar die goed** (EAS bewaart hem; download een reservekopie met `npx eas-cli credentials`).

## 3. TestFlight (iPhone)

TestFlight werkt met de `production`-bouw: dezelfde app die later in de App Store komt, maar alleen voor testers.

1. Maak in [App Store Connect](https://appstoreconnect.apple.com) een app aan: platform iOS, naam "Depiqo", primaire taal Nederlands, bundel-ID `com.getdepiqo.app`, SKU bijvoorbeeld `depiqo-ios`.
2. Noteer de **Apple ID** van de app (een getal, onder App-informatie). Zet die in `eas.json` bij `submit.production.ios.ascAppId`, en je **Team ID** (Membership-pagina op developer.apple.com) bij `appleTeamId`.
3. Bouw en stuur in:
   ```bash
   npx eas-cli build -p ios --profile production
   npx eas-cli submit -p ios --profile production --latest
   ```
   Of in één keer: `npx eas-cli build -p ios --profile production --auto-submit`.
4. Na 10 tot 30 minuten staat de bouw in App Store Connect onder TestFlight. Vul "Exportnaleving" in als dat gevraagd wordt: de app gebruikt alleen standaardversleuteling (HTTPS) van iOS; `ITSAppUsesNonExemptEncryption` staat al op `false`.
5. **Interne testers** (tot 100 mensen met een rol in je App Store Connect-team): TestFlight > Interne tests > groep maken > testers toevoegen > bouw kiezen. Geen beoordeling door Apple nodig.
6. **Externe testers** (tot 10.000, via e-mail of openbare link): vereist een korte beoordeling door Apple ("Beta App Review"). Vul testinformatie en een **demo-account** in (zie `STORE-CHECKLIST.md`).
7. Testers installeren de app **TestFlight** uit de App Store en accepteren de uitnodiging.

Wil je ook de **staging-app** via TestFlight verspreiden? Maak dan een tweede app aan in App Store Connect met bundel-ID `com.getdepiqo.app.staging` en een extra profiel in `eas.json` (kopie van `production` met `APP_ENV=staging` en een eigen `ascAppId`). Zo blijft de productie-app schoon.

## 4. Google Play: interne testtrack (Android)

1. Maak in de [Play Console](https://play.google.com/console) een app aan: naam "Depiqo", standaardtaal Nederlands, app (geen game), gratis.
2. **De eerste upload moet met de hand** (een beperking van Google):
   ```bash
   npx eas-cli build -p android --profile production
   ```
   Download het `.aab`-bestand uit EAS en upload het in de Play Console onder Testen > Interne test > Nieuwe release. Kies daarbij **Play App Signing** (Google beheert de ondertekeningssleutel).
3. Voor volgende uploads via EAS Submit: maak in Google Cloud een **serviceaccount** met toegang tot de Play Console (EAS-documentatie "Creating a Google Service Account"), download de JSON-sleutel naar `secrets/google-play-service-account.json` (staat in `.gitignore`, **nooit in git**). Daarna:
   ```bash
   npx eas-cli submit -p android --profile production --latest
   ```
   `eas.json` zet dit op de track `internal` als concept (`releaseStatus: draft`); je zet de release in de Play Console live voor testers.
4. **Testers**: Testen > Interne test > Testers > e-maillijst (tot 100 Google-accounts). Deel de aanmeldlink. Testers installeren daarna gewoon via Google Play.
5. Interne testen gaan zonder beoordeling door Google; wel moet een deel van de winkelgegevens zijn ingevuld (app-toegang, advertenties, inhoudsclassificatie, doelgroep, Data safety). Zie `STORE-CHECKLIST.md`.

## 5. Universele links en App Links (`https://app.getdepiqo.com/t/...`)

De app claimt `/t/*` en `/app-link/*` op `app.getdepiqo.com` (en voor staging ook `staging.getdepiqo.com`). Dat werkt pas als de server het bevestigt. De backend levert de bestanden zelf, vanuit zijn configuratie:

| Server-instelling | Waarde |
|---|---|
| `APP_IOS_TEAM_ID` | je Apple Team ID |
| `APP_BUNDLE_ID` | `com.getdepiqo.app` (productie). Op staging: `com.getdepiqo.app.staging,com.getdepiqo.app.dev` |
| `ANDROID_SHA256_CERT` | SHA-256 van de ondertekeningssleutel. Voor de Play-versie: Play Console > Instellingen > App-integriteit > **App-ondertekeningssleutel**. Voor de APK uit `preview`: `npx eas-cli credentials` > Android > Keystore. Meerdere waarden scheiden met komma's. |

Controleer daarna:

- `https://app.getdepiqo.com/.well-known/apple-app-site-association` geeft JSON met `TEAMID.com.getdepiqo.app` en de paden `/t/*` en `/app-link/*`.
- `https://app.getdepiqo.com/.well-known/assetlinks.json` geeft JSON met `com.getdepiqo.app` en de SHA-256.
- Android: `adb shell pm get-app-links com.getdepiqo.app` moet `verified` tonen voor `app.getdepiqo.com`.
- iOS houdt de bestanden een tijd vast. Na een wijziging: app verwijderen en opnieuw installeren.

## 6. Pushmeldingen in de builds

- **iPhone**: EAS vraagt bij de eerste bouw of het een **push-sleutel (APNs)** moet maken. Zeg ja. Controleer met `npx eas-cli credentials`.
- **Android**: Expo stuurt via Firebase Cloud Messaging. Maak een Firebase-project, voeg een Android-app toe met pakketnaam `com.getdepiqo.app` (en `.staging`, `.dev`), maak een serviceaccountsleutel (FCM V1) en upload die in EAS: `npx eas-cli credentials` > Android > Push Notifications. Zet het `google-services.json`-bestand **niet** in git als je het gebruikt; de app heeft het voor alleen Expo-push niet nodig.
- **Server**: `PUSH_SEND=1` en elke minuut `python3 run.py dispatch`. In de sandbox staat versturen standaard uit.
- Test: log op twee toestellen in; het eerste krijgt "Nieuwe inlog op je account".

## 7. Wat testers nodig hebben

- **iPhone**: de app TestFlight, een Apple ID, iOS 15.1 of nieuwer (minimum van Expo SDK 53). Voor `development`/`preview`-builds: hun toestel moet geregistreerd zijn.
- **Android**: een Google-account op de lijst van de interne test (of de APK-link van `preview`), Android 7 of nieuwer.
- **Een account op de juiste server**: voor de productie-app een uitnodiging van een verhuurder op `app.getdepiqo.com`; voor staging de demo-accounts of een uitnodiging op staging.
- **Instructies**: stuur ze `docs/TESTEN.md` (of de relevante delen) en vraag om meldingen met toestel, systeemversie, taal en stappen.
- **Wat ze niet moeten doen**: echt geld overmaken naar een IBAN uit een staging- of sandbox-app. De gele balk staat er niet voor niets.

## 8. Updates zonder nieuwe bouw (later)

`app.config.ts` is voorbereid op EAS Update (`runtimeVersion` volgt de versie van de app; `updates.url` gebruikt je project-ID). Zet het pas aan na de eerste goedgekeurde storeversie en spreek af welke wijzigingen via een update mogen (alleen JavaScript en teksten, nooit iets wat de regels voor geld of privacy verandert zonder review). Kanaal per profiel: `development`, `preview`, `production` (al ingevuld in `eas.json`).
