#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["reportlab>=4.0", "pypdfium2>=4.0", "python-docx>=1.1.0"]
# ///
"""Render a tailored resume JSON to a one-page PDF.

Deterministic layout: this script owns the page, so "fits on one page" is a
constraint it solves rather than a measurement it reports. It tries a band of
typographic scales largest-first, and only if none fit does it trim content
(and it reports exactly what it trimmed).

Usage:
    uv run scripts/render.py --tailored tailored_resume.json --out-dir DIR
    # or, in a venv with reportlab installed:
    python scripts/render.py --tailored tailored_resume.json --out-dir DIR

Prints a JSON metrics object to stdout:
    {"pdf": ..., "png": ..., "pages": 1, "fill": 0.94, "scale": 1.0,
     "lines_of_room": 4, "trimmed": [...], "warnings": [...]}
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prose import lint as prose_lint  # noqa: E402  (local, stdlib-only)

try:
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas as rl_canvas
except ImportError:  # hard failure; never degrade silently
    sys.stderr.write(
        "resume-kit: reportlab is not installed.\n"
        "  With uv (no setup needed):  uv run scripts/render.py ...\n"
        "  With pip:                   python3 -m pip install 'reportlab>=4.0' 'pypdfium2>=4.0'\n"
        "  Or run scripts/setup.sh to build a venv, then use that venv's python.\n"
    )
    raise SystemExit(2)

# ---------------------------------------------------------------------------
# Page + typography
# ---------------------------------------------------------------------------

PAGE_W, PAGE_H = letter
MARGIN_X = 0.7 * 72
MARGIN_TOP = 0.5 * 72
MARGIN_BOTTOM = 0.5 * 72
USABLE_W = PAGE_W - 2 * MARGIN_X
USABLE_H = PAGE_H - MARGIN_TOP - MARGIN_BOTTOM

ACCENT = "#2B4C7E"
DARK = "#1A1A1A"
GRAY = "#555555"


def _register_fonts() -> tuple[str, str]:
    """Embed the bundled Carlito faces (Calibri-metric, OFL) when present.

    Embedding matters beyond looks: with a base-14 font the PDF carries no
    glyphs, so every viewer substitutes its own and the rendered page stops
    matching the metrics this script laid out with. Helvetica stays as the
    fallback if someone strips assets/fonts/.
    """
    fonts_dir = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    reg, bold = fonts_dir / "Carlito-Regular.ttf", fonts_dir / "Carlito-Bold.ttf"
    if reg.exists() and bold.exists():
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        pdfmetrics.registerFont(TTFont("Carlito", str(reg)))
        pdfmetrics.registerFont(TTFont("Carlito-Bold", str(bold)))
        pdfmetrics.registerFontFamily("Carlito", normal="Carlito", bold="Carlito-Bold")
        return "Carlito", "Carlito-Bold"
    return "Helvetica", "Helvetica-Bold"


REG, BOLD = _register_fonts()

# Scales tried largest-first. Above 1.0 the page gets airier, below it tighter.
SCALES = [1.10, 1.06, 1.03, 1.00, 0.97, 0.94, 0.91, 0.88, 0.85]
MAX_TRIMS = 12


def ctx_for(scale: float) -> dict:
    """Every size/space in one dict so a single scalar tunes the whole page."""
    s = scale
    return {
        "scale": scale,
        "name": 20 * s,
        "headline": 11.5 * s,
        "contact": 8.5 * s,
        "body": 10.5 * s,
        "meta_small": 10 * s,
        "section": 11.5 * s,
        "lead": 1.20,  # line-height multiplier
        "sp_after_name": 2 * s,
        "sp_after_headline": 3 * s,
        "sp_after_contact": 7 * s,
        "sp_after_summary": 5 * s,
        "sp_before_section": 8 * s,
        "sp_after_section": 4 * s,
        "sp_before_entry": 5 * s,
        "sp_after_entry_meta": 2 * s,
        "sp_after_bullet": 1.5 * s,
        "sp_after_skill": 2 * s,
        "bullet_indent": 11 * s,
    }


# ---------------------------------------------------------------------------
# Rich text wrapping (a line may mix fonts/sizes/colors)
# ---------------------------------------------------------------------------

def _tokens(text: str):
    """Words with their surrounding spaces kept, so a run like '  |  Company'
    doesn't lose the gap that separates it from the run before it."""
    return re.findall(r"\s*\S+\s*", text)


def wrap_runs(runs, width: float, indent: float = 0.0):
    """Wrap [(text, font, size, color), ...] into lines of positioned pieces.

    Returns [[(x, text, font, size, color), ...], ...]. First line starts at
    x=0, continuation lines at x=indent (hanging indent for bullets).
    """
    lines, cur, x = [], [], 0.0
    avail = width

    def flush():
        nonlocal cur, x, avail
        if cur:
            lines.append(cur)
        cur, x = [], indent
        avail = width - indent

    def push(x0, tok, font, size, color):
        """Append to the previous piece when the style matches, so each drawn
        piece keeps its own inter-word spaces instead of relying on absolute
        token positions (which drift if a viewer substitutes the font)."""
        if cur and cur[-1][2:] == (font, size, color):
            px, ptext, *rest = cur[-1]
            cur[-1] = (px, ptext + tok, font, size, color)
        else:
            cur.append((x0, tok, font, size, color))

    for text, font, size, color in runs:
        for tok in _tokens(text):
            if cur and x + stringWidth(tok.rstrip(), font, size) > avail + 1e-6:
                flush()  # the closing line's trailing space is dropped at draw
            if not cur:
                tok = tok.lstrip()  # no dangling indent at the start of a line
            push(x, tok, font, size, color)
            x += stringWidth(tok, font, size)
    if cur:
        lines.append(cur)
    return lines


def line_height(line, lead: float) -> float:
    return max((piece[3] for piece in line), default=0.0) * lead


# ---------------------------------------------------------------------------
# Layout: produces draw ops with y measured downward from the content top
# ---------------------------------------------------------------------------

class Layout:
    def __init__(self, ctx):
        self.ctx = ctx
        self.ops = []
        self.y = 0.0

    # -- primitives ---------------------------------------------------------

    def runs(self, runs, indent=0.0, align="left", width=USABLE_W):
        lines = wrap_runs(runs, width, indent)
        for line in lines:
            lh = line_height(line, self.ctx["lead"])
            baseline = self.y + lh * 0.78
            if align == "center":
                last_x, last_t, last_f, last_s, _ = line[-1]
                total = last_x + stringWidth(last_t.rstrip(), last_f, last_s)
                cursor = (width - total) / 2.0
                for x, t, f, s, c in line:
                    self.ops.append(("text", cursor + x, baseline, t, f, s, c, 0.0))
            else:
                for x, t, f, s, c in line:
                    self.ops.append(("text", x, baseline, t, f, s, c, 0.0))
            self.y += lh
        return lines

    def centered_line(self, text, font, size, color, charspace=0.0):
        """One unwrapped centered line, optionally letterspaced (the name)."""
        w = stringWidth(text, font, size) + charspace * max(0, len(text) - 1)
        lh = size * self.ctx["lead"]
        self.ops.append((
            "text", (USABLE_W - w) / 2.0, self.y + lh * 0.78, text, font, size,
            color, charspace,
        ))
        self.y += lh

    def rule(self, color, thickness=0.6, pad=1.5):
        self.y += pad
        self.ops.append(("rule", 0.0, self.y, USABLE_W, thickness, color))
        self.y += thickness

    def space(self, amount):
        self.y += amount

    # -- resume blocks ------------------------------------------------------

    def header(self, meta):
        c = self.ctx
        self.centered_line(meta.get("name", "").upper(), BOLD, c["name"], ACCENT,
                           charspace=1.4 * c["scale"])
        self.space(c["sp_after_name"])
        if meta.get("title"):
            self.runs([(meta["title"], REG, c["headline"], GRAY)], align="center")
            self.space(c["sp_after_headline"])
        parts = [meta[k] for k in
                 ("location", "phone", "email", "linkedin", "github", "website", "relocation")
                 if meta.get(k)]
        if parts:
            self.runs([("  ·  ".join(parts), REG, c["contact"], GRAY)], align="center")
        self.space(c["sp_after_contact"])

    def summary(self, text):
        if not text:
            return
        self.runs([(text, REG, self.ctx["body"], DARK)])
        self.space(self.ctx["sp_after_summary"])

    def section(self, title):
        c = self.ctx
        self.space(c["sp_before_section"])
        self.runs([(title.upper(), BOLD, c["section"], ACCENT)])
        self.rule(ACCENT)
        self.space(c["sp_after_section"])

    def bullet(self, text):
        c = self.ctx
        indent = c["bullet_indent"]
        self.runs(
            [("•   ", REG, c["body"], ACCENT), (text, REG, c["body"], DARK)],
            indent=indent,
        )
        self.space(c["sp_after_bullet"])

    def experience(self, entries):
        c = self.ctx
        for job in entries:
            self.space(c["sp_before_entry"])
            head = [(job.get("title", ""), BOLD, c["body"] + 0.5 * c["scale"], DARK)]
            if job.get("company"):
                head.append((f"  |  {job['company']}", REG, c["body"], GRAY))
            self.runs(head)
            meta_bits = [b for b in (job.get("location"),
                                     _daterange(job)) if b]
            if meta_bits:
                self.runs([("  |  ".join(meta_bits), REG, c["meta_small"], GRAY)])
            self.space(c["sp_after_entry_meta"])
            for b in job.get("bullets", []):
                self.bullet(b)

    def skills(self, skills):
        c = self.ctx
        for label, items in skills.items():
            if not items:
                continue
            body = ", ".join(items) if isinstance(items, list) else str(items)
            self.runs([
                (f"{label.replace('_', ' ').title()}: ", BOLD, c["body"], ACCENT),
                (body, REG, c["body"], DARK),
            ])
            self.space(c["sp_after_skill"])

    def projects(self, projects):
        c = self.ctx
        for proj in projects:
            self.space(c["sp_before_entry"])
            head = [(proj.get("name", ""), BOLD, c["body"] + 0.5 * c["scale"], DARK)]
            tech = proj.get("tech")
            if tech:
                tech_s = ", ".join(tech) if isinstance(tech, list) else str(tech)
                head.append((f"  |  {tech_s}", REG, c["body"], GRAY))
            self.runs(head)
            self.space(c["sp_after_entry_meta"])
            if proj.get("description"):
                self.bullet(proj["description"])

    def education(self, entries):
        c = self.ctx
        for edu in entries:
            self.space(c["sp_before_entry"])
            head = [(edu.get("degree", ""), BOLD, c["body"] + 0.5 * c["scale"], DARK)]
            if edu.get("honors"):
                head.append((f"  |  {edu['honors']}", REG, c["body"], ACCENT))
            self.runs(head)
            bits = [b for b in (edu.get("institution"), edu.get("location"),
                                _daterange(edu)) if b]
            if bits:
                self.runs([("  |  ".join(bits), REG, c["meta_small"], GRAY)])

    def certifications(self, certs):
        c = self.ctx
        flat = []
        for cert in certs:
            if isinstance(cert, str):
                flat.append(cert)
            else:
                name = cert.get("name", "")
                issuer = cert.get("issuer")
                year = cert.get("year") or cert.get("date")
                extra = ", ".join(str(x) for x in (issuer, year) if x)
                flat.append(f"{name} ({extra})" if extra else name)
        if flat:
            self.runs([("  ·  ".join(flat), REG, c["body"], DARK)])


def _daterange(entry) -> str:
    start, end = entry.get("start"), entry.get("end")
    if start and end:
        return f"{start} – {end}"
    return start or end or ""


def build(data: dict, ctx: dict) -> Layout:
    lay = Layout(ctx)
    lay.header(data.get("meta", {}))
    lay.summary(data.get("summary"))

    if data.get("experience"):
        lay.section("Experience")
        lay.experience(data["experience"])
    if data.get("skills"):
        lay.section("Skills")
        lay.skills(data["skills"])
    if data.get("projects"):
        lay.section("Projects")
        lay.projects(data["projects"])
    if data.get("education"):
        lay.section("Education")
        lay.education(data["education"])
    if data.get("certifications"):
        lay.section("Certifications")
        lay.certifications(data["certifications"])
    return lay


# ---------------------------------------------------------------------------
# Fit solving
# ---------------------------------------------------------------------------

def _trim_once(data: dict) -> str | None:
    """Drop the single least-load-bearing item. Returns a description, or None."""
    exp = data.get("experience") or []
    counts = [(len(j.get("bullets") or []), i) for i, j in enumerate(exp)]
    if counts:
        n, idx = max(counts)
        if n >= 3:
            dropped = exp[idx]["bullets"].pop()
            return f"bullet from {exp[idx].get('company', 'experience')}: {dropped[:60]}..."
    projects = data.get("projects") or []
    if len(projects) > 1:
        dropped = projects.pop()
        return f"project: {dropped.get('name', '?')}"
    if counts:
        n, idx = max(counts)
        if n >= 2:
            dropped = exp[idx]["bullets"].pop()
            return f"bullet from {exp[idx].get('company', 'experience')}: {dropped[:60]}..."
    return None


def solve(data: dict):
    """Return (layout, ctx, trimmed[]) for the best one-page rendering."""
    trimmed = []
    for _ in range(MAX_TRIMS + 1):
        for scale in SCALES:
            ctx = ctx_for(scale)
            lay = build(data, ctx)
            if lay.y <= USABLE_H:
                return lay, ctx, trimmed
        what = _trim_once(data)
        if what is None:
            break
        trimmed.append(what)
    # Nothing fits even trimmed: return the tightest attempt so the caller can
    # report honestly rather than pretending.
    ctx = ctx_for(SCALES[-1])
    return build(data, ctx), ctx, trimmed


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def draw(lay: Layout, out_pdf: Path, title: str = "Resume") -> int:
    """Draw the layout, spilling onto further pages if it overflows.

    Overflow is a failure the caller must act on, but it must not be a *silent*
    one: content past the fold continues on page 2 rather than being drawn off
    the canvas and lost. Returns the page count actually written.
    """
    c = rl_canvas.Canvas(str(out_pdf), pagesize=letter)
    c.setTitle(title)
    page_count = max(1, int((lay.y - 1e-6) // USABLE_H) + 1)
    for page in range(page_count):
        _draw_page(c, lay.ops, page)
        c.showPage()
    c.save()
    return page_count


def _draw_page(c, ops, page: int):
    top = PAGE_H - MARGIN_TOP
    lo, hi = page * USABLE_H, (page + 1) * USABLE_H
    for op in ops:
        y_abs = op[2]  # both op kinds carry y in slot 2
        if not (lo <= y_abs < hi):
            continue
        op = (op[0], op[1], y_abs - lo) + tuple(op[3:])
        if op[0] == "text":
            _, x, y, text, font, size, color, charspace = op
            text = text.rstrip()
            if not text:
                continue
            to = c.beginText(MARGIN_X + x, top - y)
            to.setFont(font, size)
            to.setFillColor(HexColor(color))
            # Tc persists in the content stream across text objects, always set
            # it, or the letterspaced name leaks into every line below it.
            to.setCharSpace(charspace)
            to.textOut(text)
            c.drawText(to)
        elif op[0] == "rule":
            _, x0, y, w, th, color = op
            c.setStrokeColor(HexColor(color))
            c.setLineWidth(th)
            c.line(MARGIN_X + x0, top - y, MARGIN_X + x0 + w, top - y)


def _docx_page_count(docx_path: Path):
    """Page count of the DOCX as a word processor lays it out, or None.

    Uses LibreOffice when present. Optional by design: the whole point of the
    reportlab fit solver is that no office suite is required.
    """
    import shutil
    import subprocess
    import tempfile

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [soffice, f"-env:UserInstallation=file://{tmp}/profile", "--headless",
                 "--convert-to", "pdf", "--outdir", tmp, str(docx_path)],
                capture_output=True, check=True, timeout=180,
            )
            out = Path(tmp) / (docx_path.stem + ".pdf")
            if not out.exists():
                return None
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(str(out))
            n = len(doc)
            doc.close()
            return n
    except Exception:
        return None


def rasterize(pdf_path: Path, png_path: Path, dpi: int = 110) -> bool:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return False
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    page.render(scale=dpi / 72).to_pil().save(str(png_path))
    pdf.close()
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Render tailored resume JSON to a one-page PDF")
    ap.add_argument("--tailored", required=True, help="Path to tailored resume JSON")
    ap.add_argument("--out-dir", required=True, help="Directory to write resume.pdf into")
    ap.add_argument("--basename", default="resume")
    ap.add_argument("--no-png", action="store_true", help="Skip the page-1 PNG preview")
    ap.add_argument("--no-docx", action="store_true", help="Skip the editable .docx")
    ap.add_argument("--verify-docx", action="store_true",
                    help="Confirm the .docx is one page by laying it out in LibreOffice "
                         "(slow, and only possible where soffice is installed)")
    args = ap.parse_args()

    data = json.loads(Path(args.tailored).read_text())
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    lay, ctx, trimmed = solve(data)
    pdf_path = out_dir / f"{args.basename}.pdf"
    name = data.get("meta", {}).get("name", "Resume")
    pages = draw(lay, pdf_path, title=f"{name}, Resume")

    docx_path = None
    docx_error = None
    if not args.no_docx:
        try:
            from docx_out import render_docx
            docx_path = render_docx(data, ctx, out_dir / f"{args.basename}.docx")
        except ImportError:
            docx_error = ("python-docx is not installed, so no editable .docx was "
                          "written. Install it, or run with --no-docx to silence this.")

    # solve() trims in place; keep the JSON that ships next to the PDF equal to
    # the JSON that produced it.
    if trimmed:
        Path(args.tailored).write_text(json.dumps(data, indent=2))

    fill = lay.y / USABLE_H
    warnings = []
    if pages > 1:
        warnings.append(
            f"OVERFLOW: content runs to {pages} pages at the tightest scale after "
            f"{len(trimmed)} trims. NOT DELIVERABLE: cut content and re-render."
        )
    if fill < 0.85:
        warnings.append(
            f"UNDERFILLED: page is {int(fill * 100)}% full. Add content: roughly "
            f"{int((USABLE_H - lay.y) / (ctx['body'] * ctx['lead']))} more lines fit."
        )
    if trimmed:
        warnings.append(
            f"TRIMMED {len(trimmed)} item(s) to fit (and rewrote {args.tailored} to "
            "match). Prefer writing shorter content over letting the renderer choose "
            "what to drop."
        )

    prose = prose_lint(data, "tailored")
    if prose:
        warnings.append(
            f"PROSE: {len(prose)} field(s) break the house style (no em dashes, no "
            "filler). Fix the text and re-render; see prose[] below."
        )

    png_path = out_dir / f"{args.basename}.page1.png"
    png_ok = False if args.no_png else rasterize(pdf_path, png_path)
    if not args.no_png and not png_ok:
        warnings.append(
            "No PNG preview: pypdfium2 not installed, so the visual review step "
            "must be skipped (PDF is still valid)."
        )

    if docx_error:
        warnings.append(docx_error)

    docx_pages = None
    if docx_path and args.verify_docx:
        docx_pages = _docx_page_count(docx_path)
        if docx_pages is None:
            warnings.append(
                "DOCX page count unverified: LibreOffice (soffice) is not installed. "
                "The PDF is the proof of fit; Word may lay the .docx out slightly "
                "differently."
            )
        elif docx_pages != 1:
            warnings.append(
                f"DOCX RUNS TO {docx_pages} PAGES even though the PDF fits. Cut content "
                "and re-render; do not hand over the .docx."
            )

    metrics = {
        "docx": str(docx_path) if docx_path else None,
        "pdf": str(pdf_path),
        "png": str(png_path) if png_ok else None,
        "deliverable": pages == 1,
        "pages": pages,
        "fill": round(fill, 3),
        "scale": ctx["scale"],
        "content_height_pt": round(lay.y, 1),
        "usable_height_pt": round(USABLE_H, 1),
        "lines_of_room": max(0, int((USABLE_H - lay.y) / (ctx["body"] * ctx["lead"]))),
        "docx_pages": docx_pages,
        "trimmed": trimmed,
        "prose": prose,
        "warnings": warnings,
    }
    (out_dir / "fit.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    # Non-zero rc so a caller that only checks the exit status can never treat a
    # multi-page render as a finished resume.
    if pages > 1:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
