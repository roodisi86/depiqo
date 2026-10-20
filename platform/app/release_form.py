"""Release form ("Vrijgaveformulier") for a deposit held elsewhere.

When a deposit sits at a bank, at e-DEPO, at an insurer, with a guarantor or on the landlord's own
account, Depiqo cannot release it. The provider does, with its own procedure and form. This PDF
puts everything the provider needs on one page: the parties, the address, the references, the
agreed split and signature lines for tenant and landlord. It supports the provider's procedure;
it does not replace it.
"""
import io
from xml.sax.saxutils import escape

from . import db, providers, rules, services
from .util import date_nl, eur, format_iban, today

NAVY = (0.043, 0.078, 0.149)
TEAL = (0.031, 0.498, 0.471)
MUTED = (0.37, 0.44, 0.51)
LINE = (0.85, 0.88, 0.9)


def data_for(deposit):
    """Everything on the form, as plain values. Used by the PDF and by tests."""
    d = deposit
    org = db.one("SELECT * FROM organizations WHERE id = ?", (d["org_id"],))
    prop = db.one("SELECT * FROM properties WHERE id = ?", (d["property_id"],))
    tenant = db.one("SELECT * FROM tenants WHERE id = ?", (d["tenant_id"],))
    r = rules.for_deposit(d)
    tenant_cents, landlord_cents = services.payout_split(d)
    s = services.current_settlement(d)
    lines = services.settlement_lines(s) if s and s["status"] == "agreed" else []
    basis, basis_at = services.release_basis(d)
    return {
        "title": f"Vrijgaveformulier {r.term}",
        "term": r.term, "region": r.name, "reference": d["reference"],
        "address": f"{prop['address']}, {prop['postcode']} {prop['city']}",
        "tenant_name": tenant["name"], "tenant_email": tenant["email"],
        "landlord_name": org["name"], "landlord_registration": org["registration_number"], "landlord_email": org["billing_email"],
        "lease": date_nl(d["lease_start"]) + (f" tot {date_nl(d['lease_end'])}" if d["lease_end"] else ""),
        "move_out": date_nl(d["move_out_date"]) if d["move_out_date"] else None,
        "provider_kind": d["provider_kind"], "provider_label": providers.label(d["provider_kind"]),
        "provider_name": d["provider_name"], "provider_reference": d["provider_reference"],
        "reference_label": providers.PROVIDER_KINDS.get(d["provider_kind"], {}).get("reference_label", "Referentie"),
        "iban": format_iban(d["external_iban"]) if d["external_iban"] else None,
        "guarantee_expires_on": date_nl(d["guarantee_expires_on"]) if d["guarantee_expires_on"] else None,
        "obligation": d["amount_cents"], "to_tenant": tenant_cents, "to_landlord": landlord_cents,
        "lines": [(services.CATEGORIES.get(l["category"], l["category"]), l["description"], l["amount_cents"]) for l in lines],
        "basis": basis, "basis_at": date_nl(basis_at[:10]) if basis_at else None,
        "interest": ("komt toe aan de huurder. Alleen de aanbieder kent de opgebouwde rente en betaalt ze mee uit"
                     if d["region"] in providers.BE else
                     "volgens de afspraak in het huurcontract. Alleen de aanbieder kent de opgebouwde rente"),
        "release_note": r.release_note,
        "guarantee": d["provider_kind"] == "borggarantie",
        "made_on": date_nl(today()),
    }


def build(deposit, compress=True):
    """Returns PDF bytes. compress=False keeps the text streams readable (used in tests)."""
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors

    f = data_for(deposit)
    navy, teal, muted, line = (colors.Color(*c) for c in (NAVY, TEAL, MUTED, LINE))
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=13, textColor=navy, alignment=TA_LEFT)
    small = ParagraphStyle("small", parent=base, fontSize=8.5, leading=11.5, textColor=muted)
    label = ParagraphStyle("label", parent=base, fontSize=8.5, leading=11, textColor=muted)
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=teal, spaceBefore=4)
    bold = ParagraphStyle("bold", parent=base, fontName="Helvetica-Bold")

    def P(text, style=base):
        return Paragraph(escape(str(text)) if text is not None else "", style)

    def facts(rows, widths=(48 * mm, None)):
        data = [[P(k, label), P(v if v not in (None, "") else "Niet ingevuld", base)] for k, v in rows]
        t = Table(data, colWidths=widths, hAlign="LEFT")
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 1)]))
        return t

    width = A4[0] - 40 * mm
    story = [P(f["title"], h1), Spacer(1, 2 * mm),
             P(f"Verzoek aan de aanbieder om de {f['term']} vrij te geven volgens het akkoord hieronder. "
               f"Kenmerk {f['reference']}. Opgemaakt op {f['made_on']}.", small), Spacer(1, 3 * mm)]

    story += [P("1. Woning en huur", h2), facts([("Adres", f["address"]), ("Regio", f["region"]), ("Huurcontract", f["lease"]),
                                                  ("Vertrek huurder", f["move_out"]), ("Kenmerk Depiqo", f["reference"])])]
    landlord = f["landlord_name"] + (f", registratienummer {f['landlord_registration']}" if f["landlord_registration"] else "")
    story += [P("2. Partijen", h2), facts([("Huurder", f"{f['tenant_name']}, {f['tenant_email']}"),
                                           ("Verhuurder of beheerder", landlord + (f", {f['landlord_email']}" if f["landlord_email"] else ""))])]
    where = [("Soort", f["provider_label"]), ("Aanbieder", f["provider_name"]), (f["reference_label"], f["provider_reference"])]
    if f["iban"]:
        where.append(("Rekeningnummer", f["iban"]))
    if f["guarantee_expires_on"]:
        where.append(("Garantie geldig tot", f["guarantee_expires_on"]))
    story += [P(f"3. Waar staat de {f['term']}", h2), facts(where)]

    money = [[P("Borgbedrag volgens het huurcontract", base), P(eur(f["obligation"]), bold)]]
    for cat, desc, amount in f["lines"]:
        money.append([P(f"Inhouding: {cat}, {desc}", small), P(eur(amount), small)])
    money += [[P("Vrij te geven aan de huurder", bold), P(eur(f["to_tenant"]), bold)],
              [P("Vrij te geven aan de verhuurder", bold), P(eur(f["to_landlord"]), bold)]]
    mt = Table(money, colWidths=(width - 38 * mm, 38 * mm), hAlign="LEFT")
    mt.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LINEABOVE", (0, len(money) - 2), (-1, len(money) - 2), 0.6, line),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [P("4. Afgesproken verdeling", h2), mt, Spacer(1, 1 * mm),
              P(f"Basis: {f['basis']}" + (f", vastgelegd op {f['basis_at']}." if f["basis_at"] else "."), small),
              P(f"Rente: {f['interest']}.", small)]
    if f["guarantee"]:
        story.append(P("Bij een garantie is geen geld gestort. Het deel voor de huurder wordt niet uitbetaald: de garantie vervalt voor dat deel. "
                       "Het deel voor de verhuurder vraagt de verhuurder op bij de garantsteller, die het op de huurder kan verhalen.", small))

    def sign_block(who, name):
        rows = [[P(who, bold)], [P(f"Naam: {name}", base)], [P("Rekeningnummer voor de vrijgave:", label)], [Spacer(1, 5 * mm)],
                [P("Plaats en datum:", label)], [Spacer(1, 5 * mm)], [P("Handtekening:", label)], [Spacer(1, 13 * mm)]]
        t = Table(rows, colWidths=((width - 10 * mm) / 2,))
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, line), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                               ("LINEBELOW", (0, 3), (-1, 3), 0.4, line), ("LINEBELOW", (0, 5), (-1, 5), 0.4, line)]))
        return t

    signs = Table([[sign_block("Huurder", f["tenant_name"]), sign_block("Verhuurder of beheerder", f["landlord_name"])]],
                  colWidths=(width / 2, width / 2), hAlign="LEFT")
    signs.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 10 * mm / 2),
                               ("LEFTPADDING", (1, 0), (1, 0), 10 * mm / 2), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(KeepTogether([P("5. Handtekeningen", h2),
                               P(f"Huurder en verhuurder vragen samen de vrijgave van de {f['term']} zoals hierboven afgesproken.", base),
                               Spacer(1, 3 * mm), signs]))
    story += [Spacer(1, 4 * mm),
              P("Belangrijk: e-DEPO, de bank en de verzekeraar hebben elk een eigen procedure en een eigen formulier. Dit document "
                "ondersteunt die aanvraag, maar vervangt ze niet. Stuur het getekende formulier mee met de aanvraag bij de aanbieder.", bold),
              Spacer(1, 2 * mm),
              P(f"{f['release_note']} Depiqo houdt zelf geen geld aan en beslist niet over de verdeling. Dit is geen juridisch advies.", small)]

    buf = io.BytesIO()

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFillColorRGB(*NAVY)
        canvas.rect(0, A4[1] - 14 * mm, A4[0], 14 * mm, stroke=0, fill=1)
        canvas.setFillColorRGB(1, 1, 1)
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawString(20 * mm, A4[1] - 9.5 * mm, "depiqo")
        canvas.setFont("Helvetica", 8.5)
        canvas.drawRightString(A4[0] - 20 * mm, A4[1] - 9.5 * mm, f"Vrijgaveformulier · {f['reference']}")
        canvas.setFillColorRGB(*MUTED)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(20 * mm, 10 * mm, f"Opgemaakt door Depiqo op {f['made_on']}. Pagina {doc.page}.")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=16 * mm,
                            title=f["title"], author="Depiqo", pageCompression=1 if compress else 0)
    doc.build(story, onFirstPage=page, onLaterPages=page)
    return buf.getvalue()
