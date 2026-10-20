# Status van Depiqo Wallet (versie 1.0.0, 20 oktober 2026)

> **Release-validatie:** installatie, typecheck, lint, Jest, Android- en iOS-builds en end-to-end-tests tegen de backend zijn voorbereid als GitHub Actions-workflows (nog niet gedraaid). Zie [`RELEASE-VALIDATIE.md`](RELEASE-VALIDATIE.md). Tot die workflows echt gedraaid hebben, blijft alles hieronder waar.

Kort: **de code is compleet geschreven, maar de app is nog nooit geïnstalleerd, gebouwd of op een telefoon gestart.** De omgeving waarin hij is geschreven had geen toegang tot de npm-registry en geen iPhone- of Android-simulator. Wat daar wel kon, is gecontroleerd (zie hieronder). Reken erop dat de eerste installatie en de eerste bouw kleine aanpassingen vragen.

## Wat er is

- **Alle schermen** uit de opdracht: inloggen met 2FA, vergrendelen met biometrie, uitnodiging met anti-phishingcontrole, borgoverzicht en -detail met de vier gescheiden bedragen, waar de borg staat, voortgang, termijnen, volgende stap, betaalgegevens, documenten (openen, delen, foto toevoegen), eindafrekening (akkoord of bezwaar, bewijsstukken, vrijgaveformulier), doorbeleggen (alleen als de API het aanbiedt), identiteitscontrole, geschiedenis per borg en gecombineerd, hulp (vragen en antwoorden), meldingen en push, profiel (naam, taal, 2FA-status, biometrie), apparaten, privacy (meldingen per soort, gegevens downloaden, links, account verwijderen) en Depiqo Invest (overzicht met grafiek, portefeuilles met kosten en scenario's, toets met extra bevestiging, voorwaarden, rekening openen, storten met sandbox-storting, kopen/verkopen/wisselen via offerte en risicoscherm, orders/transacties/opnames, opnemen naar eigen rekening met 2FA-code of wachttijd, maandoverzichten, nieuwe servicevergoeding).
- **API-laag**: een kleine client met bearer-token, één gedeelde tokenvernieuwing, uitloggen bij intrekking, Idempotency-Key per handeling, foutcodes, en zod-schema's voor elk antwoord. Alleen endpoints uit `openapi.yaml` 0.6.0. Tijdens het schrijven ging het platform naar **API 0.6.1** (rate limit op de 2FA-code bij een nieuw IBAN, idempotentie van uploads op inhoud, nieuwe fout `push_token_in_use`, andere uitlegteksten bij verwijderen); volgens de changelog veranderde de vorm van de antwoorden niet. De nieuwe foutcode is vertaald. De testdata in `fixtures/` komt nog van 0.6.0: haal ze opnieuw op met `npm run fixtures` en draai de tests.
- **Drie talen** (nl, fr, en) met identieke sleutels; alle machine-sleutels van de server (statussen, bewijsniveaus, soorten aanbieders, gebeurtenissen, foutcodes en meer) worden in de app vertaald.
- **Configuratie**: `app.config.ts` met drie omgevingen, `eas.json` met drie bouwprofielen en submit-instellingen, tijdelijke iconen en splash.
- **Tests** (Jest), **CI** (GitHub Actions), **scripts** (talencheck, JSON-check, iconen maken, testdata ophalen) en deze documentatie.

## Wat hier wel is gecontroleerd

| Controle | Resultaat | Hoe |
|---|---|---|
| Talen | OK: 839 sleutels in nl, fr en en; 527 sleutels die de code gebruikt bestaan; 296 machine-sleutels van de server vertaald | `node scripts/check-i18n.mjs` (ook getest dat het faalt bij een ontbrekende of extra sleutel of andere plaatshouders) |
| JSON | OK: 64 bestanden geldig, geen tokens in de testdata | `node scripts/validate-json.mjs` |
| Echte antwoorden van de server | 57 antwoorden opgehaald van de lokale ontwikkelserver (`fixtures/`), tokens weggelaten | `node scripts/capture-fixtures.mjs` |
| Schema's tegen die antwoorden | Alle 57 passen; ook `/config` van de bijgewerkte server (API 0.6.1) | Deel van de tests hieronder |
| Unit-tests | **140 van 140 geslaagd**: API-client (token in header, één vernieuwing bij gelijktijdige verzoeken, nieuw token opgeslagen vóór de herhaling, uitloggen bij `refresh_token_reused` en `device_revoked`, sessie blijft bij netwerkfout, zelfde Idempotency-Key bij herhaling, foutcodes, 426), schema's, bedragen ("—", nooit het vereiste bedrag), opmaak van geld en data, talen, Invest aan/uit, deep links, IBAN, bedragen intikken | Uitgevoerd met een minimale Jest-vervanger op Node 22 met `tsx` en zod 3.25.76 die al op de computer stonden, **niet met Jest zelf** |
| TypeScript, pure delen | Geen fouten (strict) | TypeScript 6.0 op `src/api`, `src/lib`, `src/i18n` en alle tests, met de echte typen van zod |
| TypeScript, hele app | Geen fouten | Tegen zelfgeschreven **minimale stand-ins** voor React, React Native, Expo en React Query. Dit vangt fouten in de eigen code (verkeerde props, velden of API-aanroepen; getest door expres een fout te maken), maar **niet** verkeerd gebruik van de echte bibliotheken |
| Syntaxis en imports | Alle 106 `.ts/.tsx`-bestanden geldig; alle relatieve imports bestaan | esbuild |
| Kleurcontrast | Alle tekst/achtergrond-paren van het thema ≥ 4,5:1 (WCAG AA), licht en donker | Berekend |
| Iconen | Gemaakt en bekeken; app-iconen zonder transparantie | `node scripts/generate-assets.mjs` |

Bijwerking op de lokale ontwikkelserver bij het ophalen van testdata: zes demo-huurders (daan, sanne, mila, sofie, mohamed, iris) zijn ingelogd en weer uitgelogd (dus zes afgemelde apparaten en zes meldingen "Nieuwe inlog"), en voor daan zijn twee offertes gemaakt (een offerte verplaatst geen geld). Er is niets geaccepteerd, betwist, besteld of opgenomen. De server is niet herstart of opnieuw gevuld.

## Wat NIET is gedaan of gedraaid

- **`npm install`**: nooit gedaan. Er is geen `package-lock.json`. De versies in `package.json` zijn met de hand gekozen voor Expo SDK 53, zonder te kunnen controleren of ze precies bestaan of samen passen.
- **`npm run typecheck`** met de echte typen van React Native en Expo: nooit gedraaid.
- **`npm run lint`**: nooit gedraaid.
- **`npm test`** met Jest en jest-expo: nooit gedraaid (de tests zelf wel, zie hierboven).
- **De app starten**: niet in Expo Go, niet in een development build, niet op een simulator, niet op een telefoon. Geen enkel scherm is ooit getekend.
- **EAS Build en Submit**, TestFlight, Google Play: niet gedaan.
- **Schrijvende verzoeken tegen de server** (akkoord, bezwaar, foto uploaden, order, opname, IBAN, servicevergoeding, identiteit, supportvraag, naam/taal wijzigen, gegevens downloaden, account verwijderen): niet uitgeprobeerd, om de demogegevens niet te veranderen. De payloads volgen `openapi.yaml` en de Python-code van de API.
- **Pushmeldingen**: niet getest (vereist een EAS-project, sleutels en `PUSH_SEND=1`).
- **Universele links en App Links**: niet getest (vereist een gebouwde app en de juiste bestanden op `app.getdepiqo.com`).
- **Toegankelijkheid** met VoiceOver en TalkBack, grote tekst, donkere modus: alleen in de code verzorgd, nooit bekeken.
- **Beoordeling door Apple of Google**: uiteraard niet.

## Bekende risico's en punten waar ik niet zeker van was

1. **Versies.** Mogelijk bestaat een versie niet precies zo of past hij net niet. `npx expo install --fix` lost dat voor Expo-onderdelen op. Niet door Expo beheerd: `@expo-google-fonts/manrope` (`^0.2.3`, mogelijk is er een nieuwere 0.4.x), `@tanstack/react-query`, `zod` (bewust 3.x), `@testing-library/react-native`, `jest`, `eslint`. Na een geslaagde installatie: `package-lock.json` in git.
2. **TypeScript met de echte bibliotheken.** Plekken die ik het eerst zou controleren:
   - `src/notifications/push.ts`: de velden van `setNotificationHandler` (`shouldShowBanner`/`shouldShowList` bestaan pas sinds expo-notifications 0.31).
   - `app/(app)/deposit/[pid]/documents.tsx`: `ImagePicker.UIImagePickerPreferredAssetRepresentationMode.Compatible` en `mediaTypes: ['images']`.
   - `src/ui/header.ts` importeert een type uit `@react-navigation/native-stack` (komt mee met expo-router, staat niet zelf in `package.json`).
   - Typed routes van expo-router: dynamische routes worden met `as Href` doorgegeven; de eerste `npx expo start` maakt de routetypen aan in `.expo/types`.
   - `app/(app)/(tabs)/_layout.tsx`: `sceneStyle` in de tab-opties (React Navigation 7).
3. **De testbalk boven de navigatie.** `app/_layout.tsx` zet de balk boven de navigator en geeft de navigator een bovenmarge van 0 via `SafeAreaInsetsContext`. Op toestellen met een notch of Dynamic Island goed bekijken of headers niet onder de statusbalk schuiven.
4. **Vergrendelen bij terugkomen.** De app vergrendelt na 60 seconden achtergrond. Op iOS kan de systeemprompt van Face ID de app kort "inactief" maken; dat mag geen lus geven. Testen.
5. **App-wisselaar op iOS.** Het navy scherm verschijnt als de app inactief wordt. Of iOS de schermafbeelding voor de app-wisselaar maakt vóór of na dat scherm, verschilt soms. Testen op een echte iPhone.
6. **Foto uploaden.** React Native's `FormData` met `{ uri, name, type }`; de server controleert de inhoud (JPEG/PNG). Controleer dat een iPhone-foto (HEIC) als JPEG aankomt en dat er geen locatie in staat.
7. **Downloaden en delen.** `expo-file-system` (oude API, standaard in SDK 53) met de bearer-token in de headers, daarna het deelmenu. Op Android: controleer dat "Openen met" werkt.
8. **`scheme` als lijst** (`depiqo` plus `depiqo-dev`/`depiqo-staging`) in `app.config.ts`: wordt door Expo ondersteund, maar als je dev en productie naast elkaar hebt, claimen beide `depiqo://`. Op Android krijg je dan een keuzemenu. Gebruik op testtoestellen bij voorkeur `depiqo-dev://`.
9. **Expo Go op Android** ondersteunt geen pushmeldingen meer in SDK 53; dat is verwacht.
10. **Invest in productie staat uit in de build** (`INVEST_ENABLED`), bewust, vanwege de regels van Apple en Google (zie `STORE-CHECKLIST.md` §2). In development en staging staat het aan.
11. **Teksten van de server zijn Nederlands.** Juridische teksten (risico, voorwaarden, toets) komen alleen in het Nederlands van de server; in het Frans en Engels toont de app ze met de opmerking dat ze Nederlands zijn. De app vertaalt wel alle vaste sleutels. Als je Franstalige huurders bedient, moeten die teksten (op de server) vertaald worden; dat is ook een juridisch punt.
12. **Supportvraag openen**: er is geen `GET /support/{id}`; het gesprek wordt uit de lijst gehaald (bladert verder tot het gevonden is).
13. **Geen crashrapportage** in v1. Fouten van testers hoor je alleen als ze ze melden.

## Wat je als eerste controleert bij installeren

1. `npm install`, dan `npx expo install --fix`. Lees de waarschuwingen.
2. `npm run check:i18n` en `npm run check:json` (moeten meteen slagen).
3. `npm run typecheck`. Los fouten op (zie risico 2); meestal kleine typeverschillen.
4. `npm test`. De tests zijn hier al geslaagd met een vervanger; onder Jest kan de configuratie (`jest.config.js`, `transformIgnorePatterns`) nog een aanpassing vragen.
5. `npm run lint`.
6. Lokale server met `--host 0.0.0.0` (README) en `npx expo start --go`: inloggen als `sanne@huurder.test`, borg openen, de vier bedragen controleren, eindafrekening openen.
7. Development build (`eas build --profile development`) voor Face ID, push, deep links en het vergrendelscherm.
8. Doorloop `docs/TESTEN.md`, eerst de onderdelen 2, 3, 4, 7 en 9 (inloggen, sessie, ontgrendelen, bedragen, eindafrekening).
9. Zet `package-lock.json` in git en laat de GitHub-workflows draaien (zie `RELEASE-VALIDATIE.md`).

## Wat nog open staat buiten de code

- Definitieve iconen, splash en schermafbeeldingen voor de stores.
- Webpagina voor accountverwijdering (Google-eis) en een supportpagina.
- Apple- en Google-accounts op naam van de onderneming met D-U-N-S.
- EAS-project, push-sleutels, `apple-app-site-association` en `assetlinks.json` op productie.
- Juridische toets van Invest, de partner en de teksten; daarna pas `INVEST_ENABLED=1` voor de stores.
- Beslissing over certificate pinning en integriteitscontrole zodra Invest echt geld verwerkt (zie `SECURITY-PRIVACY.md`).
