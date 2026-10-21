## iOS e2e (nl)

**8 van 9 flows geslaagd.**
### maestro-nl

| Flow | Resultaat | Tijd (s) | Melding |
|---|---|---|---|
| b. Login met 2FA (lars) | FAILED | 45.0 | Unable to set permissions for app com.getdepiqo.app.dev: Failed to connect to /127.0.0.1:54275 |
| reset-app | ok | 32.0 |  |
| c. Uitnodiging via deep link: verhuurder, adres, bedrag | ok | 20.0 |  |
| d. Eindafrekening bekijken (sanne), niet reageren | ok | 94.0 |  |
| e. Meldingen, profiel, taal fr en en | ok | 95.0 |  |
| f. Uitloggen, beschermde schermen niet bereikbaar | ok | 113.0 |  |
| g. Sessie blijft na herstart | ok | 112.0 |  |
| h. Beleggen verborgen (sofie) en zichtbaar in sandbox (daan) | ok | 178.0 |  |
| Fout wachtwoord geeft vertaalde foutmelding | ok | 116.0 |  |

```
01-login-deposits-amounts FAILED
02-login-2fa FAILED
03-invite-deeplink ok
04-settlement-view ok
05-notifications-profile-language ok
06-logout-protected ok
07-session-restore ok
08-invest-visibility ok
09-wrong-password ok
```

Schermafdrukken: 15 (in het artifact, map `maestro-nl/screenshots`)

