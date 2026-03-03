"""
PPT Builder — Layout-Intelligent renderer powered by python-pptx.

Every slide passes through LayoutIntelligenceLayer before rendering, which
guarantees: no element overlap, compressed content, correct font sizes,
clamped image bounding boxes, and chart/table routing.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

from layout_engine import (
    LayoutIntelligenceLayer,
    SLIDE_W, SLIDE_H,
    MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM,
    CONTENT_LEFT, CONTENT_TOP, CONTENT_W, CONTENT_H,
    MAX_BULLETS, MAX_TABLE_COLS, MAX_TABLE_ROWS,
    MAX_TIMELINE_PHASES, MAX_CHART_BARS,
    compress_headline, compress_bullets,
    headline_font, bullet_font, metric_font,
    get_layout,
)
from chart_engine import generate_chart

logger = logging.getLogger(__name__)

# ── Layout layer singleton ───────────────────────────────────────────────────

_layout_layer = LayoutIntelligenceLayer()

# ── Theme palettes ───────────────────────────────────────────────────────────

THEMES: Dict[str, Dict[str, str]] = {
    "professional": {
        "primary": "0052CC",
        "secondary": "003366",
        "accent": "0052CC",
        "text": "1A1A1A",
        "light_text": "666666",
        "bg": "FFFFFF",
        "panel": "F5F7FA",
        "dark_bg": "0A1628",
        "card_bg": "F0F4F8",
        "table_header": "0052CC",
        "table_alt": "F0F4F8",
        "chart_bg": "F5F7FA",
    },
    "modern": {
        "primary": "E94D35",
        "secondary": "C43A27",
        "accent": "E94D35",
        "text": "1A1A1A",
        "light_text": "666666",
        "bg": "FFFFFF",
        "panel": "FFF5F2",
        "dark_bg": "1A0A06",
        "card_bg": "FFF0EB",
        "table_header": "E94D35",
        "table_alt": "FFF5F2",
        "chart_bg": "FFF5F2",
    },
    "dark": {
        "primary": "7C3AED",
        "secondary": "A78BFA",
        "accent": "7C3AED",
        "text": "1A1A1A",
        "light_text": "666666",
        "bg": "FFFFFF",
        "panel": "F5F0FF",
        "dark_bg": "0F0524",
        "card_bg": "F0EBFF",
        "table_header": "7C3AED",
        "table_alt": "F5F0FF",
        "chart_bg": "F5F0FF",
    },
    "creative": {
        "primary": "F97316",
        "secondary": "D9480F",
        "accent": "F97316",
        "text": "1A1A1A",
        "light_text": "666666",
        "bg": "FFFFFF",
        "panel": "FFF8F0",
        "dark_bg": "1A0E00",
        "card_bg": "FFF0E0",
        "table_header": "F97316",
        "table_alt": "FFF8F0",
        "chart_bg": "FFF8F0",
    },
    "minimal": {
        "primary": "111111",
        "secondary": "444444",
        "accent": "111111",
        "text": "111111",
        "light_text": "777777",
        "bg": "FFFFFF",
        "panel": "F5F5F5",
        "dark_bg": "111111",
        "card_bg": "F0F0F0",
        "table_header": "333333",
        "table_alt": "F5F5F5",
        "chart_bg": "F5F5F5",
    },
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _rgb(hex_str: str) -> RGBColor:
    return RGBColor.from_string(hex_str)


def _get_theme(theme_name: str) -> Dict[str, str]:
    return THEMES.get(theme_name, THEMES["professional"])


def _get_font_size(slide: Dict[str, Any], key: str, fallback: int) -> int:
    """Read font size from _layout metadata attached by LayoutIntelligenceLayer."""
    layout_meta = slide.get("_layout", {})
    fonts = layout_meta.get("fonts", {})
    spec = fonts.get(key, {})
    return spec.get("size", fallback)


def _get_image_bbox(slide: Dict[str, Any]):
    """Return (left, top, width, height) tuple from _layout metadata, or None."""
    layout_meta = slide.get("_layout", {})
    bbox = layout_meta.get("image_bbox")
    if bbox:
        return bbox["left"], bbox["top"], bbox["width"], bbox["height"]
    return None


def _add_shape(
    sld,
    left: float,
    top: float,
    width: float,
    height: float,
    fill_hex: str,
    *,
    shape_type=MSO_SHAPE.RECTANGLE,
    alpha: Optional[int] = None,
) -> Any:
    shape = sld.shapes.add_shape(shape_type, Inches(left), Inches(top), Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(fill_hex)
    shape.line.fill.background()
    if alpha is not None:
        from lxml import etree
        ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
        solid = shape.fill._fill.find(f"{{{ns}}}solidFill")
        if solid is not None:
            srgb = solid.find(f"{{{ns}}}srgbClr")
            if srgb is not None:
                a_el = etree.SubElement(srgb, f"{{{ns}}}alpha")
                a_el.set("val", str(alpha))
    return shape


def _add_text_box(
    sld,
    left: float,
    top: float,
    width: float,
    height: float,
    text: str,
    *,
    font_size: int = 18,
    font_color: str = "1A1A1A",
    bold: bool = False,
    alignment=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
) -> Any:
    txBox = sld.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = txBox.text_frame
    tf.word_wrap = True
    tf.auto_size = None

    try:
        txBox.anchor = anchor
    except Exception:
        pass

    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.color.rgb = _rgb(font_color)
    p.font.bold = bold
    p.alignment = alignment
    return txBox


def _add_layout_image(sld, image_path: str, slide: Dict[str, Any], fallback_box=None):
    """Add image using layout-computed bounding box, with fallback position."""
    bbox = _get_image_bbox(slide)
    if bbox:
        left, top, w, h = bbox
    elif fallback_box:
        left, top, w, h = fallback_box
    else:
        left, top, w, h = 8.5, 1.5, 4.3, 4.3

    if image_path and os.path.isfile(image_path):
        try:
            sld.shapes.add_picture(image_path, Inches(left), Inches(top), Inches(w), Inches(h))
        except Exception as exc:
            logger.warning("Could not add image: %s", exc)


def _add_headline(sld, headline: str, theme: Dict[str, str], slide: Dict[str, Any]):
    """Render the headline + accent bar using layout fonts."""
    headline = compress_headline(headline)
    font_size = _get_font_size(slide, "headline", 24)
    _add_text_box(sld, MARGIN_LEFT, MARGIN_TOP, CONTENT_W, 0.8, headline,
                  font_size=font_size, font_color=theme["text"], bold=True)
    _add_shape(sld, MARGIN_LEFT, 1.1, 1.5, 0.04, theme["accent"])


def _add_footer_bar(sld, theme: Dict[str, str]):
    _add_shape(sld, 0, SLIDE_H - 0.06, SLIDE_W, 0.06, theme["primary"])


# ── Slide renderers ─────────────────────────────────────────────────────────

def _render_title(sld, slide, image, theme):
    t = theme
    content = slide.get("content", {})
    headline = compress_headline(slide.get("headline", ""))
    subtitle = content.get("subtitle", "")
    date_ = content.get("date", "")
    presenter = content.get("presenter", "")

    # Top bar
    _add_shape(sld, 0, 0, SLIDE_W, 0.18, t["primary"])
    # Left stripe
    _add_shape(sld, 0.8, 2.0, 0.08, 1.8, t["accent"])
    # Title
    font_size = _get_font_size(slide, "headline", 44)
    _add_text_box(sld, 1.2, 2.0, 10.5, 1.8, headline,
                  font_size=font_size, font_color=t["text"], bold=True)
    # Accent line
    _add_shape(sld, 1.2, 3.7, 2.5, 0.04, t["accent"])
    # Subtitle
    if subtitle:
        _add_text_box(sld, 1.2, 4.0, 9.0, 0.7, subtitle,
                      font_size=22, font_color=t["light_text"])
    # Meta line
    meta = f"{date_}  |  {presenter}" if date_ and presenter else (date_ or presenter)
    if meta:
        _add_text_box(sld, 1.2, 5.0, 9.0, 0.5, meta,
                      font_size=14, font_color=t["light_text"])
    # Image
    _add_layout_image(sld, image, slide, fallback_box=(9.5, 2.0, 3.3, 3.3))
    _add_footer_bar(sld, t)


def _render_section_divider(sld, slide, image, theme):
    t = theme
    content = slide.get("content", {})
    title = content.get("section_title", slide.get("headline", ""))
    subtitle = content.get("section_subtitle", "")

    # Dark background
    _add_shape(sld, 0, 0, SLIDE_W, SLIDE_H, t["dark_bg"])
    # Top/bottom stripe
    _add_shape(sld, 0, 0, SLIDE_W, 0.12, t["primary"])
    _add_shape(sld, 0, SLIDE_H - 0.12, SLIDE_W, 0.12, t["primary"])
    # Title
    _add_text_box(sld, 1.5, 2.2, 10.3, 1.5, title,
                  font_size=52, font_color="FFFFFF", bold=True, alignment=PP_ALIGN.CENTER)
    # Accent bar
    _add_shape(sld, 5.5, 3.8, 2.3, 0.06, t["accent"])
    # Subtitle
    if subtitle:
        _add_text_box(sld, 2.0, 4.2, 9.3, 0.8, subtitle,
                      font_size=22, font_color="CCCCCC", alignment=PP_ALIGN.CENTER)


def _render_big_number(sld, slide, image, theme):
    t = theme
    content = slide.get("content", {})
    headline = slide.get("headline", "")
    metric = content.get("primary_metric", "N/A")
    descriptor = content.get("descriptor", "")
    supporting = content.get("supporting_line", "")

    _add_headline(sld, headline, t, slide)
    # Panel
    _add_shape(sld, 0.6, 1.4, 7.5, 5.2, t["panel"])
    # Metric
    metric_size = _get_font_size(slide, "metric", 80)
    _add_text_box(sld, 1.2, 2.0, 6.5, 2.0, metric,
                  font_size=metric_size, font_color=t["primary"], bold=True, alignment=PP_ALIGN.LEFT)
    # Descriptor
    _add_text_box(sld, 1.2, 4.0, 6.5, 0.7, descriptor,
                  font_size=28, font_color=t["text"], bold=True)
    # Supporting
    if supporting:
        _add_text_box(sld, 1.2, 4.9, 6.5, 0.6, supporting,
                      font_size=18, font_color=t["light_text"])
    _add_footer_bar(sld, t)


def _render_chart_slide(sld, slide, image, theme, *, theme_name: str = "professional"):
    t = theme
    content = slide.get("content", {})
    headline = slide.get("headline", "")
    chart_message = content.get("chart_message", "")
    data_points = content.get("data_points", [])[:MAX_CHART_BARS]

    _add_headline(sld, headline, t, slide)

    # Chart panel background
    _add_shape(sld, 0.6, 1.4, 7.5, 5.5, t.get("chart_bg", t["panel"]))

    # Chart message
    if chart_message:
        _add_text_box(sld, 0.8, 1.5, 7.0, 0.5, chart_message,
                      font_size=13, font_color=t["light_text"], bold=True)

    # Generate matplotlib chart
    chart_dir = os.path.join(os.path.dirname(__file__), "static", "charts")
    os.makedirs(chart_dir, exist_ok=True)
    slide_num = slide.get("slide_number", 1)
    chart_path = os.path.join(chart_dir, f"chart_slide_{slide_num}.png")

    chart_file = generate_chart(content, theme_name, chart_path)
    if chart_file and os.path.isfile(chart_file):
        try:
            sld.shapes.add_picture(chart_file, Inches(0.9), Inches(2.1), Inches(6.8), Inches(4.4))
        except Exception as exc:
            logger.warning("Chart image failed: %s — falling back to inline bars", exc)
            _render_inline_bars(sld, data_points, t)
    else:
        _render_inline_bars(sld, data_points, t)

    # Image on the right (if available)
    _add_layout_image(sld, image, slide, fallback_box=(8.5, 1.5, 4.3, 5.0))
    _add_footer_bar(sld, t)


def _render_inline_bars(sld, data_points: List, theme: Dict[str, str]):
    """Fallback inline bar rendering when matplotlib chart fails."""
    bar_x = 1.0
    bar_y = 2.2
    bar_max_w = 5.5
    bar_h = 0.45
    gap = 0.15

    max_val = 1.0
    parsed = []
    for dp in data_points[:MAX_CHART_BARS]:
        if isinstance(dp, dict):
            label = str(dp.get("label", dp.get("name", "")))
            val_str = str(dp.get("value", "50"))
        elif isinstance(dp, str) and ":" in dp:
            parts = dp.split(":", 1)
            label, val_str = parts[0].strip(), parts[1].strip()
        else:
            label, val_str = str(dp), "50"
        try:
            val = float("".join(c for c in val_str if c.isdigit() or c == ".") or "50")
        except ValueError:
            val = 50
        parsed.append((label, val, val_str))
        max_val = max(max_val, val)

    for i, (label, val, raw) in enumerate(parsed):
        y = bar_y + i * (bar_h + gap)
        _add_text_box(sld, bar_x - 0.1, y, 1.8, bar_h, label,
                      font_size=11, font_color=theme["text"], bold=True)
        w = max(0.3, (val / max_val) * bar_max_w) if max_val > 0 else 0.5
        _add_shape(sld, bar_x + 1.9, y + 0.05, w, bar_h - 0.1, theme["primary"])
        _add_text_box(sld, bar_x + 2.0 + w, y, 1.0, bar_h, raw,
                      font_size=11, font_color=theme["text"], bold=True)


def _render_table_slide(sld, slide, image, theme):
    t = theme
    content = slide.get("content", {})
    headline = slide.get("headline", "")
    table_title = content.get("table_title", "")
    columns = content.get("columns", [])[:MAX_TABLE_COLS]
    rows = content.get("rows", [])

    _add_headline(sld, headline, t, slide)

    if table_title:
        _add_text_box(sld, 0.8, 1.4, 8.0, 0.5, table_title,
                      font_size=14, font_color=t["text"], bold=True)

    if not columns:
        columns = ["Column 1", "Column 2", "Column 3"]

    rows = [r[:MAX_TABLE_COLS] for r in rows[:MAX_TABLE_ROWS]]
    n_rows = len(rows) + 1
    n_cols = len(columns)

    tbl_left = Inches(0.8)
    tbl_top = Inches(2.0)
    tbl_w = Inches(11.5)
    tbl_h = Inches(min(4.5, 0.55 * n_rows + 0.3))

    table_shape = sld.shapes.add_table(n_rows, n_cols, tbl_left, tbl_top, tbl_w, tbl_h)
    table = table_shape.table

    col_w = int(tbl_w / n_cols) if n_cols else tbl_w
    for ci in range(n_cols):
        table.columns[ci].width = col_w

    # Header row
    for ci, col_name in enumerate(columns):
        cell = table.cell(0, ci)
        cell.text = str(col_name)
        for p in cell.text_frame.paragraphs:
            p.font.size = Pt(12)
            p.font.bold = True
            p.font.color.rgb = _rgb("FFFFFF")
            p.alignment = PP_ALIGN.CENTER
        cell.fill.solid()
        cell.fill.fore_color.rgb = _rgb(t["table_header"])
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE

    # Data rows
    for ri, row_data in enumerate(rows):
        for ci in range(n_cols):
            cell = table.cell(ri + 1, ci)
            cell.text = str(row_data[ci]) if ci < len(row_data) else ""
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(11)
                p.font.color.rgb = _rgb(t["text"])
                p.alignment = PP_ALIGN.CENTER
            if ri % 2 == 1:
                cell.fill.solid()
                cell.fill.fore_color.rgb = _rgb(t["table_alt"])
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE

    _add_footer_bar(sld, t)


def _render_two_column(sld, slide, image, theme):
    t = theme
    content = slide.get("content", {})
    headline = slide.get("headline", "")
    left_header = content.get("left_header", "")
    left_points = compress_bullets(content.get("left_points", []))
    right_header = content.get("right_header", "")
    right_points = compress_bullets(content.get("right_points", []))

    panel_h = 5.2

    _add_headline(sld, headline, t, slide)

    # Left panel
    _add_shape(sld, 0.6, 1.4, 5.8, panel_h, t["panel"])
    if left_header:
        _add_shape(sld, 0.6, 1.4, 5.8, 0.55, t["primary"])
        _add_text_box(sld, 0.8, 1.42, 5.4, 0.5, left_header,
                      font_size=14, font_color="FFFFFF", bold=True)

    bullet_size = _get_font_size(slide, "bullets", 17)
    for i, bp in enumerate(left_points):
        _add_text_box(sld, 0.9, 2.2 + i * 0.7, 5.2, 0.6, f"▸  {bp}",
                      font_size=bullet_size, font_color=t["text"])

    # Divider
    _add_shape(sld, 6.55, 1.4, 0.03, panel_h, t["accent"])

    # Right panel
    _add_shape(sld, 6.7, 1.4, 5.8, panel_h, t["panel"])
    if right_header:
        _add_shape(sld, 6.7, 1.4, 5.8, 0.55, t["primary"])
        _add_text_box(sld, 6.9, 1.42, 5.4, 0.5, right_header,
                      font_size=14, font_color="FFFFFF", bold=True)

    for i, bp in enumerate(right_points):
        _add_text_box(sld, 7.0, 2.2 + i * 0.7, 5.2, 0.6, f"▸  {bp}",
                      font_size=bullet_size, font_color=t["text"])

    _add_footer_bar(sld, t)


def _render_comparison(sld, slide, image, theme):
    t = theme
    content = slide.get("content", {})
    headline = slide.get("headline", "")
    left_label = content.get("left_label", "Before")
    left_points = compress_bullets(content.get("left_points", []))
    right_label = content.get("right_label", "After")
    right_points = compress_bullets(content.get("right_points", []))

    _add_headline(sld, headline, t, slide)

    # Left column
    _add_shape(sld, 0.8, 1.6, 5.5, 0.55, t["panel"])
    _add_text_box(sld, 1.0, 1.62, 5.1, 0.5, left_label,
                  font_size=16, font_color=t["primary"], bold=True, alignment=PP_ALIGN.CENTER)
    _add_shape(sld, 0.8, 2.3, 5.5, 4.2, t["panel"])

    bullet_size = _get_font_size(slide, "bullets", 16)
    for i, bp in enumerate(left_points):
        _add_text_box(sld, 1.0, 2.5 + i * 0.7, 5.0, 0.6, f"▸  {bp}",
                      font_size=bullet_size, font_color=t["text"])

    # Divider
    _add_shape(sld, 6.5, 1.6, 0.03, 5.0, t["accent"])

    # Right column
    _add_shape(sld, 7.0, 1.6, 5.5, 0.55, t["panel"])
    _add_text_box(sld, 7.2, 1.62, 5.1, 0.5, right_label,
                  font_size=16, font_color=t["primary"], bold=True, alignment=PP_ALIGN.CENTER)
    _add_shape(sld, 7.0, 2.3, 5.5, 4.2, t["panel"])

    for i, bp in enumerate(right_points):
        _add_text_box(sld, 7.2, 2.5 + i * 0.7, 5.0, 0.6, f"▸  {bp}",
                      font_size=bullet_size, font_color=t["text"])

    _add_footer_bar(sld, t)


def _render_timeline(sld, slide, image, theme):
    t = theme
    content = slide.get("content", {})
    headline = slide.get("headline", "")
    phases = content.get("phases", [])[:MAX_TIMELINE_PHASES]

    _add_headline(sld, headline, t, slide)

    # Timeline panel
    _add_shape(sld, 0.6, 1.8, 12.0, 5.0, t["panel"])
    # Connector line
    _add_shape(sld, 0.8, 3.5, 11.5, 0.05, t["accent"])

    n = max(len(phases), 1)
    card_w = min(2.8, (11.5 - 0.3 * (n - 1)) / n)

    for i, phase in enumerate(phases):
        name = phase.get("name", f"Phase {i+1}") if isinstance(phase, dict) else str(phase)
        desc = phase.get("description", "") if isinstance(phase, dict) else ""

        x = 0.8 + i * (card_w + 0.3)
        # Circle node
        _add_shape(sld, x + card_w / 2 - 0.15, 3.35, 0.3, 0.3, t["primary"],
                   shape_type=MSO_SHAPE.OVAL)
        # Phase label above
        _add_text_box(sld, x, 2.2, card_w, 0.5, name,
                      font_size=14, font_color=t["primary"], bold=True, alignment=PP_ALIGN.CENTER)
        # Description below
        if desc:
            _add_text_box(sld, x, 4.0, card_w, 0.8, desc,
                          font_size=12, font_color=t["text"], alignment=PP_ALIGN.CENTER)

    _add_footer_bar(sld, t)


def _render_case_study(sld, slide, image, theme):
    t = theme
    content = slide.get("content", {})
    headline = slide.get("headline", "")
    company = content.get("company", "")
    use_case = content.get("use_case", "")
    metrics = content.get("impact_metrics", [])[:3]

    _add_headline(sld, headline, t, slide)

    # Badge
    _add_shape(sld, 0.8, 1.5, 1.8, 0.35, t["accent"])
    _add_text_box(sld, 0.85, 1.52, 1.7, 0.3, "CASE STUDY",
                  font_size=10, font_color="FFFFFF", bold=True, alignment=PP_ALIGN.CENTER)

    # Company
    _add_text_box(sld, 0.8, 2.1, 7.0, 0.7, company,
                  font_size=32, font_color=t["text"], bold=True)
    # Use case
    if use_case:
        _add_text_box(sld, 0.8, 2.9, 7.0, 0.8, use_case,
                      font_size=16, font_color=t["light_text"])

    # Metric cards
    card_w = 3.5
    gap = 0.15
    for i, m in enumerate(metrics):
        x = 0.8 + i * (card_w + gap)
        _add_shape(sld, x, 4.2, card_w, 2.0, t["card_bg"])
        label = m if isinstance(m, str) else str(m)
        _add_text_box(sld, x + 0.2, 4.5, card_w - 0.4, 1.4, label,
                      font_size=14, font_color=t["text"], bold=True, alignment=PP_ALIGN.CENTER)

    # Image
    _add_layout_image(sld, image, slide, fallback_box=(8.5, 1.5, 4.3, 4.3))
    _add_footer_bar(sld, t)


def _render_insight_blocks(sld, slide, image, theme):
    t = theme
    content = slide.get("content", {})
    headline = slide.get("headline", "")
    blocks = content.get("blocks", [])[:3]

    _add_headline(sld, headline, t, slide)

    card_w = 3.6
    gap = 0.25

    for i, block in enumerate(blocks):
        x = 0.8 + i * (card_w + gap)
        _add_shape(sld, x, 1.6, card_w, 4.5, t["card_bg"])
        # Top accent bar
        _add_shape(sld, x, 1.6, card_w, 0.06, t["primary"])

        title = block.get("title", "") if isinstance(block, dict) else str(block)
        value = block.get("value", "") if isinstance(block, dict) else ""
        desc = block.get("description", "") if isinstance(block, dict) else ""

        _add_text_box(sld, x + 0.3, 2.0, card_w - 0.6, 0.5, title,
                      font_size=14, font_color=t["text"], bold=True)
        if value:
            _add_text_box(sld, x + 0.3, 2.7, card_w - 0.6, 1.2, value,
                          font_size=36, font_color=t["primary"], bold=True)
        if desc:
            _add_text_box(sld, x + 0.3, 4.2, card_w - 0.6, 1.2, desc,
                          font_size=12, font_color=t["light_text"])

    _add_footer_bar(sld, t)


def _render_insight_bullets(sld, slide, image, theme):
    t = theme
    content = slide.get("content", {})
    headline = slide.get("headline", "")
    bullets = compress_bullets(content.get("bullets", []))

    has_image = bool(image and os.path.isfile(image))
    text_w = 6.8 if has_image else 11.5

    _add_headline(sld, headline, t, slide)
    # Panel
    _add_shape(sld, 0.6, 1.4, text_w, 4.8, t["panel"])

    bullet_size = _get_font_size(slide, "bullets", 18)
    for i, bp in enumerate(bullets):
        _add_text_box(sld, 0.8, 1.6 + i * 0.8, text_w - 0.3, 0.7, f"▸  {bp}",
                      font_size=bullet_size, font_color=t["text"])

    # Image
    if has_image:
        _add_layout_image(sld, image, slide, fallback_box=(8.2, 1.5, 4.5, 4.5))

    _add_footer_bar(sld, t)


def _render_closing(sld, slide, image, theme):
    t = theme
    content = slide.get("content", {})
    headline = slide.get("headline", "Key Takeaways & Next Steps")
    takeaways = compress_bullets(content.get("key_takeaways", content.get("bullets", [])), max_count=5)

    # Top bar
    _add_shape(sld, 0, 0, SLIDE_W, 0.18, t["primary"])
    # Headline
    font_size = _get_font_size(slide, "headline", 36)
    _add_text_box(sld, 1.0, 1.2, 11.0, 1.0, compress_headline(headline),
                  font_size=font_size, font_color=t["text"], bold=True)
    # Accent line
    _add_shape(sld, 1.0, 2.1, 2.0, 0.04, t["accent"])

    for i, tk in enumerate(takeaways):
        _add_text_box(sld, 1.0, 2.8 + i * 0.7, 10.0, 0.6, f"▸  {tk}",
                      font_size=18, font_color=t["text"])

    # Image
    _add_layout_image(sld, image, slide, fallback_box=(9.0, 4.5, 3.5, 2.5))
    _add_footer_bar(sld, t)


# ── Renderer registry ───────────────────────────────────────────────────────

RENDERERS = {
    "title": _render_title,
    "section_divider": _render_section_divider,
    "big_number": _render_big_number,
    "chart_slide": _render_chart_slide,
    "chart": _render_chart_slide,
    "table_slide": _render_table_slide,
    "two_column": _render_two_column,
    "comparison": _render_comparison,
    "timeline": _render_timeline,
    "case_study": _render_case_study,
    "insight_blocks": _render_insight_blocks,
    "insight_bullets": _render_insight_bullets,
    "closing": _render_closing,
}


# ── Main entry point ────────────────────────────────────────────────────────

def build_pptx(
    slides: List[Dict[str, Any]],
    images: List[str],
    theme_name: str,
    title: str,
    output_path: str,
) -> str:
    """Build a .pptx file from slide dicts and image paths.

    1. Runs LayoutIntelligenceLayer.process_deck() to attach _layout metadata
    2. Dispatches each slide to its registered renderer
    3. Returns the output_path
    """
    theme = _get_theme(theme_name)

    # ── Layout intelligence pass ──────────────────────────────────────────
    slides = _layout_layer.process_deck(slides, images)

    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)
    blank_layout = prs.slide_layouts[6]

    for idx, slide in enumerate(slides):
        sld = prs.slides.add_slide(blank_layout)
        slide_type = slide.get("slide_type", "insight_bullets")
        image_path = images[idx] if idx < len(images) else ""

        renderer = RENDERERS.get(slide_type, _render_insight_bullets)

        # chart_slide needs theme_name for matplotlib palette
        if slide_type in ("chart_slide", "chart"):
            renderer(sld, slide, image_path, theme, theme_name=theme_name)
        else:
            renderer(sld, slide, image_path, theme)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    prs.save(output_path)
    logger.info("Saved presentation to %s (%d slides)", output_path, len(slides))
    return output_path
