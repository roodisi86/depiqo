# API voor de huurders-app (0.6.0)

JSON-API onder `/api/v1` voor de app van Depiqo voor huurders (React Native met Expo). Alleen voor huurders: Depiqo Wallet en Depiqo Invest. Beheerders en Depiqo-medewerkers gebruiken de webapp; de API weigert hen met 403.

- Specificatie: [`openapi.yaml`](openapi.yaml) (OpenAPI 3.1). Een test vergelijkt de routes in de code met de paden in de specificatie, in beide richtingen. Een tweede test valideert echte antwoorden tegen de schema's.
- Alle regels zitten in de bestaande services (`app/services.py`, `app/investing.py`). De API vertaalt alleen tussen HTTP en die functies. Er is geen tweede kopie van de bedrijfslogica.

## Afspraken

| Onderwerp | Afspraak |
|---|---|
| Inloggen | Alleen `Authorization: Bearer <access_token>`. Cookies worden niet gelezen. Een schrijvend verzoek met de webcookie `dpq_session` maar zonder bearer-token krijgt 403 `cookie_auth_not_allowed`. Zet in de app `credentials: "omit"` bij `fetch`. |
| Fouten | Altijd `{"error": {"code", "message", "fields", "detail?"}}` met een passende HTTP-status. `code` is vast (snake_case), `message` volgt de taal. |
| Talen | `Accept-Language` met nl, fr of en; zonder header de taal die de gebruiker koos (`PATCH /me`), anders nl. Geldt voor foutmeldingen en meldingen (titel en tekst). Labels in antwoorden blijven Nederlands, altijd naast een vaste sleutel (`status` + `status_label`, `display_key`, `key` + `params`, `kind`, `explanation_key`). De app vertaalt die sleutels zelf. |
| Geld | `{"cents": 12345, "currency": "EUR"}`. Onbekend is `null` met een uitleg, nooit het bedrag van de verplichting. |
| Datums | `YYYY-MM-DD`; tijdstippen ISO 8601 met tijdzone. |
| Lijsten | `?limit=` (1 tot 100, standaard 20) en `?cursor=`; het antwoord heeft `next_cursor` (`null` op de laatste pagina). Een cursor die niet van de server komt: 400 `invalid_cursor`. |
| Idempotentie | `Idempotency-Key` (8 tot 100 tekens) wordt gehonoreerd op elk schrijvend geldverzoek; verplicht bij orders, opnames en de sandboxstorting. Hetzelfde verzoek met dezelfde sleutel krijgt 24 uur lang hetzelfde antwoord (header `Idempotent-Replayed: true`) zonder dat de actie opnieuw gebeurt. Dezelfde sleutel met een ander verzoek: 422 `idempotency_key_reused`. Alleen geslaagde antwoorden worden bewaard. Bij een upload (multipart) tellen de velden en de SHA-256 van elk bestand, niet de ruwe body. |
| Versie van de app | Stuur `X-App-Platform` en `X-App-Version` mee. Onder de minimumversie uit `/config`: 426 `app_update_required`. |
| Caching | Elk antwoord heeft `Cache-Control: no-store`. |

## Inloggen

```
App                                   API
 |  POST /auth/login                   |
 |  {email, password, device}  ------> |  rate limit (zelfde tellers als de website)
 |                                     |  wachtwoord, geen medewerker, wel huurder
 |  <------ 200 {access_token, refresh_token, ...}          (zonder 2FA)
 |  <------ 200 {mfa_required: true, mfa_token}             (met 2FA)
 |                                     |
 |  POST /auth/mfa {mfa_token, code} ->|  code uit de app of herstelcode, 5 minuten, 5 pogingen
 |  <------ 200 {access_token, refresh_token, second_factor}
```

- Toegangstoken: 15 minuten. Vernieuwingstoken: 30 dagen. Beide willekeurig, alleen als SHA-256-hash opgeslagen.
- Elke login maakt een apparaatsessie (naam, platform, versie, laatst gezien). De huurder ziet ze in de app (`GET /auth/devices`) en op de website onder Beveiliging, en kan ze daar afmelden.
- Een nieuwe login geeft een melding "Nieuwe inlog op je account".
- Wachtwoord vergeten blijft op de website: `config.links.password_reset`.

### Vernieuwen en diefstaldetectie

```
 POST /auth/refresh {refresh_token: R1}  -> 200 {access_token: A2, refresh_token: R2}   R1 is nu gebruikt
 POST /auth/refresh {refresh_token: R1}  -> 401 refresh_token_reused                     de hele apparaatsessie stopt:
                                                                                          A2 en R2 werken niet meer
```

Een gebruikt vernieuwingstoken dat opnieuw opduikt, betekent dat twee partijen hetzelfde token hebben. Daarom stopt de hele sessie op dat apparaat. Vernieuw in de app dus één keer tegelijk (één promise die alle verzoeken delen) en bewaar het nieuwe token voordat je het oude weggooit.

### Uitnodiging accepteren

```
 Link in de mail: https://<domein>/t/<token>   (opent de app via universal link of App Link)
 GET  /invites/<token>                -> verhuurder, adres, bedrag, kenmerk  (de anti-phishingcontrole: toon dit groot)
 POST /invites/<token>/accept         {password, confirm_details: true, device}
                                      -> 201 met tokens (nieuw account)
 Bestaand huurdersaccount:            eerst inloggen, dan accept met de bearer-token -> 200
 Bestaand account zonder huurdersrol: 409 use_web met de weblink in fields.url
```

## Voorbeelden

```bash
B=http://localhost:5000/api/v1
curl -s $B/config

curl -s -X POST $B/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"daan@huurder.test","password":"Depiqo-demo-2026","device":{"name":"iPhone van Daan","platform":"ios","app_version":"1.0.0"}}'
T=<access_token>

curl -s $B/deposits -H "Authorization: Bearer $T"
curl -s $B/deposits/<pid> -H "Authorization: Bearer $T" -H 'Accept-Language: fr'

# Foto van de camera toevoegen (JPEG)
curl -s -X POST $B/deposits/<pid>/documents -H "Authorization: Bearer $T" -F kind=photo -F file=@foto.jpg

# Kopen: eerst een offerte (kosten, scenario's, risico; 10 minuten geldig), dan de order
curl -s -X POST $B/invest/orders/quote -H "Authorization: Bearer $T" -H 'Content-Type: application/json' -d '{"side":"buy","amount_cents":10000}'
curl -s -X POST $B/invest/orders -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: 7c1f0d2e-order-1' -d '{"quote_id":"q_...","risk_acknowledged":true}'

curl -s "$B/notifications?limit=20" -H "Authorization: Bearer $T"
curl -s -X POST $B/auth/refresh -H 'Content-Type: application/json' -d '{"refresh_token":"..."}'
```

`tests/api_smoke.py` doet deze stappen tegen een draaiende server.

## Schermen en endpoints

| Scherm in de app | Endpoints |
|---|---|
| Opstarten | `GET /config` (minimumversie, banner STAGING of SANDBOX, links) |
| Inloggen, code | `POST /auth/login`, `POST /auth/mfa` |
| Uitnodiging | `GET /invites/{token}`, `POST /invites/{token}/accept` |
| Mijn borgen | `GET /deposits` |
| Borg | `GET /deposits/{pid}` (bedragen, voortgang, waar de borg staat, termijn, volgende stap, betaalgegevens, laatste gebeurtenissen) |
| Geschiedenis van een borg | `GET /deposits/{pid}/events` |
| Identiteit bevestigen | `POST /deposits/{pid}/identity` |
| Documenten | `GET`, `POST /deposits/{pid}/documents`, `GET /deposits/{pid}/documents/{id}` |
| Eindafrekening | `GET /deposits/{pid}/settlement`, `POST .../agree`, `POST .../dispute` |
| Vrijgaveformulier | `GET /deposits/{pid}/release-form` (PDF) |
| Waar wil je jouw deel ontvangen | `GET`, `POST`, `DELETE /deposits/{pid}/payout-choice` |
| Beleggen (overzicht of start) | `GET /invest` (waarde, inleg, vrij geld, resultaat, fondsen, grafiek 1M/6M/1Y/max, of de volgende stap van de start) |
| Toets | `GET`, `POST /invest/appropriateness`, `POST /invest/appropriateness/confirm` |
| Portefeuille kiezen | `GET /invest/portfolios?amount_cents=` |
| Voorwaarden, rekening openen | `GET`, `POST /invest/terms`, `POST /invest/account` |
| Storten | `GET /invest/deposit-instructions`; sandbox: `POST /invest/sandbox/deposit` |
| Kopen, verkopen, wisselen | `POST /invest/orders/quote`, daarna `POST /invest/orders` |
| Orders, transacties, opnames | `GET /invest/orders`, `GET /invest/transactions`, `GET /invest/withdrawals` |
| Opnemen | `POST /invest/iban` (eigen rekening registreren), `POST /invest/withdrawals` |
| Maandoverzichten | `GET /invest/statements`, `GET /invest/statements/{periode}` (PDF) |
| Nieuwe servicevergoeding | `GET`, `POST /invest/fee-change` |
| Activiteit | `GET /activity` (borg en beleggen in één lijst) |
| Meldingen | `GET /notifications`, `POST /notifications/{id}/read`, `POST /devices/push-token` |
| Hulp | `GET`, `POST /support` |
| Profiel, taal, meldingen aan of uit | `GET`, `PATCH /me` |
| Beveiliging | `GET /auth/devices`, `DELETE /auth/devices/{id}`, `POST /auth/logout` |
| Mijn gegevens | `POST /me/export`, `GET`, `POST /me/delete-request` |

## Meldingen en push

Gebeurtenissen schrijven een melding per gebruiker: uitnodiging (bestaand account), storting ontvangen, borg veilig, eindafrekening klaar, geschil afgerond, borg uitbetaald of vrijgegeven, order uitgevoerd of mislukt, opname uitgevoerd of mislukt, voorstel nieuwe servicevergoeding, nieuwe inlog, antwoord van support. De melding bewaart type en parameters; titel en tekst worden bij het lezen in de gevraagde taal opgebouwd.

Een pushbericht bevat alleen de vaste titel en de regel "Open Depiqo voor de details", in de taal van de gebruiker, plus `{notification_id, path, type}`. Nooit bedragen, adressen of namen. Pushberichten gaan via een outbox (`push_messages`) naar Expo. In de sandbox en in ontwikkeling staat versturen uit (`PUSH_SEND=0`): het bericht komt in de outbox als `skipped` met notitie `sandbox`. `python3 run.py dispatch` verstuurt openstaande berichten en leest de ontvangstbewijzen; `DeviceNotRegistered` zet de pushtoken uit. Uitloggen of afmelden van een apparaat zet de pushtoken van dat apparaat ook uit.

## Deep links

`/.well-known/apple-app-site-association` en `/.well-known/assetlinks.json` komen uit de configuratie (`APP_IOS_TEAM_ID`, `APP_BUNDLE_ID` standaard `com.getdepiqo.app`, `ANDROID_SHA256_CERT`, meerdere gescheiden door komma's). Ze dekken `/t/*` (uitnodigingen) en `/app-link/*` (links uit meldingen: `/app-link/borg/<pid>`, `/app-link/beleggen`, `/app-link/beveiliging`, `/app-link/support/<id>`). Zonder app opent de browser de bestaande pagina's: `/t/` is de uitnodigingspagina, `/app-link/*` stuurt door naar de wallet. Op Android staan de paden in het manifest van de app (intent-filter met `autoVerify`). In productie zonder team-id of certificaat geven beide bestanden 404.

## Omgevingen en veiligheid van geld

- `DEPIQO_ENV`: `development`, `staging` of `production`. `/config` geeft `environment` en `banner` (`STAGING`, `SANDBOX` of `null`), zodat de app een testbalk toont.
- Productie draait nooit een sandboxpartner, ook niet met `DEPIQO_SANDBOX=1`. Zonder echte partner geeft elk Invest-endpoint en elk endpoint dat geld zou verplaatsen 503 `partner_unavailable`; er verandert niets.
- Sandbox-endpoints (`/invest/sandbox/deposit`) bestaan alleen met de sandbox aan.
- Geen enkel endpoint verplaatst borggeld. De huurder kan akkoord gaan, bezwaar maken en kiezen waar zijn deel heen gaat; de uitbetaling start de beheerder op de website en voert de bank uit, met de controles van 0.3.

## Fouten

De meest voorkomende codes; de volledige lijst staat per endpoint in de specificatie en in `app/i18n.py`.

| Status | Codes |
|---|---|
| 400 | `invalid_json`, `invalid_cursor`, `idempotency_key_required`, `invalid_idempotency_key` |
| 401 | `token_missing`, `token_invalid`, `token_expired` (vernieuwen), `device_revoked`, `refresh_token_reused`, `invalid_credentials`, `invalid_code`, `mfa_token_invalid` |
| 403 | `staff_not_allowed`, `not_a_tenant`, `cookie_auth_not_allowed` |
| 404 | `not_found` (ook voor de borg van een ander), `invest_not_offered`, `quote_not_found` |
| 409 | `push_token_in_use`, `invest_rejected`, `quote_used`, `quote_expired`, `settlement_not_open`, `payout_choice_closed`, `deletion_blocked`, `terms_outdated` |
| 410 | `invite_expired` |
| 422 | `validation_failed` (met `fields`), `risk_acknowledged_required`, `confirm_required`, `upload_rejected`, `idempotency_key_reused` |
| 426 | `app_update_required` |
| 429 | `too_many_attempts` (ook bij foute codes voor de opnamerekening), `support_rate_limited` |
| 503 | `partner_unavailable` |
