## iOS e2e (nl)

**2 van 10 flows geslaagd.**
### maestro-nl

| Flow | Resultaat | Tijd (s) | Melding |
|---|---|---|---|
| a. Login (mila), borgen, vier bedragen, — bij onbekend | FAILED | 123.0 | Assertion is false: id: tab-profile is visible |
| b. Login met 2FA (lars) | FAILED | 94.0 | Couldn't hide the keyboard. This can happen if the app uses a custom input or doesn't expose a standard dismiss action. |
| reset-app | ok | 29.0 |  |
| c. Uitnodiging via deep link: verhuurder, adres, bedrag | ok | 21.0 |  |
| d. Eindafrekening bekijken (sanne), niet reageren | FAILED | 96.0 | Assertion is false: id: tab-profile is visible |
| e. Meldingen, profiel, taal fr en en | FAILED | 87.0 | Assertion is false: id: tab-profile is visible |
| f. Uitloggen, beschermde schermen niet bereikbaar | FAILED | 118.0 | Assertion is false: id: tab-profile is visible |
| g. Sessie blijft na herstart | FAILED | 98.0 | Assertion is false: id: tab-profile is visible |
| h. Beleggen verborgen (sofie) en zichtbaar in sandbox (daan) | FAILED | 96.0 | Assertion is false: id: tab-profile is visible |
| Fout wachtwoord geeft vertaalde foutmelding | FAILED | 92.0 | Assertion is false: id: tab-profile is visible |

```
01-login-deposits-amounts FAILED
02-login-2fa FAILED
03-invite-deeplink ok
04-settlement-view FAILED
05-notifications-profile-language FAILED
06-logout-protected FAILED
07-session-restore FAILED
08-invest-visibility FAILED
09-wrong-password FAILED
```

Schermafdrukken: 10 (in het artifact, map `maestro-nl/screenshots`)

