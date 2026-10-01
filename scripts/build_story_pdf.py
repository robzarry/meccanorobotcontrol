"""Build docs/STORY.pdf from docs/STORY.md.

    uv run --group docs scripts/build_story_pdf.py

Understands the Markdown the story uses: headings, paragraphs, bullet and
numbered lists, tables, code blocks, **bold**, *italic*, `code` and links.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, Paragraph,
                                Preformatted, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
import reportlab

# Embed ReportLab's bundled Vera fonts so the PDF looks the same in every
# viewer (the built-in Helvetica isn't embedded and some viewers fake it).
_FONT_DIR = Path(reportlab.__file__).parent / "fonts"
for name, file in [("Vera", "Vera.ttf"), ("Vera-Bold", "VeraBd.ttf"),
                   ("Vera-Italic", "VeraIt.ttf"), ("Vera-BoldItalic", "VeraBI.ttf")]:
    pdfmetrics.registerFont(TTFont(name, _FONT_DIR / file))
pdfmetrics.registerFontFamily("Vera", normal="Vera", bold="Vera-Bold",
                              italic="Vera-Italic", boldItalic="Vera-BoldItalic")
addMapping("Vera", 0, 0, "Vera")

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "STORY.md"
OUTPUT = ROOT / "docs" / "STORY.pdf"

ACCENT = colors.HexColor("#d9480f")
INK = colors.HexColor("#1c1f24")
MUTED = colors.HexColor("#646b76")
LINE = colors.HexColor("#dde1e6")
SHADE = colors.HexColor("#f4f5f7")

base = getSampleStyleSheet()
STYLES = {
    "title": ParagraphStyle("title", parent=base["Title"], textColor=INK, fontName="Vera-Bold",
                            fontSize=21, leading=26, alignment=TA_LEFT, spaceAfter=10),
    "h2": ParagraphStyle("h2", parent=base["Heading2"], textColor=ACCENT, fontName="Vera-Bold",
                         fontSize=14, leading=18, spaceBefore=16, spaceAfter=6),
    "h3": ParagraphStyle("h3", parent=base["Heading3"], textColor=INK, fontName="Vera-Bold",
                         fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=4),
    "body": ParagraphStyle("body", parent=base["BodyText"], textColor=INK, fontName="Vera",
                           fontSize=10, leading=15, spaceAfter=6),
    "cell": ParagraphStyle("cell", parent=base["BodyText"], textColor=INK, fontName="Vera",
                           fontSize=9, leading=12.5),
    "cellhead": ParagraphStyle("cellhead", parent=base["BodyText"], textColor=INK,
                               fontName="Vera-Bold", fontSize=9, leading=12.5),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=8, leading=10.5,
                           textColor=INK, backColor=SHADE, borderPadding=6,
                           spaceBefore=4, spaceAfter=10),
}


def inline(text: str) -> str:
    """Convert inline Markdown to ReportLab's mini-HTML."""
    text = escape(text)
    text = re.sub(r"`([^`]+)`", r'<font face="Courier" color="#a33a0b">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<link href="\2" color="#d9480f">\1</link>', text)
    return text


def table(rows: list[list[str]]) -> Table:
    """A table. An empty header row ("| | |") makes a label/value table whose
    first column is bold instead."""
    header, *body = rows
    has_header = any(cell.strip() for cell in header)

    def cell(text: str, bold: bool = False) -> Paragraph:
        markup = inline(text)
        return Paragraph(f"<b>{markup}</b>" if bold else markup, STYLES["cell"])

    data = [[cell(c, bold=True) for c in header]] if has_header else []
    data += [[cell(c, bold=not has_header and j == 0) for j, c in enumerate(row)]
             for row in body]

    ncols = len(header)
    width = A4[0] - 40 * mm
    col_widths = ([width * 0.28] + [width * 0.72 / (ncols - 1)] * (ncols - 1)
                  if ncols > 1 else [width])
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if has_header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), SHADE))
    t = Table(data, colWidths=col_widths, hAlign="LEFT", repeatRows=1 if has_header else 0)
    t.setStyle(TableStyle(style))
    return t


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse(markdown: str) -> list:
    flow: list = []
    lines = markdown.splitlines()
    i = 0
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            # Lines ending in bold labels ("**Last updated:** ...") stay separate.
            flow.append(Paragraph("<br/>".join(inline(p) for p in paragraph)
                                  if all(p.startswith("**") for p in paragraph)
                                  else inline(" ".join(paragraph)), STYLES["body"]))
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush()
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            flow.append(Preformatted("\n".join(block), STYLES["code"]))
        elif stripped.startswith("# "):
            flush()
            flow.append(Paragraph(inline(stripped[2:]), STYLES["title"]))
        elif stripped.startswith("## "):
            flush()
            flow.append(Paragraph(inline(stripped[3:]), STYLES["h2"]))
        elif stripped.startswith("### "):
            flush()
            flow.append(Paragraph(inline(stripped[4:]), STYLES["h3"]))
        elif stripped.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = split_row(lines[i])
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in row):
                    rows.append(row)
                i += 1
            flow.append(KeepTogether([table(rows), Spacer(1, 8)]))
            continue
        elif re.match(r"^(- |\d+\. )", stripped):
            flush()
            numbered = stripped[0].isdigit()
            items = []
            while i < len(lines) and lines[i].strip():
                item = lines[i].strip()
                if re.match(r"^(- |\d+\. )", item):
                    items.append(re.sub(r"^(- |\d+\. )", "", item))
                else:  # continuation line
                    items[-1] += " " + item
                i += 1
            style = ({"bulletType": "1"} if numbered else
                     {"bulletType": "bullet", "start": "•"})
            flow.append(ListFlowable(
                [ListItem(Paragraph(inline(t), STYLES["body"]), leftIndent=14) for t in items],
                bulletColor=ACCENT, bulletFontName="Vera-Bold", bulletFontSize=10,
                leftIndent=14, **style))
            continue
        elif not stripped:
            flush()
        else:
            paragraph.append(stripped)
        i += 1
    flush()
    return flow


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Vera", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 12 * mm, "Meccano Robot Control: Development Story")
    canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(2)
    canvas.line(20 * mm, A4[1] - 12 * mm, A4[0] - 20 * mm, A4[1] - 12 * mm)
    canvas.restoreState()


def main() -> None:
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm,
                            title="Meccano Robot Control: Development Story",
                            author="robzarry")
    doc.build(parse(SOURCE.read_text()), onFirstPage=footer, onLaterPages=footer)
    print(f"wrote {OUTPUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
