import unittest
from unittest.mock import patch

import llm_chat
from local_plan_ai import review_plan_locally


class LocalPlanAiTests(unittest.TestCase):
    def test_unreachable_model_returns_actionable_error(self):
        with patch.object(llm_chat, "OLLAMA_URL", "http://127.0.0.1:9"):
            with self.assertRaisesRegex(RuntimeError, "not reachable"):
                review_plan_locally({})

    def test_chat_falls_back_to_rules_when_model_is_down(self):
        with patch.object(llm_chat, "OLLAMA_URL", "http://127.0.0.1:9"):
            result = llm_chat.chat("What is FSI?")
        self.assertEqual(result["backend"], "rules")
        self.assertIn("DCPR-2034", result["answer"])

    def test_chat_grounds_prompt_in_dcpr_and_plan(self):
        with patch.object(llm_chat, "_ollama_chat", return_value="ok") as fake:
            result = llm_chat.chat("What is FSI?", plan_facts={"fsi_used": 1.2})
        prompt = fake.call_args[0][0][0]["content"]
        self.assertIn("[p.", prompt)
        self.assertIn("fsi_used", prompt)
        self.assertEqual(result["answer"], "ok")
        self.assertTrue(result["sources"])


if __name__ == "__main__":
    unittest.main()
