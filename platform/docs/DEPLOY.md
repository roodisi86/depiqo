# Live zetten (sandbox, zonder echt geld)

Geschikt voor een pilot met testdossiers of een demo voor investeerders en beheerders.

## Optie A: Render of Railway

1. Zet deze map in een privé GitHub-repository.
2. Nieuwe "Web Service", Python. Build: `pip install -r requirements.txt`. Start: `gunicorn -w 3 -b 0.0.0.0:$PORT "run:app"`.
3. Koppel een vaste schijf (persistent disk) op `/data`.
4. Omgevingsvariabelen, zie `.env.example`:
   - `DEPIQO_ENV=staging` voor een demo of pilot met de sandbox (de app toont STAGING), of `DEPIQO_ENV=production` met echte partners. Productie draait nooit de sandbox, ook niet met `DEPIQO_SANDBOX=1`; zonder echte partner gebeurt er dan niets financieels en geeft de API 503 `partner_unavailable`
   - `SECRET_KEY` en `BANK_WEBHOOK_SECRET`: lange willekeurige waarden
   - `DATABASE_PATH=/data/depiqo.sqlite3`, `STORAGE_DIR=/data/storage`
   - `BASE_URL=https://app.getdepiqo.com` (verplicht in staging en productie, moet met https beginnen)
   - `TRUST_PROXY=1` als er precies één proxy van de host voor de app staat (Render, Railway); anders weglaten
   - `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` voor echte e-mail
   - `DEPIQO_SANDBOX=1` (alleen in staging) zolang er geen partnerbank is; met de sandbox kan een beheerder of financieel medewerker bankberichten simuleren
   - App (0.6.0): `APP_MIN_VERSION_IOS`, `APP_MIN_VERSION_ANDROID` (standaard 1.0.0), `SUPPORT_EMAIL`, `PRIVACY_URL`, `TERMS_URL`, en voor deep links `APP_IOS_TEAM_ID`, `APP_BUNDLE_ID` (standaard `com.getdepiqo.app`) en `ANDROID_SHA256_CERT`. Push: `PUSH_SEND=1` (standaard aan in productie) en eventueel `EXPO_ACCESS_TOKEN`
   - `BANK_PARTNER`: `sandbox` (alleen met `DEPIQO_SANDBOX=1`) of de naam van een echte adapter. Leeg of onbekend: geen partner, er gebeurt niets financieels
   - `REQUIRE_2FA_FOR_STAFF=1` (standaard in productie): de beheeromgeving werkt pas na twee-stapsverificatie
5. Eerste keer: maak via een eenmalige shell een Depiqo-medewerker aan (zie hieronder), log in, zet twee-stapsverificatie aan onder Beveiliging en open `/admin`.
6. Laat elke minuut `python3 run.py dispatch` draaien (cron job of scheduler van de host). Dat verstuurt bankopdrachten en opdrachten aan de beleggingspartner die niet direct na een actie verstuurd konden worden, en pushberichten naar Expo (met ontvangstbewijzen).

## Optie B: Docker

```bash
docker build -t depiqo .
docker run -p 8000:8000 -v depiqo-data:/data --env-file .env depiqo
```

## Eerste medewerker aanmaken

```bash
python3 -c "
from app import create_app, db
from app.security import hash_password
from app.util import now_iso
app = create_app()
with app.app_context():
    db.run('INSERT INTO users (email, name, password_hash, is_staff, created_at) VALUES (?, ?, ?, 1, ?)',
           ('jij@getdepiqo.com', 'Jouw Naam', hash_password('kies-een-sterk-wachtwoord'), now_iso()))
"
```

## Schalen

SQLite volstaat voor een pilot met één server. Voor meerdere servers of echt geld: PostgreSQL (zie `ARCHITECTUUR.md`) en objectopslag voor documenten.
