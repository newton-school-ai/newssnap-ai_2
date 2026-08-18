"""NewsSnap AI - Snap Generator."""

import json
import os

from PIL import Image, ImageDraw

from src.snaps.image_handler import ImageHandler
from src.utils.image_utils import fit_text_to_box, get_font_for_language


class SnapGenerator:
    """Generates snap images from news articles."""

    def __init__(self, template_name: str = "default"):
        """Initialize with a specific template."""
        template_path = os.path.join(os.path.dirname(__file__), "templates", f"{template_name}.json")
        with open(template_path, "r", encoding="utf-8") as f:
            self.template = json.load(f)

    def generate(
        self, title: str, summary: str, image_url: str, category: str, source: str, language: str = "en"
    ) -> Image.Image:
        """Generate a snap image."""
        width = self.template["width"]
        height = self.template["height"]
        bg_color = self.template["bg_color"]

        # Create base image
        img = Image.new("RGB", (width, height), color=bg_color)
        draw = ImageDraw.Draw(img)

        # 1. Lead Image (16:9)
        lead_height = self.template.get("lead_image_height", int(width / 1.777777778))
        lead_img = ImageHandler.process_lead_image(
            image_url, width, lead_height, placeholder_color=self.template["category_bg"]
        )
        img.paste(lead_img, (0, 0))

        # 2. Category Badge
        padding = self.template["padding"]
        current_y = lead_height + padding

        category = category.upper()
        cat_font = get_font_for_language(language, self.template["category_font_size"])
        cat_bbox = draw.textbbox((0, 0), category, font=cat_font)
        cat_width = cat_bbox[2] - cat_bbox[0]
        cat_height = cat_bbox[3] - cat_bbox[1]

        cat_pad_x = 20
        cat_pad_y = 10
        cat_rect = [padding, current_y, padding + cat_width + 2 * cat_pad_x, current_y + cat_height + 2 * cat_pad_y]

        ImageHandler.draw_rounded_rectangle(draw, cat_rect, radius=8, fill=self.template["category_bg"])
        # Some fonts have top spacing, using standard text drawing
        draw.text(
            (padding + cat_pad_x, current_y + cat_pad_y), category, font=cat_font, fill=self.template["category_color"]
        )

        current_y += cat_height + 2 * cat_pad_y + padding

        # 3. Source + Timestamp at bottom
        # Format time-ago or just date. Mocking time-ago as '2h ago'
        source_text = f"{source} • 2h ago"
        source_font = get_font_for_language(language, self.template["source_font_size"])

        source_bbox = draw.textbbox((0, 0), source_text, font=source_font)
        source_height = source_bbox[3] - source_bbox[1]

        interaction_bar_height = 100
        source_y = height - interaction_bar_height - source_height - padding

        draw.text((padding, source_y), source_text, font=source_font, fill=self.template["source_color"])

        # 4. Summary text
        summary_max_height = source_y - current_y - padding
        summary_max_width = width - 2 * padding

        full_text = f"{title}\n\n{summary}" if title else summary

        sum_font, sum_lines = fit_text_to_box(
            full_text,
            language,
            summary_max_width,
            summary_max_height,
            self.template["summary_font_size_min"],
            self.template["summary_font_size_max"],
            draw,
        )

        y_text = current_y
        for line in sum_lines:
            draw.text((padding, y_text), line, font=sum_font, fill=self.template["summary_color"])
            bbox = draw.textbbox((0, 0), line, font=sum_font)
            y_text += (bbox[3] - bbox[1]) + int(sum_font.size * 0.3)

        return img
