## Android e2e (nl)

**10 van 10 flows geslaagd.**
### maestro-nl

| Flow | Resultaat | Tijd (s) | Melding |
|---|---|---|---|
| a. Login (mila), borgen, vier bedragen, — bij onbekend | ok | 41.0 |  |
| b. Login met 2FA (lars) | ok | 38.0 |  |
| reset-app | ok | 2.0 |  |
| c. Uitnodiging via deep link: verhuurder, adres, bedrag | ok | 2.0 |  |
| d. Eindafrekening bekijken (sanne), niet reageren | ok | 39.0 |  |
| e. Meldingen, profiel, taal fr en en | ok | 56.0 |  |
| f. Uitloggen, beschermde schermen niet bereikbaar | ok | 46.0 |  |
| g. Sessie blijft na herstart | ok | 33.0 |  |
| h. Beleggen verborgen (sofie) en zichtbaar in sandbox (daan) | ok | 61.0 |  |
| Fout wachtwoord geeft vertaalde foutmelding | ok | 57.0 |  |

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

