import sys
import unittest
from pathlib import Path

from shapely.geometry import Polygon

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from boundary_natural_generator import BoundaryNaturalGenerator
from plan_quality import build_local_ai_input


class PlanQualityTests(unittest.TestCase):
    def setUp(self):
        self.generator = BoundaryNaturalGenerator.__new__(BoundaryNaturalGenerator)

    def generate_layout(self, bedrooms):
        return self.generator._generate_layout_with_custom_boundary(
            [(5.0, 5.0), (45.0, 5.0), (45.0, 45.0), (5.0, 45.0)],
            num_apartments=1,
            bedrooms_per_apt=bedrooms[0],
            fsi=1.8,
            ground_coverage=0.65,
            floors=1,
            apartment_bedroom_counts=bedrooms,
        )

    def test_access_review_checks_all_apartment_rooms_are_reachable(self):
        layout = self.generate_layout([1])
        checks = {
            check["id"]: check["status"]
            for check in layout["architectural_review"]["checks"]
        }
        self.assertEqual(checks["room_access"], "pass")
        self.assertEqual(checks["common_access"], "pass")
        self.assertGreater(layout["architectural_review"]["door_candidate_count"], 0)

    def test_four_bedroom_layout_passes_strict_facade_access(self):
        layout = self.generate_layout([4])
        checks = {
            check["id"]: check["status"]
            for check in layout["architectural_review"]["checks"]
        }
        self.assertEqual(checks["facade_potential"], "pass")
        self.assertTrue(all(
            room["has_potential_facade"]
            for room in layout["architectural_review"]["apartments"][0][
                "potential_facade_contacts"
            ]
        ))
        bedrooms = [
            room
            for room in layout["apartments"][0]["rooms"]
            if room["type"] in {"bedroom", "master_bedroom"}
        ]
        self.assertEqual(len(bedrooms), 4)
        for room in bedrooms:
            polygon = Polygon(room["polygon"])
            min_x, min_y, max_x, max_y = polygon.bounds
            self.assertGreaterEqual(min(max_x - min_x, max_y - min_y), 2.7 - 1e-6)

    def test_one_through_four_bedroom_programs_pass_access_and_facade_checks(self):
        for bedrooms in range(1, 5):
            with self.subTest(bedrooms=bedrooms):
                layout = self.generate_layout([bedrooms])
                check_statuses = {
                    check["id"]: check["status"]
                    for check in layout["architectural_review"]["checks"]
                }
                self.assertEqual(check_statuses["room_access"], "pass")
                self.assertEqual(check_statuses["facade_potential"], "pass")

    def test_local_ai_receives_structured_plan_facts_not_uploaded_image(self):
        layout = self.generate_layout([1])
        facts = build_local_ai_input(layout)
        self.assertIn("geometry_checks", facts)
        self.assertIn("rooms", facts["apartments"][0])
        self.assertIn("design_issues", facts["apartments"][0])
        self.assertIn("rooms_without_facade_potential", facts["apartment_findings"][0])
        self.assertEqual(facts["apartment_findings"][0]["rooms_without_facade_potential"], [])
        self.assertNotIn("boundary_source", facts)
        self.assertNotIn("image_path", facts)


if __name__ == "__main__":
    unittest.main()
