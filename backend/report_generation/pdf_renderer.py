import html
import re
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text.strip())
    escaped = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__([^_]+)__", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", escaped)
    return escaped


def _is_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _page_footer(canvas, document):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawCentredString(A4[0] / 2, 10 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _styles():
    sample = getSampleStyleSheet()
    body = ParagraphStyle(
        "ReportBody",
        parent=sample["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#202124"),
        spaceAfter=7,
        alignment=TA_LEFT,
    )
    return {
        "body": body,
        "title": ParagraphStyle(
            "ReportTitle",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=25,
            textColor=colors.HexColor("#111111"),
            alignment=TA_CENTER,
            spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "Heading1",
            parent=sample["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=colors.HexColor("#202124"),
            spaceBefore=13,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "Heading2",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=16,
            textColor=colors.HexColor("#333333"),
            spaceBefore=11,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "Heading3",
            parent=sample["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#444444"),
            spaceBefore=9,
            spaceAfter=5,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=body,
            leftIndent=14,
            firstLineIndent=-8,
            bulletIndent=4,
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=body,
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#666666"),
        ),
        "code": ParagraphStyle(
            "Code",
            parent=body,
            fontName="Courier",
            fontSize=8,
            leading=11,
            leftIndent=8,
            rightIndent=8,
            backColor=colors.HexColor("#f4f4f4"),
            borderColor=colors.HexColor("#dddddd"),
            borderWidth=0.5,
            borderPadding=6,
            spaceBefore=5,
            spaceAfter=7,
        ),
    }


def render_markdown_to_pdf_bytes(
    markdown_text: str,
    *,
    title: str,
    bank_name: str,
    reporting_year: int,
    version_number: int,
) -> bytes:
    if not markdown_text.strip():
        raise ValueError("The final Markdown report is empty.")

    styles = _styles()
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
        author=bank_name,
        subject="IFRS S1/S2 sustainability-related financial disclosures",
    )

    story = [
        Paragraph(_inline_markdown(title), styles["title"]),
        Paragraph(
            _inline_markdown(
                f"{bank_name} | Reporting year {reporting_year} | Version {version_number}"
            ),
            styles["small"],
        ),
        Spacer(1, 10),
    ]

    lines = markdown_text.replace("\r\n", "\n").split("\n")
    paragraph_lines: list[str] = []
    code_lines: list[str] = []
    in_code_block = False
    index = 0

    def flush_paragraph():
        if not paragraph_lines:
            return
        text = " ".join(line.strip() for line in paragraph_lines if line.strip())
        paragraph_lines.clear()
        if text:
            story.append(Paragraph(_inline_markdown(text), styles["body"]))

    while index < len(lines):
        stripped = lines[index].strip()

        if stripped.startswith("```"):
            flush_paragraph()
            if in_code_block:
                story.append(
                    Paragraph(
                        "<br/>".join(html.escape(line) for line in code_lines),
                        styles["code"],
                    )
                )
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            index += 1
            continue

        if in_code_block:
            code_lines.append(lines[index])
            index += 1
            continue

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        if stripped == "---":
            flush_paragraph()
            story.append(Spacer(1, 5))
            index += 1
            continue

        if stripped.startswith("# "):
            flush_paragraph()
            heading = stripped[2:].strip()
            if heading.lower() != title.lower():
                story.append(Paragraph(_inline_markdown(heading), styles["h1"]))
            index += 1
            continue

        if stripped.startswith("## "):
            flush_paragraph()
            story.append(Paragraph(_inline_markdown(stripped[3:]), styles["h2"]))
            index += 1
            continue

        if stripped.startswith("### "):
            flush_paragraph()
            story.append(Paragraph(_inline_markdown(stripped[4:]), styles["h3"]))
            index += 1
            continue

        if re.match(r"^[-*]\s+", stripped):
            flush_paragraph()
            bullet_text = re.sub(r"^[-*]\s+", "", stripped)
            story.append(
                Paragraph(_inline_markdown(bullet_text), styles["bullet"], bulletText="-")
            )
            index += 1
            continue

        numbered = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if numbered:
            flush_paragraph()
            story.append(
                Paragraph(
                    _inline_markdown(numbered.group(2)),
                    styles["bullet"],
                    bulletText=f"{numbered.group(1)}.",
                )
            )
            index += 1
            continue

        if (
            "|" in stripped
            and index + 1 < len(lines)
            and _is_table_separator(lines[index + 1])
        ):
            flush_paragraph()
            rows = [_split_table_row(stripped)]
            index += 2
            while index < len(lines):
                table_line = lines[index].strip()
                if not table_line or "|" not in table_line:
                    break
                rows.append(_split_table_row(table_line))
                index += 1

            max_columns = max(len(row) for row in rows)
            rows = [row + [""] * (max_columns - len(row)) for row in rows]
            width = (A4[0] - 36 * mm) / max_columns
            formatted = []
            for row_index, row in enumerate(rows):
                style = styles["small"]
                if row_index == 0:
                    style = ParagraphStyle(
                        "TableHeader",
                        parent=styles["small"],
                        fontName="Helvetica-Bold",
                        textColor=colors.HexColor("#111111"),
                    )
                formatted.append([Paragraph(_inline_markdown(cell), style) for cell in row])

            table = Table(formatted, colWidths=[width] * max_columns, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cccccc")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 7))
            continue

        paragraph_lines.append(stripped)
        index += 1

    flush_paragraph()
    if in_code_block and code_lines:
        story.append(
            Paragraph(
                "<br/>".join(html.escape(line) for line in code_lines),
                styles["code"],
            )
        )

    document.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return output.getvalue()