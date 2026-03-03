"""
Layout Intelligence Layer — production-grade layout engine for agentic PPT.

Responsibilities:
  1. Map slide_type → layout template with safe bounding boxes
  2. Enforce grid-based positioning on a 13.333 × 7.5 inch slide
  3. Prevent element overlap via bounding-box collision detection
  4. Decide visual type per slide (image / chart / table / none)
  5. Scale fonts dynamically based on content length
  6. Compress overflowing content automatically
  7. Enforce design-system margins, whitespace, and max-bullet rules
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

# ── Slide dimensions (inches) ────────────────────────────────────────────────

SLIDE_W: float = 13.333
SLIDE_H: float = 7.5

# ── Design-system constants ──────────────────────────────────────────────────

MARGIN_LEFT: float = 0.8
MARGIN_RIGHT: float = 0.5
MARGIN_TOP: float = 0.35
MARGIN_BOTTOM: float = 0.45

CONTENT_LEFT: float = MARGIN_LEFT
CONTENT_RIGHT: float = SLIDE_W - MARGIN_RIGHT
CONTENT_TOP: float = 1.4          # below headline + accent line
CONTENT_BOTTOM: float = SLIDE_H - MARGIN_BOTTOM

CONTENT_W: float = CONTENT_RIGHT - CONTENT_LEFT
CONTENT_H: float = CONTENT_BOTTOM - CONTENT_TOP

HEADLINE_MAX_WORDS: int = 14
BULLET_MAX_WORDS: int = 10
MAX_BULLETS: int = 3
MAX_CHART_BARS: int = 6
MAX_TABLE_ROWS: int = 5
MAX_TABLE_COLS: int = 3
MAX_TIMELINE_PHASES: int = 4
IMAGE_MAX_WIDTH_RATIO: float = 0.45     # 45 % of slide width
IMAGE_ASPECT: float = 16 / 9


# ── Bounding box ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BBox:
    """Axis-aligned bounding box in inches."""
    left: float
    top: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    def intersects(self, other: "BBox") -> bool:
        if self.right <= other.left or other.right <= self.left:
            return False
        if self.bottom <= other.top or other.bottom <= self.top:
            return False
        return True

    def contains(self, other: "BBox") -> bool:
        return (
            self.left <= other.left
            and self.top <= other.top
            and self.right >= other.right
            and self.bottom >= other.bottom
        )

    def clamp_inside(self, outer: "BBox") -> "BBox":
        left = max(self.left, outer.left)
        top = max(self.top, outer.top)
        right = min(self.right, outer.right)
        bottom = min(self.bottom, outer.bottom)
        return BBox(left, top, max(0.1, right - left), max(0.1, bottom - top))


SLIDE_BBOX = BBox(0, 0, SLIDE_W, SLIDE_H)
SAFE_ZONE = BBox(MARGIN_LEFT, MARGIN_TOP, CONTENT_W, SLIDE_H - MARGIN_TOP - MARGIN_BOTTOM)


# ── Grid zones ───────────────────────────────────────────────────────────────

HEADLINE_ZONE = BBox(MARGIN_LEFT, MARGIN_TOP, CONTENT_W, 0.8)
ACCENT_ZONE = BBox(MARGIN_LEFT, 1.1, 1.5, 0.04)
CONTENT_ZONE = BBox(CONTENT_LEFT, CONTENT_TOP, CONTENT_W, CONTENT_H)
FOOTER_ZONE = BBox(0, SLIDE_H - MARGIN_BOTTOM, SLIDE_W, MARGIN_BOTTOM)

# Split content zone for layouts with visual on the right
TEXT_ZONE_LEFT = BBox(CONTENT_LEFT, CONTENT_TOP, CONTENT_W * 0.55, CONTENT_H)
VISUAL_ZONE_RIGHT = BBox(
    CONTENT_LEFT + CONTENT_W * 0.58,
    CONTENT_TOP,
    CONTENT_W * 0.42,
    CONTENT_H,
)

# Split content zone for two equal columns
COL_L = BBox(CONTENT_LEFT, CONTENT_TOP, CONTENT_W * 0.48, CONTENT_H)
COL_R = BBox(CONTENT_LEFT + CONTENT_W * 0.52, CONTENT_TOP, CONTENT_W * 0.48, CONTENT_H)


# ── Font intelligence ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FontSpec:
    size: int
    bold: bool = False


def scale_font(base_size: int, word_count: int) -> int:
    """Return scaled font size based on content length."""
    if word_count <= 20:
        return base_size
    if word_count <= 40:
        return max(12, base_size - 2)
    if word_count <= 60:
        return max(11, base_size - 4)
    return max(10, base_size - 6)


def headline_font(headline: str) -> FontSpec:
    wc = len(headline.split())
    size = 24 if wc <= 10 else (22 if wc <= 14 else 20)
    return FontSpec(size=size, bold=True)


def bullet_font(bullets: List[str]) -> FontSpec:
    total_words = sum(len(b.split()) for b in bullets)
    size = scale_font(18, total_words)
    return FontSpec(size=size)


def metric_font(value: str) -> FontSpec:
    length = len(value)
    size = 80 if length <= 5 else (64 if length <= 8 else 48)
    return FontSpec(size=size, bold=True)


# ── Content compression ─────────────────────────────────────────────────────

def truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"


def compress_headline(headline: str) -> str:
    return truncate_words(headline, HEADLINE_MAX_WORDS)


def compress_bullets(bullets: List[str], max_count: int = MAX_BULLETS) -> List[str]:
    out: List[str] = []
    for b in bullets[:max_count]:
        out.append(truncate_words(b, BULLET_MAX_WORDS))
    return out


def compress_content(slide: Dict[str, Any]) -> Dict[str, Any]:
    """Enforce all content-safety rules on a slide dict, mutating in place."""
    slide["headline"] = compress_headline(slide.get("headline", ""))

    content = slide.get("content", {})
    stype = slide.get("slide_type", "insight_bullets")

    # bullets
    for key in ("bullets", "left_points", "right_points", "key_takeaways"):
        if key in content:
            content[key] = compress_bullets(content[key])

    # impact_metrics
    if "impact_metrics" in content:
        content["impact_metrics"] = content["impact_metrics"][:3]

    # data_points
    if "data_points" in content:
        content["data_points"] = content["data_points"][:MAX_CHART_BARS]

    # table
    if "columns" in content:
        content["columns"] = content["columns"][:MAX_TABLE_COLS]
    if "rows" in content:
        content["rows"] = [r[:MAX_TABLE_COLS] for r in content["rows"][:MAX_TABLE_ROWS]]

    # timeline
    if "phases" in content:
        content["phases"] = content["phases"][:MAX_TIMELINE_PHASES]

    # insight blocks
    if "blocks" in content:
        content["blocks"] = content["blocks"][:3]

    slide["content"] = content
    return slide


# ── Visual decision logic ────────────────────────────────────────────────────

VisualType = Literal["image", "chart", "table", "none"]

VISUAL_RULES: Dict[str, VisualType] = {
    "title": "image",
    "section_divider": "none",
    "big_number": "none",
    "chart_slide": "chart",
    "chart": "chart",
    "table_slide": "table",
    "two_column": "image",
    "comparison": "none",
    "timeline": "none",
    "case_study": "image",
    "insight_blocks": "none",
    "insight_bullets": "image",
    "closing": "image",
}


def decide_visual(slide_type: str, content: Dict[str, Any]) -> VisualType:
    """Determine which visual element a slide should use."""
    base = VISUAL_RULES.get(slide_type, "image")

    # If chart_slide has no data_points, downgrade to image
    if base == "chart":
        dp = content.get("data_points", [])
        if not dp:
            return "image"

    # If table_slide has no rows, downgrade to none
    if base == "table":
        rows = content.get("rows", [])
        if not rows:
            return "none"

    return base


# ── Image bounding box ───────────────────────────────────────────────────────

def compute_image_bbox(zone: BBox) -> BBox:
    """Fit an image inside *zone* respecting 16:9 aspect and max-width."""
    max_w = min(zone.width, SLIDE_W * IMAGE_MAX_WIDTH_RATIO)
    max_h = zone.height

    # Fit to aspect ratio
    w = max_w
    h = w / IMAGE_ASPECT
    if h > max_h:
        h = max_h
        w = h * IMAGE_ASPECT

    # Center inside zone
    left = zone.left + (zone.width - w) / 2
    top = zone.top + (zone.height - h) / 2
    return BBox(left, top, w, h)


# ── Layout template base ────────────────────────────────────────────────────

@dataclass
class LayoutElement:
    """Describes one renderable region on a slide."""
    name: str
    bbox: BBox
    element_type: str          # headline | text | bullets | metric | image | chart | table | shape
    max_lines: int = 10
    max_words: int = 120
    font_base: int = 18
    bold: bool = False


@dataclass
class LayoutTemplate:
    """A complete layout specification for one slide type."""
    name: str
    slide_type: str
    visual_type: VisualType
    elements: List[LayoutElement] = field(default_factory=list)

    def get_element(self, name: str) -> Optional[LayoutElement]:
        for e in self.elements:
            if e.name == name:
                return e
        return None

    def validate_no_overlap(self) -> List[Tuple[str, str]]:
        """Return list of overlapping element-name pairs."""
        collisions: List[Tuple[str, str]] = []
        for i in range(len(self.elements)):
            for j in range(i + 1, len(self.elements)):
                if self.elements[i].bbox.intersects(self.elements[j].bbox):
                    collisions.append((self.elements[i].name, self.elements[j].name))
        return collisions

    def all_inside_safe_zone(self) -> bool:
        for e in self.elements:
            if not SLIDE_BBOX.contains(e.bbox):
                return False
        return True


# ── Concrete layout templates ────────────────────────────────────────────────

def _big_number_layout() -> LayoutTemplate:
    return LayoutTemplate(
        name="BigNumberLayout",
        slide_type="big_number",
        visual_type="none",
        elements=[
            LayoutElement("headline", HEADLINE_ZONE, "headline", max_lines=2, max_words=14, font_base=24, bold=True),
            LayoutElement("accent", ACCENT_ZONE, "shape"),
            LayoutElement("panel", BBox(0.6, 1.4, 7.5, 5.2), "shape"),
            LayoutElement("metric", BBox(1.2, 2.0, 6.5, 2.0), "metric", max_lines=1, max_words=3, font_base=80, bold=True),
            LayoutElement("descriptor", BBox(1.2, 4.0, 6.5, 0.7), "text", max_lines=1, max_words=6, font_base=28, bold=True),
            LayoutElement("supporting", BBox(1.2, 4.9, 6.5, 0.6), "text", max_lines=1, max_words=10, font_base=18),
        ],
    )


def _two_column_layout() -> LayoutTemplate:
    panel_h = 5.2
    return LayoutTemplate(
        name="TwoColumnLayout",
        slide_type="two_column",
        visual_type="image",
        elements=[
            LayoutElement("headline", HEADLINE_ZONE, "headline", max_lines=2, max_words=14, font_base=24, bold=True),
            LayoutElement("accent", ACCENT_ZONE, "shape"),
            LayoutElement("left_panel", BBox(0.6, 1.4, 5.8, panel_h), "shape"),
            LayoutElement("left_header", BBox(0.6, 1.4, 5.8, 0.55), "text", max_lines=1, max_words=5, font_base=14, bold=True),
            LayoutElement("left_bullets", BBox(0.9, 2.2, 5.2, 4.2), "bullets", max_lines=3, max_words=30, font_base=17),
            LayoutElement("divider", BBox(6.55, 1.4, 0.03, panel_h), "shape"),
            LayoutElement("right_panel", BBox(6.7, 1.4, 5.8, panel_h), "shape"),
            LayoutElement("right_header", BBox(6.7, 1.4, 5.8, 0.55), "text", max_lines=1, max_words=5, font_base=14, bold=True),
            LayoutElement("right_bullets", BBox(7.0, 2.2, 5.2, 4.2), "bullets", max_lines=3, max_words=30, font_base=17),
        ],
    )


def _chart_layout() -> LayoutTemplate:
    return LayoutTemplate(
        name="ChartLayout",
        slide_type="chart_slide",
        visual_type="chart",
        elements=[
            LayoutElement("headline", HEADLINE_ZONE, "headline", max_lines=2, max_words=14, font_base=24, bold=True),
            LayoutElement("accent", ACCENT_ZONE, "shape"),
            LayoutElement("chart_panel", BBox(0.6, 1.4, 7.5, 5.5), "shape"),
            LayoutElement("chart_message", BBox(0.8, 1.5, 7.0, 0.5), "text", max_lines=1, max_words=12, font_base=13),
            LayoutElement("chart_area", BBox(0.8, 2.1, 7.0, 4.5), "chart", max_lines=6),
            LayoutElement("image_zone", BBox(8.5, 1.5, 4.3, 5.0), "image"),
        ],
    )


def _table_layout() -> LayoutTemplate:
    return LayoutTemplate(
        name="TableLayout",
        slide_type="table_slide",
        visual_type="table",
        elements=[
            LayoutElement("headline", HEADLINE_ZONE, "headline", max_lines=2, max_words=14, font_base=24, bold=True),
            LayoutElement("accent", ACCENT_ZONE, "shape"),
            LayoutElement("table_title", BBox(0.8, 1.4, 8.0, 0.5), "text", max_lines=1, max_words=8, font_base=14),
            LayoutElement("table_area", BBox(0.8, 2.0, 11.5, 4.5), "table"),
        ],
    )


def _timeline_layout() -> LayoutTemplate:
    return LayoutTemplate(
        name="TimelineLayout",
        slide_type="timeline",
        visual_type="none",
        elements=[
            LayoutElement("headline", HEADLINE_ZONE, "headline", max_lines=2, max_words=14, font_base=24, bold=True),
            LayoutElement("accent", ACCENT_ZONE, "shape"),
            LayoutElement("timeline_panel", BBox(0.6, 1.8, 12.0, 5.0), "shape"),
            LayoutElement("connector", BBox(0.8, 3.5, 11.5, 0.05), "shape"),
            LayoutElement("phase_area", BBox(0.8, 2.0, 11.5, 4.5), "timeline"),
        ],
    )


def _section_divider_layout() -> LayoutTemplate:
    return LayoutTemplate(
        name="SectionDividerLayout",
        slide_type="section_divider",
        visual_type="none",
        elements=[
            LayoutElement("top_stripe", BBox(0, 0, SLIDE_W, 0.12), "shape"),
            LayoutElement("bottom_stripe", BBox(0, SLIDE_H - 0.12, SLIDE_W, 0.12), "shape"),
            LayoutElement("section_title", BBox(1.5, 2.2, 10.3, 1.5), "headline", max_lines=2, max_words=6, font_base=52, bold=True),
            LayoutElement("accent_bar", BBox(5.5, 3.8, 2.3, 0.06), "shape"),
            LayoutElement("section_subtitle", BBox(2.0, 4.2, 9.3, 0.8), "text", max_lines=1, max_words=8, font_base=22),
        ],
    )


def _case_study_layout() -> LayoutTemplate:
    return LayoutTemplate(
        name="CaseStudyLayout",
        slide_type="case_study",
        visual_type="image",
        elements=[
            LayoutElement("headline", HEADLINE_ZONE, "headline", max_lines=2, max_words=14, font_base=24, bold=True),
            LayoutElement("accent", ACCENT_ZONE, "shape"),
            LayoutElement("badge", BBox(0.8, 1.5, 1.8, 0.35), "shape"),
            LayoutElement("company", BBox(0.8, 2.1, 7.0, 0.7), "text", max_lines=1, max_words=5, font_base=32, bold=True),
            LayoutElement("use_case", BBox(0.8, 2.9, 7.0, 0.8), "text", max_lines=2, max_words=15, font_base=16),
            LayoutElement("metric_cards", BBox(0.8, 4.2, 11.2, 2.0), "metric", max_lines=3),
            LayoutElement("image_zone", BBox(8.5, 1.5, 4.3, 4.3), "image"),
        ],
    )


def _insight_blocks_layout() -> LayoutTemplate:
    card_w = 3.6
    gap = 0.25
    return LayoutTemplate(
        name="InsightBlockLayout",
        slide_type="insight_blocks",
        visual_type="none",
        elements=[
            LayoutElement("headline", HEADLINE_ZONE, "headline", max_lines=2, max_words=14, font_base=24, bold=True),
            LayoutElement("accent", ACCENT_ZONE, "shape"),
            LayoutElement("card_0", BBox(0.8, 1.6, card_w, 4.5), "metric"),
            LayoutElement("card_1", BBox(0.8 + card_w + gap, 1.6, card_w, 4.5), "metric"),
            LayoutElement("card_2", BBox(0.8 + 2 * (card_w + gap), 1.6, card_w, 4.5), "metric"),
        ],
    )


def _insight_bullets_layout(has_image: bool) -> LayoutTemplate:
    if has_image:
        text_w = 6.8
        img_bbox = BBox(8.2, 1.5, 4.5, 4.5)
    else:
        text_w = 11.5
        img_bbox = BBox(0, 0, 0, 0)

    elems = [
        LayoutElement("headline", BBox(MARGIN_LEFT, MARGIN_TOP, text_w if has_image else CONTENT_W, 0.8),
                       "headline", max_lines=2, max_words=14, font_base=24, bold=True),
        LayoutElement("accent", ACCENT_ZONE, "shape"),
        LayoutElement("panel", BBox(0.6, 1.4, text_w, 4.8), "shape"),
        LayoutElement("bullets", BBox(0.8, 1.6, text_w - 0.3, 4.5), "bullets", max_lines=3, max_words=30, font_base=18),
    ]
    if has_image:
        elems.append(LayoutElement("image_zone", img_bbox, "image"))

    return LayoutTemplate(
        name="InsightBulletsLayout",
        slide_type="insight_bullets",
        visual_type="image" if has_image else "none",
        elements=elems,
    )


def _title_layout() -> LayoutTemplate:
    return LayoutTemplate(
        name="TitleLayout",
        slide_type="title",
        visual_type="image",
        elements=[
            LayoutElement("bar", BBox(0, 0, SLIDE_W, 0.18), "shape"),
            LayoutElement("left_stripe", BBox(0.8, 2.0, 0.08, 1.8), "shape"),
            LayoutElement("title_text", BBox(1.2, 2.0, 10.5, 1.8), "headline", max_lines=3, max_words=14, font_base=44, bold=True),
            LayoutElement("accent_line", BBox(1.2, 3.7, 2.5, 0.04), "shape"),
            LayoutElement("subtitle", BBox(1.2, 4.0, 9.0, 0.7), "text", max_lines=1, max_words=10, font_base=22),
            LayoutElement("meta", BBox(1.2, 5.0, 9.0, 0.5), "text", max_lines=1, max_words=10, font_base=14),
            LayoutElement("image_zone", BBox(9.5, 2.0, 3.3, 3.3), "image"),
        ],
    )


def _closing_layout() -> LayoutTemplate:
    return LayoutTemplate(
        name="ClosingLayout",
        slide_type="closing",
        visual_type="image",
        elements=[
            LayoutElement("bar", BBox(0, 0, SLIDE_W, 0.18), "shape"),
            LayoutElement("headline", BBox(1.0, 1.2, 11.0, 1.0), "headline", max_lines=2, max_words=10, font_base=36, bold=True),
            LayoutElement("accent_line", BBox(1.0, 2.1, 2.0, 0.04), "shape"),
            LayoutElement("takeaway_area", BBox(1.0, 2.8, 10.0, 4.0), "bullets", max_lines=5, max_words=50, font_base=18),
            LayoutElement("image_zone", BBox(9.0, 4.5, 3.5, 2.5), "image"),
        ],
    )


def _comparison_layout() -> LayoutTemplate:
    return LayoutTemplate(
        name="ComparisonLayout",
        slide_type="comparison",
        visual_type="none",
        elements=[
            LayoutElement("headline", HEADLINE_ZONE, "headline", max_lines=2, max_words=14, font_base=24, bold=True),
            LayoutElement("accent", ACCENT_ZONE, "shape"),
            LayoutElement("left_label", BBox(0.8, 1.6, 5.5, 0.6), "text", max_lines=1, max_words=4, font_base=16, bold=True),
            LayoutElement("left_panel", BBox(0.8, 2.3, 5.5, 4.2), "bullets", max_lines=3, max_words=30, font_base=16),
            LayoutElement("divider", BBox(6.5, 1.6, 0.03, 5.0), "shape"),
            LayoutElement("right_label", BBox(7.0, 1.6, 5.5, 0.6), "text", max_lines=1, max_words=4, font_base=16, bold=True),
            LayoutElement("right_panel", BBox(7.0, 2.3, 5.5, 4.2), "bullets", max_lines=3, max_words=30, font_base=16),
        ],
    )


# ── Template registry ────────────────────────────────────────────────────────

_LAYOUT_BUILDERS = {
    "title": _title_layout,
    "section_divider": _section_divider_layout,
    "big_number": _big_number_layout,
    "chart_slide": _chart_layout,
    "chart": _chart_layout,
    "table_slide": _table_layout,
    "two_column": _two_column_layout,
    "comparison": _comparison_layout,
    "timeline": _timeline_layout,
    "case_study": _case_study_layout,
    "insight_blocks": _insight_blocks_layout,
    "insight_bullets": lambda: _insight_bullets_layout(has_image=True),
    "closing": _closing_layout,
}


def get_layout(slide_type: str, **kwargs) -> LayoutTemplate:
    builder = _LAYOUT_BUILDERS.get(slide_type)
    if builder is None:
        return _insight_bullets_layout(has_image=True)
    # insight_bullets needs has_image kwarg
    if slide_type == "insight_bullets":
        return _insight_bullets_layout(has_image=kwargs.get("has_image", True))
    return builder()


# ── Overlap detection ────────────────────────────────────────────────────────

def detect_overlaps(elements: List[LayoutElement]) -> List[Tuple[str, str]]:
    """Return pairs of element names whose bounding boxes collide."""
    collisions: List[Tuple[str, str]] = []
    for i in range(len(elements)):
        for j in range(i + 1, len(elements)):
            if elements[i].bbox.intersects(elements[j].bbox):
                collisions.append((elements[i].name, elements[j].name))
    return collisions


def validate_layout(layout: LayoutTemplate) -> List[str]:
    """Return list of human-readable validation errors, empty if clean."""
    errors: List[str] = []

    # Overlap check
    for a, b in layout.validate_no_overlap():
        errors.append(f"Overlap: {a} ↔ {b}")

    # Bounds check
    for e in layout.elements:
        if e.bbox.right > SLIDE_W + 0.01:
            errors.append(f"{e.name} exceeds slide right edge ({e.bbox.right:.2f} > {SLIDE_W})")
        if e.bbox.bottom > SLIDE_H + 0.01:
            errors.append(f"{e.name} exceeds slide bottom edge ({e.bbox.bottom:.2f} > {SLIDE_H})")

    return errors


# ── LayoutIntelligenceLayer — main orchestrator ──────────────────────────────

class LayoutIntelligenceLayer:
    """
    Central coordinator that processes every slide *before* it reaches the
    PPT renderer, guaranteeing:
      - correct layout template assignment
      - no element overlap
      - compressed/truncated content
      - proper visual-type decision
      - font-size scaling
      - image bounding-box clamping
    """

    def process_slide(
        self,
        slide: Dict[str, Any],
        has_image: bool = True,
    ) -> Dict[str, Any]:
        """Process a single slide dict and attach layout metadata."""

        # 1. Normalise slide_type
        stype = slide.get("slide_type", "insight_bullets")
        content = slide.get("content", {})

        # 2. Decide visual type
        visual = decide_visual(stype, content)

        # 3. Override has_image for types that forbid it
        if visual == "none":
            has_image = False

        # 4. Get layout template
        layout = get_layout(stype, has_image=has_image)

        # 5. Compress content to fit
        slide = compress_content(slide)

        # 6. Compute font sizes
        fonts: Dict[str, FontSpec] = {}
        headline = slide.get("headline", "")
        fonts["headline"] = headline_font(headline)

        bullets_key = self._find_bullets_key(content)
        if bullets_key:
            fonts["bullets"] = bullet_font(content[bullets_key])

        primary_metric = content.get("primary_metric", "")
        if primary_metric:
            fonts["metric"] = metric_font(primary_metric)

        # 7. Compute image bbox if needed
        image_bbox: Optional[BBox] = None
        if has_image and visual in ("image", "chart"):
            img_elem = layout.get_element("image_zone")
            if img_elem:
                image_bbox = compute_image_bbox(img_elem.bbox)

        # 8. Validate layout
        errors = validate_layout(layout)

        # 9. Attach layout metadata to slide
        slide["_layout"] = {
            "template": layout.name,
            "visual_type": visual,
            "fonts": {k: {"size": v.size, "bold": v.bold} for k, v in fonts.items()},
            "image_bbox": (
                {"left": image_bbox.left, "top": image_bbox.top,
                 "width": image_bbox.width, "height": image_bbox.height}
                if image_bbox else None
            ),
            "validation_errors": errors,
        }

        return slide

    def process_deck(
        self,
        slides: List[Dict[str, Any]],
        images: List[str],
    ) -> List[Dict[str, Any]]:
        """Process every slide in the deck."""
        processed: List[Dict[str, Any]] = []
        for i, slide in enumerate(slides):
            has_img = bool(i < len(images) and images[i])
            slide = self.process_slide(slide, has_image=has_img)
            processed.append(slide)
        return processed

    @staticmethod
    def needs_image(slide_type: str, content: Dict[str, Any]) -> bool:
        """Return True if this slide type benefits from an image."""
        visual = decide_visual(slide_type, content)
        return visual in ("image",)

    @staticmethod
    def needs_chart(slide_type: str, content: Dict[str, Any]) -> bool:
        """Return True if this slide should get a matplotlib chart."""
        return decide_visual(slide_type, content) == "chart"

    @staticmethod
    def needs_table(slide_type: str, content: Dict[str, Any]) -> bool:
        return decide_visual(slide_type, content) == "table"

    # ── private ──

    @staticmethod
    def _find_bullets_key(content: Dict[str, Any]) -> Optional[str]:
        for key in ("bullets", "left_points", "right_points", "key_takeaways"):
            if key in content and isinstance(content[key], list) and content[key]:
                return key
        return None
