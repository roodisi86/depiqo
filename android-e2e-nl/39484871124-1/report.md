## Android e2e (nl)

**1 van 10 flows geslaagd.**
### maestro-nl

| Flow | Resultaat | Tijd (s) | Melding |
|---|---|---|---|
| a. Login (mila), borgen, vier bedragen, — bij onbekend | FAILED | 48.0 | Assertion is false: id: login-email is visible |
| b. Login met 2FA (lars) | FAILED | 48.0 | Assertion is false: id: login-email is visible |
| reset-app | ok | 1.0 |  |
| c. Uitnodiging via deep link: verhuurder, adres, bedrag | FAILED | 45.0 | Assertion is false: id: invite-screen is visible |
| d. Eindafrekening bekijken (sanne), niet reageren | FAILED | 47.0 | Assertion is false: id: login-email is visible |
| e. Meldingen, profiel, taal fr en en | FAILED | 47.0 | Assertion is false: id: login-email is visible |
| f. Uitloggen, beschermde schermen niet bereikbaar | FAILED | 47.0 | Assertion is false: id: login-email is visible |
| g. Sessie blijft na herstart | FAILED | 47.0 | Assertion is false: id: login-email is visible |
| h. Beleggen verborgen (sofie) en zichtbaar in sandbox (daan) | FAILED | 47.0 | Assertion is false: id: login-email is visible |
| Fout wachtwoord geeft vertaalde foutmelding | FAILED | 47.0 | Assertion is false: id: login-email is visible |

```
01-login-deposits-amounts FAILED
02-login-2fa FAILED
03-invite-deeplink FAILED
04-settlement-view FAILED
05-notifications-profile-language FAILED
06-logout-protected FAILED
07-session-restore FAILED
08-invest-visibility FAILED
09-wrong-password FAILED
```

Schermafdrukken: 9 (in het artifact, map `maestro-nl/screenshots`)

