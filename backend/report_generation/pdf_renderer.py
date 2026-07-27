import html
import re
from io import BytesIO
from pathlib import Path

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    LongTable,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


FONT_REGULAR = "ReportSans"
FONT_BOLD = "ReportSans-Bold"
FONT_ITALIC = "ReportSans-Italic"
FONT_BOLD_ITALIC = "ReportSans-BoldItalic"


def _register_fonts():
    if FONT_REGULAR in pdfmetrics.getRegisteredFontNames():
        return

    font_directory = Path(reportlab.__file__).resolve().parent / "fonts"
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, font_directory / "Vera.ttf"))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, font_directory / "VeraBd.ttf"))
    pdfmetrics.registerFont(TTFont(FONT_ITALIC, font_directory / "VeraIt.ttf"))
    pdfmetrics.registerFont(
        TTFont(FONT_BOLD_ITALIC, font_directory / "VeraBI.ttf")
    )
    pdfmetrics.registerFontFamily(
        FONT_REGULAR,
        normal=FONT_REGULAR,
        bold=FONT_BOLD,
        italic=FONT_ITALIC,
        boldItalic=FONT_BOLD_ITALIC,
    )


_register_fonts()


NAVY = colors.HexColor("#071A33")
NAVY_LIGHT = colors.HexColor("#0D2D55")
BLUE = colors.HexColor("#2D7FF9")
BLUE_LIGHT = colors.HexColor("#DDEBFF")
LIME = colors.HexColor("#D6F000")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#5F6B7A")
LINE = colors.HexColor("#D8E0EA")
SURFACE = colors.HexColor("#F4F7FB")
WHITE = colors.white

MAJOR_SECTIONS = {
    "general requirements": (1, "General Requirements"),
    "governance": (2, "Governance"),
    "strategy": (3, "Strategy"),
    "risk management": (4, "Risk Management"),
    "metrics and targets": (5, "Metrics and Targets"),
}


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text.strip())
    escaped = re.sub(
        r"`([^`]+)`",
        rf'<font name="{FONT_REGULAR}">\1</font>',
        escaped,
    )
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__([^_]+)__", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", escaped)
    return escaped


def _plain_heading(text: str) -> str:
    text = re.sub(r"[*_`#]", "", text).strip()
    return re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", text).strip()


def _major_section(text: str):
    normalized = re.sub(r"[^a-z0-9]+", " ", _plain_heading(text).lower()).strip()
    return MAJOR_SECTIONS.get(normalized)


def _is_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _table_widths(rows: list[list[str]], available_width: float) -> list[float]:
    column_count = max(len(row) for row in rows)
    weights = []
    for column_index in range(column_count):
        longest = max(
            len(re.sub(r"[*_`]", "", row[column_index]))
            for row in rows
            if column_index < len(row)
        )
        weights.append(max(8, min(42, longest)))

    total_weight = sum(weights) or column_count
    widths = [available_width * weight / total_weight for weight in weights]
    minimum = min(20 * mm, available_width / column_count)
    widths = [max(minimum, width) for width in widths]
    scale = available_width / sum(widths)
    return [width * scale for width in widths]


def _draw_cover_page(canvas, document):
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, width, height, stroke=0, fill=1)

    canvas.setFillColor(NAVY_LIGHT)
    canvas.circle(width + 15 * mm, height - 28 * mm, 68 * mm, stroke=0, fill=1)
    canvas.setFillColor(BLUE)
    canvas.rect(0, height - 34 * mm, 9 * mm, 34 * mm, stroke=0, fill=1)
    canvas.setFillColor(LIME)
    canvas.rect(0, 0, width, 5 * mm, stroke=0, fill=1)

    canvas.setStrokeColor(colors.Color(1, 1, 1, alpha=0.08))
    canvas.setLineWidth(0.6)
    for offset in range(0, 90, 15):
        canvas.line(
            width - (82 - offset) * mm,
            height,
            width,
            height - (82 - offset) * mm,
        )
    canvas.restoreState()


def _draw_body_page(canvas, document):
    width, height = A4
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.6)
    canvas.line(18 * mm, height - 16 * mm, width - 18 * mm, height - 16 * mm)

    canvas.setFillColor(NAVY)
    canvas.setFont(FONT_BOLD, 7.5)
    canvas.drawString(18 * mm, height - 12 * mm, document.bank_name[:70])
    canvas.setFillColor(MUTED)
    canvas.setFont(FONT_REGULAR, 7.5)
    canvas.drawRightString(
        width - 18 * mm,
        height - 12 * mm,
        f"IFRS S1/S2 · Reporting year {document.reporting_year}",
    )

    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont(FONT_REGULAR, 7)
    canvas.drawString(18 * mm, 10.5 * mm, "CONFIDENTIAL · INTERNAL USE")
    canvas.setFont(FONT_BOLD, 7.5)
    canvas.drawRightString(
        width - 18 * mm,
        10.5 * mm,
        f"{canvas.getPageNumber():02d}",
    )
    canvas.restoreState()


def _draw_divider_page(canvas, document):
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, width, height, stroke=0, fill=1)
    canvas.setFillColor(NAVY_LIGHT)
    canvas.circle(width - 5 * mm, 38 * mm, 58 * mm, stroke=0, fill=1)
    canvas.setFillColor(BLUE)
    canvas.rect(0, 0, 9 * mm, height, stroke=0, fill=1)
    canvas.setFillColor(LIME)
    canvas.rect(9 * mm, 0, 35 * mm, 5 * mm, stroke=0, fill=1)

    canvas.setFillColor(colors.Color(1, 1, 1, alpha=0.58))
    canvas.setFont(FONT_REGULAR, 7)
    canvas.drawString(24 * mm, 13 * mm, "CONFIDENTIAL · INTERNAL USE")
    canvas.drawRightString(
        width - 20 * mm,
        13 * mm,
        f"{canvas.getPageNumber():02d}",
    )
    canvas.restoreState()


class _IFRSReportDocument(BaseDocTemplate):
    def __init__(
        self,
        output,
        *,
        title: str,
        bank_name: str,
        reporting_year: int,
        version_number: int,
    ):
        super().__init__(
            output,
            pagesize=A4,
            title=title,
            author=bank_name,
            subject="IFRS S1/S2 sustainability-related financial disclosures",
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=23 * mm,
            bottomMargin=20 * mm,
            allowSplitting=True,
        )
        self.bank_name = bank_name
        self.reporting_year = reporting_year
        self.version_number = version_number

        width, height = A4
        cover_frame = Frame(
            24 * mm,
            22 * mm,
            width - 48 * mm,
            height - 44 * mm,
            id="cover-frame",
            showBoundary=0,
        )
        body_frame = Frame(
            18 * mm,
            20 * mm,
            width - 36 * mm,
            height - 43 * mm,
            id="body-frame",
            showBoundary=0,
        )
        divider_frame = Frame(
            28 * mm,
            34 * mm,
            width - 54 * mm,
            height - 68 * mm,
            id="divider-frame",
            showBoundary=0,
        )
        self.addPageTemplates(
            [
                PageTemplate(
                    id="cover",
                    frames=[cover_frame],
                    onPage=_draw_cover_page,
                ),
                PageTemplate(
                    id="body",
                    frames=[body_frame],
                    onPage=_draw_body_page,
                ),
                PageTemplate(
                    id="divider",
                    frames=[divider_frame],
                    onPage=_draw_divider_page,
                ),
            ]
        )

    def afterFlowable(self, flowable):
        level = getattr(flowable, "_toc_level", None)
        bookmark = getattr(flowable, "_bookmark_name", None)
        if level is None or not bookmark or not isinstance(flowable, Paragraph):
            return

        text = flowable.getPlainText()
        self.canv.bookmarkPage(bookmark)
        self.notify("TOCEntry", (level, text, self.page, bookmark))


def _styles():
    sample = getSampleStyleSheet()
    body = ParagraphStyle(
        "ReportBody",
        parent=sample["BodyText"],
        fontName=FONT_REGULAR,
        fontSize=9.2,
        leading=14.2,
        textColor=INK,
        spaceAfter=7,
        alignment=TA_LEFT,
        splitLongWords=True,
    )
    return {
        "body": body,
        "lead": ParagraphStyle(
            "Lead",
            parent=body,
            fontSize=10.5,
            leading=16,
            textColor=MUTED,
            spaceAfter=12,
        ),
        "cover_bank": ParagraphStyle(
            "CoverBank",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=12,
            leading=15,
            textColor=WHITE,
            spaceAfter=6,
        ),
        "cover_title": ParagraphStyle(
            "CoverTitle",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=28,
            leading=33,
            textColor=WHITE,
            spaceAfter=8,
        ),
        "cover_standard": ParagraphStyle(
            "CoverStandard",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=12,
            leading=16,
            textColor=LIME,
            spaceBefore=6,
            spaceAfter=18,
        ),
        "cover_meta": ParagraphStyle(
            "CoverMeta",
            parent=body,
            fontSize=9,
            leading=13,
            textColor=WHITE,
        ),
        "cover_label": ParagraphStyle(
            "CoverLabel",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=8,
            leading=11,
            textColor=LIME,
        ),
        "page_title": ParagraphStyle(
            "PageTitle",
            parent=sample["Heading1"],
            fontName=FONT_BOLD,
            fontSize=22,
            leading=27,
            textColor=NAVY,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "h1": ParagraphStyle(
            "Heading1",
            parent=sample["Heading1"],
            fontName=FONT_BOLD,
            fontSize=17,
            leading=21,
            textColor=NAVY,
            spaceBefore=10,
            spaceAfter=8,
            keepWithNext=True,
            borderColor=BLUE,
            borderWidth=0,
            borderPadding=0,
            leftIndent=0,
        ),
        "h2": ParagraphStyle(
            "Heading2",
            parent=sample["Heading2"],
            fontName=FONT_BOLD,
            fontSize=12.5,
            leading=16,
            textColor=NAVY_LIGHT,
            spaceBefore=11,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "Heading3",
            parent=sample["Heading3"],
            fontName=FONT_BOLD,
            fontSize=10.2,
            leading=14,
            textColor=BLUE,
            spaceBefore=9,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "h4": ParagraphStyle(
            "Heading4",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=9.5,
            leading=13,
            textColor=NAVY,
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=body,
            leftIndent=14,
            firstLineIndent=-8,
            bulletIndent=2,
            spaceAfter=4,
            bulletColor=BLUE,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=body,
            fontSize=7.6,
            leading=10.5,
            textColor=MUTED,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=7.2,
            leading=9.4,
            textColor=WHITE,
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            parent=body,
            fontSize=7.2,
            leading=9.8,
            textColor=INK,
        ),
        "code": ParagraphStyle(
            "Code",
            parent=body,
            fontName=FONT_REGULAR,
            fontSize=7.6,
            leading=10.5,
            leftIndent=7,
            rightIndent=7,
            backColor=SURFACE,
            borderColor=LINE,
            borderWidth=0.5,
            borderPadding=7,
            spaceBefore=5,
            spaceAfter=8,
        ),
        "quote": ParagraphStyle(
            "Quote",
            parent=body,
            leftIndent=12,
            rightIndent=8,
            textColor=MUTED,
            borderColor=BLUE,
            borderWidth=0,
            borderPadding=7,
            backColor=BLUE_LIGHT,
            spaceBefore=4,
            spaceAfter=9,
        ),
        "divider_number": ParagraphStyle(
            "DividerNumber",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=11,
            leading=14,
            textColor=LIME,
            spaceAfter=10,
        ),
        "divider_title": ParagraphStyle(
            "DividerTitle",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=31,
            leading=36,
            textColor=WHITE,
            spaceAfter=14,
        ),
        "divider_subtitle": ParagraphStyle(
            "DividerSubtitle",
            parent=body,
            fontSize=10,
            leading=15,
            textColor=colors.HexColor("#BFD2EA"),
        ),
        "toc_0": ParagraphStyle(
            "TOCLevel0",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=10,
            leading=14,
            textColor=NAVY,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=7,
        ),
        "toc_1": ParagraphStyle(
            "TOCLevel1",
            parent=body,
            fontSize=8.5,
            leading=12,
            textColor=MUTED,
            leftIndent=12,
            firstLineIndent=0,
            spaceBefore=3,
        ),
        "toc_2": ParagraphStyle(
            "TOCLevel2",
            parent=body,
            fontSize=8,
            leading=11,
            textColor=MUTED,
            leftIndent=22,
            firstLineIndent=0,
            spaceBefore=2,
        ),
    }


def _document_information_table(
    *,
    title: str,
    bank_name: str,
    reporting_year: int,
    version_number: int,
    styles,
):
    rows = [
        ["Document title", title],
        ["Institution", bank_name],
        ["Reporting framework", "IFRS S1 and IFRS S2"],
        ["Reporting year", str(reporting_year)],
        ["Report version", f"{version_number}.0"],
        ["Document status", "Internal review"],
        ["Classification", "Confidential · Internal use"],
    ]
    formatted = [
        [
            Paragraph(_inline_markdown(label), styles["table_header"]),
            Paragraph(_inline_markdown(value), styles["table_cell"]),
        ]
        for label, value in rows
    ]
    table = Table(formatted, colWidths=[47 * mm, 112 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), NAVY),
                ("BACKGROUND", (1, 0), (1, -1), SURFACE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _append_major_section(story, section_number, section_title, styles, bookmark_index):
    story.extend(
        [
            NextPageTemplate("divider"),
            PageBreak(),
            Spacer(1, 42 * mm),
            Paragraph(
                f"SECTION {section_number:02d}",
                styles["divider_number"],
            ),
        ]
    )
    divider_title = Paragraph(
        _inline_markdown(section_title),
        styles["divider_title"],
    )
    divider_title._toc_level = 0
    divider_title._bookmark_name = f"section-{bookmark_index}"
    story.extend(
        [
            divider_title,
            HRFlowable(
                width=30 * mm,
                thickness=3,
                color=LIME,
                hAlign="LEFT",
                spaceBefore=2,
                spaceAfter=12,
            ),
            Paragraph(
                "Sustainability-related financial disclosures prepared for "
                "internal review under the IFRS S1 and IFRS S2 framework.",
                styles["divider_subtitle"],
            ),
            NextPageTemplate("body"),
            PageBreak(),
            Paragraph(_inline_markdown(section_title), styles["h1"]),
            HRFlowable(
                width="100%",
                thickness=0.8,
                color=LINE,
                spaceAfter=10,
            ),
        ]
    )


def _append_markdown_body(story, markdown_text: str, styles):
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    has_major_sections = any(
        _major_section(match.group(2))
        for line in lines
        if (match := re.match(r"^(#{1,4})\s+(.+)$", line.strip()))
    )

    paragraph_lines: list[str] = []
    code_lines: list[str] = []
    in_code_block = False
    major_seen = False
    bookmark_index = 0
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

        if stripped in {"---", "***", "___"}:
            flush_paragraph()
            story.append(
                HRFlowable(
                    width="100%",
                    thickness=0.6,
                    color=LINE,
                    spaceBefore=4,
                    spaceAfter=9,
                )
            )
            index += 1
            continue

        if stripped.lower() == "<!-- pagebreak -->":
            flush_paragraph()
            story.append(PageBreak())
            index += 1
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading_match:
            flush_paragraph()
            heading_level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()

            if (
                heading_level == 1
                and _plain_heading(heading_text).lower()
                in {
                    "ifrs s1/s2 sustainability-related financial report",
                    "sustainability-related financial disclosures",
                }
            ):
                index += 1
                continue

            section = _major_section(heading_text)
            if section:
                major_seen = True
                bookmark_index += 1
                _append_major_section(
                    story,
                    section[0],
                    section[1],
                    styles,
                    bookmark_index,
                )
                index += 1
                continue

            style_key = f"h{heading_level}"
            heading = Paragraph(
                _inline_markdown(heading_text),
                styles[style_key],
            )
            # Keep the contents page useful: include report sections and
            # second-level headings, but omit individual disclosure IDs.
            include_in_toc = (not has_major_sections or major_seen) and heading_level <= 2
            if include_in_toc:
                bookmark_index += 1
                heading._toc_level = min(
                    2,
                    heading_level - 1 if not major_seen else max(1, heading_level - 1),
                )
                heading._bookmark_name = f"heading-{bookmark_index}"
            story.append(heading)
            index += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote = re.sub(r"^>\s?", "", stripped)
            story.append(Paragraph(_inline_markdown(quote), styles["quote"]))
            index += 1
            continue

        if re.match(r"^[-*+]\s+", stripped):
            flush_paragraph()
            bullet_text = re.sub(r"^[-*+]\s+", "", stripped)
            story.append(
                Paragraph(
                    _inline_markdown(bullet_text),
                    styles["bullet"],
                    bulletText="•",
                )
            )
            index += 1
            continue

        numbered = re.match(r"^(\d+)[.)]\s+(.+)$", stripped)
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

            column_count = max(len(row) for row in rows)
            rows = [row + [""] * (column_count - len(row)) for row in rows]
            available_width = A4[0] - 36 * mm
            formatted = []
            for row_index, row in enumerate(rows):
                cell_style = (
                    styles["table_header"]
                    if row_index == 0
                    else styles["table_cell"]
                )
                formatted.append(
                    [
                        Paragraph(_inline_markdown(cell), cell_style)
                        for cell in row
                    ]
                )

            table = LongTable(
                formatted,
                colWidths=_table_widths(rows, available_width),
                repeatRows=1,
                hAlign="LEFT",
                splitByRow=True,
            )
            table_style = [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.65, LINE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.35, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
            for row_index in range(1, len(rows)):
                if row_index % 2 == 0:
                    table_style.append(
                        ("BACKGROUND", (0, row_index), (-1, row_index), SURFACE)
                    )
            table.setStyle(TableStyle(table_style))
            story.extend([table, Spacer(1, 9)])
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
    document = _IFRSReportDocument(
        output,
        title=title,
        bank_name=bank_name,
        reporting_year=reporting_year,
        version_number=version_number,
    )

    cover_metadata = Table(
        [
            [
                Paragraph("REPORTING YEAR", styles["cover_label"]),
                Paragraph("REPORT VERSION", styles["cover_label"]),
                Paragraph("DOCUMENT STATUS", styles["cover_label"]),
            ],
            [
                Paragraph(str(reporting_year), styles["cover_meta"]),
                Paragraph(f"{version_number}.0", styles["cover_meta"]),
                Paragraph("Internal review", styles["cover_meta"]),
            ],
        ],
        colWidths=[46 * mm, 46 * mm, 55 * mm],
        hAlign="LEFT",
    )
    cover_metadata.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.HexColor("#527398")),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    toc = TableOfContents()
    toc.levelStyles = [
        styles["toc_0"],
        styles["toc_1"],
        styles["toc_2"],
    ]
    toc.dotsMinLevel = 0

    story = [
        Spacer(1, 8 * mm),
        Paragraph(_inline_markdown(bank_name.upper()), styles["cover_bank"]),
        Spacer(1, 27 * mm),
        Paragraph(
            "SUSTAINABILITY-RELATED<br/>FINANCIAL DISCLOSURES",
            styles["cover_title"],
        ),
        HRFlowable(
            width=34 * mm,
            thickness=3,
            color=LIME,
            hAlign="LEFT",
            spaceBefore=4,
            spaceAfter=8,
        ),
        Paragraph("IFRS S1 AND IFRS S2", styles["cover_standard"]),
        Spacer(1, 42 * mm),
        cover_metadata,
        Spacer(1, 14 * mm),
        Paragraph("CONFIDENTIAL · INTERNAL USE", styles["cover_label"]),
        NextPageTemplate("body"),
        PageBreak(),
        Paragraph("Document information", styles["page_title"]),
        Paragraph(
            "Control information for the sustainability-related financial "
            "disclosures presented in this report.",
            styles["lead"],
        ),
        Spacer(1, 4 * mm),
        _document_information_table(
            title=title,
            bank_name=bank_name,
            reporting_year=reporting_year,
            version_number=version_number,
            styles=styles,
        ),
        Spacer(1, 12 * mm),
        Paragraph("Purpose and use", styles["h2"]),
        Paragraph(
            "This document supports the institution's internal sustainability "
            "reporting and review process. It is prepared for controlled use by "
            "authorised auditors, reviewers and administrators.",
            styles["body"],
        ),
        Paragraph(
            "<b>Review notice:</b> Approval status is controlled in the platform. "
            "A downloaded copy should be checked against the latest version before use.",
            styles["quote"],
        ),
        PageBreak(),
        Paragraph("Table of contents", styles["page_title"]),
        Paragraph(
            "Major disclosure sections and their supporting subsections.",
            styles["lead"],
        ),
        HRFlowable(
            width="100%",
            thickness=1,
            color=BLUE,
            spaceAfter=8,
        ),
        toc,
        PageBreak(),
    ]

    _append_markdown_body(story, markdown_text, styles)
    document.multiBuild(story)
    return output.getvalue()
