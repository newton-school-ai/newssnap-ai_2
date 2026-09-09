"""NewsSnap AI - Image Handler."""

from PIL import Image, ImageDraw

from src.utils.image_utils import download_image


class ImageHandler:
    """Handles image processing operations for snaps."""

    @staticmethod
    def process_lead_image(
        image_url: str, target_width: int, target_height: int, placeholder_color: str = "#E5E5EA"
    ) -> Image.Image:
        """Download and crop/resize the lead image to fit the target dimensions."""
        if not image_url:
            # Create a placeholder image
            img = Image.new("RGB", (target_width, target_height), color=placeholder_color)
            return img

        try:
            img = download_image(image_url)
        except Exception:
            # Fallback placeholder if download fails
            img = Image.new("RGB", (target_width, target_height), color=placeholder_color)
            return img

        # Crop and resize to target aspect ratio
        target_ratio = target_width / target_height
        img_ratio = img.width / img.height

        if img_ratio > target_ratio:
            # Image is wider than target, crop width
            new_width = int(img.height * target_ratio)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        elif img_ratio < target_ratio:
            # Image is taller than target, crop height
            new_height = int(img.width / target_ratio)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))

        return img.resize((target_width, target_height), Image.Resampling.LANCZOS)

    @staticmethod
    def draw_rounded_rectangle(draw: ImageDraw.Draw, xy: list[int], radius: int, fill: str):
        """Draw a rounded rectangle."""
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
