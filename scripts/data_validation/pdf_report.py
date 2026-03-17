"""
Generate a PDF validation report from a validate_zip result dict.
Uses reportlab Platypus for clean, structured output.
"""
import io
import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

# ── Colour palette (mirrors the dark-UI feel in a light PDF) ──────────────
C_TEAL    = colors.HexColor("#1f6c6d")
C_GREEN   = colors.HexColor("#027a48")
C_RED     = colors.HexColor("#b42318")
C_AMBER   = colors.HexColor("#e08a00")
C_GRAY_BG = colors.HexColor("#f4f4f5")
C_BORDER  = colors.HexColor("#d1d5db")
C_WHITE   = colors.white
C_BLACK   = colors.HexColor("#111827")
C_GRAY    = colors.HexColor("#6b7280")


def _styles():
    base = getSampleStyleSheet()
    extra = {
        "Title": ParagraphStyle(
            "Title", parent=base["Normal"],
            fontSize=22, leading=26, textColor=C_BLACK, spaceAfter=4,
            fontName="Helvetica-Bold",
        ),
        "Subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"],
            fontSize=10, leading=13, textColor=C_GRAY, spaceAfter=14,
            fontName="Helvetica",
        ),
        "SectionHead": ParagraphStyle(
            "SectionHead", parent=base["Normal"],
            fontSize=12, leading=15, textColor=C_BLACK, spaceBefore=18, spaceAfter=6,
            fontName="Helvetica-Bold",
        ),
        "FileHead": ParagraphStyle(
            "FileHead", parent=base["Normal"],
            fontSize=10, leading=13, textColor=C_BLACK, spaceAfter=4,
            fontName="Helvetica-Bold",
        ),
        "Body": ParagraphStyle(
            "Body", parent=base["Normal"],
            fontSize=9, leading=12, textColor=C_BLACK,
            fontName="Helvetica",
        ),
        "Small": ParagraphStyle(
            "Small", parent=base["Normal"],
            fontSize=8, leading=10, textColor=C_GRAY,
            fontName="Helvetica",
        ),
        "IssueError": ParagraphStyle(
            "IssueError", parent=base["Normal"],
            fontSize=8.5, leading=12, textColor=C_RED,
            fontName="Helvetica",
        ),
        "IssueWarning": ParagraphStyle(
            "IssueWarning", parent=base["Normal"],
            fontSize=8.5, leading=12, textColor=C_AMBER,
            fontName="Helvetica",
        ),
        "IssueInfo": ParagraphStyle(
            "IssueInfo", parent=base["Normal"],
            fontSize=8.5, leading=12, textColor=C_GRAY,
            fontName="Helvetica",
        ),
    }
    return {**{k: base[k] for k in base.byName}, **extra}


def _summary_table(result: dict, styles: dict):
    """Verdict + error/warning/row counts as a coloured summary table."""
    ok      = result.get("ok", False)
    summary = result.get("summary", {})
    errors   = summary.get("errors", 0)
    warnings = summary.get("warnings", 0)
    total_rows = summary.get("total_rows", 0)
    files_found = sum(1 for f in result.get("files", {}).values() if f.get("found"))

    verdict_text  = "All checks passed" if ok else "Validation failed"
    verdict_color = C_GREEN if ok else C_RED

    data = [
        [
            Paragraph(f'<b>{"✓" if ok else "✗"}  {verdict_text}</b>', ParagraphStyle(
                "Vrd", fontName="Helvetica-Bold", fontSize=12,
                textColor=verdict_color, leading=15,
            )),
            Paragraph(f'<b>{errors}</b><br/><font color="#6b7280" size="7">Errors</font>',
                      ParagraphStyle("C1", fontName="Helvetica-Bold", fontSize=13,
                                     textColor=C_RED, leading=16, alignment=1)),
            Paragraph(f'<b>{warnings}</b><br/><font color="#6b7280" size="7">Warnings</font>',
                      ParagraphStyle("C2", fontName="Helvetica-Bold", fontSize=13,
                                     textColor=C_AMBER, leading=16, alignment=1)),
            Paragraph(f'<b>{total_rows:,}</b><br/><font color="#6b7280" size="7">Total Rows</font>',
                      ParagraphStyle("C3", fontName="Helvetica-Bold", fontSize=13,
                                     textColor=C_TEAL, leading=16, alignment=1)),
            Paragraph(f'<b>{files_found}</b><br/><font color="#6b7280" size="7">Files Found</font>',
                      ParagraphStyle("C4", fontName="Helvetica-Bold", fontSize=13,
                                     textColor=C_TEAL, leading=16, alignment=1)),
        ]
    ]
    col_widths = [80*mm, 25*mm, 30*mm, 28*mm, 28*mm]
    tbl = Table(data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), C_GRAY_BG),
        ("BOX",         (0, 0), (-1, -1), 0.5, C_BORDER),
        ("INNERGRID",   (0, 0), (-1, -1), 0.3, C_BORDER),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1),   10),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",(0, 0), (-1, -1), 10),
    ]))
    return tbl


def _file_table(filename: str, info: dict, styles: dict):
    """One table block per CSV file."""
    rows_val = info.get("rows", 0)
    cols_val = info.get("columns", [])
    issues   = info.get("issues", [])

    has_errors   = any(i.get("level") == "error"   for i in issues)
    has_warnings = any(i.get("level") == "warning" for i in issues)

    if not info.get("found"):
        status_color = C_GRAY
        status_text  = "Missing"
    elif has_errors:
        status_color = C_RED
        status_text  = "Error"
    elif has_warnings:
        status_color = C_AMBER
        status_text  = "Warning"
    else:
        status_color = C_GREEN
        status_text  = "OK"

    accent_color = status_color

    # Header row
    header_data = [[
        Paragraph(f'<b>{filename}</b>', ParagraphStyle(
            "FH", fontName="Helvetica-Bold", fontSize=10,
            textColor=C_BLACK, leading=13,
        )),
        Paragraph(f'<b>{status_text}</b>', ParagraphStyle(
            "ST", fontName="Helvetica-Bold", fontSize=9,
            textColor=status_color, leading=12, alignment=2,
        )),
    ]]
    tbl_header = Table(header_data, colWidths=[145*mm, 25*mm])
    tbl_header.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), C_GRAY_BG),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING",   (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
        ("LINEBELOW",    (0, 0), (-1, -1), 1.5, accent_color),
    ]))

    elems = [tbl_header]

    if not info.get("found"):
        return elems

    # Stats row
    actual = info.get("actual_filename") or filename
    bom_text = ""
    if info.get("bom") is True:
        bom_text = "  ⚠ BOM detected"
    elif info.get("bom") is False:
        bom_text = "  ✓ No BOM"

    stats_data = [[
        Paragraph(f'File: <b>{actual}</b>{bom_text}', styles["Small"]),
        Paragraph(f'Rows: <b>{rows_val:,}</b>', styles["Small"]),
        Paragraph(f'Columns: <b>{len(cols_val)}</b>', styles["Small"]),
    ]]
    tbl_stats = Table(stats_data, colWidths=[95*mm, 30*mm, 45*mm])
    tbl_stats.setStyle(TableStyle([
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    elems.append(tbl_stats)

    # Issues
    if issues:
        issue_rows = []
        for issue in issues:
            lvl = issue.get("level", "info")
            icon = "✗" if lvl == "error" else ("⚠" if lvl == "warning" else "i")
            style_key = {"error": "IssueError", "warning": "IssueWarning"}.get(lvl, "IssueInfo")
            issue_rows.append([
                Paragraph(icon, styles[style_key]),
                Paragraph(issue.get("msg", ""), styles[style_key]),
            ])
        tbl_issues = Table(issue_rows, colWidths=[6*mm, 164*mm])
        tbl_issues.setStyle(TableStyle([
            ("LEFTPADDING",  (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING",   (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ]))
        elems.append(tbl_issues)

    elems.append(Spacer(1, 6))
    return elems


def build(result: dict, zip_name: str = "data.zip") -> bytes:
    """Build the PDF and return it as bytes."""
    buf    = io.BytesIO()
    styles = _styles()
    doc    = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=18*mm,  bottomMargin=18*mm,
        title="Data Validation Report",
        author="TAM App",
    )

    story = []

    # ── Header ───────────────────────────────────────────────────────────
    story.append(Paragraph("Data Validation Report", styles["Title"]))
    story.append(Paragraph(
        f'ZIP: <b>{zip_name}</b> &nbsp;&nbsp;|&nbsp;&nbsp; '
        f'Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}',
        styles["Subtitle"],
    ))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=14))

    # ── Summary ──────────────────────────────────────────────────────────
    story.append(_summary_table(result, styles))
    story.append(Spacer(1, 18))

    # ── Per-file results ─────────────────────────────────────────────────
    story.append(Paragraph("Files", styles["SectionHead"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=8))

    for filename, info in result.get("files", {}).items():
        story.extend(_file_table(filename, info, styles))

    # ── Cross-validation ─────────────────────────────────────────────────
    story.append(Paragraph("Cross-Validation", styles["SectionHead"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=8))

    cross = result.get("cross", [])
    if cross:
        cross_rows = []
        for issue in cross:
            lvl  = issue.get("level", "info")
            icon = "✗" if lvl == "error" else ("⚠" if lvl == "warning" else "i")
            style_key = {"error": "IssueError", "warning": "IssueWarning"}.get(lvl, "IssueInfo")
            cross_rows.append([
                Paragraph(icon, styles[style_key]),
                Paragraph(issue.get("msg", ""), styles[style_key]),
            ])
        tbl_cross = Table(cross_rows, colWidths=[6*mm, 164*mm])
        tbl_cross.setStyle(TableStyle([
            ("LEFTPADDING",  (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING",   (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_WHITE, C_GRAY_BG]),
        ]))
        story.append(tbl_cross)
    else:
        story.append(Paragraph(
            "✓  All cross-file checks passed — no issues found between files.",
            ParagraphStyle("CrossOK", fontName="Helvetica", fontSize=9,
                           textColor=C_GREEN, leading=12),
        ))

    # ── Footer note ──────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=6))
    story.append(Paragraph(
        "Generated by TAM App — download links are not included in this report.",
        styles["Small"],
    ))

    doc.build(story)
    return buf.getvalue()
