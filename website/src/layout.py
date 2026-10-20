"""Shared layout, navigation, photography and SEO head for the Depiqo static site (V4)."""
import json
import os
from html import escape

SITE = "https://getdepiqo.com"
APP_LOGIN = "https://app.getdepiqo.com/login"
CHECKED = "2026-10-19"
CHECKED_NL = "19 oktober 2026"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, "assets", "img")

MARK = ('<svg viewBox="0 0 64 64" aria-hidden="true" focusable="false">'
        '<circle cx="30" cy="39" r="15" fill="none" stroke="{fg}" stroke-width="8"/>'
        '<path d="M49 10V54" stroke="{fg}" stroke-width="8" stroke-linecap="round" fill="none"/>'
        '<circle cx="30" cy="39" r="5.5" fill="{acc}"/></svg>')


def mark(fg="#102139", acc="#138E83"):
    return MARK.format(fg=fg, acc=acc)


class Ctx:
    """Build context: production uses clean absolute URLs, preview uses relative .html files."""

    def __init__(self, mode, path):
        self.mode = mode          # "prod" or "preview"
        self.path = path          # output path like "nl/huurders.html"

    def link(self, target):
        frag = ""
        if "#" in target:
            target, frag = target.split("#", 1)
            frag = "#" + frag
        if target.startswith("http"):
            return target + frag
        if self.mode == "prod":
            clean = "/" + target
            if clean.endswith("index.html"):
                clean = clean[: -len("index.html")]
            elif clean.endswith(".html"):
                clean = clean[:-5]
            return clean + frag
        if target == self.path and frag:
            return frag
        depth = self.path.count("/")
        return "../" * depth + target + frag

    def asset(self, name):
        if self.mode == "prod":
            return "/assets/" + name
        return "../" * self.path.count("/") + "assets/" + name

    @staticmethod
    def canonical(path):
        clean = "/" + path
        if clean.endswith("index.html"):
            clean = clean[: -len("index.html")]
        elif clean.endswith(".html"):
            clean = clean[:-5]
        return SITE + clean


REGIONS = {
    "nl": {"lang": "nl-NL", "label": "Nederland", "short": "NL", "term": "waarborgsom", "terms": "waarborgsommen",
           "Term": "Waarborgsom", "where": "in Nederland", "end": "terugbetaling"},
    "be": {"lang": "nl-BE", "label": "België", "short": "BE", "term": "huurwaarborg", "terms": "huurwaarborgen",
           "Term": "Huurwaarborg", "where": "in Vlaanderen en Brussel", "end": "vrijgave"},
}

# Audience pages: key -> per-region slug, label and one-line description for the menu.
AUDIENCES = [
    # (key, group, {region: (slug, label, menu line)})
    ("huurders", "people", {"nl": ("huurders", "Huurders", "Zie waar je borg staat en wanneer je hem terugkrijgt"),
                            "be": ("huurders", "Huurders", "Zie waar je waarborg staat en wanneer hij vrijkomt")}),
    ("verhuurders", "people", {"nl": ("verhuurders", "Verhuurders", "Zekerheid en een onderbouwde afrekening"),
                               "be": ("verhuurders", "Verhuurders", "Zekerheid en een vlotte vrijgave")}),
    ("makelaars", "people", {"nl": ("makelaars", "Makelaars", "Borgverzoeken en opvolging zonder nabellen"),
                             "be": ("immokantoren", "Immokantoren", "Waarborgaanvragen en opvolging zonder papier")}),
    ("beheerders", "people", {"nl": ("vastgoedbeheerders", "Vastgoedbeheerders", "Alle borgdossiers in één platform"),
                              "be": ("vastgoedbeheerders", "Vastgoedbeheerders", "Alle waarborgdossiers in één platform")}),
    ("institutioneel", "people", {"nl": ("woningcorporaties", "Woningcorporaties", "Transparantie en audittrail op schaal"),
                                  "be": ("institutionele-verhuurders", "Institutionele verhuurders", "Grote portefeuilles, één werkwijze")}),
    ("banken", "partners", {"nl": ("banken", "Banken", "Depositoproducten en rekeningintegraties"),
                            "be": ("banken", "Banken", "Depositoproducten en rekeningintegraties")}),
    ("verzekeraars", "partners", {"nl": ("verzekeraars", "Verzekeraars", "Garantieproducten en risicopartnerships"),
                                  "be": ("verzekeraars", "Verzekeraars", "Garantieproducten en risicopartnerships")}),
    ("beleggen", "partners", {"nl": ("beleggingsplatformen", "Beleggingsplatformen", "Vrijwillig beleggen, apart van de borg"),
                              "be": ("beleggingsplatformen", "Beleggingsplatformen", "Vrijwillig beleggen, apart van de waarborg")}),
    ("software", "partners", {"nl": ("softwarepartners", "Software en API", "Integraties en white-label voor beheersoftware"),
                              "be": ("softwarepartners", "Software en API", "Integraties en white-label voor beheersoftware")}),
]
AUD = {key: {"group": group, **{r: {"slug": v[0], "label": v[1], "line": v[2], "path": f"{r}/{v[0]}.html"} for r, v in regs.items()}}
       for key, group, regs in AUDIENCES}

# Every page type and its path per region, used for the language/region switch and hreflang.
PAGES = {
    "home": {"nl": "nl/index.html", "be": "be/index.html"},
    "producten": {"nl": "nl/producten.html", "be": "be/producten.html"},
    "prijzen": {"nl": "nl/prijzen.html", "be": "be/prijzen.html"},
    "hoe": {"nl": "nl/hoe-het-werkt.html", "be": "be/hoe-het-werkt.html"},
    "kennisbank": {"nl": "nl/kennisbank.html", "be": "be/kennisbank.html"},
    "pilot": {"nl": "nl/pilot.html", "be": "be/pilot.html"},
    **{k: {r: v[r]["path"] for r in ("nl", "be")} for k, v in AUD.items()},
}


def counterpart(path, region):
    other = "be" if region == "nl" else "nl"
    for paths in PAGES.values():
        if paths.get(region) == path:
            return paths[other]
    return f"{other}/index.html"


def alternates(key, default=False):
    alts = {"nl-NL": PAGES[key]["nl"], "nl-BE": PAGES[key]["be"]}
    if default:
        alts["x-default"] = "index.html"
    return alts


# ---------------------------------------------------------------- photography

def _image_file(slot):
    for ext in ("webp", "avif", "jpg", "jpeg", "png"):
        p = os.path.join(IMG_DIR, f"{slot}.{ext}")
        if os.path.exists(p):
            return p
    return None


def photo(ctx, slot, alt, ratio="r-43", tone="", cls="", eager=False, preview_label=True):
    """A real photo when assets/img/<slot>.* exists, otherwise a light placeholder with the slot name.
    Briefings and AI prompts for every slot are in docs/beeldprompts.md."""
    path = _image_file(slot)
    if path:
        w, h = 1600, 1200
        try:
            from PIL import Image
            with Image.open(path) as im:
                w, h = im.size
        except Exception:
            pass
        loading = 'fetchpriority="high"' if eager else 'loading="lazy" decoding="async"'
        name = os.path.basename(path)
        return (f'<div class="photo {ratio} {cls}"><img src="{ctx.asset("img/" + name)}" alt="{escape(alt)}" '
                f'width="{w}" height="{h}" {loading}></div>')
    label = ""
    if preview_label and ctx.mode == "preview":
        label = f'<span class="ph-label"><b>Foto volgt</b> · {escape(slot)}</span>'
    return f'<div class="photo ph {tone} {ratio} {cls}" role="img" aria-label="{escape(alt)}">{label}</div>'


# ---------------------------------------------------------------- head

def head(ctx, *, lang, title, description, path, alts=None, schema=None, noindex=False, og_type="website"):
    canon = Ctx.canonical(path)
    alt = ""
    for hl, p in (alts or {}).items():
        alt += f'<link rel="alternate" hreflang="{hl}" href="{Ctx.canonical(p)}">\n'
    robots = '<meta name="robots" content="noindex, follow">\n' if noindex else ""
    ld = ""
    for s in (schema or []):
        ld += '<script type="application/ld+json">' + json.dumps(s, ensure_ascii=False) + "</script>\n"
    og_img = SITE + "/assets/og-depiqo.png"
    return f"""<title>{escape(title)}</title>
<meta name="description" content="{escape(description)}">
{robots}<link rel="canonical" href="{canon}">
{alt}<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="Depiqo">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(description)}">
<meta property="og:url" content="{canon}">
<meta property="og:image" content="{og_img}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:locale" content="{lang.replace('-', '_')}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{escape(title)}">
<meta name="twitter:description" content="{escape(description)}">
<meta name="twitter:image" content="{og_img}">
<meta name="theme-color" content="#FAFAF7">
<link rel="icon" href="{ctx.asset('favicon.svg')}" type="image/svg+xml">
<link rel="apple-touch-icon" href="{ctx.asset('apple-touch-icon.png')}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@1&family=Manrope:wght@400;500;600;700;800&display=swap">
<link rel="stylesheet" href="{ctx.asset('site.css')}">
{ld}"""


def org_schema():
    return {"@context": "https://schema.org", "@type": "Organization", "name": "Depiqo",
            "url": SITE, "logo": SITE + "/assets/depiqo-logo.png",
            "description": "Platform voor digitale huurwaarborgen en waarborgsommen in Nederland en België. In ontwikkeling."}


def breadcrumb_schema(items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": Ctx.canonical(p)}
                                for i, (n, p) in enumerate(items)]}


def faq_schema(qas):
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qas]}


# ---------------------------------------------------------------- header and footer

def _cur(ctx, path):
    return ' aria-current="page"' if ctx.path == path else ""


def header(ctx, region):
    r = region
    L = ctx.link
    home = PAGES["home"][r]
    people = [AUD[k][r] for k in ("huurders", "verhuurders", "makelaars", "beheerders", "institutioneel")]
    partners = [AUD[k][r] for k in ("banken", "verzekeraars", "beleggen", "software")]

    def items(lst):
        return "".join(f'<a class="mega-item" href="{L(a["path"])}"{_cur(ctx, a["path"])}><b>{a["label"]}</b><span>{a["line"]}</span></a>' for a in lst)

    def mob(lst):
        return "".join(f'<a href="{L(a["path"])}">{a["label"]}</a>' for a in lst)

    top = [("Producten", PAGES["producten"][r]), ("Prijzen", PAGES["prijzen"][r]),
           ("Hoe het werkt", PAGES["hoe"][r]), ("Kennisbank", PAGES["kennisbank"][r])]
    li = (f'<li><a href="{L(top[0][1])}"{_cur(ctx, top[0][1])}>Producten</a></li>'
          f'<li><details class="mega" data-mega><summary>Voor wie</summary><div class="mega-panel">'
          f'<div class="mega-group"><h2>Particulieren en vastgoed</h2>{items(people)}</div>'
          f'<div class="mega-group"><h2>Financiële en technologiepartners</h2>{items(partners)}</div>'
          f'<div class="mega-foot"><span>Niet zeker waar je begint?</span><a class="link-arrow" href="{L(PAGES["hoe"][r])}">Bekijk hoe Depiqo werkt</a></div>'
          f'</div></details></li>'
          + "".join(f'<li><a href="{L(p)}"{_cur(ctx, p)}>{n}</a></li>' for n, p in top[1:]))
    other = counterpart(ctx.path, r)
    nl_href = L(ctx.path if r == "nl" else other)
    be_href = L(ctx.path if r == "be" else other)
    region_sw = (f'<span class="region" role="group" aria-label="Kies land"><a href="{nl_href}" hreflang="nl-NL" aria-current="{"true" if r == "nl" else "false"}" lang="nl-NL">NL</a>'
                 f'<a href="{be_href}" hreflang="nl-BE" aria-current="{"true" if r == "be" else "false"}" lang="nl-BE">BE</a></span>')
    demo = L(home + "#demo")
    return f"""<a class="skip" href="#inhoud">Naar de inhoud</a>
<header class="site-header" data-header>
  <div class="wrap nav">
    <a class="brand" href="{L(home)}" aria-label="Depiqo, naar de homepage">{mark()}depiqo</a>
    <nav aria-label="Hoofdmenu"><ul class="nav-main">{li}</ul></nav>
    <div class="nav-actions">{region_sw}<a class="nav-login" href="{APP_LOGIN}">Inloggen</a><a class="btn btn-primary btn-s" href="{demo}">Plan een demo</a></div>
    <details class="menu"><summary>Menu</summary>
      <nav class="menu-panel" aria-label="Mobiel menu">
        <a href="{L(top[0][1])}">Producten</a>
        <details class="menu-group"><summary>Voor particulieren en vastgoed</summary><div>{mob(people)}</div></details>
        <details class="menu-group"><summary>Voor financiële en technologiepartners</summary><div>{mob(partners)}</div></details>
        {"".join(f'<a href="{L(p)}">{n}</a>' for n, p in top[1:])}
        <a href="{APP_LOGIN}">Inloggen</a>
        {region_sw}
        <a class="btn btn-primary" href="{demo}">Plan een demo</a>
      </nav>
    </details>
  </div>
</header>"""


def footer(ctx, region):
    r = region
    L = ctx.link
    t = REGIONS[r]
    home = PAGES["home"][r]
    if r == "nl":
        kb = [("Waarborgsom: de regels", "nl/waarborgsom.html"), ("Waarborgsom terugkrijgen", "nl/waarborgsom-terugkrijgen.html"),
              ("Waarborgsom voor verhuurders", "nl/waarborgsom-voor-verhuurders.html")]
    else:
        kb = [("Huurwaarborg in België", "be/huurwaarborg.html"), ("Huurwaarborg Vlaanderen", "be/huurwaarborg-vlaanderen.html"),
              ("Huurwaarborg Brussel", "be/huurwaarborg-brussel.html")]
    people = "".join(f'<li><a href="{L(AUD[k][r]["path"])}">{AUD[k][r]["label"]}</a></li>' for k in ("huurders", "verhuurders", "makelaars", "beheerders", "institutioneel"))
    partners = "".join(f'<li><a href="{L(AUD[k][r]["path"])}">{AUD[k][r]["label"]}</a></li>' for k in ("banken", "verzekeraars", "beleggen", "software"))
    kb_li = "".join(f'<li><a href="{L(p)}">{n}</a></li>' for n, p in kb)
    return f"""<footer class="site-footer">
  <div class="wrap foot-grid">
    <div class="stack">
      <a class="brand" href="{L(home)}" aria-label="Depiqo, naar de homepage">{mark('#FFFFFF', '#7FDCCF')}depiqo</a>
      <p>Het platform voor de {t['term']}: van borgverzoek tot {t['end']}, voor huurders, verhuurders en vastgoedbeheerders {t['where']}.</p>
      <h2>Productstatus</h2>
      <ul class="status-list">
        <li><b>Depiqo Business en Wallet</b><span class="badge b-live">Prototype</span></li>
        <li><b>Borgrekening met rente</b><span class="badge b-launch">Met partnerbank</span></li>
        <li><b>Depiqo Invest</b><span class="badge b-launch">Testversie</span></li>
      </ul>
    </div>
    <div><h2>Product</h2><ul>
      <li><a href="{L(PAGES['producten'][r])}">Producten</a></li>
      <li><a href="{L(PAGES['prijzen'][r])}">Prijzen</a></li>
      <li><a href="{L(PAGES['hoe'][r])}">Hoe het werkt</a></li>
      <li><a href="{L(PAGES['hoe'][r] + '#veiligheid')}">Veiligheid en geldstromen</a></li>
      <li><a href="{L(PAGES['pilot'][r])}">Pilotprogramma</a></li>
      <li><a href="{APP_LOGIN}">Inloggen</a></li>
    </ul></div>
    <div><h2>Voor wie</h2><ul>{people}</ul></div>
    <div><h2>Partners</h2><ul>{partners}</ul></div>
    <div><h2>Kennisbank</h2><ul>{kb_li}<li><a href="{L(r + '/echt-borgverzoek-herkennen.html')}">Een echt borgverzoek herkennen</a></li><li><a href="{L(PAGES['kennisbank'][r])}">Alle artikelen</a></li>
      <li><a href="{L(PAGES['home']['be' if r == 'nl' else 'nl'])}" hreflang="{'nl-BE' if r == 'nl' else 'nl-NL'}">{'Depiqo in België' if r == 'nl' else 'Depiqo in Nederland'}</a></li></ul></div>
  </div>
  <div class="wrap"><div class="foot-legal">
    <p>Depiqo is een platform in ontwikkeling. Depiqo is geen bank en houdt geen geld van huurders aan. Rekeningen, betalingen en rente lopen via een gereguleerde financiële partner; die partner is nog niet gekozen. Beleggen via Depiqo Invest gebeurt alleen via een vergunde beleggingspartner; Depiqo geeft geen beleggingsadvies. Depiqo Invest werkt nu in een testomgeving.</p>
    <p>De informatie op deze website is algemeen van aard en geen juridisch of financieel advies. Gecontroleerd op {CHECKED_NL}. Contact: <a href="mailto:hallo@getdepiqo.com">hallo@getdepiqo.com</a>. &copy; 2026 Depiqo (werknaam).</p>
  </div></div>
</footer>"""


def page(ctx, *, region, head_html, body, preview_flag):
    lang = REGIONS[region]["lang"]
    flag = ' data-preview="1"' if preview_flag else ""
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
{head_html}</head>
<body{flag}>
{header(ctx, region)}
<main id="inhoud">
{body}
</main>
{footer(ctx, region)}
<script src="{ctx.asset('site.js')}" defer></script>
</body>
</html>
"""
