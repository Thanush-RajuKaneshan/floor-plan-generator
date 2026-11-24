import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import app
import fsi_integration


class ChatbotRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_chatbot_server_import_does_not_initialize_fsi_model(self):
        self.assertIsNone(fsi_integration.fsi_calculator)

    def test_chatbot_api_requires_login(self):
        response = self.client.post(
            "/api/chatbot",
            json={"message": "What is FSI?"},
        )
        self.assertEqual(response.status_code, 401)

    def test_chatbot_api_answers_authenticated_question(self):
        with self.client.session_transaction() as session:
            session["username"] = "chatbot-test"

        response = self.client.post(
            "/api/chatbot",
            json={"message": "What is FSI?"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("DCPR-2034", response.get_json()["answer"])

    def test_chatbot_api_rejects_empty_or_oversized_messages(self):
        with self.client.session_transaction() as session:
            session["username"] = "chatbot-test"

        empty_response = self.client.post("/api/chatbot", json={"message": "  "})
        long_response = self.client.post(
            "/api/chatbot",
            json={"message": "x" * 501},
        )
        self.assertEqual(empty_response.status_code, 400)
        self.assertEqual(long_response.status_code, 413)

    def test_chatbot_page_uses_safe_rendering_and_api(self):
        response = self.client.get("/chatbot")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/api/chatbot", response.data)
        self.assertIn(b"bubble.textContent = text", response.data)
        self.assertNotIn(b"chatWindow.innerHTML", response.data)

    def test_local_ai_plan_review_requires_login(self):
        response = self.client.post("/api/submission/1/ai-review")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
