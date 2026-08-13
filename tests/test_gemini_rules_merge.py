import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gemini_extractor import extract_with_gemini


class GeminiRulesMergeTests(unittest.TestCase):
    @patch("gemini_extractor.extract_with_rules")
    @patch("gemini_extractor.types.GenerateContentConfig")
    @patch("gemini_extractor.genai.Client")
    def test_merges_rules_metadata_when_gemini_omits_core_fields(self, mock_client_cls, mock_config_cls, mock_rules):
        mock_rules.return_value = {
            "source_file": "demo.pdf",
            "policy_metadata": {
                "insurer_name": "Care Health Insurance",
                "policy_number": "41201895",
                "inception_or_renewal_date": "02-Apr-2022",
                "policy_end_date": "01-Apr-2023",
                "inception_premium": "50000",
            },
            "demographics": {"total_employees": 115},
            "room_rent_hospitalization": {},
            "maternity_details": {},
            "waiting_periods": {},
            "specific_benefits": {},
            "infertility_and_ambulance": {},
            "buffer_and_waiver": {},
            "extraction_meta": {"engine": "rules", "note": "fallback"},
        }

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
            "extraction_meta": {"engine": "llm", "provider": "gemini", "model": "gemini-2.5-flash"},
        }
        fake_client.models.generate_content.return_value = fake_response
        mock_client_cls.return_value = fake_client
        mock_config_cls.side_effect = lambda **kwargs: kwargs

        result = extract_with_gemini("document text", "demo.pdf", api_key="test-key")

        self.assertEqual(result["policy_metadata"]["insurer_name"], "Care Health Insurance")
        self.assertEqual(result["policy_metadata"]["policy_number"], "41201895")
        self.assertEqual(result["demographics"]["total_employees"], 115)


if __name__ == "__main__":
    unittest.main()
