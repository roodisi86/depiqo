"""Build the Depiqo static site (V4).
  python3 src/build.py            -> dist/     (production, clean URLs, for Netlify)
  python3 src/build.py preview    -> preview/  (relative links, for the shareable preview)
"""
import os
import re
import shutil
import sys
from html import escape

sys.path.insert(0, os.path.dirname(__file__))
import audiences  # noqa: E402
import home  # noqa: E402
import pages  # noqa: E402
from articles import ARTICLES, SRC  # noqa: E402
from components import PLANS  # noqa: E402
from layout import (AUD, CHECKED, CHECKED_NL, PAGES, REGIONS, ROOT, SITE, Ctx, alternates, breadcrumb_schema,  # noqa: E402
                    faq_schema, head, mark, org_schema, page)

MODE = "preview" if len(sys.argv) > 1 and sys.argv[1] == "preview" else "prod"
OUT = os.path.join(ROOT, "preview" if MODE == "preview" else "dist")
PREVIEW = MODE == "preview"
SITEMAP = []  # (path, alternates)

if os.path.isdir(OUT):
    shutil.rmtree(OUT)

# Articles with a counterpart in the other region join the region switch.
for a in ARTICLES:
    if a.get("alt"):
        other = "be" if a["region"] == "nl" else "nl"
        PAGES["art:" + a["path"]] = {a["region"]: a["path"], other: a["alt"]}


def write(path, html):
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(html)


def fill_links(ctx, html):
    return re.sub(r"\{([a-z0-9/\-]+\.html(?:#[a-z0-9\-]+)?)\}", lambda m: ctx.link(m.group(1)), html)


def emit(path, region, title, desc, body, alts, schema=None, og_type="website"):
    ctx = Ctx(MODE, path)
    h = head(ctx, lang=REGIONS[region]["lang"], title=title, description=desc, path=path, alts=alts, schema=schema, og_type=og_type)
    write(path, page(ctx, region=region, head_html=h, body=body(ctx) if callable(body) else body, preview_flag=PREVIEW))
    SITEMAP.append((path, alts))


def crumbs_schema(region, *items):
    return breadcrumb_schema([("Depiqo", PAGES["home"][region]), *items])


for region in ("nl", "be"):
    t = REGIONS[region]
    lang = t["lang"]

    # Home
    c = home.COPY[region]
    emit(PAGES["home"][region], region, c["title"], c["desc"], lambda ctx: home.build(ctx, region), alternates("home", True),
         [org_schema(), {"@context": "https://schema.org", "@type": "WebSite", "name": "Depiqo", "url": SITE, "inLanguage": lang}, faq_schema(c["faq"])])

    # Audience pages
    for key in AUD:
        title, desc, faq = audiences.meta(region, key)
        path = AUD[key][region]["path"]
        emit(path, region, title, desc, lambda ctx, k=key: audiences.build(ctx, region, k), alternates(key),
             [crumbs_schema(region, (AUD[key][region]["label"], path)), faq_schema(faq)])

    # Product, pricing, how it works, pilot
    emit(PAGES["producten"][region], region, f"Producten voor de {t['term']}: Business, Wallet en borgrekening",
         f"Depiqo Business voor beheerders, de Depiqo Wallet voor huurders en de Depiqo-borgrekening bij een partnerbank. Met per product wat er nu werkt en wat nog komt.",
         lambda ctx: pages.producten(ctx, region), alternates("producten"), [crumbs_schema(region, ("Producten", PAGES["producten"][region]))])
    ess, pro = PLANS[0], PLANS[1]
    offers = {"@context": "https://schema.org", "@type": "Product", "name": "Depiqo Business", "brand": {"@type": "Brand", "name": "Depiqo"},
              "description": f"Software voor {t['terms']} voor vastgoedbeheerders en makelaars.",
              "offers": [{"@type": "Offer", "name": p["name"], "price": str(p["base"]), "priceCurrency": "EUR",
                          "priceSpecification": {"@type": "UnitPriceSpecification", "price": str(p["base"]), "priceCurrency": "EUR", "unitText": "maand", "valueAddedTaxIncluded": False}}
                         for p in (ess, pro)]}
    emit(PAGES["prijzen"][region], region, f"Prijzen {t['label']}: vanaf € {ess['base']} per maand, gratis voor huurders",
         f"Essential € {ess['base']} per maand met {ess['included']} dossiers, Professional € {pro['base']} met {pro['included']}. Extra dossiers goedkoper op een Depiqo-borgrekening. Huurders betalen niets.",
         lambda ctx: pages.prijzen(ctx, region), alternates("prijzen"), [crumbs_schema(region, ("Prijzen", PAGES["prijzen"][region])), offers, faq_schema(pages.PRICE_FAQ)])
    emit(PAGES["hoe"][region], region, f"Hoe Depiqo werkt: van borgverzoek tot {t['end']} | Depiqo",
         f"Stap voor stap: wie doet wat, waar staat het geld en hoe Depiqo de {t['term']} en je gegevens beschermt. Het geld gaat nooit via Depiqo.",
         lambda ctx: pages.hoe(ctx, region), alternates("hoe"), [crumbs_schema(region, ("Hoe het werkt", PAGES["hoe"][region]))])
    emit(PAGES["pilot"][region], region, f"Pilotprogramma {t['label']} voor vastgoedbeheerders | Depiqo",
         f"Test Depiqo met je eigen proces {t['where']}. Wat het prototype kan, wat we samen testen en wat afhangt van partners. Geen kosten tijdens de pilot.",
         lambda ctx: pages.pilot(ctx, region), alternates("pilot"), [crumbs_schema(region, ("Pilotprogramma", PAGES["pilot"][region]))])

    # Knowledge base index
    path = PAGES["kennisbank"][region]

    def kb_body(ctx, region=region):
        items = [a for a in ARTICLES if a["region"] == region]
        cards = "".join(
            f'<a href="{ctx.link(a["path"])}"><div class="card"><span>{"Voor huurders" if any(w in a["path"] for w in ("terugkrijgen", "herkennen", "vrijgeven")) else "Regels en beheer"}</span><h3>{escape(a["h1"])}</h3><p>{escape(a["desc"])}</p></div></a>'
            for a in items)
        return f"""
<section class="page-hero" aria-labelledby="ph-t"><div class="wrap copy">
  <nav class="crumbs" aria-label="Kruimelpad"><ol><li><a href="{ctx.link(PAGES['home'][region])}">Depiqo</a></li><li aria-current="page">Kennisbank</li></ol></nav>
  <p class="eyebrow">Kennisbank</p>
  <h1 id="ph-t">De {REGIONS[region]['term']} {'in Nederland' if region == 'nl' else 'in België'}, helder uitgelegd.</h1>
  <p class="lede">Voor huurders, verhuurders en beheerders. Elke pagina is gecontroleerd aan de hand van officiële bronnen en vermeldt de datum van die controle.</p>
</div></section>
<section class="section tone-off"><div class="wrap kb-list">{cards}</div></section>"""
    emit(path, region, f"Kennisbank {t['term']}: regels, termijnen en tips | Depiqo",
         f"Uitleg over de {t['term']} {t['where']}: maximum, terugbetaling, vrijgave en fraude herkennen. Gecontroleerd aan de hand van officiële bronnen.",
         kb_body, alternates("kennisbank"), [crumbs_schema(region, ("Kennisbank", path))])

# ------------------------------------------------------------------ articles
for a in ARTICLES:
    path, region = a["path"], a["region"]
    alt = a.get("alt")
    alts = ({"nl-NL": path if region == "nl" else alt, "nl-BE": path if region == "be" else alt} if alt else {REGIONS[region]["lang"]: path})
    crumbs = [("Depiqo", PAGES["home"][region]), ("Kennisbank", PAGES["kennisbank"][region])]
    if a.get("parent"):
        crumbs.append(a["parent"])
    crumbs.append((a["crumb"], path))

    def art_body(ctx, a=a, crumbs=crumbs, region=region):
        crumb_html = "".join(
            f'<li><a href="{ctx.link(p)}">{escape(n)}</a></li>' if i < len(crumbs) - 1 else f'<li aria-current="page">{escape(n)}</li>'
            for i, (n, p) in enumerate(crumbs))
        toc = "".join(f'<li><a href="#{sid}">{escape(h)}</a></li>' for sid, h, _ in a["sections"])
        secs = "".join(f'<h2 id="{sid}">{h}</h2>{fill_links(ctx, body)}' for sid, h, body in a["sections"])
        summary = "".join(f"<li>{s}</li>" for s in a["summary"])
        srcs = ""
        if a["sources"]:
            srcs = '<h2 id="bronnen">Bronnen</h2><ul class="sources">' + "".join(
                f'<li><a href="{SRC[k][1]}" rel="noopener" target="_blank">{escape(SRC[k][0])}</a></li>' for k in a["sources"]) + "</ul>"
        related = "".join(f'<a href="{ctx.link(p)}">{escape(t_)}<span>{escape(d)}</span></a>' for p, t_, d in a["related"])
        tenant = any(w in a["path"] for w in ("terugkrijgen", "herkennen", "vrijgeven"))
        cta_target = AUD["huurders"][region]["path"] if tenant else PAGES["home"][region] + "#demo"
        cta = (f'<div class="cta-card"><h2>{"Je borg op jouw naam, met rente" if tenant else "Beheer je " + REGIONS[region]["terms"] + " met Depiqo"}</h2>'
               f'<p>{"Zie in de Depiqo-wallet waar je geld staat en wanneer je het terugkrijgt. Gratis voor huurders." if tenant else "Voor vastgoedbeheerders en makelaars die minder tijd kwijt willen zijn aan borgdossiers. Nu in pilotfase."}</p>'
               f'<a class="btn btn-light" href="{ctx.link(cta_target)}">{"Zo werkt het voor jou" if tenant else "Plan een demo"}</a></div>')
        return f"""
<section class="page-hero" aria-labelledby="ph-t">
  <div class="wrap copy">
    <nav class="crumbs" aria-label="Kruimelpad"><ol>{crumb_html}</ol></nav>
    <h1 id="ph-t">{escape(a['h1'])}</h1>
    <p class="lede">{escape(a['lede'])}</p>
    <p class="meta"><span>Laatst inhoudelijk gecontroleerd: <time datetime="{a.get('checked', '2026-10-18')}">{a.get('checked_nl', '18 oktober 2026')}</time></span><span>Algemene informatie, geen juridisch advies</span></p>
  </div>
</section>
<div class="wrap article-layout">
  <article class="prose">
    <div class="summary-box"><h2>In het kort</h2><ul>{summary}</ul></div>
    {secs}
    {srcs}
    <h2 id="verder">Verder lezen</h2>
    <div class="related">{related}</div>
  </article>
  <aside class="aside">
    <nav class="toc" aria-label="Op deze pagina"><h2>Op deze pagina</h2><ol>{toc}</ol></nav>
    {cta}
  </aside>
</div>"""
    schema = [breadcrumb_schema(crumbs),
              {"@context": "https://schema.org", "@type": "Article", "headline": a["h1"], "description": a["desc"],
               "inLanguage": REGIONS[region]["lang"], "dateModified": "2026-10-18", "datePublished": "2026-10-18",
               "mainEntityOfPage": Ctx.canonical(path), "author": {"@type": "Organization", "name": "Depiqo"},
               "publisher": {"@type": "Organization", "name": "Depiqo", "logo": {"@type": "ImageObject", "url": SITE + "/assets/depiqo-logo.png"}}}]
    emit(path, region, a["title"], a["desc"], art_body, alts, schema, og_type="article")


# ------------------------------------------------------------------ root chooser + 404
def chooser_body(ctx):
    return f"""<section class="chooser"><div class="wrap chooser-box">
  <a class="brand" href="{ctx.link('index.html')}" aria-label="Depiqo">{mark()}depiqo</a>
  <h1>Elke huurwaarborg en waarborgsom. <span class="serif">Eén helder proces.</span></h1>
  <p class="lede">Kies je land. De regels verschillen, dus onze uitleg ook.</p>
  <div class="choices">
    <a class="choice" href="{ctx.link('nl/index.html')}" hreflang="nl-NL"><b>Nederland</b><span>De waarborgsom: maximaal 2 maanden kale huur, terug binnen 14 of 30 dagen.</span></a>
    <a class="choice" href="{ctx.link('be/index.html')}" hreflang="nl-BE"><b>België</b><span>De huurwaarborg in Vlaanderen en Brussel, op een geblokkeerde rekening op naam van de huurder.</span></a>
  </div>
  <p class="small muted">Depiqo is in ontwikkeling. Depiqo is geen bank en houdt geen geld van huurders aan.</p>
</div></section>"""


ctx = Ctx(MODE, "index.html")
alts = alternates("home", True)
root_head = head(ctx, lang="nl", title="Depiqo | Huurwaarborg en waarborgsom, digitaal geregeld",
                 description="Depiqo regelt de huurwaarborg en waarborgsom digitaal voor huurders, verhuurders en vastgoedbeheerders in Nederland en België. Kies je land.",
                 path="index.html", alts=alts, schema=[org_schema()])
write("index.html", f"""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
{root_head}</head>
<body{' data-preview="1"' if PREVIEW else ''}>
<main id="inhoud">{chooser_body(ctx)}</main>
</body>
</html>
""")
SITEMAP.append(("index.html", alts))

if PREVIEW:
    # The preview host wraps its entry page in its own document skeleton.
    write("entry.html", f"""<title>Depiqo website</title>
<meta name="description" content="Preview van de Depiqo-website V4">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@1&family=Manrope:wght@400;500;600;700;800&display=swap">
<link rel="stylesheet" href="assets/site.css">
{chooser_body(ctx)}
""")

ctx = Ctx(MODE, "404.html")
nf_head = head(ctx, lang="nl", title="Pagina niet gevonden | Depiqo", description="Deze pagina bestaat niet (meer).", path="404.html", noindex=True)
write("404.html", f"""<!doctype html>
<html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
{nf_head}</head><body><main class="chooser"><div class="wrap chooser-box">
<a class="brand" href="{ctx.link('index.html')}">{mark()}depiqo</a><h1>Deze pagina bestaat niet.</h1>
<p class="lede">Misschien is ze verplaatst. Ga naar <a href="{ctx.link('nl/index.html')}">Depiqo Nederland</a> of <a href="{ctx.link('be/index.html')}">Depiqo België</a>.</p>
</div></main></body></html>
""")

# ------------------------------------------------------------------ assets, sitemap, robots, hosting
os.makedirs(os.path.join(OUT, "assets"), exist_ok=True)
for f in os.listdir(os.path.join(ROOT, "assets")):
    src = os.path.join(ROOT, "assets", f)
    if os.path.isdir(src):
        shutil.copytree(src, os.path.join(OUT, "assets", f), dirs_exist_ok=True)
    else:
        shutil.copy(src, os.path.join(OUT, "assets", f))
for f in ("favicon.svg", "depiqo-logo-horizontaal.svg"):
    shutil.copy(os.path.join(ROOT, "brand", f), os.path.join(OUT, "assets", f))

urls = ""
for p, alts in SITEMAP:
    links = "".join(f'\n    <xhtml:link rel="alternate" hreflang="{hl}" href="{Ctx.canonical(ap)}"/>' for hl, ap in alts.items()) if len(alts) > 1 else ""
    urls += f"  <url>\n    <loc>{Ctx.canonical(p)}</loc>\n    <lastmod>{CHECKED}</lastmod>{links}\n  </url>\n"
write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n{urls}</urlset>\n')

if PREVIEW:
    write("robots.txt", "User-agent: *\nDisallow: /\n")
else:
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")
    write("_headers", """/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Strict-Transport-Security: max-age=31536000; includeSubDomains
  Content-Security-Policy: default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; script-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'
/assets/*
  Cache-Control: public, max-age=3600
""")

print(f"{MODE}: {len(SITEMAP)} pages -> {OUT}")
