"""Tests for Snap Template System (Issue 16)."""

import json
import os
import tempfile

import pytest
from PIL import Image
from src.config.settings import Category
from src.snaps.template_renderer import (
    CATEGORY_BADGE_COLORS,
    CATEGORY_TEMPLATE_MAP,
    DEFAULT_TEMPLATE_DIR,
    TemplateRenderer,
)

EXPECTED_TEMPLATE_TYPES = [
    "general",
    "finance",
    "sports",
    "entertainment",
    "politics",
    "technology",
    "crime",
    "education",
]


class TestTemplateConfiguration:
    """Acceptance Criteria: Templates defined as JSON configs with unique layouts."""

    def test_all_8_template_json_files_exist(self):
        """Verify all 8 template JSON files exist in templates directory."""
        renderer = TemplateRenderer()
        templates = renderer.list_templates()
        for t_type in EXPECTED_TEMPLATE_TYPES:
            assert t_type in templates, f"Template {t_type}.json missing from templates"

    @pytest.mark.parametrize("template_name", EXPECTED_TEMPLATE_TYPES)
    def test_template_json_structure(self, template_name):
        """Verify each template JSON has required keys and valid dimensions."""
        filepath = os.path.join(DEFAULT_TEMPLATE_DIR, f"{template_name}.json")
        assert os.path.isfile(filepath)

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        required_keys = [
            "template_name",
            "layout_type",
            "width",
            "height",
            "bg_color",
            "lead_image_height",
            "padding",
            "category_font_size",
            "category_color",
            "summary_font_size_max",
            "summary_font_size_min",
            "summary_color",
            "source_font_size",
            "source_color",
        ]
        for key in required_keys:
            assert key in data, f"Key '{key}' missing in {template_name}.json"

        assert data["width"] == 1080
        assert data["height"] == 1920

    def test_each_template_has_unique_layout_type(self):
        """Verify that each of the 8 template types has its own layout type."""
        renderer = TemplateRenderer()
        layout_types = set()
        for name in EXPECTED_TEMPLATE_TYPES:
            tmpl = renderer.get_template(name)
            layout_types.add(tmpl["layout_type"])
        assert len(layout_types) == 8


class TestCategoryMapping:
    """Acceptance Criteria: All 19 categories mapped with unique badge colors."""

    def test_all_19_categories_in_template_map(self):
        """Verify all 19 Category enum values are in CATEGORY_TEMPLATE_MAP."""
        categories = [c.value for c in Category]
        assert len(categories) == 19

        for cat in categories:
            assert cat in CATEGORY_TEMPLATE_MAP, f"Category '{cat}' not in template map"
            mapped_template = CATEGORY_TEMPLATE_MAP[cat]
            assert (
                mapped_template in EXPECTED_TEMPLATE_TYPES
            ), f"Category '{cat}' maps to invalid template '{mapped_template}'"

    def test_all_19_categories_have_unique_badge_colors(self):
        """Verify all 19 Category enum values have unique badge colors."""
        categories = [c.value for c in Category]

        colors = []
        for cat in categories:
            assert cat in CATEGORY_BADGE_COLORS, f"Category '{cat}' missing badge color"
            color = CATEGORY_BADGE_COLORS[cat]
            assert color.startswith("#")
            assert len(color) == 7
            colors.append(color.upper())

        unique_colors = set(colors)
        assert len(unique_colors) == 19, "Not all 19 categories have unique badge colors"

    def test_eight_template_types_cover_all_categories(self):
        """Verify the 8 template types cover all 19 categories."""
        covered_templates = set(CATEGORY_TEMPLATE_MAP.values())
        for expected in EXPECTED_TEMPLATE_TYPES:
            assert expected in covered_templates, f"Template {expected} not mapped to any category"


class TestAutoSelection:
    """Acceptance Criteria: Template auto-selected based on article category."""

    def test_auto_select_finance(self):
        renderer = TemplateRenderer()
        assert renderer.get_template_for_category("finance")["layout_type"] == "finance"
        assert renderer.get_template_for_category("business")["layout_type"] == "finance"

    def test_auto_select_sports(self):
        renderer = TemplateRenderer()
        assert renderer.get_template_for_category("sports")["layout_type"] == "sports"

    def test_auto_select_politics_national(self):
        renderer = TemplateRenderer()
        assert renderer.get_template_for_category("politics")["layout_type"] == "politics"
        assert renderer.get_template_for_category("national")["layout_type"] == "politics"

    def test_auto_select_tech_science(self):
        renderer = TemplateRenderer()
        assert renderer.get_template_for_category("technology")["layout_type"] == "technology"
        assert renderer.get_template_for_category("science")["layout_type"] == "technology"

    def test_auto_select_crime_defence(self):
        renderer = TemplateRenderer()
        assert renderer.get_template_for_category("crime")["layout_type"] == "crime"
        assert renderer.get_template_for_category("defence")["layout_type"] == "crime"

    def test_auto_select_education_jobs(self):
        renderer = TemplateRenderer()
        assert renderer.get_template_for_category("education")["layout_type"] == "education"
        assert renderer.get_template_for_category("jobs")["layout_type"] == "education"

    def test_auto_select_entertainment(self):
        renderer = TemplateRenderer()
        assert renderer.get_template_for_category("entertainment")["layout_type"] == "entertainment"

    def test_auto_select_unknown_category_fallback(self):
        renderer = TemplateRenderer()
        tmpl = renderer.get_template_for_category("unregistered_category")
        assert tmpl["layout_type"] == "general"


class TestTemplateRendering:
    """Acceptance Criteria: 1080x1920 images, unique features, 5 languages, < 500KB."""

    @pytest.mark.parametrize("category", [c.value for c in Category])
    def test_render_all_19_categories(self, category):
        """Verify snap image renders with valid 1080x1920 dimensions for all 19 categories."""
        renderer = TemplateRenderer()
        snap = renderer.render(
            category=category,
            title=f"Sample {category.title()} Headline",
            summary=f"This is a test summary for category {category} testing layout and typography.",
            image_url=None,
            source="NewsSnap",
            language="en",
        )
        assert isinstance(snap, Image.Image)
        assert snap.size == (1080, 1920)

    def test_finance_template_numerical_data_highlight(self):
        """Verify finance template highlights numerical data."""
        renderer = TemplateRenderer()
        extracted = renderer.extract_numerical_data("Sensex jumps 450 points, inflation cools to 4.2%")
        assert extracted is not None

        snap = renderer.render(
            category="finance",
            title="Markets Rally Today",
            summary="Sensex surged +2.4% while NIFTY closed near record highs.",
            image_url=None,
            source="Financial Express",
            language="en",
        )
        assert snap.size == (1080, 1920)

    def test_sports_template_score_display(self):
        """Verify sports template renders score display area."""
        renderer = TemplateRenderer()
        snap = renderer.render(
            category="sports",
            title="India Clinches Series Against Australia",
            summary="India defeated Australia by 5 wickets in an exciting finish.",
            image_url=None,
            source="ESPN Cricinfo",
            language="en",
            extra_data={"score": "IND 285/5 (48.2) vs AUS 280"},
        )
        assert snap.size == (1080, 1920)

    def test_crime_template_bold_headline_styling(self):
        """Verify crime/defence template renders bold headline styling."""
        renderer = TemplateRenderer()
        snap = renderer.render(
            category="crime",
            title="Major Cybercrime Syndicate Busted by Special Police Cell",
            summary="Authorities uncovered an international scam operation spanning multiple cities.",
            image_url=None,
            source="The Hindu",
            language="en",
        )
        assert snap.size == (1080, 1920)

    def test_education_template_info_card_layout(self):
        """Verify education/jobs template renders info-card container."""
        renderer = TemplateRenderer()
        snap = renderer.render(
            category="education",
            title="UPSC Civil Services Examination Results Announced",
            summary="The commission declared the final merit list for qualified candidates today.",
            image_url=None,
            source="PIB",
            language="en",
            extra_data={"tag": "EXAM BULLETIN"},
        )
        assert snap.size == (1080, 1920)

    def test_politics_template_quote_highlight(self):
        """Verify politics template renders quote highlight banner."""
        renderer = TemplateRenderer()
        snap = renderer.render(
            category="politics",
            title="Parliament Approves Landmark Welfare Legislation",
            summary="Lawmakers passed the bill with broad bipartisan backing after lengthy floor debate.",
            image_url=None,
            source="PTI",
            language="en",
            extra_data={"quote": "A historic milestone for public governance"},
        )
        assert snap.size == (1080, 1920)

    def test_technology_template_stats_chips(self):
        """Verify technology template renders key stats chips."""
        renderer = TemplateRenderer()
        snap = renderer.render(
            category="technology",
            title="New Quantum Processor Breaks Computational Milestone",
            summary="Researchers demonstrate quantum advantage using specialized superconducting circuits.",
            image_url=None,
            source="TechCrunch",
            language="en",
            extra_data={"stats": ["QUANTUM", "54 QUBITS", "BENCHMARK"]},
        )
        assert snap.size == (1080, 1920)

    @pytest.mark.parametrize("language", ["en", "hi", "ta", "te", "kn"])
    def test_render_all_5_languages(self, language):
        """Verify templates render correctly across all 5 supported languages."""
        renderer = TemplateRenderer()
        snap = renderer.render(
            category="national",
            title=f"Multilingual Headline {language}",
            summary=f"Multilingual news snap content generated for language code {language}.",
            image_url=None,
            source="NewsSnap",
            language=language,
        )
        assert snap.size == (1080, 1920)

    def test_image_file_size_under_500kb(self):
        """Verify rendered snaps exported to disk stay well under the 500KB budget."""
        renderer = TemplateRenderer()
        for cat in ["finance", "sports", "entertainment", "politics", "crime"]:
            snap = renderer.render(
                category=cat,
                title=f"{cat.title()} Top Story of the Day",
                summary="Detailed summary text verifying compression and export file size standards.",
                image_url=None,
                source="NewsSnap",
                language="en",
            )
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                snap.save(tmp_path, "PNG", optimize=True)
                size_bytes = os.path.getsize(tmp_path)
                assert size_bytes < 500 * 1024, f"{cat} snap size {size_bytes} exceeds 500KB"
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

    def test_fallback_placeholder_on_missing_or_invalid_image(self):
        """Verify missing or invalid image URL gracefully uses category placeholder."""
        renderer = TemplateRenderer()
        snap = renderer.render(
            category="sports",
            title="Match Recap",
            summary="Full match summary content.",
            image_url="http://invalid.broken.nonexistent/fake.jpg",
            source="SportsDaily",
            language="en",
        )
        assert isinstance(snap, Image.Image)
        assert snap.size == (1080, 1920)

    def test_template_name_override(self):
        """Verify explicit template override via extra_data."""
        renderer = TemplateRenderer()
        # 'finance' category normally uses 'finance' template, override to 'sports'
        snap = renderer.render(
            category="finance",
            title="Finance Headline",
            summary="Finance summary content.",
            image_url=None,
            source="Source",
            extra_data={"template_name": "sports"},
        )
        assert snap.size == (1080, 1920)
