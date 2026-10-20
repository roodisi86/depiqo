# Beveiliging en privacy van de app

Per onderwerp: wat de app doet, waarom, en wat nog open staat. Vink af na controle op een echt toestel. De serverkant (rate limits, tokens als hash, auditlog, regels voor geld) staat in de documentatie van `depiqo-platform` en wordt hier alleen genoemd waar de app erop rekent.

## 1. Tokens en sessie

- [ ] **Alleen in de beveiligde opslag.** Toegangs- en vernieuwingstoken staan alleen in `expo-secure-store` (iOS Keychain, Android Keystore-versleutelde opslag), met `WHEN_UNLOCKED_THIS_DEVICE_ONLY`: leesbaar alleen als het toestel ontgrendeld is, nooit mee naar een ander toestel of een back-up. Niet in AsyncStorage, niet in bestanden, niet in de URL. Code: `src/auth/secureTokenStore.ts`.
- [ ] **Geen cookies.** Elk verzoek gaat met `Authorization: Bearer` en `credentials: "omit"`; de server weigert cookie-inlog voor de API.
- [ ] **Kort geldig toegangstoken** (15 minuten). Het vernieuwingstoken (30 dagen) werkt één keer.
- [ ] **Eén vernieuwing tegelijk.** Alle verzoeken die een nieuw token nodig hebben, delen één vernieuwing (`src/api/client.ts`). De server beëindigt de hele toestelsessie als een gebruikt vernieuwingstoken opnieuw opduikt (`refresh_token_reused`); de app voorkomt dat zelf te veroorzaken. Het nieuwe paar wordt opgeslagen vóór het oude wordt losgelaten.
- [ ] **Automatisch uitloggen** bij `device_revoked`, `token_invalid`, `refresh_token_reused` of een verlopen sessie: tokens gewist, tijdelijke bestanden gewist, gegevens uit het geheugen gewist, inlogscherm met de reden.
- [ ] **Uitloggen** roept `POST /auth/logout` aan (de server zet ook de pushtoken van dit toestel uit) en wist daarna alles lokaal, ook zonder netwerk.
- [ ] **Na opnieuw installeren** (iOS bewaart de Keychain na verwijderen van een app): de app herkent een nieuwe installatie aan een markeerbestand en wist oude sessiegegevens.
- [ ] **Android-back-up uit** (`allowBackup: false`), zodat app-gegevens niet in Google-back-ups belanden.
- [ ] **Apparatenoverzicht.** De gebruiker ziet zijn sessies (Profiel > Apparaten) en kan ze afmelden. Toestelnaam = "Depiqo app (model)", niet de naam die de eigenaar aan zijn telefoon gaf (die bevat vaak een persoonsnaam).
- [ ] **2FA** wordt ingesteld op de website; de app ondersteunt de tweede stap met code of herstelcode. De 2FA-challenge staat alleen in het geheugen, niet in een route of op schijf.

## 2. Ontgrendelen met biometrie

- [ ] **Opt-in** in Profiel; aanzetten vraagt eerst een geslaagde Face ID / vingerafdruk.
- [ ] Bij **starten** en na **60 seconden op de achtergrond** vraagt de app om te ontgrendelen. Tot dan zijn de schermen bij een koude start niet eens geladen en doet de app geen API-verzoeken. Bij terugkomen ligt het vergrendelscherm over de app en is de inhoud verborgen voor VoiceOver/TalkBack.
- [ ] **Terugval**: "Inloggen met wachtwoord" beëindigt de sessie en gaat naar het inlogscherm. De toegangscode van het toestel wordt als terugval van het systeem toegestaan.
- [ ] Een foto maken of het deelmenu openen telt niet als "op de achtergrond" (`withLockSuspended`).
- **Keuze in v1**: biometrie is een slot in de app (`expo-local-authentication`), niet een sleutel die aan biometrie vastzit in de Keychain (`requireAuthentication` van secure-store). Reden: dat zou bij elke tokenvernieuwing (elk kwartier) en op Android bij elk wegschrijven om biometrie vragen. Wil je het strenger: sla dan alleen het vernieuwingstoken op met `requireAuthentication: true` en vraag biometrie alleen bij de koude start. Dat kost een paar uur werk en extra testen.

## 3. Netwerk en certificaten

- [ ] **Alleen HTTPS** voor staging en productie. `app.config.ts` en `src/config/env.ts` weigeren een `http`-adres buiten development. iOS App Transport Security staat alleen in de development-app open (voor de laptop op je wifi). Android blokkeert http standaard in release-builds.
- [ ] **Time-out** van 20 seconden per verzoek.
- [ ] **Downloads alleen van de eigen API.** Bestanden worden alleen opgehaald met het token als het pad van de server komt en begint met `/api/v1/`. Een link van elders krijgt nooit het token.
- [ ] **Antwoorden gecontroleerd.** Elk antwoord gaat door een zod-schema (`src/api/schemas.ts`). Een onverwacht antwoord geeft een nette fout ("antwoord dat de app niet begrijpt"), geen half scherm. Geld in een andere munt dan EUR wordt geweigerd.

**Certificate pinning: niet in v1.** Waarom:
- Expo heeft het niet ingebouwd; het vraagt een extra native module (bijvoorbeeld `react-native-ssl-public-key-pinning`, met config-plugin) en dus een development build.
- Een fout bij het vernieuwen van certificaten (bijvoorbeeld een andere certificaatuitgever bij de hostingpartij) maakt de app voor iedereen onbruikbaar tot er een nieuwe versie in de stores staat.
- De aanvalsweg die pinning dichtzet (een aanvaller met een eigen vertrouwd certificaat op het toestel) is al klein: Android-apps vertrouwen standaard geen certificaten die de gebruiker zelf installeerde, iOS vraagt een bewuste handeling, en de server beperkt de schade (kortlevende tokens, detectie van hergebruik, 2FA en wachttijd voor een nieuw IBAN).

Pinning later toevoegen (aanbevolen zodra Invest echt geld verwerkt):
1. Installeer `react-native-ssl-public-key-pinning` en voeg de config-plugin toe; bouw opnieuw.
2. Pin de **publieke sleutel (SPKI-hash)** van de tussenliggende certificaatuitgever van `app.getdepiqo.com` plus minstens één **reservesleutel** die je nu al aanmaakt en veilig bewaart. Niet het bladcertificaat (dat wisselt om de paar maanden).
3. Pin alleen in `production`; staging en development niet (anders kun je niet testen met proxy's).
4. Maak een rotatieplan: nieuwe sleutel eerst als extra pin uitbrengen, pas daarna wisselen. Houd `minimum_app_version` in `/config` als noodrem.

## 4. Gejailbreakte of geroote toestellen

- **Standpunt v1: geen detectie en geen blokkade.** Detectie is eenvoudig te omzeilen, geeft valse meldingen (ook bij mensen met aangepaste toegankelijkheid of oudere toestellen) en schijnveiligheid. De bescherming zit op de server: elke geldactie wordt daar gecontroleerd, opnames gaan alleen naar een geregistreerde eigen rekening (met 2FA meteen, anders na een wachttijd), en borggeld kan de app helemaal niet verplaatsen.
- **Later, voor Invest met echt geld**: overweeg Play Integrity (Android) en App Attest (iOS) voor risicovolle acties (IBAN registreren, opnemen, orders). Dat vraagt een controle op de server; alleen een controle in de app heeft weinig zin.

## 5. Logging

- [ ] De app logt bijna niets. `console` mag alleen in `src/lib/log.ts` (ESLint-regel `no-console`), en dat logt alleen in development builds, na `redact()` (tokens, wachtwoorden, codes, IBAN's, e-mailadressen en namen worden weggelaten).
- [ ] Geen API-antwoorden, tokens of persoonsgegevens in logs, ook niet bij fouten. Foutmeldingen bevatten alleen de foutcode.
- [ ] Geen analytics en geen crashrapportage in v1. Voeg je die toe (bijvoorbeeld Sentry): zet persoonsgegevens en request-bodies uit, en werk de privacylabels in de stores bij.
- [ ] De testgegevens in `fixtures/` bevatten geen tokens (`npm run check:json` controleert dat).

## 6. Pushmeldingen

- [ ] De server stuurt alleen een **vaste korte titel** ("Je storting is ontvangen") en "Open Depiqo voor de details", plus `notification_id`, `path` en `type`. **Nooit bedragen, adressen of namen.** Wat er op het vergrendelscherm staat, is daarom niet gevoelig; het Android-kanaal mag het tonen.
- [ ] De details laadt de app pas na inloggen (en na Face ID als dat aan staat).
- [ ] Het pad uit een melding gaat door dezelfde strenge parser als deep links (`src/lib/deeplink.ts`); onbekende paden worden genegeerd.
- [ ] De app vraagt **niet vanzelf** om toestemming; de gebruiker kiest via een kaart met uitleg.
- [ ] Per soort uit te zetten (Privacy > Pushmeldingen). Uitloggen of een toestel afmelden zet de pushtoken op de server uit.
- [ ] Expo is verwerker (Expo Push Service stuurt door naar Apple en Google). Opnemen in de privacyverklaring en de verwerkersafspraken.

## 7. Schermafbeeldingen en app-wisselaar

- [ ] Zodra de app niet actief is, ligt er een navy scherm met het logo over alles (`PrivacyShield`), zodat de app-wisselaar op iOS geen bedragen toont.
- [ ] Op gevoelige schermen (borg, bedragen, betaalgegevens, beleggen, profiel, uitnodiging) zet de app `FLAG_SECURE` via `expo-screen-capture`: op Android geen schermafbeelding en een leeg voorbeeld in de app-wisselaar; op iOS blokkeert het schermopnames waar het systeem dat toelaat. In development builds staat dit uit, zodat testers schermafbeeldingen kunnen maken.
- **Beperking**: iOS staat apps niet toe gewone schermafbeeldingen echt te verbieden. Een gebruiker kan zijn eigen gegevens altijd fotograferen; het doel is dat er niets per ongeluk zichtbaar wordt.

## 8. Deep links en invoer

- [ ] Alleen `https://app.getdepiqo.com/...` (en `staging.getdepiqo.com`), `depiqo://` en de varianten voor dev en staging. Alleen de paden `/t/<token>` en `/app-link/borg|beleggen|beveiliging|support`. Tokens en ID's met een strikt patroon; alles anders gaat naar het startscherm.
- [ ] Een uitnodiging toont eerst verhuurder, adres, bedrag en kenmerk met de waarschuwing tegen phishing; accepteren kan pas na een expliciet vinkje.
- [ ] Een link uit een serverfout (`use_web`) opent alleen als het een http(s)-adres is.
- [ ] Bestandsnamen van downloads worden opgeschoond; tijdelijke bestanden staan in de cachemap en worden bij uitloggen en bij het starten gewist.

## 9. Geld

- [ ] De app heeft **geen endpoint om borggeld te verplaatsen** (de server ook niet). De uitbetaling start de verhuurder en voert de bank uit.
- [ ] Elke schrijvende geldactie stuurt een **Idempotency-Key**: één per handeling, dezelfde bij opnieuw proberen (ook na een netwerkfout of een tokenvernieuwing), een nieuwe als de gebruiker iets anders invult. Knoppen staan uit en dubbel tikken wordt genegeerd zolang een verzoek loopt.
- [ ] Na een netwerkfout bij een geldactie zegt de app eerlijk "We weten niet zeker of je verzoek is aangekomen. Probeer het opnieuw: het wordt niet dubbel uitgevoerd."
- [ ] Een order kan alleen na een **offerte** (kosten vooraf, scenario's, risico) en een **expliciet vinkje** op het risicoscherm; de offerte verloopt na 10 minuten.
- [ ] Opnemen alleen naar de geregistreerde eigen rekening, met bevestiging van bedrag en gemaskeerd IBAN.
- [ ] Gesimuleerde gegevens worden nooit als echt getoond: testbalk uit `/config`, en extra meldingen bij een sandbox-rekening en de sandbox-beleggingspartner.

## 10. Gegevensminimalisatie

- [ ] De app bewaart **geen gegevens op schijf** behalve de tokens, de taalkeuze en de keuze voor biometrie. Alles wat van de server komt, staat alleen in het geheugen (React Query, zonder opslag) en is weg na uitloggen of afsluiten.
- [ ] Geen contacten, geen locatie, geen microfoon (Android-machtigingen uitgezet), geen toegang tot alle foto's (systeemkiezer).
- [ ] Foto's worden opnieuw gecomprimeerd (kwaliteit 70 %) en de app vraagt geen EXIF-gegevens op. Bij het opnieuw comprimeren gaan EXIF-gegevens zoals de locatie normaal verloren. **Nog niet gecontroleerd**: upload een foto met locatie en controleer op de server dat er geen GPS-gegevens in het bestand staan.
- [ ] Geboortedatum en volledige naam alleen bij de identiteitscontrole, en alleen naar de server voor de partnerbank.

## 11. Rechten onder de AVG / GDPR

| Recht | Waar in de app |
|---|---|
| Inzage en overdraagbaarheid | Privacy > Gegevens downloaden (`POST /me/export`, één JSON-bestand). De app waarschuwt dat het bestand gevoelig is en verwijdert de kopie uit de cache bij uitloggen. |
| Rectificatie | Naam wijzigen in Profiel; e-mailadres via support (zo blijft de koppeling aan de borg kloppen). |
| Verwijdering | Privacy > Account verwijderen: uitleg wat meteen weg is en wat de wet laat bewaren, de redenen als het nog niet kan, bevestiging met wachtwoord. |
| Bezwaar tegen berichten | Pushmeldingen per soort uit te zetten. |
| Informatie | Links naar privacyverklaring en voorwaarden (uit `/config`), contact via support. |

- [ ] Google vraagt daarnaast een **webpagina** waar je ook zonder app om verwijdering kunt vragen (zie `STORE-CHECKLIST.md`). Die bestaat nog niet.

## 12. Afhankelijkheden bijwerken

- [ ] Weinig afhankelijkheden: alleen Expo-modules, React Query, zod, react-native-svg en het lettertype. Geen analytics of advertentie-SDK's.
- [ ] Na `npm install` het `package-lock.json` in git zetten en in CI `npm ci` gebruiken (zie `.github/workflows/mobile-checks.yml` in de hoofdmap en `docs/RELEASE-VALIDATIE.md`).
- [ ] Elke maand: `npx expo install --check`, `npm audit`, en de releasenotes van Expo lezen. Zet Dependabot of Renovate aan op GitHub.
- [ ] Elk jaar: overstappen naar de nieuwe Expo SDK (Apple en Google eisen nieuwe systeemversies; Expo ondersteunt ongeveer de laatste drie SDK's).
- [ ] Na een update: `npm run check` en de belangrijkste delen van `docs/TESTEN.md` (inloggen, vernieuwen, bedragen, geldacties) op twee toestellen.
