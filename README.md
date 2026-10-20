# Depiqo

Eén repository voor het platform en de app voor huurders.

| Map | Wat |
|---|---|
| `platform/` | Het Depiqo-platform (Flask, Python 3.13): Business, Wallet op het web, beheer en de API voor de app (`/api/v1`). Zie `platform/README.md`. |
| `mobile/` | Depiqo Wallet, de app voor huurders (Expo SDK 53, React Native, TypeScript). Zie `mobile/README.md` en `mobile/docs/STATUS.md`. |
| `mobile/.maestro/` | End-to-end-tests voor de app (Maestro), met `run-suite.sh` om ze in CI te draaien. |
| `.github/workflows/` | De vier workflows hieronder. |
| `.github/scripts/` | Hulpscripts voor CI: backend starten met verse demodata, testdata voor 2FA en uitnodiging, TOTP-code, logscan op tokens, rapport. |

Er wordt nergens echt geld verwerkt: CI draait het platform altijd in `development` met de sandbox.

## Hoe CI werkt

| Workflow | Wanneer | Wat het doet |
|---|---|---|
| **Platform** (`platform.yml`) | bij wijzigingen in `platform/` | Alle unittests (gewoon en met `TZ=UTC`), de contracttest voor de app (`tests/test_mobile_contract.py`), de API-rooktest tegen een draaiende server en de browsertest in Chromium. |
| **Mobile checks** (`mobile-checks.yml`) | bij wijzigingen in `mobile/` | Echte `npm install` en `npx expo install --fix`, `expo-doctor` (meldt, faalt niet), `tsc`, `eslint`, `jest` (jest-expo) en de talencheck. Maakt de eerste `package-lock.json`. |
| **Android e2e** (`android-e2e.yml`) | push naar `main`, of met de hand | Bouwt een release-APK (JavaScript in de APK), start de backend met verse demodata, draait alle Maestro-flows op een Android 14-emulator: in het Nederlands, met grote tekst en donkere modus, en in het Frans en Engels. |
| **iOS e2e** (`ios-e2e.yml`) | alleen met de hand (macOS-minuten zijn duur) | Bouwt de app voor de iPhone-simulator (Release) en draait dezelfde flows. |

## Resultaten (artifacts)

Elke run zet zijn resultaten onder **Actions → de run → Artifacts**:

- `platform-results`: testuitvoer, rooktest, schermafdrukken van de browsertest, serverlogs.
- `mobile-checks`: uitvoer van install, expo-doctor, tsc, eslint, jest (ook als JSON) en de talencheck.
- `lockfile`: de gegenereerde `package.json` en `package-lock.json` om te committen.
- `apk-ci`: de APK van de CI-run (praat met `10.0.2.2`, dus alleen voor de emulator). `apk-staging` alleen als de repository-variabele `STAGING_API_URL` is gezet.
- `android-e2e-<variant>` en `ios-e2e-<variant>`: Maestro-resultaten per flow (JUnit), schermafdrukken, `report.html`, de app-log (gecontroleerd op tokens) en de serverlog.
- `android-build-logs` en `ios-build-logs`: Gradle- of Xcode-log en de gecontroleerde instellingen.

Uitleg per workflow, hoe je de artifacts leest, wat nog met de hand moet en hoe je de repository aanmaakt: **`mobile/docs/RELEASE-VALIDATIE.md`**.
