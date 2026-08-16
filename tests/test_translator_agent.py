"""Tests for Multi-Language Translator Agent (Issue 13).

Acceptance Criteria covered:
  AC1 - Translations produced for all 5 languages from any source language
  AC2 - Translations read naturally (not word-by-word literal translation)
  AC3 - Language-specific prompts handle idioms and cultural context
  AC4 - Back-translation quality check passes for 90%+ of translations
  AC5 - IndicTrans2 fallback works when Groq API is unavailable
  AC6 - Batch translation: 20 summaries to all 5 languages in < 60 seconds
  AC7 - Output text uses correct script for each language (Devanagari, Tamil, Telugu, Kannada)
  AC8 - Numbers, proper nouns, and abbreviations handled correctly across languages
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from src.agents.translator_agent import TranslatorAgent
from src.utils.language_utils import detect_language, validate_script

# Mock summary to translate
SAMPLE_EN_SUMMARY = (
    "India scored 350 runs in the first innings of the test match against England at Lords. "
    "Virat Kohli hit a spectacular century. The RBI noted that this victory boosts national morale."
)

# Mock translated texts simulating natural phrasing and correct scripts
MOCK_TRANSLATIONS = {
    "hi": "भारत ने लॉर्ड्स में इंग्लैंड के खिलाफ टेस्ट मैच की पहली पारी में 350 रन बनाए। विराट कोहली ने शानदार शतक लगाया। RBI ने कहा कि इस जीत से राष्ट्रीय मनोबल बढ़ता है।",
    "ta": "லார்ட்ஸில் இங்கிலாந்துக்கு எதிரான டெஸ்ட் போட்டியின் முதல் இன்னிங்ஸில் இந்தியா 350 ரன்கள் எடுத்தது. விராட் கோலி ஒரு அற்புதமான சதத்தை அடித்தார். இந்த வெற்றி தேசிய மன உறுதியை அதிகரிக்கும் என்று RBI குறிப்பிட்டது.",
    "te": "లార్డ్స్‌లో ఇంగ్లాండ్‌తో జరిగిన టెస్ట్ మ్యాచ్ తొలి ఇన్నింగ్స్‌లో భారత్ 350 పరుగులు చేసింది. విరాట్ కోహ్లీ అద్భుతమైన సెంచరీ సాధించాడు. ఈ విజయం జాతీయ ధైర్యాన్ని పెంచుతుందని RBI పేర్కొంది.",
    "kn": "ಲಾರ್ಡ್ಸ್‌ನಲ್ಲಿ ಇಂಗ್ಲೆಂಡ್ ವಿರುದ್ಧದ ಟೆಸ್ಟ್ ಪಂದ್ಯದ ಮೊದಲ ಇನ್ನಿಂಗ್ಸ್‌ನಲ್ಲಿ ಭಾರತ 350 ರನ್ ಗಳಿಸಿತು. ವಿರಾಟ್ ಕೊಹ್ಲಿ ಅದ್ಭುತ ಶತಕ ಬಾರಿಸಿದರು. ಈ ವಿಜಯವು ರಾಷ್ಟ್ರೀಯ ಸ್ಥೈರ್ಯವನ್ನು ಹೆಚ್ಚಿಸುತ್ತದೆ ಎಂದು RBI ಗಮನಿಸಿದೆ.",
}


@pytest.fixture
def mock_groq_client():
    """Mock the Groq client to return predefined translated texts."""
    with patch("src.agents.translator_agent.groq.Groq") as mock_groq:
        client_instance = mock_groq.return_value

        def mock_create(*args, **kwargs):
            messages = kwargs.get("messages", [])
            system_prompt = messages[0]["content"] if messages else ""

            # Simple routing based on the system prompt target language
            if "back into English" in system_prompt:
                content = SAMPLE_EN_SUMMARY
            elif "to Hindi" in system_prompt:
                content = MOCK_TRANSLATIONS["hi"]
            elif "to Tamil" in system_prompt:
                content = MOCK_TRANSLATIONS["ta"]
            elif "to Telugu" in system_prompt:
                content = MOCK_TRANSLATIONS["te"]
            elif "to Kannada" in system_prompt:
                content = MOCK_TRANSLATIONS["kn"]
            else:
                content = "Translated text."

            mock_choice = MagicMock()
            mock_choice.message.content = content
            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            return mock_response

        client_instance.chat.completions.create.side_effect = mock_create
        yield client_instance


# ---------------------------------------------------------------------------
# AC1 - Translations produced for all 5 languages
# ---------------------------------------------------------------------------
def test_translate_all_languages(mock_groq_client):
    """AC1: Translator agent returns a dict with translations for all 5 languages."""
    agent = TranslatorAgent(api_key="test")
    translations = agent.translate_all(SAMPLE_EN_SUMMARY, source_lang="en")

    assert "en" in translations
    assert "hi" in translations
    assert "ta" in translations
    assert "te" in translations
    assert "kn" in translations

    assert translations["hi"] == MOCK_TRANSLATIONS["hi"]


# ---------------------------------------------------------------------------
# AC2 & AC3 - Natural phrasing & Language-specific prompts
# ---------------------------------------------------------------------------
def test_system_prompt_instructs_natural_translation():
    """AC2/AC3: The system prompt must explicitly request natural, non-literal translation and handle idioms."""
    from src.agents.translator_agent import TRANSLATOR_SYSTEM_PROMPT

    assert "not word-for-word literally" in TRANSLATOR_SYSTEM_PROMPT.lower()
    assert "idioms and cultural context" in TRANSLATOR_SYSTEM_PROMPT.lower()


# ---------------------------------------------------------------------------
# AC4 - Back-translation quality check
# ---------------------------------------------------------------------------
def test_back_translate_quality_check(mock_groq_client):
    """AC4: Back-translation should pass the semantic overlap check (>0.5 overlap)."""
    agent = TranslatorAgent(api_key="test")
    # Using the mock, it translates the Hindi mock text back to SAMPLE_EN_SUMMARY
    passed, score = agent.back_translate_check(SAMPLE_EN_SUMMARY, MOCK_TRANSLATIONS["hi"], target_lang="hi")
    assert passed is True
    assert score >= 0.5  # Since it returns the exact same string, overlap is 1.0
    assert score == 1.0


def test_back_translate_quality_check_failure(mock_groq_client):
    """AC4: Low semantic overlap should fail the quality check."""
    agent = TranslatorAgent(api_key="test")
    # Test against completely unrelated original text
    unrelated_text = "The stock market crashed today."
    passed, score = agent.back_translate_check(unrelated_text, MOCK_TRANSLATIONS["hi"], target_lang="hi")
    assert passed is False
    assert score < 0.5


# ---------------------------------------------------------------------------
# AC5 - IndicTrans2 fallback works when Groq API is unavailable
# ---------------------------------------------------------------------------
def test_indictrans2_fallback_on_api_failure():
    """AC5: If Groq throws an exception, the fallback mechanism should be used."""
    with patch("src.agents.translator_agent.groq.Groq") as mock_groq:
        client_instance = mock_groq.return_value
        client_instance.chat.completions.create.side_effect = Exception("API Quota Exceeded")

        agent = TranslatorAgent(api_key="test")
        result = agent.translate(SAMPLE_EN_SUMMARY, "hi")

        assert "[IndicTrans2 Fallback: hi]" in result
        assert SAMPLE_EN_SUMMARY in result


# ---------------------------------------------------------------------------
# AC6 - Batch translation: 20 summaries in < 60 seconds
# ---------------------------------------------------------------------------
def test_batch_translation_performance(mock_groq_client):
    """AC6: Translates 20 summaries to all 5 languages in < 60 seconds."""
    agent = TranslatorAgent(api_key="test")
    summaries = [f"Article {i} summary about politics." for i in range(20)]

    start = time.time()
    results = agent.batch_translate(summaries)
    elapsed = time.time() - start

    assert len(results) == 20
    assert elapsed < 60.0

    # Ensure all languages are present in the batch output
    for res in results:
        assert set(res.keys()) == {"en", "hi", "ta", "te", "kn"}


# ---------------------------------------------------------------------------
# AC7 - Output text uses correct script
# ---------------------------------------------------------------------------
def test_script_validation():
    """AC7: Validate script helper correctly identifies language scripts."""
    # Hindi/Devanagari
    assert validate_script(MOCK_TRANSLATIONS["hi"], "hi") is True
    assert validate_script(MOCK_TRANSLATIONS["hi"], "ta") is False

    # Tamil
    assert validate_script(MOCK_TRANSLATIONS["ta"], "ta") is True
    assert validate_script(MOCK_TRANSLATIONS["ta"], "te") is False

    # Telugu
    assert validate_script(MOCK_TRANSLATIONS["te"], "te") is True
    assert validate_script(MOCK_TRANSLATIONS["te"], "hi") is False

    # Kannada
    assert validate_script(MOCK_TRANSLATIONS["kn"], "kn") is True
    assert validate_script(MOCK_TRANSLATIONS["kn"], "en") is False

    # English
    assert validate_script("Standard english text 123", "en") is True


# ---------------------------------------------------------------------------
# AC8 - Numbers, proper nouns, and abbreviations handled correctly
# ---------------------------------------------------------------------------
def test_proper_nouns_and_numbers_extraction():
    """AC8: Verify numbers and proper nouns like abbreviations are preserved."""
    from src.utils.language_utils import extract_proper_nouns_and_numbers

    text = "In 2024, the RBI projected a 7.2% growth for India and USA."
    numbers, proper_nouns = extract_proper_nouns_and_numbers(text)

    assert "2024" in numbers
    assert "7.2" in numbers
    assert "RBI" in proper_nouns
    assert "India" in proper_nouns
    assert "USA" in proper_nouns


def test_language_detection():
    """Verify that detect_language falls back gracefully."""
    assert detect_language("") == "en"

    # Hindi frequency check
    assert detect_language("यह एक हिंदी वाक्य है।") == "hi"

    # Tamil frequency check
    assert detect_language("இது ஒரு தமிழ் வாக்கியம்.") == "ta"
