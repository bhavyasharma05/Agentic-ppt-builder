"""
LangGraph-based multi-layer agentic pipeline for PPT generation.
McKinsey-style executive consulting presentation pipeline.
"""

import os
import json
import time
import random
import logging
import subprocess
import langchain
from typing import TypedDict, List, Dict, Any
from dotenv import load_dotenv
from openai import OpenAI
from langgraph.graph import StateGraph, END
from layout_engine import LayoutIntelligenceLayer
from visual_intent import VisualIntentLayer

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Fix: langchain 1.x doesn't expose 'debug' until set
if not hasattr(langchain, "debug"):
    langchain.debug = False

load_dotenv()

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
)
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
IMAGE_API_URL = "https://ppt-agent.bhavyakumarsharma1234.workers.dev"
IMAGE_API_TOKEN = "12345678"

IMAGES_DIR = os.path.join(os.path.dirname(__file__), "static", "images")
os.makedirs(IMAGES_DIR, exist_ok=True)


# ── State schema ──────────────────────────────────────────────────────────────

class PipelineState(TypedDict, total=False):
    input: Dict[str, Any]
    understanding: Dict[str, Any]
    research: Dict[str, Any]
    structure: List[Dict[str, Any]]
    slides: List[Dict[str, Any]]
    images: List[str]
    output_path: str
    error: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _chat(system: str, user: str) -> str:
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


def _parse_json(raw: str) -> Any:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    return json.loads(cleaned)


# ── Layer 1 – Understanding ──────────────────────────────────────────────────

def understanding_layer(state: PipelineState) -> dict:
    inp = state["input"]
    prompt = f"""You are a senior McKinsey strategy consultant. Analyze this presentation request.

Request:
Title: {inp.get('title', '')}
Topic: {inp.get('topic', '')}
Description: {inp.get('description', '')}
Number of slides: {inp.get('num_slides', 8)}

Return a JSON object:
{{
  "type": "strategy|market_analysis|transformation|performance_review|investment_thesis|innovation",
  "audience": "board|c_suite|investors|leadership_team|stakeholders",
  "tone": "executive",
  "key_themes": ["theme1", "theme2", "theme3", "theme4", "theme5"],
  "narrative_arc": "situation > complication > resolution",
  "core_question": "the strategic question this presentation answers"
}}

Think like a McKinsey partner framing a client engagement.
Return ONLY valid JSON."""

    raw = _chat("You are a senior strategy consultant at McKinsey.", prompt)
    try:
        data = _parse_json(raw)
    except Exception:
        data = {
            "type": "strategy",
            "audience": "c_suite",
            "tone": "executive",
            "key_themes": [inp.get("topic", "Strategic insight")],
            "narrative_arc": "situation > complication > resolution",
            "core_question": inp.get("topic", ""),
        }
    return {"understanding": data}


# ── Layer 2 – Research ────────────────────────────────────────────────────────

def research_layer(state: PipelineState) -> dict:
    inp = state["input"]
    understanding = state.get("understanding", {})
    prompt = f"""You are a McKinsey research analyst preparing data for a board-level presentation.

Strategic analysis: {json.dumps(understanding)}
Topic: {inp.get('topic', '')}
Description: {inp.get('description', '')}

Generate executive-grade research. Return JSON:
{{
  "key_insights": ["insight1", "insight2", "insight3", "insight4", "insight5", "insight6", "insight7", "insight8"],
  "metrics": [
    {{"label": "metric name", "value": "number or %", "context": "why it matters"}},
    {{"label": "metric name", "value": "number or %", "context": "why it matters"}},
    {{"label": "metric name", "value": "number or %", "context": "why it matters"}}
  ],
  "case_studies": [
    {{"company": "name", "action": "what they did", "result": "quantified outcome"}}
  ],
  "market_data": [
    {{"data_point": "description", "value": "number"}}
  ],
  "recommendations": ["actionable recommendation 1", "actionable recommendation 2", "actionable recommendation 3"]
}}

Use realistic illustrative data. Emphasize numbers and outcomes.
Return ONLY valid JSON."""

    raw = _chat("You are a McKinsey research analyst and data strategist.", prompt)
    try:
        data = _parse_json(raw)
    except Exception:
        data = {"key_insights": [inp.get("topic", "Key insight")], "metrics": [], "case_studies": [], "market_data": [], "recommendations": []}
    return {"research": data}


# ── Layer 3 – Structure Planning ──────────────────────────────────────────────

def structure_layer(state: PipelineState) -> dict:
    inp = state["input"]
    understanding = state.get("understanding", {})
    research = state.get("research", {})
    num_slides = int(inp.get("num_slides", 8))

    prompt = f"""You are a McKinsey / BCG presentation architect creating a premium executive deck.

Title: {inp.get('title', '')}
Topic: {inp.get('topic', '')}
Audience: Board / C-Suite
Analysis: {json.dumps(understanding)}
Research: {json.dumps(research)}

STRICT DESIGN RULES:
- This is a VISUAL presentation, NOT a text document.
- Every slide MUST use a structured layout with at least one visual element.
- No plain white empty slides. No paragraph text. No decorative filler.
- Maximum 3 bullets per content block, each under 10 words.
- Headlines must be insight-driven sentences, UNDER 14 WORDS.
- Prioritize whitespace and clarity. Slides must feel board-ready.

AVAILABLE SLIDE TYPES:
  * "title"             – opening slide with title + subtitle
  * "section_divider"   – dark background, large centered text, minimal (use to separate sections)
  * "big_number"        – hero metric with descriptor
  * "chart_slide"       – bar/line chart with data points
  * "table_slide"       – structured table (max 3 columns, max 4 rows)
  * "two_column"        – symmetric left/right bullet columns
  * "comparison"        – before/after or option A vs B with labels
  * "timeline"          – horizontal 3-4 phase roadmap
  * "case_study"        – company example with impact metrics
  * "insight_blocks"    – 3 insight cards side by side
  * "closing"           – key takeaways

STRUCTURE REQUIREMENTS:
- Slide 1: "title"
- Last slide: "closing"
- Include at least 1 "section_divider"
- Include at least 1 "chart_slide"
- Include at least 1 "table_slide"
- Include at least 1 "big_number"
- Include at least 1 "two_column" or "comparison"
- Vary the remaining slides for visual rhythm

Return a JSON array of exactly {num_slides} objects:
[
  {{
    "slide_number": 1,
    "slide_type": "title",
    "headline": "Insight headline under 14 words",
    "purpose": "what strategic point this slide makes",
    "data_source": "which research data to use"
  }}
]

Return ONLY a valid JSON array."""

    raw = _chat("You are a McKinsey presentation architect.", prompt)
    try:
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("slides", [data])
    except Exception:
        data = [
            {"slide_number": 1, "slide_type": "title", "headline": inp.get("title", "Presentation"), "purpose": "Title"},
            {"slide_number": 2, "slide_type": "closing", "headline": "Key Takeaways & Next Steps", "purpose": "Closing"},
        ]
    return {"structure": data}


# ── Layer 4 – Refactor (McKinsey content generation) ─────────────────────────

def refactor_layer(state: PipelineState) -> dict:
    structure = state.get("structure", [])
    research = state.get("research", {})
    inp = state["input"]

    prompt = f"""You are a senior McKinsey / BCG consultant creating premium executive slide content.

Structure: {json.dumps(structure)}
Research: {json.dumps(research)}
Topic: {inp.get('topic', '')}
Audience: Board / C-Suite

STRICT DESIGN RULES (violating these causes visual overflow):
1. Every headline MUST be an insight-driven sentence, UNDER 14 WORDS.
2. Maximum 3 bullets per content block, each UNDER 10 WORDS.
3. Each slide communicates ONE clear insight.
4. Emphasize numbers and outcomes. No fluff. No paragraphs.
5. Executive tone. Slides must feel board-ready.
6. Every slide needs at least one visual structure element.

For each slide, return the correct content based on slide_type:

If slide_type = "title":
  content = {{"subtitle": "subtitle under 10 words", "date": "March 2026", "presenter": "Strategic Advisory Team"}}

If slide_type = "section_divider":
  content = {{"section_title": "Section Name (2-4 words)", "section_subtitle": "optional context under 8 words"}}

If slide_type = "big_number":
  content = {{"primary_metric": "e.g. $407B (max 6 chars)", "descriptor": "max 4 words", "supporting_line": "context max 6 words"}}

If slide_type = "chart_slide":
  content = {{"chart_type": "bar|line", "chart_message": "what chart shows under 10 words", "data_points": ["Label A: 45%", "Label B: 30%", "Label C: 25%"]}}

If slide_type = "table_slide":
  content = {{"table_title": "title under 8 words", "columns": ["Col1", "Col2", "Col3"], "rows": [["row1a", "row1b", "row1c"], ["row2a", "row2b", "row2c"], ["row3a", "row3b", "row3c"]]}}

If slide_type = "two_column":
  content = {{"left_header": "Left Title", "left_points": ["point1", "point2", "point3"], "right_header": "Right Title", "right_points": ["point1", "point2", "point3"]}}

If slide_type = "comparison":
  content = {{"left_label": "Before", "left_points": ["p1", "p2", "p3"], "right_label": "After", "right_points": ["p1", "p2", "p3"]}}

If slide_type = "timeline":
  content = {{"phases": [{{"name": "Launch", "description": "max 5 words"}}, {{"name": "Scale", "description": "max 5 words"}}]}}

If slide_type = "case_study":
  content = {{"company": "Company Name", "use_case": "one sentence under 12 words", "impact_metrics": ["metric1", "metric2", "metric3"]}}

If slide_type = "insight_blocks":
  content = {{"blocks": [{{"title": "Block Title", "value": "key metric or stat", "description": "under 8 words"}}, {{"title": "Block Title", "value": "key metric", "description": "under 8 words"}}, {{"title": "Block Title", "value": "key metric", "description": "under 8 words"}}]}}

If slide_type = "insight_bullets":
  content = {{"bullets": ["point under 10 words", "point under 10 words", "point under 10 words"]}}

If slide_type = "closing":
  content = {{"key_takeaways": ["takeaway under 10 words", "takeaway under 10 words", "takeaway under 10 words"]}}

Return a JSON array:
[
  {{
    "slide_number": 1,
    "slide_type": "...",
    "headline": "Insight headline under 14 words",
    "content": {{}},
    "visual_elements": {{
      "background_style": "white_panels|dark_contrast",
      "accent_element": "left_bar|top_divider|content_panel",
      "color_theme": "corporate_blue|neutral_dark"
    }},
    "visual_hint": "brief image description for this slide",
    "speaker_notes": "brief presenter note"
  }}
]

Return ONLY valid JSON array."""

    raw = _chat("You are a senior McKinsey strategy consultant creating executive presentations.", prompt)
    try:
        data = _parse_json(raw)
        if not isinstance(data, list):
            data = data.get("slides", [data])
    except Exception:
        data = []
        for s in structure:
            slide_type = s.get("slide_type", "insight_bullets")
            fallback = {
                "slide_number": s.get("slide_number", 1),
                "slide_type": slide_type,
                "headline": s.get("headline", "Strategic Insight"),
                "content": {"bullets": [s.get("purpose", "Key point")]} if slide_type == "insight_bullets" else {},
                "visual_hint": s.get("headline", ""),
                "speaker_notes": "",
            }
            data.append(fallback)
    return {"slides": data}


# ── Layer 5 – Image Generation ────────────────────────────────────────────────


MAX_RETRIES = 3
RETRY_BACKOFF = [3, 6, 10]  # seconds between retries


def generate_image(prompt: str, save_path: str) -> str:
    """Generate an image via Cloudflare Worker using curl and save to disk.

    Uses curl.exe with forced IPv4 (-4) to avoid Cloudflare IPv6 TLS
    handshake resets. Retries up to MAX_RETRIES times on failure.

    Args:
        prompt: The image generation prompt.
        save_path: Absolute path where the image file will be saved.

    Returns:
        The save_path on success.

    Raises:
        RuntimeError: If all retry attempts fail.
    """
    full_prompt = prompt
    body = json.dumps({"prompt": full_prompt})
    last_error: str = ""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = subprocess.run(
                [
                    "curl.exe",
                    "-4", "-s",
                    "-o", save_path,
                    "-w", "%{http_code}",
                    "-X", "POST",
                    "-H", f"Authorization: Bearer {IMAGE_API_TOKEN}",
                    "-H", "Content-Type: application/json",
                    "-d", body,
                    "--max-time", "60",
                    IMAGE_API_URL,
                ],
                capture_output=True,
                text=True,
                timeout=90,
            )
        except subprocess.TimeoutExpired:
            last_error = f"curl timed out (attempt {attempt}/{MAX_RETRIES})"
            logger.warning("%s for: %s", last_error, prompt[:80])
        except Exception as exc:
            last_error = f"curl execution failed (attempt {attempt}/{MAX_RETRIES}): {exc}"
            logger.warning("%s", last_error)
        else:
            http_code = result.stdout.strip()
            if http_code == "200" and os.path.isfile(save_path) and os.path.getsize(save_path) > 1000:
                return save_path

            # Non-200 or empty file — clean up partial download
            if os.path.isfile(save_path):
                os.remove(save_path)
            last_error = (
                f"Image API returned HTTP {http_code} (attempt {attempt}/{MAX_RETRIES})"
            )
            logger.warning("%s for: %s", last_error, prompt[:80])

        # Back off before next retry (skip after final attempt)
        if attempt < MAX_RETRIES:
            wait = RETRY_BACKOFF[attempt - 1]
            logger.info("Retrying in %ds...", wait)
            time.sleep(wait)

    raise RuntimeError(
        f"Image generation failed after {MAX_RETRIES} attempts for: {prompt[:80]}. "
        f"Last error: {last_error}"
    )


_layout_intel = LayoutIntelligenceLayer()
_visual_intent = VisualIntentLayer()


def visual_intent_layer(state: PipelineState) -> dict:
    """Analyze every slide with VisualIntentLayer and attach _visual_intent metadata."""
    slides = state.get("slides", [])
    for slide in slides:
        intent = _visual_intent.analyze_slide(slide)
        slide["_visual_intent"] = intent.to_dict()
        slide_num = slide.get("slide_number", "?")
        if intent.needs_image:
            logger.info(
                "Slide %s: image needed — type=%s, subject=%s",
                slide_num, intent.visual_type, intent.primary_subject[:40],
            )
        else:
            reason = "chart preferred" if intent.use_chart else "not visual"
            logger.info("Slide %s: image skipped (%s)", slide_num, reason)
    return {"slides": slides}


def image_generation_layer(state: PipelineState) -> dict:
    slides = state.get("slides", [])
    image_paths: List[str] = []
    images_generated = 0

    for idx, slide in enumerate(slides):
        slide_num = slide.get("slide_number", idx + 1)
        intent = slide.get("_visual_intent", {})

        # Use VisualIntentLayer decision
        if not intent.get("needs_image", False):
            logger.info("Slide %d: no image needed — skipping", slide_num)
            image_paths.append("")
            continue

        # Use the semantically-generated prompt from VisualIntentLayer
        prompt = intent.get("generated_prompt", "")
        if not prompt:
            prompt = slide.get("visual_hint", slide.get("headline", "abstract data visualization"))

        filename = f"slide_{slide_num}.png"
        filepath = os.path.join(IMAGES_DIR, filename)

        try:
            generate_image(prompt, filepath)
            logger.info("Slide %d: image generated — prompt: %s", slide_num, prompt[:60])
            image_paths.append(filepath)
            images_generated += 1
        except RuntimeError as exc:
            logger.error("Slide %d: image generation failed — %s", slide_num, exc)
            raise  # stop pipeline on failure

        # Random delay between slides to avoid rate-limiting (skip after last)
        if idx < len(slides) - 1:
            delay = round(random.uniform(3.0, 4.0), 2)
            logger.info("Waiting %.2fs before next image…", delay)
            time.sleep(delay)

    logger.info("Image generation complete: %d images for %d slides", images_generated, len(slides))
    return {"images": image_paths}


# ── Layer 6 – Review ─────────────────────────────────────────────────────────

def review_layer(state: PipelineState) -> dict:
    slides = state.get("slides", [])
    inp = state["input"]
    requested = int(inp.get("num_slides", 8))

    if len(slides) < requested:
        for i in range(len(slides), requested):
            slides.append({
                "slide_number": i + 1,
                "slide_type": "insight_bullets",
                "headline": f"Additional Strategic Insight #{i + 1 - len(slides) + 1}",
                "content": {"bullets": ["Further analysis required"]},
                "visual_hint": "",
                "speaker_notes": "",
            })
    elif len(slides) > requested:
        slides = slides[:requested]

    for i, slide in enumerate(slides):
        slide["slide_number"] = i + 1
        if "slide_type" not in slide:
            slide["slide_type"] = "insight_bullets"
        if "headline" not in slide:
            slide["headline"] = slide.get("title", "Strategic Insight")
        if "content" not in slide:
            slide["content"] = {"bullets": ["Key point"]}

    return {"slides": slides}


# ── Layer 7 – PPT Builder ────────────────────────────────────────────────────

def ppt_builder_layer(state: PipelineState) -> dict:
    from ppt_builder import build_pptx

    slides = state.get("slides", [])
    images = state.get("images", [])
    inp = state["input"]
    theme = inp.get("theme", "professional")
    title = inp.get("title", "Presentation")

    output_path = os.path.join(os.path.dirname(__file__), "static", "output.pptx")
    try:
        build_pptx(slides, images, theme, title, output_path)
        return {"output_path": output_path}
    except Exception as e:
        return {"error": str(e)}


# ── Build the LangGraph pipeline ─────────────────────────────────────────────

def build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("understanding", understanding_layer)
    graph.add_node("research", research_layer)
    graph.add_node("structure", structure_layer)
    graph.add_node("refactor", refactor_layer)
    graph.add_node("visual_intent", visual_intent_layer)
    graph.add_node("image_generation", image_generation_layer)
    graph.add_node("review", review_layer)
    graph.add_node("ppt_builder", ppt_builder_layer)

    graph.set_entry_point("understanding")
    graph.add_edge("understanding", "research")
    graph.add_edge("research", "structure")
    graph.add_edge("structure", "refactor")
    graph.add_edge("refactor", "visual_intent")
    graph.add_edge("visual_intent", "image_generation")
    graph.add_edge("image_generation", "review")
    graph.add_edge("review", "ppt_builder")
    graph.add_edge("ppt_builder", END)

    return graph.compile()


pipeline = build_graph()


def run_pipeline(user_input: Dict[str, Any]) -> PipelineState:
    initial_state: PipelineState = {
        "input": user_input,
        "understanding": {},
        "research": {},
        "structure": [],
        "slides": [],
        "images": [],
        "output_path": "",
        "error": "",
    }
    result = pipeline.invoke(initial_state)
    return result
