"""NewsSnap AI - Snap Template Renderer (Issue 16).

Provides a JSON-based template configuration and rendering engine for news snaps.
Supports:
- 8 template types covering all 19 categories
- Unique layout and color scheme per template
- Unique badge colors for all 19 categories
- Category-based auto-selection
- Category-specific visual elements (numerical highlights, score displays,
  bold headline styling, info-card containers, quote banners, stats chips)
- Multi-language font rendering for all 5 languages (en, hi, ta, te, kn)
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw

from src.snaps.image_handler import ImageHandler
from src.utils.image_utils import fit_text_to_box, get_font_for_language

# ---------------------------------------------------------------------------
# Category Mappings and Palette
# ---------------------------------------------------------------------------

CATEGORY_TEMPLATE_MAP: Dict[str, str] = {
    # Core news
    "national": "politics",
    "international": "general",
    "politics": "politics",
    "business": "finance",
    "finance": "finance",
    "sports": "sports",
    # Tech and science
    "technology": "technology",
    "science": "technology",
    "automobile": "general",
    # Society
    "education": "education",
    "health": "general",
    "entertainment": "entertainment",
    "lifestyle": "general",
    # India specific
    "crime": "crime",
    "environment": "general",
    "jobs": "education",
    "defence": "crime",
    "real_estate": "general",
    "opinion": "general",
}

CATEGORY_BADGE_COLORS: Dict[str, str] = {
    "national": "#3F72AF",
    "international": "#2980B9",
    "politics": "#9B59B6",
    "business": "#27AE60",
    "finance": "#16A085",
    "sports": "#E67E22",
    "technology": "#34495E",
    "science": "#1ABC9C",
    "automobile": "#C0392B",
    "education": "#F39C12",
    "health": "#E74C3C",
    "entertainment": "#8E44AD",
    "lifestyle": "#F1C40F",
    "crime": "#2C3E50",
    "environment": "#2ECC71",
    "jobs": "#3498DB",
    "defence": "#7F8C8D",
    "real_estate": "#D35400",
    "opinion": "#95A5A6",
}

DEFAULT_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

# Pattern to extract numerical data from news headlines/summaries
_NUMERICAL_PATTERN = re.compile(
    r"(?:[+-]?\d+(?:\.\d+)?%|"
    r"(?:Rs\.?|INR|\$|EUR|GBP)\s*\d+(?:,\d+)*(?:\.\d+)?(?:\s*(?:crore|cr|lakh|million|billion|trillion|k|m|b))?|"
    r"\d+(?:,\d+)*(?:\.\d+)?\s*(?:crore|cr|lakh|million|billion|trillion|pts|points|percent)|"
    r"(?:SENSEX|NIFTY)\s*[+-]?\d+(?:,\d+)*(?:\.\d+)?)",
    re.IGNORECASE,
)


class TemplateRenderer:
    """Renders category-specific news snaps using JSON template configurations."""

    def __init__(self, templates_dir: Optional[str] = None):
        """Initialize template renderer and load JSON templates."""
        self.templates_dir = templates_dir or DEFAULT_TEMPLATE_DIR
        self._templates: Dict[str, Dict[str, Any]] = {}
        self._load_templates()

    def _load_templates(self) -> None:
        """Load all JSON template configs from templates directory."""
        if not os.path.isdir(self.templates_dir):
            return

        for filename in os.listdir(self.templates_dir):
            if filename.endswith(".json"):
                template_name = filename[:-5]
                filepath = os.path.join(self.templates_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        self._templates[template_name] = json.load(f)
                except Exception:
                    pass

    def list_templates(self) -> List[str]:
        """Return list of loaded template names."""
        return sorted(list(self._templates.keys()))

    def get_template(self, template_name: str) -> Dict[str, Any]:
        """Get template config by name, falling back to general or default."""
        if template_name in self._templates:
            return self._templates[template_name]
        if "general" in self._templates:
            return self._templates["general"]
        if "default" in self._templates:
            return self._templates["default"]

        # Default fallback dictionary
        return {
            "template_name": "general",
            "layout_type": "general",
            "width": 1080,
            "height": 1920,
            "bg_color": "#FFFFFF",
            "lead_image_height": 608,
            "padding": 60,
            "category_font_size": 38,
            "category_color": "#FFFFFF",
            "category_bg": "#3F72AF",
            "summary_font_size_max": 68,
            "summary_font_size_min": 38,
            "summary_color": "#1C1C1E",
            "source_font_size": 34,
            "source_color": "#8E8E93",
            "accent_color": "#3F72AF",
        }

    def get_template_for_category(self, category: str) -> Dict[str, Any]:
        """Auto-select template based on category string."""
        cat_key = category.strip().lower()
        template_name = CATEGORY_TEMPLATE_MAP.get(cat_key, "general")
        return self.get_template(template_name)

    def get_badge_color(self, category: str) -> str:
        """Return distinct badge color for category, with fallback."""
        cat_key = category.strip().lower()
        return CATEGORY_BADGE_COLORS.get(cat_key, "#3F72AF")

    @staticmethod
    def extract_numerical_data(text: str) -> Optional[str]:
        """Extract first prominent numerical or financial metric from text."""
        if not text:
            return None
        match = _NUMERICAL_PATTERN.search(text)
        if match:
            return match.group(0).strip()
        return None

    def render(
        self,
        category: str,
        title: str,
        summary: str,
        image_url: Optional[str] = None,
        source: str = "",
        language: str = "en",
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Image.Image:
        """Render a 1080x1920 snap image based on category template.

        Args:
            category: Article category slug.
            title: Headline string.
            summary: Summary paragraph string.
            image_url: Optional lead image URL.
            source: News source name.
            language: Language code ('en', 'hi', 'ta', 'te', 'kn').
            extra_data: Optional dictionary with custom highlights, scores,
                        tags, or template override.

        Returns:
            Rendered PIL Image (RGB, 1080x1920).
        """
        extra = extra_data or {}
        template_override = extra.get("template_name")
        if template_override and template_override in self._templates:
            template = self.get_template(template_override)
        else:
            template = self.get_template_for_category(category)

        layout_type = template.get("layout_type", "general")
        width = template.get("width", 1080)
        height = template.get("height", 1920)
        bg_color = template.get("bg_color", "#FFFFFF")
        padding = template.get("padding", 60)
        badge_color = extra.get("badge_color") or self.get_badge_color(category)

        # Base canvas
        img = Image.new("RGB", (width, height), color=bg_color)
        draw = ImageDraw.Draw(img)

        # 1. Lead Image
        lead_height = template.get("lead_image_height", 608)
        lead_img = ImageHandler.process_lead_image(image_url or "", width, lead_height, placeholder_color=badge_color)
        img.paste(lead_img, (0, 0))

        current_y = lead_height + padding

        # 2. Category Badge
        cat_display = category.replace("_", " ").upper()
        cat_font = get_font_for_language(language, template.get("category_font_size", 38))
        cat_bbox = draw.textbbox((0, 0), cat_display, font=cat_font)
        cat_width = cat_bbox[2] - cat_bbox[0]
        cat_height = cat_bbox[3] - cat_bbox[1]

        cat_pad_x = 22
        cat_pad_y = 10
        cat_rect = [
            padding,
            current_y,
            padding + cat_width + 2 * cat_pad_x,
            current_y + cat_height + 2 * cat_pad_y,
        ]
        draw.rounded_rectangle(cat_rect, radius=8, fill=badge_color)
        draw.text(
            (padding + cat_pad_x, current_y + cat_pad_y),
            cat_display,
            font=cat_font,
            fill=template.get("category_color", "#FFFFFF"),
        )

        current_y += cat_height + 2 * cat_pad_y + int(padding * 0.6)

        # 3. Bottom Source and Timestamp Bar
        source_display = f"{source} - 2h ago" if source else "NewsSnap - Just now"
        source_font = get_font_for_language(language, template.get("source_font_size", 34))
        source_bbox = draw.textbbox((0, 0), source_display, font=source_font)
        source_height = source_bbox[3] - source_bbox[1]

        interaction_bar_height = 90
        source_y = height - interaction_bar_height - source_height - padding

        draw.text(
            (padding, source_y),
            source_display,
            font=source_font,
            fill=template.get("source_color", "#8E8E93"),
        )

        # 4. Template-Specific Visual Layout Features
        content_max_y = source_y - int(padding * 0.8)

        if layout_type == "finance":
            current_y = self._render_finance_highlight(
                draw, current_y, padding, width, title, summary, template, language, extra
            )
        elif layout_type == "sports":
            current_y = self._render_sports_score(
                draw, current_y, padding, width, title, summary, template, language, extra
            )
        elif layout_type == "crime":
            current_y = self._render_crime_headline(draw, current_y, padding, width, title, template, language)
            title = ""  # Title already drawn with bold styling
        elif layout_type == "education":
            current_y = self._render_education_card(
                draw, current_y, padding, width, content_max_y, template, language, extra
            )
        elif layout_type == "politics":
            current_y = self._render_politics_quote(
                draw, current_y, padding, width, title, summary, template, language, extra
            )
        elif layout_type == "technology":
            current_y = self._render_tech_stats(
                draw, current_y, padding, width, title, summary, template, language, extra
            )

        # 5. Summary Text Box
        summary_max_height = content_max_y - current_y
        summary_max_width = width - 2 * padding

        full_text = f"{title}\n\n{summary}" if title else summary

        if summary_max_height > 60:
            sum_font, sum_lines = fit_text_to_box(
                full_text,
                language,
                summary_max_width,
                summary_max_height,
                template.get("summary_font_size_min", 36),
                template.get("summary_font_size_max", 64),
                draw,
            )

            y_text = current_y
            line_spacing = int(sum_font.size * 0.28)
            for line in sum_lines:
                draw.text(
                    (padding, y_text),
                    line,
                    font=sum_font,
                    fill=template.get("summary_color", "#1C1C1E"),
                )
                bbox = draw.textbbox((0, 0), line, font=sum_font)
                y_text += (bbox[3] - bbox[1]) + line_spacing

        return img

    def _render_finance_highlight(
        self,
        draw: ImageDraw.Draw,
        current_y: int,
        padding: int,
        width: int,
        title: str,
        summary: str,
        template: Dict[str, Any],
        language: str,
        extra: Dict[str, Any],
    ) -> int:
        """Render numerical data callout pill/box for finance template."""
        data_text = extra.get("numerical_highlight") or self.extract_numerical_data(f"{title} {summary}")
        if not data_text:
            data_text = "MARKET UPDATE"

        highlight_font = get_font_for_language(language, template.get("data_highlight_font_size", 44))
        data_display = f"DATA HIGHLIGHT: {data_text}"
        bbox = draw.textbbox((0, 0), data_display, font=highlight_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        pad_x, pad_y = 24, 14
        box_w = min(text_w + 2 * pad_x, width - 2 * padding)
        rect = [padding, current_y, padding + box_w, current_y + text_h + 2 * pad_y]

        draw.rounded_rectangle(
            rect,
            radius=10,
            fill=template.get("data_highlight_bg", "#E8F8F5"),
            outline=template.get("data_highlight_border_color", "#A3E4D7"),
            width=2,
        )
        draw.text(
            (padding + pad_x, current_y + pad_y),
            data_display,
            font=highlight_font,
            fill=template.get("data_highlight_text_color", "#0E6655"),
        )
        return current_y + text_h + 2 * pad_y + int(padding * 0.5)

    def _render_sports_score(
        self,
        draw: ImageDraw.Draw,
        current_y: int,
        padding: int,
        width: int,
        title: str,
        summary: str,
        template: Dict[str, Any],
        language: str,
        extra: Dict[str, Any],
    ) -> int:
        """Render score / match result display banner for sports template."""
        score_text = extra.get("score") or "MATCH RESULT / LIVE UPDATE"
        score_font = get_font_for_language(language, template.get("score_banner_font_size", 42))

        bbox = draw.textbbox((0, 0), score_text, font=score_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        banner_w = width - 2 * padding
        banner_h = text_h + 28
        rect = [padding, current_y, padding + banner_w, current_y + banner_h]

        draw.rounded_rectangle(
            rect,
            radius=12,
            fill=template.get("score_banner_bg", "#FDF2E9"),
            outline=template.get("score_banner_border_color", "#F5CBA7"),
            width=2,
        )
        # Center the score text
        text_x = padding + max((banner_w - text_w) // 2, 20)
        draw.text(
            (text_x, current_y + 14),
            score_text,
            font=score_font,
            fill=template.get("score_banner_text_color", "#BA4A00"),
        )
        return current_y + banner_h + int(padding * 0.5)

    def _render_crime_headline(
        self,
        draw: ImageDraw.Draw,
        current_y: int,
        padding: int,
        width: int,
        title: str,
        template: Dict[str, Any],
        language: str,
    ) -> int:
        """Render extra-bold headline styling for crime and defence template."""
        if not title:
            return current_y

        head_font = get_font_for_language(language, template.get("headline_font_size", 68))
        max_w = width - 2 * padding

        from src.utils.image_utils import wrap_text

        lines = wrap_text(title, head_font, max_w, draw)
        y_text = current_y

        # Optional accent highlight bar next to headline
        accent_color = template.get("accent_color", "#C0392B")
        bar_x = padding
        text_offset_x = padding + 20

        total_h = 0
        line_heights = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=head_font)
            lh = (bbox[3] - bbox[1]) + int(head_font.size * 0.25)
            line_heights.append(lh)
            total_h += lh

        draw.rectangle([bar_x, current_y, bar_x + 8, current_y + total_h], fill=accent_color)

        for i, line in enumerate(lines):
            draw.text(
                (text_offset_x, y_text),
                line,
                font=head_font,
                fill=template.get("headline_color", "#922B21"),
            )
            y_text += line_heights[i]

        return y_text + int(padding * 0.5)

    def _render_education_card(
        self,
        draw: ImageDraw.Draw,
        current_y: int,
        padding: int,
        width: int,
        content_max_y: int,
        template: Dict[str, Any],
        language: str,
        extra: Dict[str, Any],
    ) -> int:
        """Render info-card container layout for education and jobs template."""
        card_rect = [
            padding - 15,
            current_y - 10,
            width - padding + 15,
            content_max_y + 10,
        ]
        draw.rounded_rectangle(
            card_rect,
            radius=template.get("card_radius", 16),
            fill=template.get("card_bg", "#FFFFFF"),
            outline=template.get("card_border_color", "#E5E8EB"),
            width=2,
        )

        bulletin_text = extra.get("tag") or "OFFICIAL BULLETIN / INFO CARD"
        bulletin_font = get_font_for_language(language, 32)
        bbox = draw.textbbox((0, 0), bulletin_text, font=bulletin_font)
        tag_w = bbox[2] - bbox[0]
        tag_h = bbox[3] - bbox[1]

        tag_rect = [
            padding,
            current_y,
            padding + tag_w + 24,
            current_y + tag_h + 14,
        ]
        draw.rounded_rectangle(
            tag_rect,
            radius=6,
            fill=template.get("bulletin_tag_bg", "#FEF9E7"),
        )
        draw.text(
            (padding + 12, current_y + 7),
            bulletin_text,
            font=bulletin_font,
            fill=template.get("bulletin_tag_text_color", "#B9770E"),
        )

        return current_y + tag_h + 14 + int(padding * 0.5)

    def _render_politics_quote(
        self,
        draw: ImageDraw.Draw,
        current_y: int,
        padding: int,
        width: int,
        title: str,
        summary: str,
        template: Dict[str, Any],
        language: str,
        extra: Dict[str, Any],
    ) -> int:
        """Render quote / statement highlight strip for politics template."""
        quote_text = extra.get("quote")
        if not quote_text:
            return current_y

        q_font = get_font_for_language(language, template.get("quote_font_size", 42))
        display = f'"{quote_text}"'
        bbox = draw.textbbox((0, 0), display, font=q_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        box_w = min(text_w + 32, width - 2 * padding)
        rect = [padding, current_y, padding + box_w, current_y + text_h + 20]

        draw.rounded_rectangle(
            rect,
            radius=8,
            fill=template.get("quote_banner_bg", "#F4ECF7"),
            outline=template.get("quote_banner_border_color", "#D7BDE2"),
            width=2,
        )
        draw.text(
            (padding + 16, current_y + 10),
            display,
            font=q_font,
            fill=template.get("quote_banner_text_color", "#5B2C6F"),
        )
        return current_y + text_h + 20 + int(padding * 0.5)

    def _render_tech_stats(
        self,
        draw: ImageDraw.Draw,
        current_y: int,
        padding: int,
        width: int,
        title: str,
        summary: str,
        template: Dict[str, Any],
        language: str,
        extra: Dict[str, Any],
    ) -> int:
        """Render key tech stats / spec chips for technology template."""
        chips = extra.get("stats") or ["TECH BRIEF", "ANALYSIS"]
        if isinstance(chips, str):
            chips = [chips]

        chip_font = get_font_for_language(language, template.get("stats_chip_font_size", 34))
        chip_x = padding
        max_h = 0

        for chip in chips[:3]:
            bbox = draw.textbbox((0, 0), chip, font=chip_font)
            cw = bbox[2] - bbox[0]
            ch = bbox[3] - bbox[1]
            max_h = max(max_h, ch)

            if chip_x + cw + 28 > width - padding:
                break

            rect = [chip_x, current_y, chip_x + cw + 28, current_y + ch + 16]
            draw.rounded_rectangle(
                rect,
                radius=6,
                fill=template.get("stats_chip_bg", "#EAECEE"),
                outline=template.get("stats_chip_border_color", "#BDC3C7"),
                width=1,
            )
            draw.text(
                (chip_x + 14, current_y + 8),
                chip,
                font=chip_font,
                fill=template.get("stats_chip_text_color", "#2C3E50"),
            )
            chip_x += cw + 40

        return current_y + max_h + 16 + int(padding * 0.5)
