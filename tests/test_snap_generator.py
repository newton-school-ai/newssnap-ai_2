"""Tests for SnapGenerator."""

import os

import pytest
from PIL import Image
from src.snaps.snap_generator import SnapGenerator


def test_snap_generator_initialization():
    gen = SnapGenerator()
    assert gen.template["width"] == 1080
    assert gen.template["height"] == 1920


def test_snap_generation_fallback_image(tmp_path):
    gen = SnapGenerator()

    # Generate a snap
    snap = gen.generate(
        title="India Wins Cricket World Cup",
        summary="India defeated Australia by 6 wickets in the final...",
        image_url="invalid-url",
        category="Sports",
        source="Times of India",
        language="en",
    )

    assert isinstance(snap, Image.Image)
    assert snap.size == (1080, 1920)

    output_path = os.path.join(tmp_path, "test_snap.png")
    snap.save(output_path, "PNG", optimize=True)

    # Check if file size is reasonable (e.g. less than 500KB)
    file_size = os.path.getsize(output_path)
    assert file_size < 500 * 1024  # 500KB


@pytest.mark.parametrize("language", ["en", "hi", "ta", "te", "kn"])
def test_snap_generation_all_languages(language):
    gen = SnapGenerator()

    # Using some dummy text, it will use the correct font and fallback to dummy if needed
    snap = gen.generate(
        title=f"Test Title {language}",
        summary=f"This is a test summary for language {language}.",
        image_url="",
        category="Test",
        source="Test Source",
        language=language,
    )

    assert snap.size == (1080, 1920)
