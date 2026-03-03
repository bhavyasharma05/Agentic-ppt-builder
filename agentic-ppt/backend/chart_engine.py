"""
Chart Intelligence Engine — matplotlib chart generation for data slides.

Generates corporate-styled bar and line charts as PNG images,
sized and colored to match the presentation design system.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# ── Corporate colour palettes (hex) ─────────────────────────────────────────

PALETTES: Dict[str, List[str]] = {
    "professional": ["#0052CC", "#003366", "#336699", "#6699CC", "#99CCFF", "#CCE5FF"],
    "modern":       ["#E94D35", "#C43A27", "#F97316", "#FB923C", "#FDBA74", "#FED7AA"],
    "dark":         ["#7C3AED", "#A78BFA", "#6D28D9", "#8B5CF6", "#C4B5FD", "#DDD6FE"],
    "creative":     ["#F97316", "#D9480F", "#FB923C", "#FDBA74", "#FED7AA", "#FFF0E5"],
    "minimal":      ["#111111", "#444444", "#777777", "#AAAAAA", "#CCCCCC", "#EEEEEE"],
}

NEUTRAL_BG = "#FFFFFF"
GRID_COLOR = "#E0E0E0"
LABEL_COLOR = "#333333"
TICK_COLOR = "#666666"

# ── Helpers ──────────────────────────────────────────────────────────────────

_NUM_RE = re.compile(r"[\d,]+\.?\d*")


def _parse_value(raw: str) -> float:
    """Extract the first numeric value from a string like '$4.5B' or '67%'."""
    clean = raw.replace(",", "")
    m = _NUM_RE.search(clean)
    if m:
        return float(m.group())
    return 0.0


def _parse_data_points(data_points: List) -> Tuple[List[str], List[float], List[str]]:
    """Parse various data_point formats into parallel lists of labels, values, raw."""
    labels: List[str] = []
    values: List[float] = []
    raw_vals: List[str] = []

    for dp in data_points:
        if isinstance(dp, dict):
            label = str(dp.get("label", dp.get("name", "")))
            val_str = str(dp.get("value", "0"))
        elif isinstance(dp, str) and ":" in dp:
            parts = dp.split(":", 1)
            label = parts[0].strip()
            val_str = parts[1].strip()
        else:
            label = str(dp)
            val_str = "50"

        labels.append(label)
        values.append(_parse_value(val_str))
        raw_vals.append(val_str)

    return labels, values, raw_vals


# ── Chart generators ────────────────────────────────────────────────────────

def generate_bar_chart(
    data_points: List,
    chart_message: str = "",
    theme_name: str = "professional",
    save_path: str = "chart.png",
    width_inches: float = 7.0,
    height_inches: float = 4.5,
) -> str:
    """Generate a horizontal bar chart and save as PNG. Returns file path."""
    palette = PALETTES.get(theme_name, PALETTES["professional"])
    labels, values, raw_vals = _parse_data_points(data_points)

    if not labels:
        labels, values, raw_vals = ["No data"], [1.0], ["—"]

    n = len(labels)
    colors = [palette[i % len(palette)] for i in range(n)]

    fig, ax = plt.subplots(figsize=(width_inches, height_inches))
    fig.patch.set_facecolor(NEUTRAL_BG)
    ax.set_facecolor(NEUTRAL_BG)

    y_pos = np.arange(n)
    bars = ax.barh(y_pos, values, color=colors, height=0.55, edgecolor="none")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=11, color=LABEL_COLOR, fontweight="bold")
    ax.invert_yaxis()

    # Value labels on bars
    for bar, rv in zip(bars, raw_vals):
        ax.text(
            bar.get_width() + max(values) * 0.02,
            bar.get_y() + bar.get_height() / 2,
            rv,
            va="center",
            fontsize=10,
            color=TICK_COLOR,
            fontweight="bold",
        )

    ax.set_xlim(0, max(values) * 1.2 if max(values) > 0 else 1)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(5))
    ax.tick_params(axis="x", labelsize=9, colors=TICK_COLOR)
    ax.grid(axis="x", color=GRID_COLOR, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color(GRID_COLOR)
    ax.spines["left"].set_visible(False)

    if chart_message:
        fig.suptitle(chart_message, fontsize=12, color=LABEL_COLOR, x=0.05, ha="left", y=0.97)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=NEUTRAL_BG)
    plt.close(fig)
    return save_path


def generate_line_chart(
    data_points: List,
    chart_message: str = "",
    theme_name: str = "professional",
    save_path: str = "chart.png",
    width_inches: float = 7.0,
    height_inches: float = 4.5,
) -> str:
    """Generate a line chart and save as PNG. Returns file path."""
    palette = PALETTES.get(theme_name, PALETTES["professional"])
    labels, values, _ = _parse_data_points(data_points)

    if not labels:
        labels, values = ["—"], [0.0]

    fig, ax = plt.subplots(figsize=(width_inches, height_inches))
    fig.patch.set_facecolor(NEUTRAL_BG)
    ax.set_facecolor(NEUTRAL_BG)

    x = np.arange(len(labels))
    ax.plot(x, values, color=palette[0], linewidth=2.5, marker="o", markersize=7, zorder=5)
    ax.fill_between(x, values, alpha=0.08, color=palette[0])

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10, color=LABEL_COLOR, fontweight="bold")

    ax.yaxis.set_major_locator(ticker.MaxNLocator(5))
    ax.tick_params(axis="y", labelsize=9, colors=TICK_COLOR)
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color(GRID_COLOR)
    ax.spines["left"].set_color(GRID_COLOR)

    if chart_message:
        fig.suptitle(chart_message, fontsize=12, color=LABEL_COLOR, x=0.05, ha="left", y=0.97)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=NEUTRAL_BG)
    plt.close(fig)
    return save_path


# ── Dispatcher ───────────────────────────────────────────────────────────────

def generate_chart(
    content: Dict[str, Any],
    theme_name: str,
    save_path: str,
) -> Optional[str]:
    """Auto-select chart type from slide content and generate it.

    Returns the save_path on success, None if content has no data.
    """
    data_points = content.get("data_points", [])
    if not data_points:
        return None

    chart_type = content.get("chart_type", "bar").lower()
    chart_message = content.get("chart_message", "")

    if chart_type == "line":
        return generate_line_chart(data_points, chart_message, theme_name, save_path)
    return generate_bar_chart(data_points, chart_message, theme_name, save_path)
