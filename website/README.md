# Depiqo — website (V4)

Statische marketingwebsite voor Depiqo, per land: Nederland (waarborgsom) en België (huurwaarborg, Vlaanderen en Brussel). V4 is licht en menselijk: warme fotografie, echte productschermen, een menu "Voor wie" met negen doelgroeppagina's, en prijzen met rekentool.

## Pagina's (per land)

- Homepage, Producten, Prijzen (met rekentool), Hoe het werkt (met veiligheid en geldstromen), Pilot, Kennisbank en 9 artikelen.
- Voor wie, particulieren en vastgoed: Huurders, Verhuurders, Makelaars (BE: Immokantoren), Vastgoedbeheerders, Woningcorporaties (BE: Institutionele verhuurders).
- Voor wie, partners: Banken, Verzekeraars, Beleggingsplatformen, Software en API.

## Formulieren (Netlify Forms)

| Formulier | Waar | Labels |
|---|---|---|
| `demo-aanvraag` | Home, beheerders, makelaars, corporaties, prijzen, pilot | `doelgroep`, `regio-site` |
| `verhuurder-aanvraag` | Verhuurders | `doelgroep`, `regio-site` |
| `partner-aanvraag` | Banken, verzekeraars, beleggingsplatformen, software | `partnertype`, `doelgroep`, `regio-site` |

Huurders krijgen geen formulier: hun pagina leidt naar het controleren van een echte uitnodiging en naar inloggen.

## Foto's

17 fotoplekken. Zolang een beeld ontbreekt, toont de site een lichte placeholder. Zet een beeld als `assets/img/<slot>.jpg` en bouw opnieuw. Stijlprompt, prompts per beeld en het assetregister staan in `docs/beeldprompts.md`.

## Prijzen

Eén bron in de code: `PLANS` in `src/components.py`. Dezelfde getallen staan in het platform (`app/billing.py`). Pas ze altijd op beide plekken aan.

## Structuur

```
src/        Python-generator (layout.py, components.py, home.py, audiences.py, pages.py, articles.py, build.py)
assets/     CSS, JS, social image, iconen
brand/      Logo's als SVG (richting A = gekozen, B en C = verkenningen)
docs/       SEO-contentplan, claimsregister, open punten en testresultaten
dist/       Productiebuild (clean URL's, voor getdepiqo.com)
preview/    Previewbuild (relatieve links, robots: noindex)
```

## Bouwen

Vereist alleen Python 3.

```
python3 src/build.py          # -> dist/
python3 src/build.py preview  # -> preview/
```

## Live zetten op Netlify

1. Maak een Netlify-site en sleep de map `dist/` naar Netlify (of koppel een repo met publish directory `dist`).
2. Koppel het domein getdepiqo.com.
3. De formulieren werken via Netlify Forms (zie hierboven). Zet per formulier een e-mailmelding aan, of koppel ze aan je CRM via een webhook.
4. Meld `https://getdepiqo.com/sitemap.xml` aan bij Google Search Console en Bing Webmaster Tools.

`_headers` zet beveiligingsheaders (CSP, HSTS, X-Frame-Options).

## Inhoud aanpassen

- Homepagecopy per land: `src/home.py`. Doelgroeppagina's: `src/audiences.py`. Producten, prijzen, hoe het werkt, pilot: `src/pages.py`.
- SEO-pagina's: `src/articles.py`. Elke juridische uitspraak hoort bij een bron in `SRC`.
- Controledatum: `CHECKED` in `src/layout.py`. Pas die alleen aan na een echte inhoudelijke controle.
- Interne links in artikeltekst schrijf je als `{nl/waarborgsom.html}`; de generator maakt er de juiste URL van.

## Talen en regio's

- `/nl/` = Nederland (nl-NL), `/be/` = België, Nederlandstalig (nl-BE).
- `hreflang` wordt alleen gezet tussen pagina's die echt equivalent zijn.
- Engels en Frans zijn voorbereid in de structuur maar nog niet gepubliceerd: juridische tekst wordt niet automatisch vertaald.
