"""RFQ package PDF renderer (Lane B).

render(fields_json, views_root=".") -> PDF bytes.

Port of samples/src/rfq.py with every hardcoded string replaced by values from
fields.json, plus the Slot + stamp logic from samples/src/rfq_chair.py:
reportlab lays out the pages and reserves empty boxes (Slots) for the views,
then pymupdf stamps each view PDF (vector) into its box.

Pages: 1 RFQ cover, 2 spec sheet + views, 3 requirements, 4 supplier quote form,
5 internal provenance page (options.include_internal_page, default true).

Field lookup is forgiving: a missing field prints "Not specified" (or is skipped)
instead of crashing, so a half-filled job still renders.
"""
from __future__ import annotations

import datetime as dt
import io
import os
from xml.sax.saxutils import escape

import pymupdf
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

INK = colors.HexColor("#1b2430")
MUTED = colors.HexColor("#5b6675")
RULE = colors.HexColor("#c9d1db")
BAND = colors.HexColor("#eef2f6")
ACCENT = colors.HexColor("#1f4e79")
SRC_COLORS = {"CAD": "#1f6f43", "ENG": "#8a5a00", "AI": "#5b3fa0"}
SEV_COLORS = {"error": "#a33a2a", "warn": "#b06f00", "info": "#1f4e79"}

ss = getSampleStyleSheet()
body = ParagraphStyle("body", parent=ss["Normal"], fontName="Helvetica", fontSize=9, leading=12.5, textColor=INK)
small = ParagraphStyle("small", parent=body, fontSize=7.5, leading=10, textColor=MUTED)
cell = ParagraphStyle("cell", parent=body, fontSize=8.2, leading=10.5)
cellb = ParagraphStyle("cellb", parent=cell, fontName="Helvetica-Bold")
h1 = ParagraphStyle("h1", parent=body, fontName="Helvetica-Bold", fontSize=17, leading=21, spaceAfter=2)
h2 = ParagraphStyle("h2", parent=body, fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=ACCENT,
                    spaceBefore=10, spaceAfter=5)
kicker = ParagraphStyle("kicker", parent=body, fontName="Helvetica-Bold", fontSize=7.5, textColor=MUTED, leading=10)
sub = ParagraphStyle("sub", parent=body, textColor=MUTED, fontSize=10)

NA = "Not specified"


# ---------------------------------------------------------------- helpers
def esc(v) -> str:
    return escape(str(v))


def P(t, s=cell):
    return Paragraph(t, s)


def fmt_date(s):
    if not s:
        return NA
    try:
        return dt.date.fromisoformat(str(s)[:10]).strftime("%d %b %Y")
    except ValueError:
        return str(s)


def fmt_value(v) -> str:
    """Any field value -> escaped display text."""
    if v is None or v == "" or v == []:
        return NA
    if isinstance(v, dict):
        if {"x", "y", "z"} <= v.keys():
            return f"{float(v['x']):.1f} x {float(v['y']):.1f} x {float(v['z']):.1f} mm"
        if "company" in v:
            return esc(", ".join(str(v[k]) for k in ("company", "contact", "email") if v.get(k)))
        return esc(", ".join(f"{k}: {x}" for k, x in v.items() if x not in (None, "")))
    if isinstance(v, list):
        if v and isinstance(v[0], dict) and "feature" in v[0]:
            return "<br/>".join(esc(f"{d.get('feature')}: {d.get('value')} {d.get('unit') or ''}".strip()) for d in v)
        return esc(", ".join(str(x) for x in v))
    return esc(v)


def grid(data, widths, header=True):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
          ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), ACCENT)]
    t.setStyle(TableStyle(st))
    return t


def hdr(*cols):
    return [Paragraph(f'<font color="white"><b>{c}</b></font>', cell) for c in cols]


class Fields:
    """Read access to fields.json with source tags."""

    def __init__(self, data: dict):
        self.f = data.get("fields") or {}
        self.show_tags = (data.get("options") or {}).get("show_tags", True)

    def raw(self, key, default=None):
        e = self.f.get(key)
        if not e:
            return default
        v = e.get("value")
        return default if v in (None, "", []) else v

    def src(self, key):
        return (self.f.get(key) or {}).get("source")

    def tag(self, key_or_kind):
        kind = key_or_kind if key_or_kind in SRC_COLORS else self.src(key_or_kind)
        if not self.show_tags or kind not in SRC_COLORS:
            return ""
        return f'<font name="Helvetica-Bold" size="6.5" color="{SRC_COLORS[kind]}">[{kind}]</font> '

    def text(self, key, default=NA):
        v = self.raw(key)
        return default if v is None else fmt_value(v)

    def tagged(self, key, default=NA):
        return self.tag(key) + self.text(key, default)


class Slot(Flowable):
    """Empty box whose page position is recorded, so a vector view can be stamped in afterwards."""

    def __init__(self, registry, name, w, h, caption):
        super().__init__()
        self.registry, self.name, self.width, self.height, self.caption = registry, name, w, h, caption

    def wrap(self, *a):
        return self.width, self.height

    def draw(self):
        c = self.canv
        x, y = c.absolutePosition(0, 0)
        self.registry[self.name] = (c.getPageNumber(), x, y, self.width, self.height)
        c.setStrokeColor(RULE); c.setLineWidth(0.5); c.rect(0, 0, self.width, self.height)
        c.setFont("Helvetica-Bold", 7.5); c.setFillColor(MUTED); c.drawString(5, 5, self.caption)


def bullets(items):
    out = []
    for i in items:
        out.append(P(f"•&nbsp;&nbsp;{i}", body)); out.append(Spacer(1, 2))
    return out


def as_lines(v):
    """AI text may be a string (possibly multi-line) or a list; return a list of escaped lines."""
    if v is None:
        return []
    if isinstance(v, list):
        return [esc(x) for x in v if str(x).strip()]
    lines = [ln.strip(" -•\t") for ln in str(v).splitlines() if ln.strip()]
    return [esc(x) for x in lines]


def block(F, key, default=NA):
    """A tagged paragraph, or tagged bullets if the value has several lines/items."""
    lines = as_lines(F.raw(key))
    if not lines:
        return [P(F.tag(key) + default, body)]
    if len(lines) == 1:
        return [P(F.tag(key) + lines[0], body)]
    return [P(F.tag(key), body)] + bullets(lines)


# ---------------------------------------------------------------- main
def render(fields_json: dict, views_root: str = ".") -> bytes:
    F = Fields(fields_json)
    opts = fields_json.get("options") or {}
    buyer = F.raw("buyer", {}) or {}
    country = (buyer.get("country") or "US").upper()
    page_size = (opts.get("page_size") or ("letter" if country in ("US", "CA", "MX") else "a4")).lower()
    PAGE = A4 if page_size == "a4" else letter
    include_internal = opts.get("include_internal_page", True)

    part_no = F.raw("part_number", "PART")
    rev = F.raw("revision", "")
    part_name = F.raw("part_name", "Part")
    job_id = str(fields_json.get("job_id") or "")
    rfq_no = F.raw("rfq_number") or f"RFQ-{dt.date.today():%Y}-{(job_id.replace('-', '')[:6] or '0001').upper()}"
    issue = F.raw("issue_date") or dt.date.today().isoformat()
    company = buyer.get("company") or "Buyer"
    email = buyer.get("email") or ""
    qtys = F.raw("qty_breaks", []) or []
    material = F.raw("material")
    finish = F.raw("finish")
    quote_due = fmt_date(F.raw("quote_due"))
    part_label = f"{part_no} Rev {rev}" if rev else part_no

    def chrome(c, doc):
        w, h = PAGE
        c.saveState()
        c.setFillColor(ACCENT); c.rect(0, h - 6, w, 6, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 8); c.setFillColor(INK)
        c.drawString(0.7 * inch, h - 0.45 * inch, company.upper())
        c.setFont("Helvetica", 8); c.setFillColor(MUTED)
        c.drawRightString(w - 0.7 * inch, h - 0.45 * inch, f"{rfq_no}  ·  {part_label}")
        c.setStrokeColor(RULE); c.setLineWidth(0.5)
        c.line(0.7 * inch, h - 0.53 * inch, w - 0.7 * inch, h - 0.53 * inch)
        c.line(0.7 * inch, 0.6 * inch, w - 0.7 * inch, 0.6 * inch)
        c.setFont("Helvetica", 7)
        c.drawString(0.7 * inch, 0.42 * inch, f"Confidential: property of {company}, for quotation purposes only")
        c.drawRightString(w - 0.7 * inch, 0.42 * inch, f"Page {doc.page}")
        c.restoreState()

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=PAGE, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                          topMargin=0.75 * inch, bottomMargin=0.8 * inch,
                          title=f"RFQ Package - {part_no} {part_name}", author=company)
    fw = PAGE[0] - 1.4 * inch
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(doc.leftMargin, doc.bottomMargin, fw, doc.height, id="f",
                                                             leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
                                       onPage=chrome)])
    slots: dict = {}
    s = []

    # ---------------- page 1: RFQ cover
    s.append(P("REQUEST FOR QUOTATION", kicker))
    s.append(P(esc(f"{part_name}, {part_label}"), h1))
    subtitle = " · ".join(esc(x) for x in (material, finish) if x)
    if qtys:
        subtitle += (" · " if subtitle else "") + f"{len(qtys)} quantity break{'s' if len(qtys) != 1 else ''}"
    s.append(P(subtitle or "&nbsp;", sub))
    s.append(Spacer(1, 10))
    contact = "<br/>".join(esc(x) for x in (buyer.get("contact"), email) if x) or NA
    meta = [
        [P("<b>RFQ number</b>"), P(esc(rfq_no)), P("<b>Issue date</b>"), P(fmt_date(issue))],
        [P("<b>Buyer</b>"), P(esc(company)), P("<b>Quote due</b>"), P(f"<b>{quote_due}</b>")],
        [P("<b>Contact</b>"), P(contact), P("<b>Validity</b>"), P("Quote valid 60 days")],
        [P("<b>Incoterms</b>"), P(F.text("incoterms", "Supplier to state")), P("<b>Payment</b>"), P(F.text("payment_terms", "Net 30"))],
    ]
    t = Table(meta, colWidths=[70, 200, 70, fw - 340])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BAND), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.white),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    s.append(t)

    s.append(P("Line items", h2))
    rows = [hdr("Line", "Part no.", "Description", "Material / finish", "Qty", "Target delivery")]
    mf = " / ".join(esc(x) for x in (material, finish) if x) or NA
    for i, q in enumerate(qtys or [None]):
        rows.append([P(str(i + 1)), P(esc(part_label)), P(esc(part_name)), P(mf),
                     P(f"<b>{esc(q)}</b>" if q is not None else "TBD"), P(fmt_date(F.raw("target_delivery")))])
    s.append(grid(rows, [30, 80, 125, 135, 40, fw - 410]))

    s.append(P("Scope of work", h2))
    s += block(F, "scope_of_work")

    s.append(P("Package contents", h2))
    src_name = (F.raw("source_filename") or f"{part_no}.step")
    pk = [hdr("Doc", "Title", "Format")]
    contents = [("A", "RFQ cover (this page)", "PDF, p.1"), ("B", "Part specification sheet and drawing views", "PDF, p.2"),
                ("C", "Quality, finish and packaging requirements", "PDF, p.3"),
                ("D", "Supplier quote response form", "PDF, p.4"),
                ("E", f"3D model, {src_name}", "STEP (attached separately)")]
    if include_internal:
        contents.append(("F", "Data provenance and open items (internal)", "PDF, p.5"))
    for a, b, c_ in contents:
        pk.append([P(a), P(esc(b)), P(c_)])
    s.append(grid(pk, [34, 300, fw - 334]))

    s.append(P("How to respond", h2))
    s.append(P(f"Complete the quote response form (Doc D) and return it with any exceptions to "
               f"{esc(email) or 'the buyer contact above'} by {quote_due}. If a requirement drives cost, say so and "
               "offer an alternative. We review price, lead time, quality record and responsiveness, not price alone.", body))
    if F.show_tags:
        s.append(Spacer(1, 10))
        s.append(P(f"Field sources: {F.tag('CAD')}from STEP geometry · {F.tag('ENG')}entered by the engineer · "
                   f"{F.tag('AI')}drafted by AI, reviewed by engineer. Set options.show_tags=false for the supplier copy.", small))
    s.append(PageBreak())

    # ---------------- page 2: spec sheet + views
    s.append(P("DOC B", kicker))
    s.append(P("Part Specification Sheet", h1))
    s.append(Spacer(1, 4))
    vw, vh = (fw - 8) / 2, 150
    names = {"front": "FRONT", "top": "TOP", "right": "RIGHT", "iso": "ISOMETRIC"}
    vt = Table([[Slot(slots, "front", vw, vh, names["front"]), Slot(slots, "top", vw, vh, names["top"])],
                [Slot(slots, "right", vw, vh, names["right"]), Slot(slots, "iso", vw, vh, names["iso"])]],
               colWidths=[vw + 4] * 2, rowHeights=[vh + 6] * 2)
    vt.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    s.append(vt)
    s.append(P("Views generated from STEP geometry, not to scale. The 3D model governs geometry; "
               "requirements below govern tolerances and finish.", small))
    s.append(Spacer(1, 6))
    vol = F.raw("volume_mm3")
    area = F.raw("surface_area_mm2")
    spec = [
        ("Part", f"{esc(part_name)}, {esc(part_label)}", "part_number"),
        ("Overall envelope", F.text("bbox_mm"), "bbox_mm"),
        ("Volume", f"{float(vol) / 1000:.1f} cm³" if vol else NA, "volume_mm3"),
        ("Surface area", f"{float(area) / 100:.1f} cm²" if area else NA, "surface_area_mm2"),
        ("Material", F.text("material"), "material"),
        ("Finish", F.text("finish"), "finish"),
        ("General tolerance", F.text("general_tolerance"), "general_tolerance"),
        ("Critical dimensions", F.text("critical_dims", "None specified"), "critical_dims"),
        ("Likely process", "<br/>".join(as_lines(F.raw("process_notes"))) or NA, "process_notes"),
    ]
    sp = [hdr("Attribute", "Value", "Source")]
    for a, v, key in spec:
        sp.append([P(f"<b>{a}</b>"), P(v), P(F.tag(key))])
    s.append(grid(sp, [110, fw - 150, 40]))
    s.append(PageBreak())

    # ---------------- page 3: requirements
    s.append(P("DOC C", kicker))
    s.append(P("Quality, Finish and Packaging Requirements", h1))
    crit = F.raw("critical_dims", []) or []
    if crit:
        s.append(P("Critical-to-function characteristics", h2))
        ctf = [hdr("#", "Characteristic", "Requirement", "Unit")]
        for i, d in enumerate(crit, 1):
            ctf.append([P(str(i)), P(esc(d.get("feature", ""))), P(esc(d.get("value", ""))), P(esc(d.get("unit") or ""))])
        s.append(grid(ctf, [20, 170, 170, fw - 360]))
    s.append(P("Inspection", h2))
    s += block(F, "inspection_requirements", "Supplier to state standard inspection.")
    certs = F.raw("certs", []) or []
    s.append(P("Quality documentation", h2))
    if certs:
        s.append(P(F.tag("certs") + "Ship the following with each lot:", body))
        s += bullets([esc(c) for c in certs])
    else:
        s.append(P("None specified. Supplier to state standard documentation.", body))
    s.append(P("Process and finish", h2))
    s += block(F, "process_notes")
    if finish:
        s.append(P(F.tag("finish") + f"Finish: {esc(finish)}. Finish after all machining unless noted.", body))
    s.append(P("Workmanship", h2))
    s += bullets(["Break all sharp edges unless noted. No burrs in holes or threads.",
                  f"General tolerance {F.text('general_tolerance')} unless a tighter tolerance is stated.",
                  "Non-conforming parts are not to be shipped without written deviation approval from the buyer."])
    s.append(P("Packaging and delivery", h2))
    s += block(F, "packaging")
    s.append(P(f"Target delivery: {fmt_date(F.raw('target_delivery'))}. Label each box with part number, revision, "
               "quantity and PO number.", body))
    notes = F.raw("notes")
    if notes:
        s.append(P("Engineer notes", h2))
        s += block(F, "notes")
    s.append(P("Commercial terms", h2))
    s.append(P(f"Drawings, models and this RFQ are confidential and remain the property of {esc(company)}. "
               "They may be shared with sub-tier processors only as needed to quote or produce the part. "
               "Changes to material, process or sub-tier suppliers after award require written notice.", body))
    s.append(PageBreak())

    # ---------------- page 4: quote response form
    s.append(P("DOC D", kicker))
    s.append(P("Supplier Quote Response Form", h1))
    s.append(P(f"Return by {quote_due}.", ParagraphStyle("sub2", parent=body, textColor=MUTED)))
    s.append(Spacer(1, 8))
    sup = [[P("<b>Supplier name</b>"), P(""), P("<b>Quote ref.</b>"), P("")],
           [P("<b>Contact / email</b>"), P(""), P("<b>Date</b>"), P("")],
           [P("<b>Certifications</b>"), P("[  ] ISO 9001   [  ] AS9100   [  ] Other: ________"), P(""), P("")]]
    t = Table(sup, colWidths=[90, 220, 60, fw - 370], rowHeights=[22, 22, 22])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, RULE), ("SPAN", (1, 2), (3, 2)),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("BACKGROUND", (0, 0), (0, -1), BAND), ("BACKGROUND", (2, 0), (2, 1), BAND)]))
    s.append(t)
    s.append(P("Pricing", h2))
    pr = [hdr("Line", "Qty", "Unit price", "Extended", "Lead time (days ARO)", "Notes")]
    for i, q in enumerate(qtys or [""]):
        pr.append([P(str(i + 1)), P(esc(q)), P(""), P(""), P(""), P("")])
    pr.append([P("NRE"), P("1"), P(""), P(""), P(""), P("Programming, fixtures, gauges")])
    t = Table(pr, colWidths=[36, 40, 80, 80, 110, fw - 346], rowHeights=[None] + [24] * (len(pr) - 1))
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, RULE), ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    s.append(t)
    qs = as_lines(F.raw("quote_form_questions"))
    if qs:
        s.append(P(F.tag("quote_form_questions") + "Questions for the supplier", h2))
        qt = Table([[P(f"<b>{q}</b>"), P("")] for q in qs], colWidths=[200, fw - 200])
        qt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, RULE), ("BACKGROUND", (0, 0), (0, -1), BAND),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 7),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
        s.append(qt)
    s.append(P("Exceptions, DFM suggestions and cost drivers", h2))
    t = Table([[P("")]], colWidths=[fw], rowHeights=[70])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, RULE)]))
    s.append(t)
    s.append(Spacer(1, 14))
    sig = Table([[P("Authorized signature"), P("Name and title"), P("Date")], [P(""), P(""), P("")]],
                colWidths=[fw * 0.45, fw * 0.35, fw * 0.2], rowHeights=[14, 26])
    sig.setStyle(TableStyle([("LINEBELOW", (0, 1), (-1, 1), 0.6, INK), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED)]))
    s.append(sig)

    # ---------------- page 5: provenance / flags (internal)
    if include_internal:
        s.append(PageBreak())
        s.append(P("DOC F  ·  INTERNAL, NOT SENT TO SUPPLIERS", kicker))
        s.append(P("Data Provenance and Open Items", h1))
        s.append(P("Where every printed value came from. A plain STEP file carries geometry only; material, "
                   "tolerances, finish and commercial terms come from the engineer, and text sections are drafted by AI "
                   "and reviewed before export.", body))
        s.append(P("Flags raised during generation", h2))
        flags = fields_json.get("flags") or []
        if flags:
            fl = [hdr("Severity", "Field", "Message")]
            for f in flags:
                sev = (f.get("severity") or "info").lower()
                fl.append([P(f'<font color="{SEV_COLORS.get(sev, "#1f4e79")}"><b>{esc(sev.upper())}</b></font>'),
                           P(esc(f.get("field") or "")), P(esc(f.get("message") or ""))])
            s.append(grid(fl, [55, 95, fw - 150]))
        else:
            s.append(P("No flags.", body))
        s.append(P("Field sources", h2))
        pv = [hdr("Field", "Value", "Source", "Note")]
        for key, e in F.f.items():
            v = e.get("value")
            txt = "<br/>".join(as_lines(v)) if (e.get("source") == "AI" or isinstance(v, str)) else fmt_value(v)
            if len(txt) > 160:
                txt = txt[:157] + "..."
            pv.append([P(esc(key), small), P(txt or NA, small), P(F.tag(e.get("source")) or esc(e.get("source") or ""), small),
                       P(esc(e.get("note") or ""), small)])
        s.append(grid(pv, [95, fw - 285, 45, 145]))

    doc.build(s)
    return _stamp_views(buf.getvalue(), slots, fields_json.get("views") or [], views_root)


def _resolve(key, views_root):
    for p in (key, os.path.join(views_root, key)):
        if p and os.path.isfile(p):
            return p
    return None


def _stamp_views(pdf_bytes, slots, views, views_root):
    out = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    by_name = {v.get("name"): v.get("key") for v in views}
    for name, (pno, x, y, w, h) in slots.items():
        page = out[pno - 1]
        ph = page.rect.height
        r = pymupdf.Rect(x + 4, ph - (y + h) + 4, x + w - 4, ph - y - 14)  # leave room for caption
        path = _resolve(by_name.get(name), views_root) if by_name.get(name) else None
        if path:
            src = pymupdf.open(path)
            page.show_pdf_page(r, src, 0, keep_proportion=True)
            src.close()
        else:
            page.insert_textbox(r + (0, r.height / 2 - 8, 0, 0), "View not available", fontsize=8,
                                color=(0.36, 0.4, 0.46), align=pymupdf.TEXT_ALIGN_CENTER)
    data = out.tobytes(garbage=4, deflate=True)
    out.close()
    return data
