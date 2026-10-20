# Testplan Depiqo Wallet

Per scherm: wat je doet en wat je moet zien, op iPhone (iOS) en Android. Vink af wat klopt. Noteer bij een fout: toestel, systeemversie, taal, account, wat je deed en een schermafbeelding (in een development build mag dat; in staging en productie blokkeert Android schermafbeeldingen op gevoelige schermen, dat is de bedoeling).

**Voorbereiding**

- Server: lokaal (zie README, `--host 0.0.0.0`) of staging. Demo-wachtwoord `Depiqo-demo-2026`.
- App: een development build ("Depiqo Dev") of een preview-build ("Depiqo Staging"). Expo Go is genoeg voor de meeste schermen, niet voor push, Face ID en universele links.
- Test minstens op: één iPhone met Face ID, één Android met vingerafdruk. Liefst ook een kleine telefoon (iPhone SE of vergelijkbaar).
- Zet vóór je begint `python3 seed.py --reset` op de lokale server, zodat de demogegevens kloppen.

Legenda: **[iOS]** alleen iPhone, **[A]** alleen Android, anders beide.

---

## 1. Starten en omgeving

- [ ] App start zonder rood foutscherm. Splash met het Depiqo-logo op navy, daarna het inlogscherm.
- [ ] Lokaal of staging: bovenaan een gele balk "SANDBOX · testomgeving, geen echt geld" of "STAGING · ...". In productie zonder sandbox: geen balk.
- [ ] Zet de server uit en start de app: inlogscherm verschijnt; inloggen geeft "Geen verbinding met Depiqo...". Geen crash.
- [ ] Zet op de server `APP_MIN_VERSION_IOS=9.0.0` en `APP_MIN_VERSION_ANDROID=9.0.0` en herstart: de app toont "Werk de app bij" over alles heen. Zet het terug.

## 2. Inloggen en twee-stapsverificatie

- [ ] Fout wachtwoord: "Dat e-mailadres en wachtwoord passen niet bij elkaar."
- [ ] Zes keer fout: "Te veel mislukte pogingen..." en "Probeer het over ongeveer 15 minuten opnieuw."
- [ ] Leeg veld of ongeldig e-mailadres: melding onder het veld, er wordt niets verstuurd.
- [ ] `sanne@huurder.test`: je komt op "Mijn borg".
- [ ] Een beheerder (`beheer@voorbeeldvastgoed.test`): "Deze app is voor huurders..."
- [ ] "Wachtwoord vergeten?" opent de website.
- [ ] Zet 2FA aan op de website voor een demo-huurder. Inloggen vraagt nu een code. Fout code: "Deze code klopt niet...". Goede code: ingelogd.
- [ ] Met een herstelcode: ingelogd, en een melding "Herstelcode gebruikt, je hebt nog N herstelcodes".
- [ ] Wacht langer dan 5 minuten op het codescherm: "Deze inlogpoging is verlopen" en een knop terug naar inloggen.
- [ ] Na inloggen staat er op de website onder Beveiliging een apparaat "Depiqo app (toestelmodel)" en je krijgt een melding "Nieuwe inlog op je account".

## 3. Sessie, vernieuwen en afmelden

- [ ] Laat de app 20 minuten open (het toegangstoken verloopt na 15). Ververs "Mijn borg": werkt zonder opnieuw inloggen.
- [ ] Meld dit toestel af op de website (Beveiliging) of via een ander toestel. Ververs in de app: je komt op het inlogscherm met "Dit toestel is afgemeld. Log opnieuw in om verder te gaan."
- [ ] Profiel > Uitloggen > bevestigen: inlogscherm. Na opnieuw inloggen start je op "Mijn borg" (niet op Profiel).
- [ ] Verwijder de app en installeer opnieuw [iOS]: je bent uitgelogd (oude sessie is niet meer bruikbaar).

## 4. Ontgrendelen met Face ID of vingerafdruk

- [ ] Profiel: schakelaar "Ontgrendel Depiqo met Face ID" (of vingerafdruk). Aanzetten vraagt Face ID / vingerafdruk.
- [ ] Toestel zonder ingestelde biometrie: de schakelaar staat er niet; tekst "kan op dit toestel niet".
- [ ] Sluit de app helemaal en open opnieuw: vergrendelscherm, Face ID-vraag verschijnt vanzelf. Gelukt: je ziet je borg.
- [ ] Face ID mislukt of annuleren: "Ontgrendelen is niet gelukt", knop "Ontgrendelen" opnieuw, en "Inloggen met wachtwoord" brengt je naar het inlogscherm.
- [ ] App 2 minuten op de achtergrond, terug: vergrendeld. App 10 seconden op de achtergrond: niet vergrendeld.
- [ ] Een foto maken of het deelmenu openen en terugkomen: niet vergrendeld.
- [ ] VoiceOver/TalkBack aan op het vergrendelscherm: je hoort alleen het vergrendelscherm, niet de bedragen eronder.

## 5. App-wisselaar en schermafbeeldingen

- [ ] Open een borg, ga naar de app-wisselaar: je ziet het Depiqo-logo op navy, geen bedragen. [iOS] en [A]
- [ ] [A] In een staging- of productiebuild: schermafbeelding op een borg kan niet (zwart of melding). In een development build kan het wel (zodat testers kunnen melden).

## 6. Uitnodiging en deep links

Haal een geldige uitnodigingslink op: log op de website in als `staff@depiqo.test`, ga naar Beheer > Mail en kopieer de link `/t/...` uit een uitnodigingsmail, of nodig als beheerder een nieuwe huurder uit.

Openen op de telefoon:
- Development build: `npx uri-scheme open "depiqo://t/TOKEN" --ios` of `--android` (vanaf je laptop), of zet `depiqo://t/TOKEN` in een notitie en tik erop.
- [A] `adb shell am start -W -a android.intent.action.VIEW -d "depiqo://t/TOKEN"`
- Expo Go: `exp://192.168.1.20:8081/--/t/TOKEN`
- Universele link `https://app.getdepiqo.com/t/TOKEN`: alleen met een gebouwde app en een server met de juiste `apple-app-site-association` en `assetlinks.json` (zie TESTFLIGHT-EN-PLAY.md).

- [ ] De uitnodiging toont groot: verhuurder, adres, bedrag, kenmerk; en de waarschuwing "Klopt iets niet? Ga dan niet verder."
- [ ] Zonder vinkje "Ik heb gecontroleerd..." is de knop niet te gebruiken.
- [ ] Nieuw account: wachtwoord korter dan 12 tekens of niet gelijk: melding onder het veld. Goed: je bent ingelogd en ziet de borg.
- [ ] Dezelfde link nog eens: "Deze link is verlopen of al gebruikt..."
- [ ] Bestaand account, niet ingelogd: "Je hebt al een account" en "Inloggen en accepteren"; na inloggen kom je terug op de uitnodiging en accepteer je.
- [ ] Een onzinnige link (`depiqo://t/kort` of `https://app.getdepiqo.com/iets`): je komt op het startscherm, geen crash.
- [ ] Meldingslinks: tik in Meldingen op "Nieuwe inlog op je account": je komt bij Apparaten. Op een melding over een borg: je komt bij die borg.

## 7. Mijn borg (overzicht en detail)

- [ ] `sanne`: kaart met adres, verhuurder, kenmerk, status "Bekijk de eindafrekening" en vier bedragen.
- [ ] `mila` (garantie): "Ontvangen —" met "Geen geld gestort: een derde staat garant". **Nergens staat het vereiste bedrag als ontvangen of geblokkeerd.**
- [ ] `daan`: alle vier bedragen ingevuld, "Je borg staat veilig", Rente apart.
- [ ] Detail: "Wat nu" (indien van toepassing) met de juiste knop; "Waar staat je borg" met aanbieder, referentie, bewijs; bij `mila` de einddatum van de garantie; bij een sandbox-rekening de melding "Testomgeving".
- [ ] Een borg die op storting wacht: betaalgegevens met "Kopieer" bij IBAN en kenmerk. Na kopiëren staat er "Gekopieerd" en plakken in een andere app geeft precies de waarde.
- [ ] Voortgang: stappen met Klaar / Nu / Later.
- [ ] Termijnen: datum, "Nog N dagen" of "N dagen over tijd".
- [ ] Trek omlaag om te verversen.
- [ ] Geschiedenis: lijst laadt meer bij scrollen.

## 8. Documenten en foto's

- [ ] Lijst met soort, bestandsnaam, grootte, datum, door wie.
- [ ] Tik op een PDF: deelmenu, "Open in Bestanden/Boeken/Drive" toont het document.
- [ ] Foto toevoegen: zonder soort te kiezen staan de knoppen uit.
- [ ] Soorten zijn precies: Foto, Plaatsbeschrijving of opleverrapport, Overig.
- [ ] "Foto maken": eerste keer de vraag om de camera (in het Nederlands op een Nederlandse iPhone). Weigeren: nette melding. Toestaan: foto verschijnt in de lijst.
- [ ] "Kies uit je foto's": de systeemkiezer opent (Android 13+ vraagt geen toestemming). Een HEIC-foto van een iPhone wordt als JPEG verstuurd.
- [ ] Een gesloten dossier: "Dit dossier is gesloten..."
- [ ] Twee keer snel op "Foto maken" tikken: één upload.

## 9. Eindafrekening

- [ ] `sanne`: regels met categorie, omschrijving, bedrag; "Bewijsstuk bekijken" opent het document; totalen; "Depiqo beslist niet in een geschil".
- [ ] Bezwaar: minder dan 10 tekens geeft een melding; daarna "Bezwaar versturen". Status wordt "Bezwaar gemaakt". (Zet daarna de demo terug met `seed.py --reset`.)
- [ ] Akkoord: bevestiging met het bedrag dat terugkomt; daarna status "Akkoord".
- [ ] Vliegtuigmodus aan, tik Akkoord, vliegtuigmodus uit, tik opnieuw: de server voert het één keer uit (zelfde Idempotency-Key). Melding "We weten niet zeker of je verzoek is aangekomen...".
- [ ] `sofie`: "Vrijgaveformulier downloaden" geeft een PDF.

## 10. Doorbeleggen

- [ ] `mohamed`: in de borg "Waar ontvang je jouw deel" met "Op je beleggingsrekening". Terug naar eigen rekening en weer naar beleggen werkt (met vinkje en bevestiging).
- [ ] `sanne` (nog geen akkoord): geen doorbeleggen te zien.

## 11. Geschiedenis

- [ ] Tab Geschiedenis: borg-gebeurtenissen en beleggingstransacties door elkaar, nieuwste eerst; bedragen met + of −; meer laden bij scrollen.

## 12. Meldingen in de app

- [ ] Ongelezen meldingen hebben een stip en de tab een getal.
- [ ] Tik op een melding: stip weg, je gaat naar de juiste plek.
- [ ] Wissel de taal naar Frans: titels en teksten van meldingen zijn nu Frans (de server vertaalt ze).

## 13. Pushmeldingen

Vereist: development- of preview-build, EAS-project-ID in `app.config.ts`, en een server die echt verstuurt (`PUSH_SEND=1`; standaard staat dat uit in de sandbox). Op de server: `python3 run.py dispatch` verstuurt de wachtrij.

- [ ] Er komt nooit vanzelf een systeemvraag om meldingen. Op "Mijn borg" en Meldingen staat een kaart "Meldingen aanzetten?" met uitleg.
- [ ] "Zet meldingen aan": systeemvraag; na toestaan verdwijnt de kaart.
- [ ] Na weigeren [iOS]: de kaart zegt dat meldingen uit staan en "Open instellingen" opent de instellingen van de app.
- [ ] Log in op een tweede toestel: het eerste krijgt "Nieuwe inlog op je account" / "Open Depiqo voor de details". **Geen bedragen, namen of adressen in de melding.**
- [ ] Vergrendelscherm: alleen die korte titel en regel.
- [ ] Tik op de melding terwijl de app dicht is: app opent (eerst Face ID als dat aan staat) en gaat naar Apparaten.
- [ ] Tik terwijl je uitgelogd bent: na inloggen kom je op de juiste plek.
- [ ] Privacy > Pushmeldingen: zet "Beveiliging" uit; een nieuwe inlog geeft geen push meer (wel in de lijst in de app).
- [ ] Uitloggen: daarna komen er geen pushmeldingen meer op dit toestel.

## 14. Profiel, apparaten en taal

- [ ] Naam wijzigen en opslaan: nieuwe naam staat er na verversen ook op de website.
- [ ] Taal: Nederlands / Français / English. Alle teksten wisselen meteen, ook statussen ("Je borg staat veilig" > "Votre garantie est en sécurité"). Na het sluiten van de app blijft de taal staan. Op de website is de taal ook gewijzigd.
- [ ] Telefoon in het Frans, nieuwe installatie: app start in het Frans. Telefoon in het Duits: Nederlands.
- [ ] Twee-stapsverificatie: "Aan"/"Uit" klopt met de website; de knop opent de beveiligingspagina.
- [ ] Apparaten: dit toestel met "Dit toestel"; een ander toestel afmelden werkt en dat toestel moet opnieuw inloggen.

## 15. Privacy en gegevens

- [ ] "Gegevens downloaden": deelmenu met een bestand `depiqo-export-JJJJ-MM-DD.json`; openen toont je gegevens.
- [ ] Privacyverklaring en gebruiksvoorwaarden openen de juiste pagina's.
- [ ] Account verwijderen met `sanne` (lopende borg): "Verwijderen kan nu nog niet" met de reden en een knop naar de borg. Geen wachtwoordveld.
- [ ] Een account zonder lopende borg (maak er een via een uitnodiging en laat de beheerder de borg annuleren): fout wachtwoord geeft "Dit wachtwoord klopt niet"; goed wachtwoord + vinkje + bevestiging: account verwijderd, uitgelogd, inloggen lukt niet meer.

## 16. Hulp

- [ ] Nieuwe vraag: zonder categorie of met minder dan 10 tekens: melding (het onderwerp is niet verplicht). Met een borg gekozen: verstuurd, je ziet het gesprek.
- [ ] Vier vragen binnen 10 minuten: "Je hebt net al een paar vragen gestuurd..."
- [ ] Beantwoord als `staff@depiqo.test` (Beheer > Support): in de app staat het antwoord onder "Depiqo" en de status "Beantwoord".

## 17. Beleggen (Invest)

- [ ] Account zonder recht op Invest (`sofie@huurder.test`, huurder bij Stadswonen Gent): **geen** tab Beleggen.
- [ ] Start de server met `DEPIQO_SANDBOX=0` (dan is er geen beleggingspartner): de tab verdwijnt (`/me` zegt dan niet "available"). Als een scherm toch open was: alleen "Nog niet beschikbaar".
- [ ] `sanne`: tab Beleggen met "Je borg wordt nooit belegd", "Sandbox: geen echt geld" en de drie stappen.
- [ ] Toets: alle vragen verplicht. Antwoorden die niet passen: "Mogelijk niet passend", redenen, risico, vinkje en "Toch verder" met nog een bevestiging.
- [ ] Voorwaarden: twee vinkjes nodig, daarna portefeuilles.
- [ ] Portefeuilles: bedrag wijzigen herberekent kosten in euro en scenario's. Kies er een, "Rekening openen", bevestigen.
- [ ] `daan`: waarde, resultaat, grafiek (1 mnd, 6 mnd, 1 jaar, Alles), fondsen, kosten per jaar.
- [ ] Storten: IBAN en kenmerk met kopieerknop. In de sandbox: "Storting nadoen" verhoogt het vrije geld.
- [ ] Kopen € 10: melding minimum € 25. Kopen € 50: risicoscherm met kosten vooraf in euro, scenario's, risico, "nog m:ss geldig". Zonder vinkje geen order. Met vinkje: "Order geplaatst", daarna in Orders.
- [ ] Wacht 10 minuten op het risicoscherm: "verlopen", knop "Nieuw overzicht opvragen".
- [ ] Twee keer snel op "order plaatsen": één order.
- [ ] Verkopen met "Alles verkopen"; Wisselen naar een andere portefeuille.
- [ ] Opnemen (`daan`, rekening al geregistreerd): bedrag hoger dan beschikbaar geeft een melding; bevestiging toont bedrag en gemaskeerd IBAN.
- [ ] Nieuw IBAN registreren zonder 2FA: melding over de wachttijd met datum. Ongeldig IBAN: "Dit IBAN klopt niet".
- [ ] Maandoverzichten: PDF opent.
- [ ] Servicevergoeding zonder voorstel: "Er is geen voorstel...".

## 18. Taal, donkere modus en grote tekst

- [ ] Elk scherm hierboven één keer in het Frans en één keer in het Engels: geen sleutels als `invest.value` in beeld, geen afgekapte knoppen.
- [ ] Donkere modus (systeeminstelling): navy achtergrond, leesbare tekst, testbalk goed leesbaar.
- [ ] Grootste tekstgrootte (iOS: Toegankelijkheid > Weergave en tekstgrootte > Grotere tekst; Android: Lettergrootte maximaal): bedragen en knoppen blijven leesbaar, niets overlapt, alles is te scrollen.
- [ ] VoiceOver [iOS] / TalkBack [A]: elke knop heeft een duidelijke naam ("Kopieer IBAN", "Akkoord gaan"); bedragen worden voorgelezen als "Ontvangen: nog niet bekend. Geen geld gestort: ..."; vinkjes zeggen of ze aan of uit staan.
- [ ] Alle knoppen zijn makkelijk te raken (minstens vingertopgroot).

## 19. Offline en slechte verbinding

- [ ] Vliegtuigmodus en ververs: "Geen verbinding met Depiqo...", met "Opnieuw proberen". Wat al geladen was blijft staan.
- [ ] Zet de verbinding terug en tik "Opnieuw proberen": de gegevens laden.
- [ ] Langzame verbinding (Android: ontwikkelaarsopties; iOS: Network Link Conditioner): knoppen tonen een spinner en staan uit zolang een verzoek loopt.
- [ ] Na 20 seconden zonder antwoord: "Depiqo reageert niet op tijd."

---

## Na het testen

- Zet de demo terug: `python3 seed.py --reset` (dit verwijdert alles wat je in de lokale demo deed).
- Meld fouten met: toestel, systeemversie, app-omgeving (Dev/Staging), taal, account, stappen, wat je verwachtte en wat je zag.
