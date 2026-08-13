import os
import unittest

from main import pick_provider


class ProviderPriorityTests(unittest.TestCase):
    def test_prefers_anthropic_when_available(self):
        original = {"ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"), "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"), "GOOGLE_API_KEY": os.environ.get("GOOGLE_API_KEY")}
        try:
            os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
            os.environ["GEMINI_API_KEY"] = "AIza-test"
            os.environ.pop("GOOGLE_API_KEY", None)
            self.assertEqual(pick_provider(), "anthropic")
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_falls_back_to_gemini_when_anthropic_missing(self):
        original = {"ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"), "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"), "GOOGLE_API_KEY": os.environ.get("GOOGLE_API_KEY")}
        try:
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ["GEMINI_API_KEY"] = "AIza-test"
            os.environ.pop("GOOGLE_API_KEY", None)
            self.assertEqual(pick_provider(), "gemini")
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_uses_rules_without_llm_keys(self):
        original = {"ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"), "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"), "GOOGLE_API_KEY": os.environ.get("GOOGLE_API_KEY")}
        try:
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            self.assertEqual(pick_provider(), "rules")
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
