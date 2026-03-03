"""
Visual Intent Layer — semantic image prompt intelligence for agentic PPT.

Analyzes slide JSON to decide whether an image is needed, what kind of
visual best communicates the insight, and generates a high-relevance
prompt that avoids generic corporate stock imagery.

Pipeline position: runs AFTER refactor, BEFORE image generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# ── Constants ────────────────────────────────────────────────────────────────

# Slide types that NEVER need a generated image
NO_IMAGE_TYPES: Set[str] = {
    "big_number",
    "chart_slide",
    "chart",
    "table_slide",
    "comparison",
    "timeline",
    "section_divider",
}

# Slide types that conditionally benefit from images
CONDITIONAL_IMAGE_TYPES: Set[str] = {
    "case_study",
    "two_column",
    "insight_blocks",
}

# Slide types that always benefit from images
ALWAYS_IMAGE_TYPES: Set[str] = {
    "title",
    "insight_bullets",
    "closing",
}

# Generic prompts to reject — if the final prompt looks like these, rewrite it
BANNED_SUBJECTS: List[str] = [
    "business meeting",
    "handshake",
    "team discussion",
    "office environment",
    "corporate office",
    "people in suits",
    "conference room",
    "business people talking",
    "group discussion",
    "professional team",
    "office workers",
    "business presentation",
    "meeting room",
    "corporate handshake",
    "abstract background",
    "blue background",
]

# Industry keyword → industry label mapping
INDUSTRY_KEYWORDS: Dict[str, str] = {
    "healthcare": "healthcare",
    "medical": "healthcare",
    "hospital": "healthcare",
    "pharma": "pharmaceuticals",
    "drug": "pharmaceuticals",
    "clinical": "healthcare",
    "patient": "healthcare",
    "finance": "finance",
    "banking": "finance",
    "investment": "finance",
    "portfolio": "finance",
    "trading": "finance",
    "fintech": "finance",
    "insurance": "insurance",
    "retail": "retail",
    "ecommerce": "retail",
    "e-commerce": "retail",
    "store": "retail",
    "shopping": "retail",
    "consumer": "retail",
    "logistics": "logistics",
    "supply chain": "logistics",
    "warehouse": "logistics",
    "shipping": "logistics",
    "freight": "logistics",
    "distribution": "logistics",
    "manufacturing": "manufacturing",
    "factory": "manufacturing",
    "production": "manufacturing",
    "assembly": "manufacturing",
    "industrial": "manufacturing",
    "technology": "technology",
    "software": "technology",
    "cloud": "technology",
    "saas": "technology",
    "platform": "technology",
    "digital": "technology",
    "ai": "technology",
    "machine learning": "technology",
    "automation": "technology",
    "data": "technology",
    "analytics": "technology",
    "energy": "energy",
    "renewable": "energy",
    "solar": "energy",
    "oil": "energy",
    "gas": "energy",
    "sustainability": "energy",
    "education": "education",
    "university": "education",
    "training": "education",
    "learning": "education",
    "automotive": "automotive",
    "vehicle": "automotive",
    "ev": "automotive",
    "electric vehicle": "automotive",
    "real estate": "real estate",
    "property": "real estate",
    "construction": "real estate",
    "telecom": "telecommunications",
    "network": "telecommunications",
    "5g": "telecommunications",
    "agriculture": "agriculture",
    "farming": "agriculture",
    "food": "agriculture",
    "media": "media",
    "entertainment": "media",
    "streaming": "media",
    "content": "media",
    "travel": "travel",
    "hospitality": "travel",
    "tourism": "travel",
    "hotel": "travel",
    "airline": "travel",
}

# Industry → preferred visual subjects (specific, non-generic)
INDUSTRY_VISUALS: Dict[str, List[str]] = {
    "healthcare": [
        "medical diagnostic dashboard with patient data visualization",
        "laboratory with biotech equipment and data screens",
        "digital health monitoring interface with vital signs",
    ],
    "pharmaceuticals": [
        "pharmaceutical research lab with molecular visualization",
        "clinical trial data analytics dashboard",
        "drug development pipeline visualization",
    ],
    "finance": [
        "financial trading terminal with real-time market data",
        "portfolio analytics dashboard with risk metrics",
        "digital banking interface with transaction flow",
    ],
    "insurance": [
        "insurance risk assessment dashboard with analytics",
        "actuarial data visualization with probability curves",
    ],
    "retail": [
        "retail analytics dashboard showing sales heatmap",
        "smart store shelf with digital price tags and sensors",
        "e-commerce fulfillment center with automated systems",
    ],
    "logistics": [
        "global supply chain network map with live tracking",
        "automated warehouse with robotic picking systems",
        "logistics control tower dashboard with fleet tracking",
    ],
    "manufacturing": [
        "smart factory floor with robotic assembly line",
        "industrial IoT sensor network visualization",
        "manufacturing quality control dashboard",
    ],
    "technology": [
        "AI neural network architecture visualization",
        "cloud infrastructure dashboard with microservices",
        "data pipeline architecture with real-time processing",
    ],
    "energy": [
        "renewable energy grid management dashboard",
        "solar farm with performance monitoring overlay",
        "energy consumption analytics with sustainability metrics",
    ],
    "education": [
        "digital learning platform analytics dashboard",
        "interactive classroom with educational technology",
    ],
    "automotive": [
        "electric vehicle battery management system display",
        "autonomous driving sensor fusion visualization",
        "connected vehicle fleet management dashboard",
    ],
    "real estate": [
        "smart building management system dashboard",
        "urban development project 3D visualization",
    ],
    "telecommunications": [
        "5G network coverage visualization with signal mapping",
        "telecom infrastructure monitoring dashboard",
    ],
    "agriculture": [
        "precision agriculture drone monitoring dashboard",
        "smart farming IoT sensor data visualization",
    ],
    "media": [
        "content streaming analytics dashboard with engagement metrics",
        "media distribution pipeline visualization",
    ],
    "travel": [
        "travel platform booking analytics dashboard",
        "hotel revenue management system interface",
    ],
}

# Fallback visuals when no industry is detected
GENERIC_MEANINGFUL_VISUALS: List[str] = [
    "strategic data analytics dashboard with KPI metrics",
    "digital transformation roadmap visualization",
    "performance metrics dashboard with trend analysis",
    "process optimization flowchart with efficiency indicators",
    "innovation ecosystem map with interconnected nodes",
    "growth trajectory visualization with milestone markers",
    "competitive landscape radar chart on digital screen",
    "operational efficiency dashboard with real-time gauges",
]

# Patterns that indicate numeric / statistical content
NUMERIC_PATTERNS: List[re.Pattern] = [
    re.compile(r"\$[\d,.]+[BMKTbmkt]?", re.IGNORECASE),
    re.compile(r"\d+\.?\d*\s*%"),
    re.compile(r"\d+[xX]\s"),
    re.compile(r"(?:increase|decrease|growth|decline|revenue|profit|margin|roi|cagr|irr|npv)\b", re.IGNORECASE),
    re.compile(r"\b\d{2,}(?:,\d{3})+\b"),
    re.compile(r"\b(?:billion|million|trillion|thousand)\b", re.IGNORECASE),
]

# Action verbs that suggest a visual direction
ACTION_VERBS: Dict[str, str] = {
    "transform": "transformation process visualization",
    "optimize": "optimization metrics dashboard",
    "scale": "scaling architecture diagram",
    "migrate": "migration pathway visualization",
    "automate": "automation workflow with robotic processes",
    "integrate": "system integration architecture map",
    "launch": "product launch timeline with milestone tracking",
    "expand": "market expansion geographic visualization",
    "reduce": "cost reduction funnel with savings breakdown",
    "accelerate": "acceleration metrics with velocity tracking",
    "disrupt": "market disruption landscape visualization",
    "innovate": "innovation pipeline with stage-gate process",
    "deploy": "deployment architecture with rollout phases",
    "consolidate": "consolidation framework with merger flow",
    "restructure": "organizational restructure diagram",
    "digitize": "digital transformation maturity model",
    "diversify": "portfolio diversification matrix",
    "penetrate": "market penetration heatmap by region",
    "acquire": "acquisition integration roadmap",
    "streamline": "streamlined process flow with efficiency gains",
}

# Visual type classification
VISUAL_TYPE_RULES: Dict[str, str] = {
    "title": "conceptual",
    "closing": "conceptual",
    "case_study": "literal",
    "insight_bullets": "conceptual",
    "two_column": "literal",
    "insight_blocks": "abstract",
}

# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class VisualIntent:
    """Output of visual intent analysis for one slide."""
    needs_image: bool
    use_chart: bool
    visual_type: str            # literal | conceptual | abstract | diagrammatic
    primary_subject: str
    secondary_context: str
    industry_context: str
    action_focus: str
    generated_prompt: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "needs_image": self.needs_image,
            "use_chart": self.use_chart,
            "visual_type": self.visual_type,
            "primary_subject": self.primary_subject,
            "secondary_context": self.secondary_context,
            "industry_context": self.industry_context,
            "action_focus": self.action_focus,
            "generated_prompt": self.generated_prompt,
        }


# ── Core engine ──────────────────────────────────────────────────────────────

class VisualIntentLayer:
    """
    Semantic analysis layer that transforms slide content into
    high-relevance image prompts or decides to skip image generation.

    Usage:
        layer = VisualIntentLayer()
        intent = layer.analyze_slide(slide_json)
        if intent.needs_image:
            image = generate_image(intent.generated_prompt, path)
    """

    # ── public API ───────────────────────────────────────────────────────

    def analyze_slide(self, slide: Dict[str, Any]) -> VisualIntent:
        """Analyze a single slide and return visual intent."""
        slide_type = slide.get("slide_type", "insight_bullets")
        headline = slide.get("headline", "")
        content = slide.get("content", {})

        # 1. Hard rejection for non-visual slide types
        if slide_type in NO_IMAGE_TYPES:
            use_chart = slide_type in ("chart_slide", "chart")
            return VisualIntent(
                needs_image=False,
                use_chart=use_chart,
                visual_type="none",
                primary_subject="",
                secondary_context="",
                industry_context="",
                action_focus="",
                generated_prompt="",
            )

        # 2. Extract semantic components
        all_text = self._collect_text(headline, content)
        entities = self._extract_entities(all_text)
        industry = self._detect_industry(all_text)
        is_numeric = self._is_numeric_content(headline, content)
        action = self._detect_action(all_text)
        visual_type = VISUAL_TYPE_RULES.get(slide_type, "conceptual")

        # 3. Numeric content → prefer chart over image (but not case_study)
        if is_numeric and slide_type in CONDITIONAL_IMAGE_TYPES and slide_type != "case_study":
            return VisualIntent(
                needs_image=False,
                use_chart=True,
                visual_type="diagrammatic",
                primary_subject=entities[0] if entities else "",
                secondary_context=entities[1] if len(entities) > 1 else "",
                industry_context=industry,
                action_focus=action,
                generated_prompt="",
            )

        # 4. Conditional types — evaluate image value
        if slide_type in CONDITIONAL_IMAGE_TYPES:
            needs = self._evaluate_image_value(slide_type, content, entities)
            if not needs:
                return VisualIntent(
                    needs_image=False,
                    use_chart=False,
                    visual_type="none",
                    primary_subject=entities[0] if entities else "",
                    secondary_context=entities[1] if len(entities) > 1 else "",
                    industry_context=industry,
                    action_focus=action,
                    generated_prompt="",
                )

        # 5. Generate prompt
        prompt = self._generate_prompt(
            headline=headline,
            entities=entities,
            industry=industry,
            action=action,
            visual_type=visual_type,
            content=content,
        )

        return VisualIntent(
            needs_image=True,
            use_chart=False,
            visual_type=visual_type,
            primary_subject=entities[0] if entities else headline[:40],
            secondary_context=entities[1] if len(entities) > 1 else "",
            industry_context=industry,
            action_focus=action,
            generated_prompt=prompt,
        )

    def analyze_deck(self, slides: List[Dict[str, Any]]) -> List[VisualIntent]:
        """Analyze every slide in a deck and return intents."""
        return [self.analyze_slide(s) for s in slides]

    # ── text collection ──────────────────────────────────────────────────

    @staticmethod
    def _collect_text(headline: str, content: Dict[str, Any]) -> str:
        """Flatten all textual content from a slide into one string."""
        parts: List[str] = [headline]

        for key in (
            "subtitle", "section_title", "section_subtitle",
            "descriptor", "supporting_line", "chart_message",
            "table_title", "company", "use_case",
            "left_header", "right_header", "left_label", "right_label",
        ):
            val = content.get(key, "")
            if val:
                parts.append(str(val))

        for key in ("bullets", "left_points", "right_points",
                     "key_takeaways", "impact_metrics"):
            items = content.get(key, [])
            if isinstance(items, list):
                for item in items:
                    parts.append(str(item))

        blocks = content.get("blocks", [])
        if isinstance(blocks, list):
            for b in blocks:
                if isinstance(b, dict):
                    parts.extend([
                        str(b.get("title", "")),
                        str(b.get("value", "")),
                        str(b.get("description", "")),
                    ])

        phases = content.get("phases", [])
        if isinstance(phases, list):
            for p in phases:
                if isinstance(p, dict):
                    parts.extend([str(p.get("name", "")), str(p.get("description", ""))])
                else:
                    parts.append(str(p))

        return " ".join(p for p in parts if p).lower()

    # ── entity extraction ────────────────────────────────────────────────

    _STOPWORDS: Set[str] = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can", "this", "that",
        "these", "those", "it", "its", "our", "we", "they", "their", "your",
        "not", "no", "nor", "so", "if", "as", "up", "out", "about", "into",
        "over", "after", "before", "between", "under", "above", "through",
        "during", "each", "every", "all", "both", "few", "more", "most",
        "other", "some", "such", "than", "too", "very", "just", "also",
        "how", "what", "which", "who", "whom", "why", "where", "when",
        "key", "new", "next", "strategic", "critical", "major", "across",
    }

    def _extract_entities(self, text: str) -> List[str]:
        """Extract meaningful noun entities from text, ranked by relevance."""
        words = re.findall(r"[a-z][a-z'-]+", text)
        freq: Dict[str, int] = {}
        for w in words:
            if w in self._STOPWORDS or len(w) < 3:
                continue
            freq[w] = freq.get(w, 0) + 1

        bigrams = self._extract_bigrams(words)
        for bg in bigrams:
            freq[bg] = freq.get(bg, 0) + 3

        ranked = sorted(freq.items(), key=lambda x: -x[1])
        return [w for w, _ in ranked[:6]]

    @staticmethod
    def _extract_bigrams(words: List[str]) -> List[str]:
        """Extract meaningful two-word phrases."""
        bigrams: List[str] = []
        skip = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "is", "are", "key", "new",
        }
        for i in range(len(words) - 1):
            if words[i] in skip or words[i + 1] in skip:
                continue
            if len(words[i]) >= 3 and len(words[i + 1]) >= 3:
                bigrams.append(f"{words[i]} {words[i + 1]}")
        return bigrams[:5]

    # ── industry detection ───────────────────────────────────────────────

    @staticmethod
    def _detect_industry(text: str) -> str:
        """Detect the most relevant industry from slide text."""
        scores: Dict[str, int] = {}
        for keyword, industry in INDUSTRY_KEYWORDS.items():
            if keyword in text:
                scores[industry] = scores.get(industry, 0) + 1

        if not scores:
            return ""
        return max(scores, key=scores.get)

    # ── numeric detection ────────────────────────────────────────────────

    @staticmethod
    def _is_numeric_content(headline: str, content: Dict[str, Any]) -> bool:
        """Return True if the slide is predominantly numeric / statistical."""
        combined = headline + " " + str(content)
        matches = 0
        for pat in NUMERIC_PATTERNS:
            matches += len(pat.findall(combined))
        return matches >= 2

    # ── action detection ─────────────────────────────────────────────────

    @staticmethod
    def _detect_action(text: str) -> str:
        """Find the strongest action verb and return its visual mapping."""
        for verb, visual in ACTION_VERBS.items():
            if verb in text:
                return visual
        return ""

    # ── image value evaluation ───────────────────────────────────────────

    @staticmethod
    def _evaluate_image_value(
        slide_type: str,
        content: Dict[str, Any],
        entities: List[str],
    ) -> bool:
        """For conditional slide types, decide if an image adds value."""

        if slide_type == "insight_blocks":
            blocks = content.get("blocks", [])
            has_values = any(
                isinstance(b, dict) and b.get("value")
                for b in blocks
            )
            if has_values:
                return False

        if slide_type == "two_column":
            left = content.get("left_points", [])
            right = content.get("right_points", [])
            total_bullets = len(left) + len(right)
            if total_bullets >= 5:
                return False

        if slide_type == "case_study":
            metrics = content.get("impact_metrics", [])
            if len(metrics) >= 3:
                return True

        if len(entities) < 2:
            return False

        return True

    # ── prompt generation ────────────────────────────────────────────────

    def _generate_prompt(
        self,
        headline: str,
        entities: List[str],
        industry: str,
        action: str,
        visual_type: str,
        content: Dict[str, Any],
    ) -> str:
        """Build a high-relevance image prompt from semantic analysis."""

        # Start with industry-specific visual if available
        base_visual = ""
        if industry and industry in INDUSTRY_VISUALS:
            visuals = INDUSTRY_VISUALS[industry]
            best = self._pick_best_visual(visuals, entities)
            base_visual = best

        # If action verb gives a strong visual direction, use it
        if action and not base_visual:
            base_visual = action

        # If still no base, derive from entities
        if not base_visual and entities:
            base_visual = self._entities_to_visual(entities, visual_type)

        # Fallback to generic meaningful visual
        if not base_visual:
            base_visual = self._pick_best_visual(GENERIC_MEANINGFUL_VISUALS, entities)

        # Sanitize — reject banned subjects
        base_visual = self._sanitize_prompt(base_visual)

        # Compose final prompt with required suffixes
        prompt = self._compose_final(base_visual, industry, visual_type)

        return prompt

    @staticmethod
    def _pick_best_visual(visuals: List[str], entities: List[str]) -> str:
        """Pick the visual description that best overlaps with entities."""
        if not visuals:
            return ""
        if not entities:
            return visuals[0]

        best_score = -1
        best = visuals[0]
        for v in visuals:
            v_lower = v.lower()
            score = sum(1 for e in entities if e in v_lower)
            if score > best_score:
                best_score = score
                best = v
        return best

    @staticmethod
    def _entities_to_visual(entities: List[str], visual_type: str) -> str:
        """Convert extracted entities into a visual description."""
        top = entities[:3]

        if visual_type == "literal":
            return f"{' '.join(top)} in operational context"
        if visual_type == "abstract":
            return f"abstract visualization of {' and '.join(top[:2])} concepts"
        if visual_type == "diagrammatic":
            return f"technical diagram showing {' '.join(top)} architecture"

        return f"conceptual visualization of {' '.join(top)} strategy"

    def _sanitize_prompt(self, prompt: str) -> str:
        """Remove/replace banned generic subjects."""
        prompt_lower = prompt.lower()
        for banned in BANNED_SUBJECTS:
            if banned in prompt_lower:
                prompt = re.sub(
                    re.escape(banned),
                    "data-driven analytics interface",
                    prompt,
                    flags=re.IGNORECASE,
                )
        return prompt

    @staticmethod
    def _compose_final(base: str, industry: str, visual_type: str) -> str:
        """Assemble final prompt with required directives, under 250 chars."""
        suffix = ", no text, 16:9 composition, clean professional style"

        industry_tag = f", {industry} industry" if industry else ""

        core = f"{base}{industry_tag}{suffix}"

        if len(core) > 250:
            over = len(core) - 250
            base = base[:len(base) - over - 3] + "…"
            core = f"{base}{industry_tag}{suffix}"

        return core[:250]
