## Android e2e (fr-en)

**20 van 20 flows geslaagd.**
### maestro-en

| Flow | Resultaat | Tijd (s) | Melding |
|---|---|---|---|
| a. Login (mila), borgen, vier bedragen, — bij onbekend | ok | 41.0 |  |
| b. Login met 2FA (lars) | ok | 43.0 |  |
| reset-app | ok | 3.0 |  |
| c. Uitnodiging via deep link: verhuurder, adres, bedrag | ok | 2.0 |  |
| d. Eindafrekening bekijken (sanne), niet reageren | ok | 46.0 |  |
| e. Meldingen, profiel, taal fr en en | ok | 63.0 |  |
| f. Uitloggen, beschermde schermen niet bereikbaar | ok | 56.0 |  |
| g. Sessie blijft na herstart | ok | 39.0 |  |
| h. Beleggen verborgen (sofie) en zichtbaar in sandbox (daan) | ok | 71.0 |  |
| Fout wachtwoord geeft vertaalde foutmelding | ok | 64.0 |  |

```
01-login-deposits-amounts ok
02-login-2fa ok
03-invite-deeplink ok
04-settlement-view ok
05-notifications-profile-language ok
06-logout-protected ok
07-session-restore ok
08-invest-visibility ok
09-wrong-password ok
```

Schermafdrukken: 19 (in het artifact, map `maestro-en/screenshots`)

### maestro-fr

| Flow | Resultaat | Tijd (s) | Melding |
|---|---|---|---|
| a. Login (mila), borgen, vier bedragen, — bij onbekend | ok | 62.0 |  |
| b. Login met 2FA (lars) | ok | 48.0 |  |
| reset-app | ok | 2.0 |  |
| c. Uitnodiging via deep link: verhuurder, adres, bedrag | ok | 2.0 |  |
| d. Eindafrekening bekijken (sanne), niet reageren | ok | 46.0 |  |
| e. Meldingen, profiel, taal fr en en | ok | 64.0 |  |
| f. Uitloggen, beschermde schermen niet bereikbaar | ok | 56.0 |  |
| g. Sessie blijft na herstart | ok | 41.0 |  |
| h. Beleggen verborgen (sofie) en zichtbaar in sandbox (daan) | ok | 73.0 |  |
| Fout wachtwoord geeft vertaalde foutmelding | ok | 66.0 |  |

```
01-login-deposits-amounts ok
02-login-2fa ok
03-invite-deeplink ok
04-settlement-view ok
05-notifications-profile-language ok
06-logout-protected ok
07-session-restore ok
08-invest-visibility ok
09-wrong-password ok
```

Schermafdrukken: 19 (in het artifact, map `maestro-fr/screenshots`)

