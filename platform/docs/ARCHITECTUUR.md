# Architectuur

## Uitgangspunten

1. **Depiqo houdt geen geld aan.** Het geld staat bij een bank (of, later, een vergunde beleggingspartij). Depiqo stuurt opdrachten en volgt wat de bank meldt.
2. **De bank is de bron van waarheid.** De tabellen `bank_accounts` en `bank_transactions` zijn een schaduwgrootboek dat alleen via bankberichten verandert.
3. **Elke statuswijziging gaat via `services.transition()`.** Die controleert de statusmachine, wie de wijziging mag doen, en schrijft in dezelfde transactie de audittrail. De update gebruikt `WHERE status = <oude status>`, zodat twee gelijktijdige acties elkaar niet overschrijven.
4. **Regels zijn versiebeheerd.** Elk dossier bewaart de regelversie waaronder het startte, en alle berekeningen gebruiken die versie.
5. **De bankkoppeling is vervangbaar en faalt dicht.** De workflow kent alleen de interface `BankPartner`. Zonder geconfigureerde partner gebeurt er niets financieels.
6. **Geen bankaanroep binnen een databasetransactie.** Opdrachten aan de bank gaan via een outbox (`bank_instructions`).
7. **Een bedrag dat niet bevestigd is, toont het scherm niet als geld.** Verplichting, ontvangst, blokkering en rente zijn vier aparte cijfers.

## Statusmachine

```
concept → uitnodiging verstuurd → identificatie loopt → wacht op storting
  → storting ontvangen (alleen bank) → zekerheid geregistreerd (bank, of verklaring van een financieel medewerker bij "elders")
  → vertrek gestart → afrekening voorgesteld → akkoord | betwist
  → uitbetaling loopt (vrijgave-opdracht naar bank) → uitbetaald en gesloten (bank)
Uitzonderingen: identificatie mislukt, geannuleerd, juridische blokkade (onthoudt de vorige status).
Bij "elders": uitnodiging → wacht op storting → zekerheid geregistreerd → … → akkoord → gesloten
  (sinds 0.4.0 alleen via "Vrijgave bij aanbieder bevestigd", met bewijs van de aanbieder).
Import van een bestaande borg elders: concept → zekerheid geregistreerd (bewijsniveau "verklaard").
```

### Keuze: geen nieuwe statussen, wel een ander label (0.3.0)

De status `secured` betekent sinds 0.3.0 "zekerheid geregistreerd". Hoe sterk die zekerheid is, is een apart gegeven: het bewijsniveau (borg elders) of de blokkering door de bank (Depiqo-borgrekening). We hebben bewust geen extra statussen toegevoegd: het bewijsniveau kan stijgen terwijl het dossier verder loopt (vertrek, afrekening), en dan zou elke status een variant per bewijsniveau nodig hebben. In plaats daarvan:

- `states.display_status(d)` maakt het label. Alleen een door de bank bevestigde blokkering of bewijsniveau `legal` krijgt het groene "Zekerheid bevestigd". Lagere niveaus krijgen een amber of neutraal label, zoals "Ontvangst verklaard door beheerder".
- `states.assurance(d)` geeft het bewijs in elke status (ook na `secured`). Lijsten, het dashboard, de afstemming en de CSV-export tonen het naast de status.
- De generieke label in `LABELS` is "Zekerheid geregistreerd" (blauw), zodat ook de audittrail niets belooft wat niet bewezen is.

## Bewijsniveaus bij een borg elders

| Niveau | Wie | Voorwaarde | Telt mee als dekking (`eligible_value_cents`) | Label |
|---|---|---|---|---|
| `declared` | Beheerder of financieel medewerker | Klik op "Ontvangst verklaren" | Nee | Ontvangst verklaard door beheerder (amber) |
| `document` | Beheerder of financieel medewerker | Een geüpload document van soort `bankbewijs` | Nee | Bankbewijs ontvangen, niet geverifieerd (neutraal) |
| `verified` | Alleen Depiqo-medewerker | Notitie verplicht | Ja | Ontvangst geverifieerd door Depiqo (blauw) |
| `legal` | Alleen Depiqo-medewerker | Document van soort `blokkering` (blokkeringsattest of bewijs e-DEPO) | Ja; `legal_lock_status` = `active` | Zekerheid bevestigd (groen) |

Het niveau gaat alleen omhoog. Elke stap staat in `deposit_evidence` (wie, wanneer, notitie, document) en in de audittrail. `asset_value_cents` is het verklaarde bedrag; `eligible_value_cents` blijft leeg tot `verified`. Migratie 004 zet bestaande bevestigingen uit 0.2 op `declared` en haalt hun dekking weg.

## Aanbieders van borgen elders (0.4.0, `app/providers.py`)

Positie: je houdt je vastgoedsoftware en je huidige aanbieders, en beheert alle huurwaarborgen, ongeacht waar ze staan, op één plek. Een borg met `holding = 'external'` krijgt daarom vier extra velden (migratie 006):

| Kolom | Betekenis |
|---|---|
| `provider_kind` | `verhuurder_rekening`, `bank_geblokkeerd`, `e_depo`, `verzekering_tak26`, `borggarantie`, `ocmw`, `anders`, of leeg (nog niet bekend) |
| `provider_name` | Vrije tekst, bijvoorbeeld de naam van de bank of verzekeraar (maximaal 120 tekens) |
| `provider_reference` | Rekeningnummer, dossiernummer of certificaatnummer (maximaal 60 tekens) |
| `guarantee_expires_on` | Einddatum van een garantie; alleen bij `borggarantie` en `ocmw` |

`external_iban` blijft bestaan: verplicht bij `verhuurder_rekening` en bij een lege soort (het gedrag van 0.3), optioneel bij de andere soorten, en leeg bij `borggarantie` en `ocmw` omdat de huurder daar niets stort (geen betaalgegevens, geen betaalherinnering, "Ontvangen" blijft "—").

**Afbeelding op het zekerheidsmodel.** `borggarantie` → `security_type = 'guarantee'`; alle andere soorten → `external_account` (label nu "Borg buiten Depiqo"). `custodian` is de naam van de aanbieder, behalve bij `verhuurder_rekening` (dan leeg: de verhuurder of beheerder bewaart zelf).

**Bewijsniveaus.** De regels van 0.3 blijven: alleen `verified` en `legal` tellen mee als dekking. Per soort toont de bewijsladder welk stuk past (`providers.evidence_hint`), bijvoorbeeld "Bewijs van e-DEPO" of "Certificaat van de verzekeraar met de inpandgeving". Eén toevoeging: bij `verhuurder_rekening` weigert `set_evidence` het niveau `legal`, want geld op de rekening van de verhuurder is niet juridisch geblokkeerd. Het hoogste niveau is daar `verified`.

**Regio's: waarschuwen, nooit blokkeren.** `providers.region_warnings(region, kind)`:
- `e_depo`, `ocmw` en `verzekering_tak26` bestaan alleen in België; bij een woning in Nederland volgt een waarschuwing.
- `verhuurder_rekening` in Vlaanderen of Brussel: een waarborg in geld moet op een geblokkeerde rekening op naam van de huurder staan. In Brussel komt daar bij dat contanten niet zijn toegestaan.
- Een garantie die eindigt vóór het einde van de huur geeft ook een waarschuwing.

De waarschuwing staat live in het formulier (data-attributen per optie, `app.js`), als melding na het opslaan, als balk op het dossier en per rij in het importvoorbeeld. Ze houdt niets tegen: de beheerder kent het contract.

**Invoer.** Nieuw dossier en een aparte pagina "Waar staat de borg" (`/app/borgen/<pid>/aanbieder`, beheerder en vastgoedbeheerder, alleen zolang het dossier loopt, met auditlog `deposit.provider_updated` en een regel in de audittrail). Heeft Depiqo het bewijs al geverifieerd (`verified` of `legal`), dan kan alleen de einddatum van een garantie nog veranderen; een andere aanbieder vraagt nieuw bewijs via Depiqo. CSV-import: optionele kolommen `provider_kind`, `provider_name`, `provider_reference`, `guarantee_expires_on`, met Nederlandse kolomnamen (`aanbieder`, `naam_aanbieder`, `referentie`, `garantie_tot`) en Nederlandse waarden ("rekening verhuurder", "e-DEPO", "tak 26", "garantie", "OCMW") als alias (`providers.parse_kind`). Een onbekende waarde is een fout; een regiowaarschuwing niet. De CSV-export heeft vier kolommen erbij (`sandbox` blijft de laatste).

**Overzicht.** `providers.overview(org_id)` geeft voor lopende dossiers per plek (Depiqo-borgrekening, elke soort, aanbieder onbekend) het aantal, de totale verplichting en hoeveel alleen verklaard zijn. Dat is het blok "Waar staan je borgen" op het dashboard; elke regel opent de borgenlijst met filter `aanbieder=<soort>`.

**Afstemming.** Twee afwijkingen erbij: een borg elders zonder aanbieder, en een garantie die binnen 60 dagen eindigt of al verlopen is terwijl het dossier nog loopt.

**Facturatie.** Ongewijzigd: elke soort is een "borg elders" en kost het tarief voor elders. Unit economics ongewijzigd.

**Waarom geen backfill.** Voor borgen elders van vóór 0.4.0 weet Depiqo niet waar ze staan. Raden (bijvoorbeeld Nederland = rekening van de verhuurder) zou een bewering zijn zonder bron. Ze staan als "aanbieder onbekend" en als afwijking in de afstemming tot iemand het invult.

## Vrijgave bij een aanbieder (0.4.0, `app/release_form.py`)

Een borg die elders staat, geeft Depiqo niet vrij: de aanbieder doet dat met een eigen procedure en formulier. Depiqo levert het papierwerk en legt de uitkomst vast.

1. **Vrijgaveformulier.** Zodra de verdeling vaststaat (status `agreed` na akkoord van de huurder of na een afgesloten geschil, en daarna ter archivering bij `closed`) maakt `release_form.build(deposit)` met reportlab een PDF van één pagina: partijen, adres, kenmerk, soort en naam van de aanbieder met referentie, verplichting, inhoudingen, de verdeling (aan huurder en aan verhuurder), de basis (akkoord of vonnis, met datum) en handtekeningvakken voor huurder en verhuurder. Er staat bij dat e-DEPO, de bank en de verzekeraar elk een eigen procedure en formulier hebben, die dit document ondersteunt maar niet vervangt. Bij een garantie staat erbij dat er geen geld is gestort.
2. **Downloaden.** Business: iedereen met `deposit.view` (`/app/borgen/<pid>/vrijgaveformulier.pdf`). Wallet: alleen de huurder van dat dossier (`/wallet/borg/<pid>/vrijgaveformulier.pdf`). Elke download komt in het auditlog (`deposit.release_form`) en in de audittrail.
3. **Bevestigen.** Financieel medewerker of beheerder (`deposit.payout`) kiest "Vrijgave bij aanbieder bevestigd" met een document van soort `vrijgave` ("Bewijs van vrijgave of terugbetaling"). `services.confirm_external_release` sluit het dossier via de gewone `transition(agreed → closed)`, zet `release_document_id`, waarde en dekking op 0 en een actieve blokkering op `released`. Het label wordt "Vrijgegeven en gesloten".

**Keuze: de oude snelweg ingepakt, geen nieuwe status.** In 0.3 sloot "Terugbetaling registreren" een borg elders met één klik. Die klik bestaat niet meer: `start_payout` stuurt een borg elders door naar `confirm_external_release`, dus ook de oude actie `uitbetalen` vraagt nu het bewijs. Er kwam geen status "vrijgave aangevraagd bij aanbieder" bij: de aanvraag gebeurt buiten Depiqo en Depiqo kan ze niet volgen. Het dossier blijft op "akkoord" staan (met termijnbewaking en een taak "Vrijgave regelen" in Vandaag te doen) tot het bewijs er is. Geen enkele bestaande test sloot een borg elders, dus geen test hoefde hiervoor te veranderen.

## Depiqo Invest (0.5.0, `app/investing.py`, `app/views/invest.py`)

### Scheiding van de borg

Een borg is zekerheid voor de verhuurder; een belegging is eigen geld van de huurder. Die twee raken elkaar nooit:

- Invest heeft eigen tabellen (migratie 007): `invest_accounts`, `invest_appropriateness`, `invest_orders`, `invest_fills`, `invest_transactions`, `invest_instructions`, `invest_events`, `invest_payout_choices`, `invest_sandbox_clock`. Een rekening hoort bij `users.id` (de persoon), heeft geen `org_id` en geen verwijzing naar een borg of een bankrekening voor borgen.
- Niets in de borgflow leest Invest, behalve twee functies bij de uitbetaling: `payout_destination(deposit)` (de keuze van de huurder) en `on_payout_completed(...)` (na de bedragcontrole). `security_type`, `eligible_value_cents` en de dekking veranderen nooit door Invest; een belegging is nooit onderpand.
- Beheerders van organisaties zien niets, ook niet of een huurder belegt (zie `BEVEILIGING.md`).

### Rollen

Depiqo geeft geen advies en voert geen orders uit. De partner (een vergunde beleggingsonderneming) doet de identiteitscontrole, beoordeelt de kennis- en ervaringstoets (MiFID-passendheidstoets), opent de rekening op naam van de huurder, bewaart de fondsen, voert orders uit, int de servicevergoeding van Depiqo en stuurt de officiële overzichten en de jaaropgave. Depiqo verwijst door, toont het overzicht en bewaart wat er gebeurde (antwoorden, uitslag, akkoord met voorwaarden, keuzes) met tijdstip.

### Partner: keuze en adaptercontract

`INVEST_PARTNER` werkt als `BANK_PARTNER`: `sandbox` alleen als `DEPIQO_SANDBOX=1`, een naam uit `INVEST_ADAPTERS`, of leeg (`DisabledInvest`: alles weigert). Zonder partner is Beleggen verborgen (met een korte kaart "Nog niet beschikbaar"), geven alle routes 404 en weigert de webhook. Per organisatie zet een Depiqo-medewerker Beleggen aan of uit (`organizations.invest_enabled`).

Een adapter is een subklasse van `InvestmentPartner`:

| Methode | Sleutel | Antwoord | Bevestiging via |
|---|---|---|---|
| `assess_appropriateness(user, answers)` | geen | `result`, `score`, `reasons` | (antwoord) |
| `open_account(user, account, key)` | `invest-open:<rekening>` | `external_id`, `status` (`pending` of `active`) | `account.activated` |
| `deposit_instructions(account)` | geen (lezen) | `iban` (klantengeldrekening), `beneficiary`, `reference` | `deposit.received` |
| `place_order(account, order, key)` | `invest-order:<order>` | `provider_ref` | `order.executed` (met fills) of `order.failed` |
| `withdraw(account, amount, iban, key)` | `invest-withdraw:<rekening>:<willekeurig>` | `provider_ref` | `withdrawal.completed` of `withdrawal.failed` |
| `charge_fee(account, amount, period, key)` | `invest-fee:<rekening>:<maand>` | `provider_ref` | `fee.charged` (eventueel met verkoop-fills) |
| `price(fund, day)` | geen (lezen) | koers × 10000 | |

Een echte partner (een API van een beleggingsonderneming) moet daarvoor ondersteunen: onboarding met eigen KYC en een passendheidstoets via API, rekeningen op naam van de klant met een klantengeldrekening en een kenmerk per klant, orders in bedragen met fractionele stukken (4 decimalen), idempotentiesleutels op elke schrijfactie, webhooks met handtekening voor elke statuswijziging, posities en koersen per dag, inning van een externe vergoeding (de servicevergoeding van Depiqo), opnames naar een geverifieerde eigen rekening, maand- en jaaroverzichten, en de essentiële-informatiedocumenten per fonds. Elke fout geeft `InvestPartnerError` (tijdelijk, opnieuw) of `InvestUnavailable` (blijvend).

### Outbox: aparte tabel

Opdrachten aan de beleggingspartner staan in `invest_instructions`, niet in `bank_instructions`. Bewust: het is een andere partner met een eigen dispatcher en eigen soorten (`open`, `order`, `withdraw`, `fee`); de CHECK op `bank_instructions.kind` en de koppeling aan `bank_accounts` passen niet; en de afstemming van borgen moet nooit beleggingsopdrachten tonen. Het patroon is hetzelfde: schrijven in dezelfde transactie als de order, direct versturen na de commit (`dispatch`), claimen met een optimistische update, nieuwe pogingen tot `MAX_INSTRUCTION_ATTEMPTS`, dan `failed`. `run.py dispatch` verstuurt beide wachtrijen.

**Mislukt is definitief (0.5.2).** Mislukt een order of opname (de dispatcher geeft op, of de partner meldt `order.failed` of `withdrawal.failed`), dan ziet de huurder "Mislukt" en dat blijft zo. Een medewerker kan zo'n opdracht niet opnieuw versturen: dan zou een order uitgevoerd worden die de huurder op dat moment niet meer wil. De huurder plaatst zelf een nieuwe. "Opnieuw" bestaat alleen voor servicekosten en voor een rekeningopening die nog wacht.

**Berichten (0.5.2).** Een bericht wordt in één savepoint verwerkt: lukt een deel niet, dan blijft er niets van over in het grootboek en krijgt het bericht een fout. Een bericht voor een rekening of opdracht die Depiqo nog niet kent, krijgt `retryable = 1` en wordt opnieuw verwerkt als de partner het nog eens stuurt (zoals bij de bank in 0.3.1). Medewerkers kunnen elk bericht met een fout opnieuw laten verwerken. Elke fill wordt gecontroleerd: bekend fonds, gehele positieve getallen, bedrag gelijk aan stukken × koers (één cent afronding), nooit meer verkocht dan in bezit; de dag is een echte datum tussen de opening van de rekening en morgen.

### Grootboek, afronding en koersen

- Geld in centen; stukken met 4 decimalen (`units_1e4`), koersen in euro × 10000 (`price_1e4`).
- Kopen: per fonds het bedrag naar rato van de weging (naar beneden afgerond, de rest naar het fonds met de grootste weging), stukken naar beneden afgerond; wat overblijft blijft vrij geld. Verkopen van een bedrag: per fonds naar rato van de waarde, naar boven afgerond, zodat de opbrengst het bedrag dekt. Waarde = stukken × koers, half omhoog op de cent.
- Vrij geld = som van `invest_transactions`; gereserveerd = lopende kooporders, opnames, servicekostenopdrachten én de servicekosten die al zijn opgebouwd maar nog niet verrekend (naar boven afgerond) plus een eventueel doorgeschoven rest. Een order of opname kan alleen met wat daarna overblijft. De controle gebeurt in dezelfde IMMEDIATE-transactie als de reservering, zodat twee verzoeken nooit hetzelfde geld uitgeven.
- Het saldo is nooit negatief: elke transactie die het saldo onder nul zou brengen, weigert het hele bericht (`LedgerError`).
- Een order wordt uitgevoerd tegen de koers van de volgende handelsdag van de partner. In de sandbox is dat de dag nadat de klok vooruit gaat.
- Sandboxkoersen: per fonds een vaste random walk (zaad = fondsnaam) vanaf 2 januari 2023, met drift en beweeglijkheid per beleggingscategorie. De drift is netto van de lopende kosten: **fondskosten zitten in de koers** en worden nooit apart afgeschreven. Elke aanroep geeft dezelfde koers. De sandboxklok (`invest_sandbox_clock.offset_days`) loopt alleen vooruit via "Koersen een dag vooruitzetten".
- De grafiek komt uit `history()`: waarde en inleg per dag uit de transacties en fills, op de server getekend als SVG (polyline, geen script, geen inline stijl).

### Kosten en servicevergoeding

- Vooraf in euro: `costs(bedrag, portefeuille)` geeft servicekosten, lopende kosten en transactiekosten voor 1 en 3 jaar, uitgaande van een gelijke waarde; `scenarios()` drie voorbeelden (gunstig, neutraal, ongunstig) per jaar, samengesteld, na kosten. Beide staan op het scherm vóór elk akkoord.
- Servicevergoeding: elke rekening heeft haar eigen tarief (`fee_rate_bps`), vastgelegd bij het akkoord met de voorwaarden. Elke dag waarde fondsen × tarief / 10000 / 365 in miljoenste centen (`fee_accrued_micro`); vrij geld telt niet mee. Op de laatste dag van de maand: afgerond half omhoog op de cent, plus een doorgeschoven rest, een `fee`-opdracht aan de partner; wat onder een halve cent blijft, vervalt. De partner int en meldt `fee.charged`; is er te weinig vrij geld, dan verkoopt hij eerst naar rato, en hij int nooit meer dan het vrije geld plus de opbrengst. Wat hij niet kon innen, schuift door naar de volgende keer (`fee_carry_cents`). Medewerkers kunnen het opgebouwde bedrag direct laten verrekenen.
- Een nieuw tarief van een medewerker (staff-instelling `invest_fee_bps`) geldt voor nieuwe rekeningen. Bestaande rekeningen krijgen een voorstel (`pending_fee_bps`) en een e-mail; tot de huurder akkoord gaat, blijft het oude tarief. Bij akkoord worden eerst de dagen tot vandaag tegen het oude tarief opgebouwd: een nieuw tarief werkt nooit terug.
- Unit economics: belegd vermogen, actieve beleggers, servicekosten van de maand (verrekend en opgebouwd), lopende omzet (AUM × vergoeding / 12) en marge na een aangenomen partnerprijs per actieve rekening (`partner_cost_invest_account_cents`, standaard € 0,30).

### Doorbeleggen bij terugbetaling

1. Status `agreed`, Depiqo-borgrekening, actieve beleggingsrekening, Beleggen aan voor de organisatie van díe borg: de huurder kiest in de wallet "naar mijn beleggingsrekening" en bevestigt met een vinkje. `invest_payout_choices` bewaart keuze, tijdstip, de klantengeld-IBAN van de partner en het kenmerk. Kiezen en terugdraaien zijn elk één voorwaardelijke SQL-opdracht: alleen zolang de borg op `agreed` staat en er nog geen vrijgave-opdracht is. Een pagina die eerder werd geladen, kan de keuze dus niet meer wijzigen.
2. `start_payout` leest de keuze in dezelfde IMMEDIATE-transactie als de statuswijziging en zet ze in de vrijgave-opdracht (`tenant_destination`). Op dat moment wordt opnieuw gecontroleerd: partner beschikbaar, rekening actief bij die partner, Beleggen aan voor de organisatie van de borg, rekening van de huurder van de borg. Klopt iets niet, dan gaat het deel naar de eigen rekening van de huurder; de keuze wordt `fallback`, met een regel in het auditlog (zonder organisatie), een e-mail aan de huurder (niet in het communicatielog van het dossier) en een afwijking die alleen Depiqo-medewerkers zien.
3. `payout.completed` gaat eerst door de controle uit 0.3 (exact de opgedragen bedragen). Of er geld naar Invest ging, volgt alleen uit `tenant_destination` in de vrijgave-opdracht, nooit uit de keuzetabel. Dan wordt de storting (`payout:<dossier>`) in dezelfde transactie op de beleggingsrekening gezet en pas dan is de keuze `paid`. Kan dat niet (partner weg, rekening niet actief), dan wordt de keuze `unrecorded`: zichtbaar voor medewerkers tot de partner de storting meldt. Klopt het bedrag niet, dan gebeurt er aan de beleggingskant niets.
4. Het geld komt binnen als vrij geld; de huurder beslist zelf of hij het belegt.

### Wisselen, opnemen en de schakelaar per organisatie (0.5.2)

- **Wisselen** bewaart het doel in `pending_switch`. De portefeuille verandert pas als de verkoop is uitgevoerd én de nieuwe aankoop is geplaatst. Mislukt de verkoop, dan blijft alles zoals het was en ziet de huurder een melding. Kan de aankoop nog niet worden geplaatst, dan blijft de wissel openstaan en probeert `continue_switches()` het opnieuw (bij elk bericht en elke dag); het bericht van de partner wordt gewoon verwerkt.
- **Opnemen** kan alleen naar de eigen, geregistreerde rekening (`own_iban`). Registreren of wijzigen: met twee-stapsverificatie aan en een verse code direct bruikbaar, anders na 7 dagen. Altijd een e-mail. De partner controleert de naam van de rekeninghouder (`verify_account_holder`; de sandbox accepteert de eigen naam, een echte partner doet een naamcontrole bij de ontvangende bank).
- **Schakelaar uit** voor een organisatie: geen nieuwe rekeningen, geen nieuwe aankopen, geen wissels en geen doorbeleggen. Wie al een rekening heeft, kan blijven kijken, verkopen, opnemen en overzichten downloaden, en de servicekosten lopen door zoals afgesproken.
- **Vóór elke verbintenis** (kopen, verkopen, wisselen, doorbeleggen) staat de risicowaarschuwing. Kopen en wisselen gaan via een controlepagina met de kosten in euro voor dat bedrag en de scenario's, en een vinkje.

### Overzichten

Per kalendermaand een PDF (reportlab): waarde aan het begin en eind, stortingen, opnames, orders, servicekosten en posities. Alleen de huurder downloadt het. Het officiële overzicht en de jaaropgave komen van de partner.

## API voor de huurders-app (0.6.0, `app/api/`)

Een eigen blueprint onder `/api/v1` voor de app (React Native met Expo). De uitleg voor ontwikkelaars van de app staat in `docs/api/README.md`, het contract in `docs/api/openapi.yaml`.

- **Geen tweede kopie van de regels.** Elk endpoint roept dezelfde functies aan als de wallet: `services.verify_identity`, `tenant_agree`, `tenant_dispute`, `storage.save_upload`, `release_form.build`, `investing.place_order`, `withdraw`, `register_own_iban`, `choose_payout` enzovoort. De API valideert alleen de vorm van de invoer en vertaalt uitzonderingen naar een foutcode. Een paar kleine uitbreidingen zijn gedeeld met de web: `investing.terms()` (de tekst die je accepteert, ook op de webpagina), `history(since=...)` voor de grafiekperiodes, `withdrawal_view()`, `withdraw()` geeft het opdrachtnummer terug, en `states.display()` geeft naast label en kleur een vaste sleutel.
- **Indeling:** `app/api/__init__.py` (blueprint, toegang, foutformaat, taal, cursors, idempotentie), `auth.py` (config, inloggen, tokens, apparaten, uitnodigingen, pushtoken), `me.py` (profiel, export, verwijderen, meldingen), `deposits.py`, `invest.py`, `activity.py`, `support.py`. Tokens in `app/apitokens.py`, meldingen en push in `app/notify.py`, teksten in `app/i18n.py`, deep links in `app/views/applinks.py`, de supportpagina voor medewerkers in `app/views/support_admin.py`.
- **Tokens:** zie `BEVEILIGING.md`. Tabellen `api_devices`, `api_access_tokens`, `api_refresh_tokens` (rotatie met `used_at` en `replaced_by`), `api_mfa_challenges`.
- **Idempotentie:** `api_idempotency` per gebruiker en sleutel, met een hash van methode, pad en body. Eerst een rij zonder antwoord (een tweede gelijktijdig verzoek krijgt 409 `idempotency_in_progress`), na een geslaagd antwoord het antwoord erbij; bij een fout verdwijnt de rij, zodat opnieuw proberen kan. Na 24 uur vervalt de sleutel.
- **Offertes:** `invest_quotes` bewaart wat de huurder zag (kosten, scenario's, risico), 10 minuten geldig, één keer bruikbaar. De order claimt de offerte met een voorwaardelijke update; lukt de order niet, dan komt de offerte vrij.
- **Meldingen:** `notifications` met type en parameters. De bestaande gebeurtenissen schrijven ze, in dezelfde transactie als de gebeurtenis (wordt die teruggedraaid, dan de melding ook): uitnodiging, storting, blokkering, afrekening, geschil, uitbetaling, vrijgave bij een aanbieder, orders, opnames, voorstel servicevergoeding, nieuwe inlog, antwoord van support. Push via de outbox `push_messages`; de dispatcher draait met `python3 run.py dispatch`.
- **Talen:** `app/i18n.py` is een catalogus met Nederlands als bron en Frans en Engels. Een melding bewaart type en parameters en wordt bij het lezen in de gevraagde taal opgebouwd; voor het dossier blijft ook de Nederlandse tekst bewaard. Bedragen, percentages en datums worden per taal opgemaakt.
- **Activiteit:** `GET /activity` voegt twee bronnen samen op tijdstip met een cursor van (tijdstip, bron, id). De tijd van een beleggingstransactie is het moment van boeken.
- **Omgevingen:** `DEPIQO_ENV` is development, staging of production. Staging en productie hebben dezelfde verplichte geheimen en https; alleen staging mag de sandbox. `partners.bank()` en `investing.partner()` weigeren een sandboxadapter in productie, ook als de configuratie hem aanzet.

## Vier cijfers per borg

`services.balances(d)` geeft vier aparte cijfers. Een onbekend cijfer is `None` en verschijnt als "—" met een korte uitleg, nooit als het borgbedrag.

| Cijfer | Depiqo-borgrekening | Borg elders |
|---|---|---|
| Vereiste borg | `amount_cents` | `amount_cents` |
| Ontvangen | Som van de stortingen die de bank meldde | Borgbedrag vanaf bewijsniveau `document` |
| Bevestigd geblokkeerd | Waarde bij een actieve blokkering door de bank | Borgbedrag bij `legal` |
| Rente | Bijgeschreven rente volgens de bank | Niet bekend bij Depiqo |

## Bankpartner: keuze, fail-closed en adapter-interface (`app/partners.py`)

### Keuze van de partner

| Instelling | Resultaat |
|---|---|
| `BANK_PARTNER=sandbox` en `DEPIQO_SANDBOX=1` | Sandbox-bank (standaard in ontwikkeling) |
| `BANK_PARTNER=sandbox` en `DEPIQO_SANDBOX=0` | Geen partner: de sandbox staat uit |
| `BANK_PARTNER=<naam>` die in `BANK_ADAPTERS` staat | Die adapter |
| Leeg of onbekend | Geen partner (`DisabledBank`) |

`bank()` valt nooit stil terug op de sandbox. Zonder partner:

- kan niemand een dossier met een Depiqo-borgrekening aanmaken of importeren;
- kan een huurder zijn identiteit niet bevestigen voor een rekening (de wallet toont "Er is geen financiële partner gekoppeld");
- start geen uitbetaling, en verstuurt de dispatcher niets;
- worden bankberichten geweigerd (`/webhooks/bank/<provider>` geeft 404 voor een andere dan de ingestelde partner);
- tonen Business, de wallet en de beheeromgeving een duidelijke melding.

`bank_for_account(acct)` controleert dat de rekening bij de ingestelde partner hoort. Een blokkering telt alleen als bevestigd (label, "Bevestigd geblokkeerd", totalen) als de rekening bij de actieve partner staat (`services.lock_trusted`); een sandboxblokkering terwijl de sandbox uit staat heet "SANDBOX, niet bevestigd". Een echte adapter weigert dus een sandboxrekening (`provider = 'sandbox'`), en sandboxberichten of -acties worden geweigerd als de sandbox uit staat. Sandboxrekeningen dragen overal het label SANDBOX (dossier, lijst, wallet, afstemming, CSV-kolom `sandbox`).

### Interface voor een adapter (Banqup, Korfine, Certo, …)

Een adapter is een subklasse van `BankPartner` met een unieke `name`, een `display_name` (getoond als bewaarder) en deze methodes. Elke opdracht krijgt een **idempotentiesleutel**: dezelfde sleutel moet hetzelfde resultaat geven en nooit een tweede rekening of uitbetaling.

| Methode | Sleutel | Antwoord | Bevestiging later via |
|---|---|---|---|
| `open_account(deposit, tenant, idempotency_key)` | `open:<deposit_id>` | `external_id`, `iban`, `holder_name`, `interest_rate_bps`, `provider_ref` | (antwoord is genoeg) |
| `request_block(account, idempotency_key)` | `block:<bank_account_id>` | `provider_ref` | `account.blocked` |
| `request_release(account, tenant_cents, landlord_cents, reference, idempotency_key)` | `release:<bank_account_id>` | `provider_ref` | `payout.completed` |
| `payment_instructions(account, deposit)` | geen (alleen lezen) | `iban`, `beneficiary`, `reference`, `amount_cents` | |

Fouten: `PartnerError` voor een tijdelijke fout (de dispatcher probeert opnieuw), `PartnerUnavailable` voor een blijvende weigering (direct mislukt). Registreer de klasse in `BANK_ADAPTERS` onder haar configuratienaam.

### Bankberichten

Berichten komen binnen op `POST /webhooks/bank/<provider>`, ondertekend met HMAC-SHA256 (`X-Depiqo-Signature`), en worden eenmalig verwerkt op `event_id`. Een adapter vertaalt de berichten van de bank naar deze vier typen:

| Bericht | Velden | Effect |
|---|---|---|
| `deposit.received` | `external_id`, `amount_cents`, `ref` | Saldo bijwerken; bij volledig bedrag → storting ontvangen en een blokkeeropdracht in de outbox |
| `account.blocked` | `external_id` | Blokkeeropdracht uitgevoerd; → zekerheid geregistreerd, `legal_lock_status` = `active`, waarde = saldo |
| `interest.credited` | `external_id`, `amount_cents`, `ref` | Rente bijschrijven (voor de huurder) |
| `payout.completed` | `external_id`, `tenant_cents`, `landlord_cents`, `ref` | Alleen als beide bedragen precies gelijk zijn aan de vrijgave-opdracht: rekening gesloten, opdracht uitgevoerd, dossier gesloten. Anders: fout op het bankbericht, melding in de afstemming en de audittrail, dossier blijft open |

Begint een bank zonder API, dan kan dezelfde adapter met periodieke bestanden werken: de outbox wordt dan een exportbestand en de berichten een importbestand.

## Outbox voor bankopdrachten (`bank_instructions`)

1. Een actie (identiteit bevestigd, storting volledig, uitbetaling gestart) schrijft in **dezelfde transactie** als de statuswijziging een rij met `kind` (`open`, `block`, `release`), `payload_json` en een unieke `idempotency_key`. Mislukt de statuswijziging, dan bestaat de opdracht ook niet.
2. Na de commit probeert `services.dispatch_instructions(ids)` de opdracht direct te versturen (uit te zetten met `DISPATCH_INLINE=0`).
3. De dispatcher claimt een rij met een optimistische update (`pending` → `sent`, `attempts + 1`), roept de partner aan **buiten** een transactie, en legt het antwoord vast: `acknowledged` (bank heeft de opdracht aangenomen), of `confirmed` voor `open` (rekening bestaat). Bij een tijdelijke fout gaat de rij terug naar `pending`; na `MAX_INSTRUCTION_ATTEMPTS` (standaard 5) wordt ze `failed`.
4. Een rij die langer dan 10 minuten op `sent` staat (proces gecrasht), wordt opnieuw verstuurd met dezelfde sleutel.
5. Bankberichten zetten `block` en `release` op `confirmed`. Elke statusupdate van de dispatcher geldt alleen vanuit `sent`, zodat een time-out nooit een opdracht overschrijft die de bank intussen bevestigde.
6. Bij een uitbetaling staat de rekening in dezelfde transactie als de opdracht op `release_requested`. Een `payout.completed` die binnenkomt terwijl de opdracht nog `pending` of `sent` is, wordt dus gewoon verwerkt.
7. Een bankbericht dat om een timingreden is geweigerd (`onbekende rekening`, `uitbetaling zonder vrijgave-opdracht`) krijgt `retryable = 1`: als de bank hetzelfde `event_id` opnieuw stuurt, wordt het opnieuw verwerkt in plaats van als dubbel genegeerd. Een Depiqo-medewerker kan elk bankbericht met een fout opnieuw laten verwerken.
8. Een nieuwe poging van de gebruiker (bijvoorbeeld een nieuwe identiteitscontrole) zet een mislukte opdracht met dezelfde sleutel terug op `pending`.

Versturen: automatisch na elke actie, met de knop "Opdrachten versturen" in de beheeromgeving, of `python3 run.py dispatch` (bijvoorbeeld elke minuut via cron). Een mislukte opdracht zet een medewerker terug in de wachtrij met "Opnieuw" (zelfde sleutel).

Gevolg voor de flow: na de identiteitscontrole blijft een dossier op "identificatie loopt" tot de bank de rekening heeft geopend. Met de sandbox gebeurt dat direct.

## Afstemming

`finance.reconciliation()` vergelijkt per dossier de verplichting, het saldo volgens de bank, de laatste bankopdracht en het bewijs, en noemt afwijkingen: saldo lager dan de verplichting terwijl de zekerheid geregistreerd staat; bank meldt geen blokkering; dossier gesloten maar rekening niet; mislukte opdracht; vrijgave na `RELEASE_CONFIRM_DAYS` (5) niet bevestigd; bankberichten met fouten; borg elders langer dan `DECLARED_MAX_DAYS` (14) alleen verklaard; borg elders zonder aanbieder; garantie die binnen 60 dagen eindigt of verlopen is. Te zien voor Depiqo (`/admin/afstemming`, alle organisaties) en voor beheerder en financieel medewerker (`/app/afstemming`).

## Zekerheidsmodel: verplichting en onderpand

Een borg bestaat uit twee dingen die we apart bijhouden:

1. **De verplichting.** Wat de huurder als zekerheid verschuldigd is: `deposits.amount_cents`, binnen het wettelijk maximum. Dit verandert niet door rente of koersen.
2. **Het onderpand.** Wat die verplichting dekt, en hoe hard die dekking is. Dat staat in deze kolommen van `deposits`:

| Kolom | Betekenis |
|---|---|
| `security_type` | `bank_deposit` (geld op een rekening bij de partnerbank), `external_account` (borg buiten Depiqo: rekening van de verhuurder, geblokkeerde bankrekening, e-DEPO, verzekeraar, OCMW), `guarantee` (garantie of borgstelling door een derde, sinds 0.4.0 in gebruik), later `pledged_portfolio` (verpande beleggingsrekening) |
| `custodian` | Wie het onderpand bewaart, bijvoorbeeld de partnerbank. Leeg als de borg bij de verhuurder staat |
| `beneficiary` | Ten gunste van wie het onderpand staat: de organisatie (verhuurder of beheerder) |
| `legal_lock_status` | De juridische blokkering of verpanding bij de bewaarder: `none`, `requested`, `active`, `released`. Dit is iets anders dan de juridische blokkade van een dossier (status `legal_hold`), die Depiqo zelf zet bij beslag of een procedure |
| `asset_value_cents` | De waarde van het onderpand volgens de bewaarder |
| `eligible_value_cents` | Het deel dat als zekerheid meetelt. Bij een bankdeposito is dat het hele saldo zodra de blokkering actief is; zonder actieve blokkering telt niets mee |

`services.coverage_bps(deposit)` geeft de dekking: meetellende waarde gedeeld door de verplichting, in basispunten (10000 = 100%). Met bijgeschreven rente kan dat boven 100% komen; die rente gaat bij uitbetaling naar de huurder.

**Waarom zo.** Vandaag is onderpand bijna altijd geld op een rekening, en dan vallen waarde en verplichting samen. Bij een verpande beleggingsrekening (fase 3) of een garantie is dat niet zo: de waarde beweegt, er geldt een veiligheidsmarge en de juridische vorm verschilt. Door verplichting en onderpand nu al te scheiden, kan dat later zonder de statusmachine aan te passen. `eligible_value_cents` is dan de waarde na marge, en de dekking laat zien of er moet worden bijgestort.

**Wie wat zet.** Alleen bankberichten wijzigen `legal_lock_status` en de waarden bij een Depiqo-borgrekening (`services.set_security` en `sync_security_from_bank`). Bij een borg elders zet de verklaring van een financieel medewerker het type op `external_account` en `asset_value_cents` op het borgbedrag; `eligible_value_cents` volgt het bewijsniveau (zie hierboven).

## Regels per versie (`app/rules.py`)

`RULESETS` is een dict per versie (nu alleen `2026-10-18`). Elke versie heeft per regio het maximum, de termijnen (`return_days` of `return_months`) en het interne streefdoel. `max_amount_cents`, `validate_deposit` en `deadline` krijgen de versie van het dossier (`deposits.rule_version`); nieuwe dossiers krijgen `RULE_VERSION`. Een nieuwe wet wordt een nieuwe sleutel; een bestaande versie wijzig je nooit. Een onbekende versie geeft `UnknownRuleVersion`, geen stille terugval. Een test met een nepversie bewijst dat een oud dossier zijn oude maximum en termijn houdt.

## Facturatie

Zie `app/billing.py`. `PLANS` bevat Essential en Professional; Enterprise heeft eigen bedragen. `price()` maakt de factuurregels: basis, inbegrepen, extra elders, extra Depiqo-borgrekening, nieuwe dossiers en eventueel de pilotkorting.

**Plangeschiedenis.** Elke planwijziging schrijft een rij in `organization_plan_history` (plan, Enterprise-bedragen, `valid_from`). Een raming of factuur gebruikt het plan dat gold op de **eerste dag van de factuurmaand** (`plan_for_period`). Een beheerder die zelf wisselt, krijgt het nieuwe plan vanaf de eerste dag van de volgende maand. Een Depiqo-medewerker kiest een ingangsmaand vanaf de lopende maand; een afgelopen maand corrigeer je met een creditnota. De nieuwste beslissing wint: een wijziging verwijdert ingeplande rijen met een latere ingangsdatum (het auditlog bewaart ze). `organizations.plan` bevat de laatste keuze.

**Betaling en creditnota's.** Een factuur heeft `payment_status` (`open`, `paid`, of `none` bij € 0) en een vervaldatum (14 dagen); "te laat" is open na de vervaldatum. Een Depiqo-medewerker zet een uitgereikte, open factuur op betaald, of crediteert een factuur die nog niet betaald is: het origineel krijgt status `credited`, en een creditnota (`kind = 'credit'`, negatieve bedragen, `credit_for_id`) volgt de gewone nummering. Een unieke index staat één uitgereikte factuur per organisatie en maand toe; na crediteren kan de maand opnieuw worden gefactureerd.

## Unit economics

`finance.unit_economics()` rekent per organisatie en in totaal: actieve dossiers per soort, MRR volgens de plannen (voor en na pilotkorting), aangenomen partnerkosten en brutomarge. De aannames (standaard € 0,50 per actieve Depiqo-rekening per maand, € 2,00 per nieuwe Depiqo-rekening, € 0 per borg elders) staan in `staff_settings` en past een Depiqo-medewerker aan op `/admin/unit-economics`. De pagina waarschuwt als de prijs per extra Depiqo-dossier lager is dan de partnerkosten; met de standaardaannames is dat bij beide plannen zo.

## Gegevens

SQLite in ontwikkeling, schema in `migrations/`. Het SQL is bewust standaard gehouden. Overstap naar PostgreSQL: `psycopg` als driver, `?` vervangen door `%s` in `app/db.py`, `INTEGER PRIMARY KEY` → `BIGSERIAL`, tijdstempels → `TIMESTAMPTZ`. Bedragen zijn overal centen als geheel getal.

## Rollen

Zie `PERMISSIONS` in `app/security.py` en het overzicht op de pagina Team. Elke schrijfactie controleert de rol op de server; de interface verbergt alleen knoppen.
