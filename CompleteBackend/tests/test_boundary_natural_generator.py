import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import ezdxf
import numpy as np
from shapely.affinity import rotate
from shapely.geometry import Polygon

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from boundary_natural_generator import BoundaryNaturalGenerator


class BoundaryNaturalGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.generator = BoundaryNaturalGenerator.__new__(BoundaryNaturalGenerator)
        self.plot_boundary = [(5.0, 5.0), (45.0, 5.0), (45.0, 45.0), (5.0, 45.0)]

    def test_two_apartment_program_fits_inside_plot_without_overlaps(self):
        layout = self.generator._generate_layout_with_custom_boundary(
            self.plot_boundary,
            num_apartments=2,
            bedrooms_per_apt=1,
            fsi=1.8,
            ground_coverage=0.65,
            floors=1,
            apartment_bedroom_counts=[1, 1],
        )

        self.assertEqual(len(layout["apartments"]), 2)
        self.assertEqual(
            [apartment["bedrooms"] for apartment in layout["apartments"]],
            [1, 1],
        )

        envelope = Polygon(layout["building_envelope"])
        room_polygons = [Polygon(room["polygon"]) for room in layout["all_rooms"]]
        self.assertTrue(all(envelope.covers(polygon) for polygon in room_polygons))
        for index, polygon in enumerate(room_polygons):
            for other in room_polygons[index + 1:]:
                self.assertLessEqual(polygon.intersection(other).area, 1e-6)

        self.assertAlmostEqual(
            sum(room["area"] for room in layout["all_rooms"]),
            layout["floor_area"],
        )
        self.assertLessEqual(layout["ground_coverage_utilized"], 0.65)
        self.assertLessEqual(layout["fsi_utilized"], 1.8)
        self.assertEqual(
            {element["type"] for element in layout["circulation_elements"]},
            {"staircase", "lift", "central_lobby", "corridor"},
        )
        corridor = Polygon(next(
            element["polygon"]
            for element in layout["circulation_elements"]
            if element["type"] == "corridor"
        ))
        balconies = [
            Polygon(room["polygon"])
            for apartment in layout["apartments"]
            for room in apartment["rooms"]
            if room["type"] == "balcony"
        ]
        entrances = [
            Polygon(room["polygon"])
            for apartment in layout["apartments"]
            for room in apartment["rooms"]
            if room["type"] == "entrance"
        ]
        foyers = [
            Polygon(room["polygon"])
            for apartment in layout["apartments"]
            for room in apartment["rooms"]
            if room["type"] == "foyer"
        ]
        living_rooms = [
            Polygon(room["polygon"])
            for apartment in layout["apartments"]
            for room in apartment["rooms"]
            if room["type"] == "living"
        ]
        apartment_halls = [
            Polygon(room["polygon"])
            for apartment in layout["apartments"]
            for room in apartment["rooms"]
            if room["type"] == "corridor"
        ]
        self.assertTrue(all(balcony.distance(corridor) > 0 for balcony in balconies))
        self.assertTrue(all(entrance.distance(corridor) == 0 for entrance in entrances))
        self.assertTrue(all(
            foyer.distance(apartment_hall) == 0
            for foyer, apartment_hall in zip(foyers, apartment_halls)
        ))

    def test_mixed_program_gives_every_habitable_room_facade_contact(self):
        layout = self.generator._generate_layout_with_custom_boundary(
            self.plot_boundary,
            num_apartments=2,
            bedrooms_per_apt=1,
            fsi=1.8,
            ground_coverage=0.65,
            floors=1,
            apartment_bedroom_counts=[1, 2],
        )
        self.assertEqual(
            next(
                check["status"]
                for check in layout["architectural_review"]["checks"]
                if check["id"] == "facade_potential"
            ),
            "pass",
        )
        self.assertTrue(all(
            room["has_potential_facade"]
            for apartment in layout["architectural_review"]["apartments"]
            for room in apartment["potential_facade_contacts"]
        ))

    def test_rejects_floorplate_that_cannot_fit_in_setback_envelope(self):
        small_plot = [(0.0, 0.0), (15.0, 0.0), (15.0, 15.0), (0.0, 15.0)]
        with self.assertRaisesRegex(ValueError, "does not contain a rectangular floorplate"):
            self.generator._generate_layout_with_custom_boundary(
                small_plot,
                num_apartments=1,
                bedrooms_per_apt=1,
                fsi=1.8,
                ground_coverage=0.65,
                floors=1,
                apartment_bedroom_counts=[1],
            )

    def test_rejects_mismatched_apartment_mix(self):
        with self.assertRaisesRegex(ValueError, "bedroom counts must match"):
            self.generator.generate_boundary_natural_layout(
                boundary_image_path="unused.png",
                num_apartments=3,
                bedrooms_per_apt=1,
                apartment_bedroom_counts=[1, 2],
            )

    def test_image_extraction_uses_the_enclosed_plot_not_the_page_background(self):
        self.generator.min_plot_area = 100.0
        self.generator.max_plot_area = 10000.0
        image = np.full((240, 320, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (30, 40), (290, 200), (0, 0, 0), 4)

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "plot.png"
            self.assertTrue(cv2.imwrite(str(image_path), image))
            points = self.generator.extract_boundary_from_image(
                str(image_path), target_area=1000.0
            )

        polygon = Polygon(points)
        min_x, min_y, max_x, max_y = polygon.bounds
        self.assertAlmostEqual(polygon.area, 1000.0, places=3)
        self.assertAlmostEqual((max_x - min_x) / (max_y - min_y), 260 / 160, delta=0.05)

    def test_image_without_a_closed_outline_returns_an_actionable_error(self):
        image = np.full((240, 320, 3), 255, dtype=np.uint8)

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "blank.png"
            self.assertTrue(cv2.imwrite(str(image_path), image))
            with self.assertRaisesRegex(ValueError, "Could not find an enclosed plot outline"):
                self.generator.extract_boundary_from_image(str(image_path), target_area=1000.0)

    def test_single_flat_floorplate_has_no_empty_second_apartment_row(self):
        layout = self.generator._generate_layout_with_custom_boundary(
            self.plot_boundary,
            num_apartments=1,
            bedrooms_per_apt=1,
            fsi=1.0,
            ground_coverage=0.65,
            floors=10,
            apartment_bedroom_counts=[1],
        )
        self.assertEqual(len(layout["apartments"]), 1)
        self.assertEqual(len(layout["apartment_zones"]), 1)
        self.assertLess(layout["floor_area"], 150.0)
        self.assertLessEqual(layout["fsi_utilized"], 1.0)

    def test_sample_two_2bhk_request_is_rejected_when_fsi_per_floor_is_too_small(self):
        plot_length = 1500.0 ** 0.5
        plot = [(0.0, 0.0), (plot_length, 0.0),
                (plot_length, plot_length), (0.0, plot_length)]
        with self.assertRaisesRegex(ValueError, "FSI per floor allows 150.0 sq m"):
            self.generator._generate_layout_with_custom_boundary(
                plot,
                num_apartments=2,
                bedrooms_per_apt=1,
                fsi=1.0,
                ground_coverage=0.65,
                floors=10,
                apartment_bedroom_counts=[2, 2],
            )

    def test_rejects_apartment_program_that_exceeds_ground_coverage_limit(self):
        plot = [(0.0, 0.0), (22.0, 0.0), (22.0, 22.0), (0.0, 22.0)]
        with self.assertRaisesRegex(ValueError, "ground coverage allows"):
            self.generator._generate_layout_with_custom_boundary(
                plot,
                num_apartments=6,
                bedrooms_per_apt=2,
                fsi=3.0,
                ground_coverage=0.65,
                floors=1,
                apartment_bedroom_counts=[2] * 6,
            )

    def test_rotated_plot_can_contain_a_rotated_floorplate(self):
        rotated_plot = rotate(
            Polygon(self.plot_boundary), 25, origin="centroid", use_radians=False
        )
        layout = self.generator._generate_layout_with_custom_boundary(
            list(rotated_plot.exterior.coords[:-1]),
            num_apartments=1,
            bedrooms_per_apt=1,
            fsi=1.0,
            ground_coverage=0.65,
            floors=1,
            apartment_bedroom_counts=[1],
        )
        plot = Polygon(layout["plot_boundary"])
        for room in layout["all_rooms"]:
            self.assertTrue(plot.buffer(-0.99).covers(Polygon(room["polygon"])))

    def test_all_design_variants_pass_facade_checks(self):
        layouts = [
            self.generator._generate_layout_with_custom_boundary(
                self.plot_boundary,
                num_apartments=1,
                bedrooms_per_apt=1,
                fsi=1.8,
                ground_coverage=0.65,
                floors=1,
                apartment_bedroom_counts=[1],
                design_variant=variant,
            )
            for variant in range(3)
        ]
        living_bounds = [
            Polygon(next(
                room["polygon"]
                for room in layout["apartments"][0]["rooms"]
                if room["type"] == "living"
            )).bounds
            for layout in layouts
        ]
        names = [layout["design_variant_name"] for layout in layouts]
        self.assertEqual([name.split(":")[0] for name in names],
                         ["Concept 1", "Concept 2", "Concept 3"])
        self.assertEqual(len(set(names)), 3)
        self.assertEqual(len(set(living_bounds)), 3)

    def test_same_input_and_variant_reproduce_identical_room_geometry(self):
        layouts = [
            self.generator._generate_layout_with_custom_boundary(
                self.plot_boundary,
                num_apartments=2,
                bedrooms_per_apt=1,
                fsi=1.8,
                ground_coverage=0.65,
                floors=1,
                apartment_bedroom_counts=[1, 1],
                design_variant=0,
            )
            for _ in range(2)
        ]
        room_geometry = [
            [(room["type"], room["polygon"], room["area"]) for room in layout["all_rooms"]]
            for layout in layouts
        ]
        self.assertEqual(room_geometry[0], room_geometry[1])

    def test_boundary_image_generates_visualization_and_json(self):
        self.generator.natural_generator = SimpleNamespace(colors={})
        image = np.full((240, 320, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (30, 40), (290, 200), (0, 0, 0), 4)

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "plot.png"
            png_path = Path(temp_dir) / "layout.png"
            json_path = Path(temp_dir) / "layout.json"
            self.assertTrue(cv2.imwrite(str(image_path), image))

            layout = self.generator.generate_boundary_natural_layout(
                boundary_image_path=str(image_path),
                num_apartments=1,
                bedrooms_per_apt=1,
                fsi=1.0,
                floors=1,
                target_area=1500.0,
                apartment_bedroom_counts=[1],
            )
            self.generator.visualize_boundary_layout(layout, save_path=str(png_path))
            self.generator.save_layout_data(layout, str(json_path))

            self.assertGreater(png_path.stat().st_size, 0)
            self.assertGreater(json_path.stat().st_size, 0)

    def test_dxf_export_includes_boundaries_from_saved_json_structure(self):
        self.generator.natural_generator = SimpleNamespace(colors={})
        image = np.full((240, 320, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (30, 40), (290, 200), (0, 0, 0), 4)

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "plot.png"
            dxf_path = Path(temp_dir) / "layout.dxf"
            self.assertTrue(cv2.imwrite(str(image_path), image))

            layout = self.generator.generate_boundary_natural_layout(
                boundary_image_path=str(image_path),
                num_apartments=1,
                bedrooms_per_apt=1,
                fsi=1.0,
                floors=1,
                target_area=1500.0,
                apartment_bedroom_counts=[1],
            )
            self.generator.export_to_dxf(layout, str(dxf_path))

            modelspace = ezdxf.readfile(dxf_path).modelspace()
            layers = [entity.dxf.layer for entity in modelspace]
            self.assertGreaterEqual(layers.count("boundary"), 4)
            self.assertGreaterEqual(layers.count("building_envelope"), 4)
            self.assertGreater(
                sum(layer == "doors" for layer in layers),
                0,
            )


if __name__ == "__main__":
    unittest.main()
