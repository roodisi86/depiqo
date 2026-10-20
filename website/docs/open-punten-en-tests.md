# Open punten en testresultaten (oplevering 1)

## Uitgevoerde controles (18 oktober 2026)

- Productie- en previewbuild: geslaagd (17 HTML-pagina's incl. 404 en landkeuze).
- Interne links en ankers: geen gebroken links (geautomatiseerd).
- hreflang: wederkerig tussen alle paren; x-default alleen op de homepages.
- JSON-LD: alle blokken geldige JSON (Organization, WebSite, BreadcrumbList, Article). Niet gevalideerd met Google Rich Results Test.
- Unieke titles en meta descriptions (NL/BE-paren met hreflang uitgezonderd); één h1 per pagina.
- Geen oude merknamen in de output.
- Mobiel (390 px): geen horizontale scroll op alle pagina's.
- Interactie: tabs, rekentool en formuliervalidatie getest in Chromium; geen JavaScript-fouten.

## Niet uitgevoerd

- Lighthouse / Core Web Vitals: niet gemeten. Meet na livegang met PageSpeed Insights.
- Toegankelijkheidsaudit met screenreader: niet uitgevoerd. Contrast van de kleurtokens is berekend, de rest niet.
- Formulierinzending via Netlify: alleen testbaar na deploy.
- Andere browsers dan Chromium.

## Open voor livegang

1. Merkcheck "Depiqo" bij BOIP/EUIPO (klassen 9, 36, 42) en domeinen registreren (getdepiqo.com, depiqo.eu/.nl/.be).
2. E-mailadres hallo@getdepiqo.com aanmaken (staat in de foutmelding van het formulier).
3. Privacyverklaring en cookieverklaring toevoegen (formulier verwerkt persoonsgegevens).
4. Google Fonts lokaal hosten (AVG; Duitse rechtspraak over Google Fonts) en de CSP daarop aanpassen.
5. Juridische pagina's laten nakijken door de advocaat (zie claimsregister, items met "laten bevestigen").
6. Bedrijfsgegevens (KvK/KBO, adres) in de footer zodra de entiteit bestaat.
7. Analytics met toestemming (bijv. Plausible of een consent-tool) zodra je meten wilt.
8. Link "Inloggen" toevoegen zodra Depiqo Business bestaat (oplevering 2).

## V4 — tests op 19 oktober 2026

- Build productie en preview: 40 pagina's elk.
- Linkcontrole over alle pagina's: 0 kapotte links of ankers.
- SEO-controle: 1 h1 per pagina, titels tot 70 tekens en uniek, beschrijvingen 70–165 tekens, hreflang wederkerig op alle 40 pagina's.
- Chromium (Playwright): desktop 1440 px en mobiel 390 px zonder horizontale scroll; megamenu opent met Enter en sluit met Escape (focus terug op de knop); mobiel menu met uitklapgroepen; rekentool prijzen klopt met het platform (900 dossiers, 60% Depiqo, 30 nieuw: Essential € 660, Professional € 489; 150/0%/5: € 161,50 en € 314); formuliervalidatie toont foutmeldingen.
- Fotovervanging getest: een beeld in `assets/img/` vervangt de placeholder met juiste breedte en hoogte.
- Niet getest: Google Fonts laden niet in de testomgeving (systeemlettertype gebruikt), echte Netlify-inzendingen, Safari en Firefox, schermlezers, Lighthouse-scores.

## Open punten V4

- Foto's genereren of kopen en het assetregister invullen voordat de site live gaat.
- Prijsmodel is een introductietarief: valideren in pilotgesprekken.
- Inloggen verwijst naar `app.getdepiqo.com`; dat domein moet nog aan het platform gekoppeld worden.
- Engelse en Franse versie (Brussel) volgen.
