import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gemini_extractor import extract_with_gemini


class GeminiExtractorTests(unittest.TestCase):
    @patch("gemini_extractor.types.GenerateContentConfig")
    @patch("gemini_extractor.genai.Client")
    def test_extract_with_gemini_does_not_pass_response_schema(self, mock_client_cls, mock_config_cls):
        fake_client = MagicMock()
        fake_response = MagicMock()
        fake_response.parsed = {
            "source_file": "demo.pdf",
            "policy_metadata": {},
            "demographics": {},
            "room_rent_hospitalization": {},
            "maternity_details": {},
            "waiting_periods": {},
            "specific_benefits": {},
            "infertility_and_ambulance": {},
            "buffer_and_waiver": {},
            "extraction_meta": {
                "engine": "llm",
                "provider": "gemini",
                "model": "gemini-2.5-flash"
            }
        }
        fake_client.models.generate_content.return_value = fake_response
        mock_client_cls.return_value = fake_client
        mock_config_cls.side_effect = lambda **kwargs: kwargs

        result = extract_with_gemini("document text", "demo.pdf", api_key="test-key")

        self.assertIn("source_file", result)
        self.assertEqual(result["source_file"], "demo.pdf")
        config_kwargs = mock_config_cls.call_args.kwargs
        self.assertNotIn("response_schema", config_kwargs)

    @patch("gemini_extractor.types.GenerateContentConfig")
    @patch("gemini_extractor.genai.Client")
    def test_extract_with_gemini_injects_source_file_before_validation(self, mock_client_cls, mock_config_cls):
        fake_client = MagicMock()
        fake_response = MagicMock()
        fake_response.parsed = {
            "policy_metadata": {},
            "demographics": {},
            "room_rent_hospitalization": {},
            "maternity_details": {},
            "waiting_periods": {},
            "specific_benefits": {},
            "infertility_and_ambulance": {},
            "buffer_and_waiver": {},
            "extraction_meta": {
                "engine": "llm",
                "provider": "gemini",
                "model": "gemini-2.5-flash"
            }
        }
        fake_client.models.generate_content.return_value = fake_response
        mock_client_cls.return_value = fake_client
        mock_config_cls.side_effect = lambda **kwargs: kwargs

        result = extract_with_gemini("document text", "demo.pdf", api_key="test-key")

        self.assertEqual(result["source_file"], "demo.pdf")
        self.assertEqual(result["extraction_meta"]["provider"], "gemini")

    @patch("gemini_extractor.types.GenerateContentConfig")
    @patch("gemini_extractor.genai.Client")
    def test_extract_with_gemini_flattens_numeric_value_objects(self, mock_client_cls, mock_config_cls):
        fake_client = MagicMock()
        fake_response = MagicMock()
        fake_response.parsed = {
            "source_file": "demo.pdf",
            "policy_metadata": {},
            "demographics": {
                "total_employees": {"value": 115, "raw_text": "115 employees", "source_page": 1},
                "total_lives_covered": {"value": 120, "raw_text": "120 lives covered", "source_page": 1},
            },
            "room_rent_hospitalization": {},
            "maternity_details": {},
            "waiting_periods": {},
            "specific_benefits": {},
            "infertility_and_ambulance": {},
            "buffer_and_waiver": {},
            "extraction_meta": {"engine": "llm", "provider": "gemini", "model": "gemini-2.5-flash"},
        }
        fake_client.models.generate_content.return_value = fake_response
        mock_client_cls.return_value = fake_client
        mock_config_cls.side_effect = lambda **kwargs: kwargs

        result = extract_with_gemini("document text", "demo.pdf", api_key="test-key")

        self.assertEqual(result["demographics"]["total_employees"], 115)
        self.assertEqual(result["demographics"]["total_lives_covered"], 120)


if __name__ == "__main__":
    unittest.main()
