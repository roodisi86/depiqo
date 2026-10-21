## Android e2e (large-dark)

**10 van 10 flows geslaagd.**
### maestro-nl

| Flow | Resultaat | Tijd (s) | Melding |
|---|---|---|---|
| a. Login (mila), borgen, vier bedragen, — bij onbekend | ok | 42.0 |  |
| b. Login met 2FA (lars) | ok | 39.0 |  |
| reset-app | ok | 2.0 |  |
| c. Uitnodiging via deep link: verhuurder, adres, bedrag | ok | 2.0 |  |
| d. Eindafrekening bekijken (sanne), niet reageren | ok | 43.0 |  |
| e. Meldingen, profiel, taal fr en en | ok | 56.0 |  |
| f. Uitloggen, beschermde schermen niet bereikbaar | ok | 50.0 |  |
| g. Sessie blijft na herstart | ok | 34.0 |  |
| h. Beleggen verborgen (sofie) en zichtbaar in sandbox (daan) | ok | 60.0 |  |
| Fout wachtwoord geeft vertaalde foutmelding | ok | 58.0 |  |

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

Schermafdrukken: 19 (in het artifact, map `maestro-nl/screenshots`)

