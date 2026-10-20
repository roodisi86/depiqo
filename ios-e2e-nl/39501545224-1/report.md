## iOS e2e (nl)

**1 van 10 flows geslaagd.**
### maestro-nl

| Flow | Resultaat | Tijd (s) | Melding |
|---|---|---|---|
| a. Login (mila), borgen, vier bedragen, — bij onbekend | FAILED | 129.0 | Assertion is false: id: tab-profile is visible |
| b. Login met 2FA (lars) | FAILED | 113.0 | Assertion is false: id: tab-profile is visible |
| reset-app | ok | 25.0 |  |
| c. Uitnodiging via deep link: verhuurder, adres, bedrag | FAILED | 52.0 | Assertion is false: id: invite-screen is visible |
| d. Eindafrekening bekijken (sanne), niet reageren | FAILED | 110.0 | Assertion is false: id: tab-profile is visible |
| e. Meldingen, profiel, taal fr en en | FAILED | 104.0 | Assertion is false: id: tab-profile is visible |
| f. Uitloggen, beschermde schermen niet bereikbaar | FAILED | 106.0 | Assertion is false: id: tab-profile is visible |
| g. Sessie blijft na herstart | FAILED | 111.0 | Assertion is false: id: tab-profile is visible |
| h. Beleggen verborgen (sofie) en zichtbaar in sandbox (daan) | FAILED | 111.0 | Assertion is false: id: tab-profile is visible |
| Fout wachtwoord geeft vertaalde foutmelding | FAILED | 112.0 | Assertion is false: id: tab-profile is visible |

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

Schermafdrukken: 10 (in het artifact, map `maestro-nl/screenshots`)

