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
BLUE_LIGHT = colors.HexColor("#E8F0FF")
BLUE_PALE = colors.HexColor("#F3F7FF")
LIME = colors.HexColor("#CBEA22")
INK = colors.HexColor("#142033")
MUTED = colors.HexColor("#617086")
LINE = colors.HexColor("#DCE4EE")
SURFACE = colors.HexColor("#F4F7FA")
PAPER = colors.HexColor("#FCFDFE")
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
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, width, height, stroke=0, fill=1)

    # Editorial split cover: a quiet publication area paired with a bold
    # standards panel. All elements are vector-based and remain sharp at any
    # zoom level in the Approval viewer.
    panel_width = 62 * mm
    panel_x = width - panel_width
    canvas.setFillColor(NAVY)
    canvas.rect(panel_x, 0, panel_width, height, stroke=0, fill=1)
    canvas.setFillColor(BLUE)
    canvas.rect(panel_x, height - 111 * mm, panel_width, 111 * mm, stroke=0, fill=1)

    canvas.setFillColor(BLUE_LIGHT)
    canvas.circle(width + 14 * mm, height - 43 * mm, 51 * mm, stroke=0, fill=1)
    canvas.setFillColor(BLUE)
    canvas.circle(width + 14 * mm, height - 43 * mm, 34 * mm, stroke=0, fill=1)

    canvas.setFillColor(LIME)
    canvas.rect(22 * mm, height - 25 * mm, 13 * mm, 2.6 * mm, stroke=0, fill=1)
    canvas.rect(panel_x, 0, panel_width, 4 * mm, stroke=0, fill=1)

    canvas.setFillColor(MUTED)
    canvas.setFont(FONT_BOLD, 6.8)
    canvas.drawString(
        22 * mm,
        height - 35 * mm,
        "SUSTAINABILITY DISCLOSURE SERIES",
    )
    canvas.setFont(FONT_REGULAR, 6.8)
    canvas.drawRightString(panel_x - 9 * mm, height - 35 * mm, str(document.reporting_year))

    bank_name = document.bank_name.upper()[:74]
    bank_size = 10.5
    available_bank_width = panel_x - 31 * mm
    while (
        bank_size > 8
        and pdfmetrics.stringWidth(bank_name, FONT_BOLD, bank_size)
        > available_bank_width
    ):
        bank_size -= 0.5
    canvas.setFillColor(NAVY)
    canvas.setFont(FONT_BOLD, bank_size)
    canvas.drawString(22 * mm, height - 54 * mm, bank_name)

    canvas.setFillColor(NAVY)
    canvas.setFont(FONT_BOLD, 22)
    canvas.drawString(22 * mm, height - 94 * mm, "SUSTAINABILITY-")
    canvas.drawString(22 * mm, height - 105 * mm, "RELATED FINANCIAL")
    canvas.drawString(22 * mm, height - 116 * mm, "DISCLOSURES")

    canvas.setFillColor(BLUE)
    canvas.roundRect(
        22 * mm,
        height - 137 * mm,
        49 * mm,
        10 * mm,
        5 * mm,
        stroke=0,
        fill=1,
    )
    canvas.setFillColor(WHITE)
    canvas.setFont(FONT_BOLD, 7.5)
    canvas.drawCentredString(
        46.5 * mm,
        height - 133.7 * mm,
        "IFRS S1  /  IFRS S2",
    )

    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.7)
    canvas.line(22 * mm, 88 * mm, panel_x - 10 * mm, 88 * mm)
    metadata = [
        ("REPORTING YEAR", str(document.reporting_year)),
        ("REPORT VERSION", f"{document.version_number}.0"),
        ("STATUS", "Internal review"),
    ]
    column_width = (panel_x - 32 * mm) / 3
    for index, (label, value) in enumerate(metadata):
        x = 22 * mm + index * column_width
        canvas.setFillColor(MUTED)
        canvas.setFont(FONT_BOLD, 6.4)
        canvas.drawString(x, 79 * mm, label)
        canvas.setFillColor(NAVY)
        canvas.setFont(FONT_BOLD if index < 2 else FONT_REGULAR, 9)
        canvas.drawString(x, 70 * mm, value)

    canvas.setFillColor(MUTED)
    canvas.setFont(FONT_BOLD, 6.5)
    canvas.drawString(22 * mm, 23 * mm, "CONFIDENTIAL  /  INTERNAL USE")

    canvas.setFillColor(WHITE)
    canvas.setFont(FONT_BOLD, 7)
    canvas.drawString(panel_x + 10 * mm, height - 29 * mm, "REPORTING YEAR")
    canvas.setFont(FONT_BOLD, 46)
    canvas.drawString(panel_x + 9 * mm, height - 52 * mm, str(document.reporting_year)[-2:])

    canvas.setFillColor(colors.HexColor("#9DB5D4"))
    canvas.setFont(FONT_BOLD, 7)
    canvas.drawString(panel_x + 10 * mm, 96 * mm, "ISSB STANDARDS")
    canvas.setFillColor(WHITE)
    canvas.setFont(FONT_BOLD, 31)
    canvas.drawString(panel_x + 9 * mm, 76 * mm, "S1")
    canvas.setFillColor(LIME)
    canvas.drawString(panel_x + 9 * mm, 57 * mm, "S2")
    canvas.setFillColor(colors.HexColor("#9DB5D4"))
    canvas.setFont(FONT_REGULAR, 7)
    canvas.drawString(panel_x + 10 * mm, 30 * mm, "FINANCIAL DISCLOSURES")
    canvas.restoreState()


def _draw_body_page(canvas, document):
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, width, height, stroke=0, fill=1)

    canvas.setFillColor(BLUE)
    canvas.rect(18 * mm, height - 13.1 * mm, 3.2 * mm, 3.2 * mm, stroke=0, fill=1)

    canvas.setFillColor(NAVY)
    canvas.setFont(FONT_BOLD, 7.5)
    canvas.drawString(24 * mm, height - 12 * mm, document.bank_name[:70])
    canvas.setFillColor(MUTED)
    canvas.setFont(FONT_REGULAR, 7.5)
    canvas.drawRightString(
        width - 18 * mm,
        height - 12 * mm,
        f"{document.reporting_year}  /  IFRS S1 + IFRS S2",
    )
    canvas.setStrokeColor(BLUE)
    canvas.setLineWidth(1.15)
    canvas.line(18 * mm, height - 16 * mm, 49 * mm, height - 16 * mm)
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(49 * mm, height - 16 * mm, width - 18 * mm, height - 16 * mm)

    canvas.setFillColor(SURFACE)
    canvas.rect(0, 0, width, 16 * mm, stroke=0, fill=1)
    canvas.setFillColor(LIME)
    canvas.rect(width - 45 * mm, 15.2 * mm, 27 * mm, 0.8 * mm, stroke=0, fill=1)
    canvas.setFillColor(MUTED)
    canvas.setFont(FONT_REGULAR, 7)
    canvas.drawString(18 * mm, 7 * mm, "CONFIDENTIAL  /  INTERNAL USE")
    canvas.setFillColor(BLUE)
    canvas.roundRect(
        width - 31 * mm,
        4.1 * mm,
        13 * mm,
        7.8 * mm,
        3.9 * mm,
        stroke=0,
        fill=1,
    )
    canvas.setFillColor(WHITE)
    canvas.setFont(FONT_BOLD, 7.5)
    canvas.drawCentredString(
        width - 24.5 * mm,
        6.6 * mm,
        f"{canvas.getPageNumber():02d}",
    )
    canvas.restoreState()


def _draw_divider_page(canvas, document):
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, width, height, stroke=0, fill=1)

    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, 52 * mm, height, stroke=0, fill=1)
    canvas.setFillColor(BLUE)
    canvas.rect(52 * mm, height - 5 * mm, width - 52 * mm, 5 * mm, stroke=0, fill=1)
    canvas.setFillColor(BLUE_PALE)
    canvas.circle(width + 6 * mm, height - 45 * mm, 55 * mm, stroke=0, fill=1)
    canvas.setStrokeColor(BLUE_LIGHT)
    canvas.setLineWidth(12)
    canvas.circle(width + 8 * mm, height - 47 * mm, 38 * mm, stroke=1, fill=0)
    canvas.setFillColor(LIME)
    canvas.rect(0, 0, 52 * mm, 4 * mm, stroke=0, fill=1)

    canvas.saveState()
    canvas.translate(20 * mm, 41 * mm)
    canvas.rotate(90)
    canvas.setFillColor(colors.HexColor("#91A8C3"))
    canvas.setFont(FONT_BOLD, 7)
    canvas.drawString(0, 0, "SUSTAINABILITY-RELATED FINANCIAL DISCLOSURES")
    canvas.restoreState()

    canvas.setFillColor(MUTED)
    canvas.setFont(FONT_REGULAR, 7)
    canvas.drawString(70 * mm, 15 * mm, "CONFIDENTIAL  /  INTERNAL USE")
    canvas.setFillColor(NAVY)
    canvas.setFont(FONT_BOLD, 7.5)
    canvas.drawRightString(
        width - 18 * mm,
        15 * mm,
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
        self.report_title = title

        width, height = A4
        cover_frame = Frame(
            22 * mm,
            20 * mm,
            width - 44 * mm,
            height - 40 * mm,
            id="cover-frame",
            showBoundary=0,
        )
        body_frame = Frame(
            18 * mm,
            18 * mm,
            width - 36 * mm,
            height - 39 * mm,
            id="body-frame",
            showBoundary=0,
        )
        divider_frame = Frame(
            70 * mm,
            42 * mm,
            width - 88 * mm,
            height - 84 * mm,
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
        fontSize=9,
        leading=14,
        textColor=INK,
        spaceAfter=7.5,
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
        "eyebrow": ParagraphStyle(
            "Eyebrow",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=7,
            leading=10,
            textColor=BLUE,
            spaceAfter=7,
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
            fontSize=24,
            leading=29,
            textColor=NAVY,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "h1": ParagraphStyle(
            "Heading1",
            parent=sample["Heading1"],
            fontName=FONT_BOLD,
            fontSize=18,
            leading=22,
            textColor=NAVY,
            spaceBefore=11,
            spaceAfter=8,
            keepWithNext=True,
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
            textColor=NAVY_LIGHT,
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
        "meta_label": ParagraphStyle(
            "MetaLabel",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=7.2,
            leading=10,
            textColor=NAVY,
        ),
        "meta_value": ParagraphStyle(
            "MetaValue",
            parent=body,
            fontSize=8.2,
            leading=11,
            textColor=INK,
        ),
        "meta_card_label": ParagraphStyle(
            "MetaCardLabel",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=6.4,
            leading=9,
            textColor=MUTED,
        ),
        "meta_card_value": ParagraphStyle(
            "MetaCardValue",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=11,
            leading=14,
            textColor=NAVY,
        ),
        "card_title": ParagraphStyle(
            "CardTitle",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=8.5,
            leading=12,
            textColor=NAVY,
            spaceAfter=5,
        ),
        "card_body": ParagraphStyle(
            "CardBody",
            parent=body,
            fontSize=8,
            leading=12,
            textColor=MUTED,
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
            borderWidth=0.8,
            borderPadding=7,
            backColor=BLUE_PALE,
            spaceBefore=4,
            spaceAfter=9,
        ),
        "divider_number": ParagraphStyle(
            "DividerNumber",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=9,
            leading=12,
            textColor=BLUE,
            spaceAfter=14,
        ),
        "divider_title": ParagraphStyle(
            "DividerTitle",
            parent=body,
            fontName=FONT_BOLD,
            fontSize=30,
            leading=35,
            textColor=NAVY,
            spaceAfter=14,
        ),
        "divider_subtitle": ParagraphStyle(
            "DividerSubtitle",
            parent=body,
            fontSize=10,
            leading=15,
            textColor=MUTED,
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
            Paragraph(_inline_markdown(label.upper()), styles["meta_label"]),
            Paragraph(_inline_markdown(value), styles["meta_value"]),
        ]
        for label, value in rows
    ]
    table = Table(formatted, colWidths=[43 * mm, 116 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), BLUE_PALE),
                ("BACKGROUND", (1, 0), (1, -1), WHITE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBEFORE", (0, 0), (0, -1), 2.2, BLUE),
                ("LINEBELOW", (0, 0), (-1, -1), 0.45, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6.5),
            ]
        )
    )
    return table


def _metadata_summary_cards(*, reporting_year, version_number, styles):
    labels = ["REPORTING YEAR", "REPORT VERSION", "DOCUMENT STATUS"]
    values = [str(reporting_year), f"{version_number}.0", "Internal review"]
    table = Table(
        [
            [
                Paragraph(label, styles["meta_card_label"])
                for label in labels
            ],
            [
                Paragraph(value, styles["meta_card_value"])
                for value in values
            ],
        ],
        colWidths=[53 * mm, 53 * mm, 53 * mm],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("LINEABOVE", (0, 0), (-1, 0), 2.2, BLUE),
                ("LINEBEFORE", (1, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                ("TOPPADDING", (0, 1), (-1, 1), 1),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
            ]
        )
    )
    return table


def _purpose_cards(styles):
    cards = [
        (
            "ABOUT THIS PUBLICATION",
            "This report supports the institution's controlled sustainability "
            "reporting and internal review process under IFRS S1 and IFRS S2.",
        ),
        (
            "REVIEW CONTROL",
            "Approval status is controlled in the platform. Downloaded copies "
            "should be checked against the latest report version before use.",
        ),
    ]
    cells = []
    for title, text in cards:
        cells.append(
            [
                Paragraph(title, styles["card_title"]),
                Paragraph(text, styles["card_body"]),
            ]
        )

    table = Table(
        [[cells[0], cells[1]]],
        colWidths=[77 * mm, 77 * mm],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), BLUE_PALE),
                ("BACKGROUND", (1, 0), (1, 0), SURFACE),
                ("LINEABOVE", (0, 0), (0, 0), 2.2, BLUE),
                ("LINEABOVE", (1, 0), (1, 0), 2.2, LIME),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LINEBEFORE", (1, 0), (1, 0), 5, WHITE),
            ]
        )
    )
    return table


def _append_major_section(story, section_number, section_title, styles, bookmark_index):
    story.extend(
        [
            NextPageTemplate("divider"),
            PageBreak(),
            Spacer(1, 50 * mm),
            Paragraph(
                f"SECTION  /  {section_number:02d}",
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
                width=28 * mm,
                thickness=2.5,
                color=BLUE,
                hAlign="LEFT",
                spaceBefore=2,
                spaceAfter=14,
            ),
            Paragraph(
                "Decision-useful sustainability-related financial information "
                "prepared for internal review under the IFRS S1 and IFRS S2 "
                "framework.",
                styles["divider_subtitle"],
            ),
            NextPageTemplate("body"),
            PageBreak(),
            Paragraph(
                f"{section_number:02d}  /  DISCLOSURE SECTION",
                styles["eyebrow"],
            ),
            Paragraph(_inline_markdown(section_title), styles["h1"]),
            HRFlowable(
                width=29 * mm,
                thickness=2,
                color=LIME,
                hAlign="LEFT",
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
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, NAVY),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
            for row_index in range(1, len(rows)):
                if row_index % 2 == 0:
                    table_style.append(
                        ("BACKGROUND", (0, row_index), (-1, row_index), BLUE_PALE)
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

    toc = TableOfContents()
    toc.levelStyles = [
        styles["toc_0"],
        styles["toc_1"],
        styles["toc_2"],
    ]
    toc.dotsMinLevel = 0

    story = [
        NextPageTemplate("body"),
        PageBreak(),
        Paragraph("01  /  DOCUMENT CONTROL", styles["eyebrow"]),
        Paragraph("Report profile", styles["page_title"]),
        Paragraph(
            "Identity, status and controlled-use information for this "
            "sustainability-related financial disclosure report.",
            styles["lead"],
        ),
        Spacer(1, 2 * mm),
        _metadata_summary_cards(
            reporting_year=reporting_year,
            version_number=version_number,
            styles=styles,
        ),
        Spacer(1, 8 * mm),
        Paragraph("Document register", styles["h2"]),
        _document_information_table(
            title=title,
            bank_name=bank_name,
            reporting_year=reporting_year,
            version_number=version_number,
            styles=styles,
        ),
        Spacer(1, 9 * mm),
        _purpose_cards(styles),
        PageBreak(),
        Paragraph("02  /  NAVIGATION", styles["eyebrow"]),
        Paragraph("Inside this report", styles["page_title"]),
        Paragraph(
            "A structured view of the five IFRS disclosure areas and their "
            "supporting subsections.",
            styles["lead"],
        ),
        HRFlowable(
            width=32 * mm,
            thickness=2.2,
            color=BLUE,
            hAlign="LEFT",
            spaceAfter=8,
        ),
        toc,
        PageBreak(),
    ]

    _append_markdown_body(story, markdown_text, styles)
    document.multiBuild(story)
    return output.getvalue()
