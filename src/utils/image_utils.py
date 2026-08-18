"""NewsSnap AI - Image utilities."""

import io
import os
from typing import List, Tuple

import httpx
from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")

FONT_MAP = {
    "en": "NotoSans-Regular.ttf",
    "hi": "NotoSansDevanagari-Regular.ttf",
    "ta": "NotoSansTamil-Regular.ttf",
    "te": "NotoSansTelugu-Regular.ttf",
    "kn": "NotoSansKannada-Regular.ttf",
}


def get_font_for_language(language: str, size: int) -> ImageFont.FreeTypeFont:
    """Get the appropriate font for a given language."""
    font_file = FONT_MAP.get(language.lower(), "NotoSans-Regular.ttf")
    font_path = os.path.join(FONTS_DIR, font_file)

    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        # Fallback to default if font file is missing
        return ImageFont.load_default()


def download_image(url: str) -> Image.Image:
    """Download an image from a URL and return a PIL Image."""
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")
    except Exception as e:
        # Return a blank white image or raise? Let's raise to let caller handle
        raise ValueError(f"Could not download image from {url}: {e}")


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.Draw) -> List[str]:
    """Wrap text to fit within a given width."""
    lines = []
    paragraphs = text.split("\n")
    for paragraph in paragraphs:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue

        current_line = []
        for word in words:
            current_line.append(word)
            test_line = " ".join(current_line)
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]

            if width > max_width:
                if len(current_line) == 1:
                    # Word itself is longer than max_width
                    lines.append(current_line[0])
                    current_line = []
                else:
                    current_line.pop()
                    lines.append(" ".join(current_line))
                    current_line = [word]
        if current_line:
            lines.append(" ".join(current_line))
    return lines


def fit_text_to_box(
    text: str, language: str, max_width: int, max_height: int, min_size: int, max_size: int, draw: ImageDraw.Draw
) -> Tuple[ImageFont.FreeTypeFont, List[str]]:
    """Find the largest font size that allows text to fit in a bounding box."""
    best_font = get_font_for_language(language, min_size)
    best_lines = wrap_text(text, best_font, max_width, draw)

    # Binary search for optimal font size
    low = min_size
    high = max_size

    while low <= high:
        mid = (low + high) // 2
        font = get_font_for_language(language, mid)
        lines = wrap_text(text, font, max_width, draw)

        # Calculate total height
        total_height = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            total_height += (bbox[3] - bbox[1]) + (mid * 0.2)  # Adding some line spacing

        if total_height <= max_height:
            best_font = font
            best_lines = lines
            low = mid + 1
        else:
            high = mid - 1

    return best_font, best_lines
