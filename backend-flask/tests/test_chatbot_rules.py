import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from chatbot_rules import answer_question


class ChatbotRulesTests(unittest.TestCase):
    def test_fsi_definition_includes_local_dcpr_source(self):
        answer = answer_question("What does FSI mean?")
        self.assertIn("ratio of the combined gross floor area", answer)
        self.assertIn("DCPR-2034", answer)
        self.assertIn("Regulation 2(IV)(61)", answer)

    def test_generation_explanation_sets_concept_limitations(self):
        answer = answer_question("How is the plan generated?")
        self.assertIn("three floor-plan concepts", answer)
        self.assertIn("not DCPR approvals", answer)

    def test_setback_explains_generator_assumption(self):
        answer = answer_question("Explain the building setback")
        self.assertIn("2 m inset", answer)
        self.assertIn("not a site-specific DCPR setback determination", answer)

    def test_unknown_question_does_not_make_up_a_regulatory_answer(self):
        answer = answer_question("What is the exact permitted height for my parcel?")
        self.assertIn("don't have a verified rule", answer)
        self.assertIn("I won't guess", answer)


if __name__ == "__main__":
    unittest.main()
