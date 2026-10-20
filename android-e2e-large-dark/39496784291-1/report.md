## Android e2e (large-dark)

**9 van 10 flows geslaagd.**
### maestro-nl

| Flow | Resultaat | Tijd (s) | Melding |
|---|---|---|---|
| a. Login (mila), borgen, vier bedragen, — bij onbekend | ok | 54.0 |  |
| b. Login met 2FA (lars) | ok | 47.0 |  |
| reset-app | ok | 2.0 |  |
| c. Uitnodiging via deep link: verhuurder, adres, bedrag | ok | 2.0 |  |
| d. Eindafrekening bekijken (sanne), niet reageren | FAILED | 63.0 | Assertion is false: id: settlement-dispute is visible |
| e. Meldingen, profiel, taal fr en en | ok | 62.0 |  |
| f. Uitloggen, beschermde schermen niet bereikbaar | ok | 56.0 |  |
| g. Sessie blijft na herstart | ok | 38.0 |  |
| h. Beleggen verborgen (sofie) en zichtbaar in sandbox (daan) | ok | 70.0 |  |
| Fout wachtwoord geeft vertaalde foutmelding | ok | 66.0 |  |

```
01-login-deposits-amounts ok
02-login-2fa ok
03-invite-deeplink ok
04-settlement-view FAILED
05-notifications-profile-language ok
06-logout-protected ok
07-session-restore ok
08-invest-visibility ok
09-wrong-password ok
```

Schermafdrukken: 19 (in het artifact, map `maestro-nl/screenshots`)

