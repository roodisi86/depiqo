# Publiceren in de App Store en Google Play: checklist voor een financiële app

Depiqo Wallet toont huurders hun borg (die staat bij een partnerbank, bij de verhuurder of bij een andere aanbieder) en laat ze reageren op de eindafrekening. Depiqo Invest laat huurders beleggen bij een vergunde partner. Voor beide stores is dit een **financiële app**. Daar gelden strengere regels dan voor een gewone app. Deze lijst is een werklijst, geen juridisch advies: laat de punten over vergunningen en privacy toetsen door een jurist.

Vink af wat klaar is.

## 1. Accounts op naam van de onderneming

- [ ] **D-U-N-S-nummer** voor de onderneming (gratis, via Apple of Dun & Bradstreet; reken op 1 tot 14 dagen). Nodig voor beide stores.
- [ ] **Apple Developer Program als organisatie** (niet als persoon). Apple eist dat apps voor bank- en financiële diensten worden ingediend door de rechtspersoon die de dienst levert (richtlijn 5.1.1(ix)).
- [ ] **Google Play Console als organisatie**, met geverifieerde gegevens. Google eist voor apps met financiële producten en diensten een organisatieaccount.
- [ ] **EU-handelaarsstatus (Digital Services Act)**: in App Store Connect en de Play Console aangeven dat je een handelaar bent, met adres, telefoon en e-mail die openbaar in de store komen.
- [ ] Rollen: geef medewerkers toegang via de teams van Apple en Google, deel geen wachtwoorden.

## 2. Invest blijft uit tot partner en juridische toets rond zijn

De store-build (`production`) bevat Invest standaard **niet**: `app.config.ts` zet `INVEST_ENABLED` uit voor productie, en de app toont Invest alleen als de build, `/config` én `/me` het toestaan.

Waarom:

- Apple richtlijn **3.2.1 (viii)**: apps voor beleggen, handelen of vermogensbeheer moeten worden ingediend **door de financiële instelling die die dienst levert**. Depiqo is geen beleggingsonderneming; het verwijst door naar een vergunde partner. Apple kan dan vragen dat de partner de app indient, of om bewijs van vergunning en samenwerking. Zonder dat risico je afwijzing of verwijdering.
- Apple richtlijn **2.3.1**: geen verborgen functies die na de beoordeling op afstand worden aangezet. Een server-schakelaar alleen is dus niet genoeg; daarom zit de schakelaar ook in de build.
- Google Play vraagt bij beleggingsfuncties om een **verklaring financiële functies** en kan om vergunningen per land vragen.
- In Nederland en België gelden regels voor beleggingsdiensten (AFM en MiFID II in Nederland, FSMA in België), onder meer over de passendheidstoets, kosteninformatie vooraf en reclame. Of Depiqo als verwijzer een vergunning of vrijstelling nodig heeft, moet een jurist beoordelen.

Invest aanzetten in de stores kan pas als:
- [ ] de beleggingspartner een vergunning heeft voor de landen waar je publiceert en het contract getekend is;
- [ ] een jurist de teksten (risico, rol van Depiqo, kosten, scenario's, passendheidstoets) en de rolverdeling heeft goedgekeurd;
- [ ] duidelijk is wie de app indient (Depiqo met bewijs van de samenwerking, of de partner), en Apple dat accepteert;
- [ ] je een nieuwe build maakt met `INVEST_ENABLED=1`, de functie meldt in de beoordelingsnotities en de verklaringen in beide stores bijwerkt.

## 3. App Store Connect (Apple)

**App-gegevens**
- [ ] Naam: "Depiqo" (controleer of hij vrij is). Ondertitel, bijvoorbeeld "Je huurborg, veilig en overzichtelijk".
- [ ] Primaire categorie: **Financiën**. Primaire taal: Nederlands; lokalisaties Frans en Engels.
- [ ] Bundel-ID `com.getdepiqo.app`. SKU naar keuze.
- [ ] Beschrijving en trefwoorden in nl, fr en en. Geen beloftes over rendement; noem dat Depiqo geen geld van de borg verplaatst.
- [ ] **Support-URL** (verplicht), bijvoorbeeld `https://getdepiqo.com/support`. Die pagina moet bestaan en een manier geven om contact op te nemen.
- [ ] **Privacybeleid-URL** (verplicht): dezelfde als `PRIVACY_URL` op de server (de app toont die link onder Privacy). Nu `https://getdepiqo.com/privacy`.
- [ ] Marketing-URL (optioneel): `https://getdepiqo.com`.
- [ ] Copyright: "2026 [juridische naam van de onderneming]".

**Leeftijdsclassificatie**
- [ ] Vragenlijst invullen: geen geweld, geen gokken, geen ongecontroleerde inhoud van gebruikers (supportberichten gaan alleen naar Depiqo). Uitkomst waarschijnlijk 4+. Huurcontracten sluiten volwassenen; dat hoeft de leeftijdsclassificatie niet te veranderen.

**App-privacy (privacylabels)**. Wat de app echt verzamelt of naar de server stuurt:

| Apple-categorie | Wat in Depiqo | Gekoppeld aan gebruiker | Doel | Tracking |
|---|---|---|---|---|
| Contactgegevens > Naam | naam in het profiel; volledige naam bij de identiteitscontrole | Ja | App-functionaliteit | Nee |
| Contactgegevens > E-mailadres | inlog en account | Ja | App-functionaliteit | Nee |
| Contactgegevens > Overige contactgegevens | geboortedatum bij de identiteitscontrole (naar de partnerbank) | Ja | App-functionaliteit | Nee |
| Financiële gegevens > Overige financiële gegevens | borgbedragen, eindafrekening, beleggingsgegevens (alleen als Invest aan staat), IBAN van de eigen rekening voor opnames | Ja | App-functionaliteit | Nee |
| Gebruikersinhoud > Foto's of video's | foto's die de huurder bij zijn borg zet | Ja | App-functionaliteit | Nee |
| Gebruikersinhoud > Klantenservice | vragen aan support | Ja | App-functionaliteit | Nee |
| Identificatoren > Gebruikers-ID | account-ID | Ja | App-functionaliteit | Nee |
| Identificatoren > Apparaat-ID | Expo-pushtoken en toestelmodel van de sessie (voor push en het overzicht "Apparaten") | Ja | App-functionaliteit | Nee |

- [ ] **Niet** verzameld: locatie, contacten, browsegeschiedenis, zoekgeschiedenis, gebruiksgegevens/analytics, crashgegevens (v1 heeft geen crashrapportage; zet dit label aan als je er later een toevoegt), advertenties.
- [ ] "Tracking": **nee**. Geen advertentie-ID, geen trackers van derden.
- [ ] Controleer dit opnieuw bij elke nieuwe versie (bijvoorbeeld als er crashrapportage bij komt).

**Account verwijderen (richtlijn 5.1.1(v))**
- [ ] De app heeft het: Profiel > Privacy en gegevens > Account verwijderen. Het legt uit wat meteen wordt verwijderd en wat volgens de wet bewaard blijft, en toont waarom het nog niet kan (lopende borg, geld of orders op de beleggingsrekening). Apple staat zulke wettelijke uitzonderingen toe voor gereguleerde diensten, zolang je het duidelijk uitlegt.
- [ ] Noem in de beoordelingsnotities waar de knop zit.

**Beoordeling: demo-account en notities**
- [ ] Maak op **productie** (`app.getdepiqo.com`) een aparte testorganisatie "Depiqo Review" met een testpand en een uitnodiging voor `review@getdepiqo.com` (of vergelijkbaar), zodat er een borg zichtbaar is. Gebruik duidelijk testgegevens en geen echt geld. Twee-stapsverificatie uit voor dit account (of geef een vaste herstelcode in de notities).
- [ ] Vul bij "Aanmeldgegevens" het e-mailadres en wachtwoord in.
- [ ] Beoordelingsnotities (voorbeeld): "Depiqo Wallet is for tenants whose landlord uses Depiqo. Tenants join through an invitation link from their landlord; there is no open sign-up. The app shows the rental deposit (held at a partner bank, the landlord, or another provider), lets the tenant respond to the final settlement and upload photos. The app never moves money. Account deletion: Profile > Privacy > Delete account. Demo account: …"
- [ ] Contactpersoon met telefoonnummer voor vragen van Apple.

**Exportnaleving (versleuteling)**
- [ ] De app gebruikt alleen de standaardversleuteling van het systeem (HTTPS/TLS, Keychain). `ITSAppUsesNonExemptEncryption` staat op `false` in `app.config.ts`, dus App Store Connect vraagt er niet meer naar. Voeg je eigen versleuteling toe, dan dit opnieuw beoordelen.

**Schermafbeeldingen**
- [ ] iPhone 6,9 inch: 1320 × 2868 (of 1290 × 2796) pixels, staand. Minstens 1, liefst 5 tot 8 per taal. Apple schaalt ze naar kleinere iPhones.
- [ ] Geen iPad nodig (`supportsTablet: false`).
- [ ] Maak ze in de staging-app met demo-gegevens, maar **zonder de gele testbalk** en zonder echte persoonsgegevens. Toon niets wat de app niet kan (Invest alleen als het aan staat).
- [ ] App-icoon 1024 × 1024 zonder transparantie. De huidige iconen in `assets/` zijn **tijdelijk**; laat een ontwerper definitieve maken.

## 4. Google Play Console

**Winkelvermelding**
- [ ] Naam "Depiqo" (max. 30 tekens), korte beschrijving (80), volledige beschrijving (4000), in nl, fr en en.
- [ ] App-icoon 512 × 512 PNG; **feature graphic** 1024 × 500.
- [ ] Telefoon-schermafbeeldingen: minstens 2, tussen 320 en 3840 pixels, verhouding 9:16 (bijvoorbeeld 1080 × 1920).
- [ ] Categorie: **Financiën**. Contactgegevens: e-mail (verplicht), website, telefoon.
- [ ] Privacybeleid-URL.

**App-inhoud (verplichte verklaringen)**
- [ ] **App-toegang**: "Alle of sommige functies zijn beperkt" > inloggegevens van het review-account met uitleg (zelfde als bij Apple).
- [ ] **Advertenties**: bevat geen advertenties.
- [ ] **Inhoudsclassificatie (IARC)**: vragenlijst; categorie "Hulpprogramma's, productiviteit, communicatie of andere"; uitkomst waarschijnlijk PEGI 3 / Iedereen.
- [ ] **Doelgroep**: 18 jaar en ouder (dan gelden de regels voor kinderen niet).
- [ ] **Financiële functies**: verklaar wat de app doet. Voor v1: inzage in een huurborg die bij een bank of aanbieder staat, geen betalingen, geen leningen, geen beleggen (Invest staat uit). Werk dit bij voordat Invest aangaat ("beleggen"/"vermogensbeheer"), met de vergunning van de partner.
- [ ] **Gegevensbeveiliging (Data safety)**:

| Google-categorie | Gegevenstype | Verzameld | Gedeeld met derden | Optioneel | Doel |
|---|---|---|---|---|---|
| Persoonlijke info | Naam, e-mailadres | Ja | Nee* | Nee | Accountbeheer, app-functionaliteit |
| Persoonlijke info | Overige info (geboortedatum bij de identiteitscontrole) | Ja | Nee* | Ja (alleen bij een Depiqo-borgrekening) | App-functionaliteit, fraudepreventie/naleving |
| Financiële info | Betalingsinfo gebruiker (IBAN eigen rekening, alleen Invest) | Ja | Nee* | Ja | App-functionaliteit |
| Financiële info | Overige financiële info (borg, afrekening) | Ja | Nee* | Nee | App-functionaliteit |
| Foto's en video's | Foto's | Ja | Nee | Ja | App-functionaliteit |
| Berichten | Overige berichten in de app (supportvragen) | Ja | Nee | Ja | Klantenservice |
| App-info en -prestaties | (niets in v1) | Nee | | | |
| Apparaat- of andere ID's | Pushtoken, toestelmodel | Ja | Nee | Ja (push) | App-functionaliteit, beveiliging |

  \* Gegevens die de server doorgeeft aan de partnerbank of beleggingspartner om de dienst uit te voeren, gelden bij Google als verwerking door een dienstverlener of als wettelijk verplicht, niet als "delen". **Laat dit bevestigen door je jurist** en houd het gelijk met je privacyverklaring.
  - [ ] "Gegevens zijn versleuteld tijdens overdracht": **ja** (alleen HTTPS in staging en productie).
  - [ ] "Gebruikers kunnen verzoeken om verwijdering": **ja**.
- [ ] **Verwijder-URL** (verplicht bij Google): een webpagina buiten de app waar iemand kan lezen hoe hij zijn account laat verwijderen, ook zonder de app (bijvoorbeeld `https://getdepiqo.com/account-verwijderen` met uitleg en een e-mailadres). **Deze pagina bestaat nog niet.**
- [ ] **Machtigingen**: camera (foto bij de borg), biometrie, meldingen. Geen toegang tot alle foto's (de app gebruikt de systeemkiezer; `READ_MEDIA_IMAGES` is uitgezet), geen locatie, geen microfoon.

## 5. Voor beide stores

- [ ] Versienummer in `app.config.ts` (`version`, nu 1.0.0); buildnummers verhoogt EAS zelf.
- [ ] `APP_MIN_VERSION_IOS` en `APP_MIN_VERSION_ANDROID` op de server pas verhogen als de nieuwe versie in de stores staat.
- [ ] Productieserver: `apple-app-site-association` en `assetlinks.json` ingericht (zie `TESTFLIGHT-EN-PLAY.md` §5).
- [ ] Pushmeldingen: APNs-sleutel en FCM-sleutel in EAS; `PUSH_SEND=1` op productie.
- [ ] Privacyverklaring vermeldt: wat de app verzamelt (tabel hierboven), Expo als verwerker voor pushmeldingen, de partnerbank en beleggingspartner, bewaartermijnen, rechten (inzage via "Gegevens downloaden", verwijderen via de app), contact.
- [ ] Testers hebben `docs/TESTEN.md` doorlopen op iPhone en Android, in drie talen.
- [ ] Geen testbalk in productie (`/config` geeft `banner: null`); controleer in de productie-build.
- [ ] Plan voor support: wie leest `support@getdepiqo.com` en Beheer > Support, binnen welke tijd.
