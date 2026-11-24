#!/usr/bin/env python3
"""
Boundary Natural Generator - Integration of Boundary-Based Generation with Natural Multi-Apartment Layout
Combines the boundary extraction capabilities with the sophisticated architectural logic from natural_multi_apartment_generator.py
"""

import os
import sys
import math
import cv2
import numpy as np
# Set matplotlib to use non-GUI backend before importing pyplot
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for web server
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Polygon
from matplotlib.collections import PatchCollection
from typing import List, Dict, Tuple, Optional
from shapely.affinity import affine_transform
from shapely.geometry import Polygon as ShapelyPolygon, Point, box
from shapely.ops import unary_union
from plan_quality import build_geometry_review
from apartment_solver import (
    SHAFT_OK, bathroom_count as bathroom_count_for, frontage_needed, solve_apartment,
)

ROOM_ZONES = {
    "entrance": "apartment_circulation", "corridor": "apartment_circulation",
    "living": "public", "dining": "public", "kitchen": "service", "utility": "service",
    "bathroom": "service", "master_bathroom": "service", "storage": "service",
}
import json
from datetime import datetime

# Import the natural apartment generator
try:
    from natural_multi_apartment_generator import NaturalMultiApartmentFloorPlanGenerator
except ImportError:
    print("❌ Error: Could not import NaturalMultiApartmentFloorPlanGenerator")
    # Don't sys.exit() when used as a module - raise ImportError instead
    raise ImportError("NaturalMultiApartmentFloorPlanGenerator not available")

# Import DXF export capabilities
try:
    from dxf_export_module import FloorPlanDXFExporter
    print("✅ DXF export module loaded successfully")
    DXF_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Warning: DXF export module not available: {e}")
    FloorPlanDXFExporter = None
    DXF_AVAILABLE = False

class BoundaryNaturalGenerator:
    """Integrated boundary-based natural apartment generator"""
    
    def __init__(self):
        """Initialize the boundary natural generator"""
        print("🏗️ Initializing Boundary Natural Generator...")
        
        # Initialize the natural apartment generator
        self.natural_generator = NaturalMultiApartmentFloorPlanGenerator()
        
        # Remove fixed target area - now supports dynamic sizing
        self.normalize_to_fixed_area = False  # Allow natural plot sizes
        self.min_plot_area = 100.0  # Minimum viable plot area in sq m
        self.max_plot_area = 10000.0  # Maximum reasonable plot area in sq m
        
        print("✅ Boundary Natural Generator initialized with dynamic sizing support")
    
    def extract_boundary_from_image(self, image_path: str, 
                                   target_area: Optional[float] = None) -> Optional[List[Tuple[float, float]]]:
        """Extract boundary from user-provided image with optional target area"""
        
        if not os.path.exists(image_path):
            raise ValueError(f"Plot boundary image not found: {image_path}")
        
        try:
            print(f"📁 Processing boundary image: {os.path.basename(image_path)}")
            
            # Read and process image
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(
                    f"Could not read plot boundary image: {os.path.basename(image_path)}"
                )
            
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Accept either dark outlines on a light page or light outlines on a dark page.
            _, dark_foreground = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU
            )
            _, light_foreground = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
            )
            image_height, image_width = gray.shape
            candidates = []
            for mask in (dark_foreground, light_foreground):
                contours, _ = cv2.findContours(
                    mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )
                for contour in contours:
                    x, y, width, height = cv2.boundingRect(contour)
                    touches_image_edge = (
                        x <= 1 or y <= 1
                        or x + width >= image_width - 1
                        or y + height >= image_height - 1
                    )
                    if not touches_image_edge and cv2.contourArea(contour) > 0:
                        candidates.append(contour)

            if not candidates:
                raise ValueError(
                    "Could not find an enclosed plot outline. Leave a light/dark margin "
                    "between the plot boundary and the image edges."
                )

            largest_contour = max(candidates, key=cv2.contourArea)
            perimeter = cv2.arcLength(largest_contour, True)
            simplified_contour = cv2.approxPolyDP(
                largest_contour, max(1.0, perimeter * 0.002), True
            )
            if len(simplified_contour) < 3:
                raise ValueError("The detected plot outline has fewer than three corners")

            boundary_points = [
                (float(point[0][0]), float(point[0][1]))
                for point in simplified_contour
            ]
            if not ShapelyPolygon(boundary_points).is_valid:
                raise ValueError("The detected plot outline is not a valid polygon")

            # Normalize and scale the boundary (preserve original size unless specified)
            processed_boundary = self.process_boundary(boundary_points, target_area)
            
            print(f"✅ Extracted boundary with {len(processed_boundary)} points")
            return processed_boundary
            
        except cv2.error as exc:
            raise ValueError(f"Could not process plot boundary image: {exc}") from exc
    
    def process_boundary(self, boundary_points: List[Tuple[float, float]], 
                        target_area: Optional[float] = None) -> List[Tuple[float, float]]:
        """Process boundary points - normalize only if needed or requested"""
        
        if not boundary_points:
            return boundary_points
        
        # Create polygon from points
        boundary_poly = ShapelyPolygon(boundary_points)
        current_area = boundary_poly.area
        
        if current_area <= 0:
            print("❌ Invalid boundary area")
            return boundary_points
        
        # Convert pixel coordinates to reasonable metric coordinates if needed
        processed_points = self._convert_pixel_to_metric(boundary_points, current_area)
        processed_poly = ShapelyPolygon(processed_points)
        processed_area = processed_poly.area
        
        # Only normalize if specifically requested or if area is outside reasonable bounds
        if target_area is not None:
            print(f"📊 Normalizing to target area: {target_area:.1f} sq m")
            processed_points = self._normalize_to_target_area(processed_points, target_area)
            final_poly = ShapelyPolygon(processed_points)
            final_area = final_poly.area
            print(f"📊 Boundary processed: {current_area:.1f} → {final_area:.1f} sq m")
        elif processed_area < self.min_plot_area or processed_area > self.max_plot_area:
            # Auto-scale to reasonable size if outside bounds
            if processed_area < self.min_plot_area:
                auto_target = self.min_plot_area * 2  # 200 sq m minimum
            else:
                auto_target = self.max_plot_area * 0.8  # 8000 sq m maximum
            
            print(f"📊 Auto-scaling plot from {processed_area:.1f} to {auto_target:.1f} sq m")
            processed_points = self._normalize_to_target_area(processed_points, auto_target)
            final_poly = ShapelyPolygon(processed_points)
            final_area = final_poly.area
            print(f"📊 Boundary auto-scaled: {current_area:.1f} → {final_area:.1f} sq m")
        else:
            # Keep original size if within reasonable bounds
            final_area = processed_area
            print(f"📊 Boundary preserved at original scale: {final_area:.1f} sq m")
        
        return processed_points
    
    def _convert_pixel_to_metric(self, boundary_points: List[Tuple[float, float]], 
                               current_area: float) -> List[Tuple[float, float]]:
        """Convert pixel coordinates to metric coordinates if needed"""
        
        # Check if coordinates are likely in pixels (large numbers, integer-like)
        max_coord = max(max(abs(x), abs(y)) for x, y in boundary_points)
        avg_coord = sum(abs(x) + abs(y) for x, y in boundary_points) / (2 * len(boundary_points))
        
        # If coordinates are very large (likely pixels), convert to meters
        if max_coord > 1000 or avg_coord > 500:
            print(f"📐 Converting pixel coordinates to metric (max coord: {max_coord:.0f})")
            
            # Assume typical building plot: convert pixels to meters
            # Typical residential plot: 20-50m per side
            # Scale factor based on assumption that 100-500 pixels = 20-50 meters
            pixel_to_meter_ratio = 0.1  # 10 pixels per meter (adjustable)
            
            metric_points = []
            for x, y in boundary_points:
                metric_x = x * pixel_to_meter_ratio
                metric_y = y * pixel_to_meter_ratio
                metric_points.append((metric_x, metric_y))
            
            # Ensure positive coordinates
            min_x = min(x for x, y in metric_points)
            min_y = min(y for x, y in metric_points)
            
            if min_x < 0 or min_y < 0:
                offset_x = max(0, -min_x + 5)  # 5m buffer
                offset_y = max(0, -min_y + 5)  # 5m buffer
                metric_points = [(x + offset_x, y + offset_y) for x, y in metric_points]
            
            metric_area = ShapelyPolygon(metric_points).area
            print(f"📐 Converted {len(metric_points)} points, area: {metric_area:.1f} sq m")
            return metric_points
        else:
            # Already in reasonable metric scale
            # Ensure positive coordinates
            min_x = min(x for x, y in boundary_points)
            min_y = min(y for x, y in boundary_points)
            
            if min_x < 0 or min_y < 0:
                offset_x = max(0, -min_x + 5)  # 5m buffer
                offset_y = max(0, -min_y + 5)  # 5m buffer
                return [(x + offset_x, y + offset_y) for x, y in boundary_points]
            
            return boundary_points
    
    def _normalize_to_target_area(self, boundary_points: List[Tuple[float, float]], 
                                 target_area: float) -> List[Tuple[float, float]]:
        """Normalize boundary to specific target area"""
        
        boundary_poly = ShapelyPolygon(boundary_points)
        current_area = boundary_poly.area
        
        if current_area <= 0:
            return boundary_points
        
        # Calculate scale factor to achieve target area
        scale_factor = (target_area / current_area) ** 0.5
        
        # Get centroid for scaling
        centroid = boundary_poly.centroid
        cx, cy = centroid.x, centroid.y
        
        # Scale points around centroid
        scaled_points = []
        for x, y in boundary_points:
            # Translate to origin
            dx = x - cx
            dy = y - cy
            
            # Scale
            scaled_x = dx * scale_factor
            scaled_y = dy * scale_factor
            
            # Translate back (with offset to ensure positive coordinates)
            final_x = scaled_x + cx * scale_factor + 5  # 5m buffer
            final_y = scaled_y + cy * scale_factor + 5  # 5m buffer
            
            scaled_points.append((final_x, final_y))
        
        return scaled_points
    
    def calculate_optimal_apartment_sizing(self, plot_area: float, num_apartments: int, 
                                         bedrooms_per_apt: int, fsi: float, 
                                         ground_coverage: float) -> Dict:
        """Calculate optimal apartment and room sizing based on actual plot area"""
        
        # Calculate available building area
        max_ground_area = plot_area * ground_coverage
        max_total_buildable = plot_area * fsi
        
        # Area per apartment
        area_per_apartment = max_ground_area / num_apartments
        
        # Calculate room scaling factor based on apartment size
        # Base apartment sizes for different bedroom counts
        base_apartment_areas = {
            1: 45,   # 1BHK base: ~45 sq m
            2: 65,   # 2BHK base: ~65 sq m  
            3: 85,   # 3BHK base: ~85 sq m
            4: 110   # 4BHK base: ~110 sq m
        }
        
        base_area = base_apartment_areas.get(bedrooms_per_apt, 65)
        scale_factor = max(0.8, min(3.0, area_per_apartment / base_area))  # Keep reasonable scaling
        
        sizing_info = {
            'plot_area': plot_area,
            'max_ground_area': max_ground_area,
            'max_total_buildable': max_total_buildable,
            'area_per_apartment': area_per_apartment,
            'base_apartment_area': base_area,
            'room_scale_factor': scale_factor,
            'estimated_efficiency': min(0.85, area_per_apartment / (base_area * 1.2))
        }
        
        print(f"📊 Apartment sizing analysis:")
        print(f"   🏠 Area per apartment: {area_per_apartment:.1f} sq m")
        print(f"   📏 Room scale factor: {scale_factor:.2f}x")
        print(f"   ⚡ Space efficiency: {sizing_info['estimated_efficiency']*100:.1f}%")
        
        return sizing_info
    
    def generate_boundary_natural_layout(
        self, 
        boundary_image_path: str,
        num_apartments: int, 
        bedrooms_per_apt: int,
        fsi: float = 1.8,
        ground_coverage: float = 0.65,
        floors: int = 1,
        target_area: Optional[float] = None,
        apartment_bedroom_counts: Optional[List[int]] = None,
        design_variant: int = 0
    ) -> Dict:
        """Generate a dimensioned, non-overlapping floor plan within a custom boundary."""

        if num_apartments < 1:
            raise ValueError("At least one apartment is required")
        if bedrooms_per_apt not in {1, 2, 3, 4}:
            raise ValueError("Apartments must have between 1 and 4 bedrooms")
        if fsi <= 0 or not 0 < ground_coverage <= 1 or floors < 1:
            raise ValueError("FSI and floor count must be positive; coverage must be in (0, 1]")
        if target_area is not None and target_area <= 0:
            raise ValueError("Target plot area must be positive")

        if apartment_bedroom_counts is None:
            apartment_bedroom_counts = [bedrooms_per_apt] * num_apartments
        if len(apartment_bedroom_counts) != num_apartments:
            raise ValueError("Apartment bedroom counts must match the apartment count")
        if any(count not in {1, 2, 3, 4} for count in apartment_bedroom_counts):
            raise ValueError("Apartments must have between 1 and 4 bedrooms")
        if design_variant not in {0, 1, 2}:
            raise ValueError("Design variant must be 0, 1, or 2")
        
        print(
            f"\n🏢 Generating {num_apartments} apartments with bedroom counts "
            f"{apartment_bedroom_counts} within custom boundary"
        )
        print(f"🖼️ Boundary image: {os.path.basename(boundary_image_path)}")
        print(f"🏗️ FSI: {fsi}, Ground Coverage: {ground_coverage*100}%, Floors: {floors}")
        if target_area is not None:
            print(f"🎯 Target area: {target_area:.1f} sq m")
        else:
            print(f"🎯 Using natural plot dimensions")
        
        # Extract boundary from image with optional target area
        boundary_points = self.extract_boundary_from_image(boundary_image_path, target_area)
        if not boundary_points:
            raise ValueError("Could not extract boundary from image")
        
        # Generate a shared-core floor plan from the extracted boundary.
        layout = self._generate_layout_with_custom_boundary(
            boundary_points,
            num_apartments,
            bedrooms_per_apt,
            fsi,
            ground_coverage,
            floors,
            apartment_bedroom_counts,
            design_variant
        )
        
        # Add boundary-specific metadata
        layout['boundary_source'] = boundary_image_path
        layout['boundary_type'] = 'custom_user_defined'
        layout['generation_method'] = 'boundary_natural_integration'
        layout['original_area_preserved'] = target_area is None
        layout['specified_target_area'] = target_area
        
        return layout
    
    def _generate_layout_with_custom_boundary(
        self,
        boundary_points: List[Tuple[float, float]],
        num_apartments: int,
        bedrooms_per_apt: int,
        fsi: float,
        ground_coverage: float,
        floors: int,
        apartment_bedroom_counts: Optional[List[int]] = None,
        design_variant: int = 0
    ) -> Dict:
        """Build flats around a shared corridor and validate every space geometrically."""

        apartment_bedroom_counts = apartment_bedroom_counts or [bedrooms_per_apt] * num_apartments
        if len(apartment_bedroom_counts) != num_apartments:
            raise ValueError("Apartment bedroom counts must match the apartment count")
        plot_poly = ShapelyPolygon(boundary_points).buffer(0)
        if plot_poly.is_empty or not plot_poly.is_valid or plot_poly.area <= 0:
            raise ValueError("The uploaded plot boundary is invalid or has no area")

        plot_area = plot_poly.area
        setback = plot_poly.buffer(-2.0)
        if setback.is_empty or setback.area < plot_area * 0.25:
            setback = plot_poly.buffer(-1.0)
        if setback.is_empty:
            raise ValueError("The plot is too small to provide a 1 m building setback")

        if setback.geom_type == "Polygon":
            envelope_poly = setback
        else:
            envelope_poly = max(setback.geoms, key=lambda geom: geom.area)
        building_envelope = list(envelope_poly.exterior.coords[:-1])

        square_meters_per_square_foot = 0.092903
        base_unit_areas = {
            1: 430 * square_meters_per_square_foot,
            2: 730 * square_meters_per_square_foot,
            3: 1100 * square_meters_per_square_foot,
            4: 1600 * square_meters_per_square_foot
        }
        if design_variant not in range(3):
            raise ValueError("Design variant must be 0, 1, or 2")
        corridor_width = 1.8
        core_width = 6.0
        core_height = 6.5
        stair_width = 2.5
        lift_width = 2.0
        lift_depth = 2.0

        apartment_specs = [
            {"apartment_number": index + 1, "bedrooms": bedrooms,
             "area": base_unit_areas[bedrooms]}
            for index, bedrooms in enumerate(apartment_bedroom_counts)
        ]
        rows: List[List[Dict]] = [[]] if num_apartments == 1 else [[], []]
        row_areas = [0.0, 0.0]
        for spec in sorted(apartment_specs, key=lambda item: (-item["area"], item["apartment_number"])):
            row_index = 0 if len(rows) == 1 or row_areas[0] <= row_areas[1] else 1
            rows[row_index].append(spec)
            row_areas[row_index] += spec["area"]

        # Shallow enough that every living room and bedroom gets an outside wall,
        # deepened in 0.5 m steps while the floorplate is too long for the envelope.
        ideal_depth = min(10.0, max(6.0, min(
            base_unit_areas[bedrooms] / frontage_needed(bedrooms)
            for bedrooms in apartment_bedroom_counts
        )))
        envelope_box = envelope_poly.minimum_rotated_rectangle.exterior.coords
        envelope_sides = sorted(
            math.dist(envelope_box[i], envelope_box[i + 1]) for i in range(2)
        )
        unit_depth = ideal_depth
        while unit_depth < 10.0:
            trial_width = core_width + max(row_areas) / unit_depth
            trial_depth = (
                unit_depth + corridor_width + (core_height - corridor_width) / 2
                if len(rows) == 1 else 2 * unit_depth + corridor_width
            )
            short_side, long_side = sorted((trial_width, trial_depth))
            if short_side <= envelope_sides[0] and long_side <= envelope_sides[1]:
                break
            unit_depth = min(10.0, unit_depth + 0.5)
        for row in rows:
            for spec in row:
                spec["width"] = spec["area"] / unit_depth

        row_widths = [sum(spec["width"] for spec in row) for row in rows]
        corridor_length = max(row_widths)
        plan_width = core_width + corridor_length
        plan_depth = (
            unit_depth + corridor_width + (core_height - corridor_width) / 2
            if len(rows) == 1
            else 2 * unit_depth + corridor_width
        )
        core_area = core_width * core_height
        corridor_area = corridor_length * corridor_width
        floor_area = sum(spec["area"] for spec in apartment_specs) + core_area + corridor_area
        coverage_limit = plot_area * ground_coverage
        fsi_per_floor_limit = plot_area * fsi / floors
        max_floor_area = min(coverage_limit, fsi_per_floor_limit)

        if floor_area > max_floor_area + 1e-6:
            limiting_rule = "ground coverage" if coverage_limit <= fsi_per_floor_limit else "FSI per floor"
            raise ValueError(
                f"The selected flats and shared circulation need {floor_area:.1f} sq m per floor, "
                f"but {limiting_rule} allows {max_floor_area:.1f} sq m per floor "
                f"(coverage limit {coverage_limit:.1f} sq m; FSI limit "
                f"{fsi_per_floor_limit:.1f} sq m for {floors} floors)"
            )

        from shapely.affinity import rotate

        rectangle = envelope_poly.minimum_rotated_rectangle
        rectangle_points = list(rectangle.exterior.coords)
        dx = rectangle_points[1][0] - rectangle_points[0][0]
        dy = rectangle_points[1][1] - rectangle_points[0][1]
        long_axis_angle = math.degrees(math.atan2(dy, dx))
        candidate_angles = list(dict.fromkeys((0.0, long_axis_angle, long_axis_angle + 90.0)))
        placement = None
        selected_angle = 0.0
        for candidate_angle in candidate_angles:
            candidate_envelope = rotate(
                envelope_poly, -candidate_angle, origin="centroid", use_radians=False
            )
            min_x, min_y, max_x, max_y = candidate_envelope.bounds
            for swap_axes in (False, True):
                world_width, world_depth = (
                    (plan_depth, plan_width) if swap_axes else (plan_width, plan_depth)
                )
                if world_width > max_x - min_x or world_depth > max_y - min_y:
                    continue
                center_x = (min_x + max_x - world_width) / 2
                center_y = (min_y + max_y - world_depth) / 2
                step = max(0.25, min(world_width, world_depth) / 24)
                x_values = np.arange(min_x, max_x - world_width + step * 0.5, step)
                y_values = np.arange(min_y, max_y - world_depth + step * 0.5, step)
                origins = [(center_x, center_y)]
                origins.extend(
                    sorted(
                        ((float(x), float(y)) for x in x_values for y in y_values),
                        key=lambda origin: (origin[0] - center_x) ** 2
                        + (origin[1] - center_y) ** 2
                    )
                )
                for origin_x, origin_y in origins:
                    footprint = box(
                        origin_x, origin_y,
                        origin_x + world_width, origin_y + world_depth
                    )
                    if candidate_envelope.covers(footprint):
                        placement = (origin_x, origin_y, swap_axes)
                        selected_angle = candidate_angle
                        break
                if placement:
                    break
            if placement:
                break

        if placement is None:
            raise ValueError(
                "The plot does not contain a rectangular floorplate large enough for the selected "
                "flats, 1.8 m common corridor, staircase, and lift"
            )
        origin_x, origin_y, swap_axes = placement
        rotation_origin = envelope_poly.centroid
        transform = (
            [0, 1, 1, 0, origin_x, origin_y]
            if swap_axes else [1, 0, 0, 1, origin_x, origin_y]
        )

        def to_world(local_polygon):
            rotated_geometry = affine_transform(local_polygon, transform)
            return rotate(
                rotated_geometry, selected_angle,
                origin=rotation_origin, use_radians=False
            )

        active_apartment_number = None
        next_room_number = 1

        def add_room(room_type: str, local_polygon, zone: str) -> Dict:
            world_polygon = to_world(local_polygon)
            if world_polygon.geom_type != "Polygon" or world_polygon.is_empty or not world_polygon.is_valid:
                raise ValueError(f"Could not create a valid polygon for {room_type}")
            return {
                "room_id": f"room-{next_room_number}",
                "apartment_number": active_apartment_number,
                "type": room_type,
                "polygon": list(world_polygon.exterior.coords[:-1]),
                "area": world_polygon.area,
                "target_area": world_polygon.area,
                "zone": zone,
                "is_touching": True
            }

        def add_room_with_id(room_type: str, local_polygon, zone: str) -> Dict:
            nonlocal next_room_number
            room = add_room(room_type, local_polygon, zone)
            next_room_number += 1
            return room

        corridor_y_min = unit_depth
        corridor_y_max = unit_depth + corridor_width
        core_y_min = (corridor_y_min + corridor_y_max) / 2 - core_height / 2
        plan_core = box(0, core_y_min, core_width, core_y_min + core_height)
        stair = box(0, plan_core.bounds[1], stair_width, plan_core.bounds[3])
        lift = box(stair_width, plan_core.bounds[1], stair_width + lift_width,
                   plan_core.bounds[1] + lift_depth)
        lobby = plan_core.difference(unary_union([stair, lift]))
        if lobby.geom_type != "Polygon" or lobby.is_empty:
            raise ValueError("Could not create a connected lobby in the circulation core")

        circulation_elements = [
            add_room_with_id("staircase", stair, "circulation"),
            add_room_with_id("lift", lift, "circulation"),
            add_room_with_id("central_lobby", lobby, "circulation"),
            add_room_with_id(
                "corridor",
                box(core_width, corridor_y_min, plan_width, corridor_y_max),
                "circulation"
            )
        ]

        apartments: List[Dict] = []
        variant_names: List[str] = []
        row_layouts = (
            [(0, rows[0], "upper")]
            if len(rows) == 1
            else [(0, rows[0], "lower"), (1, rows[1], "upper")]
        )
        for row_index, row, common_edge in row_layouts:
            x_cursor = core_width
            for spec in row:
                unit_width = spec["width"]
                active_apartment_number = spec["apartment_number"]
                if row_index == 0:
                    if len(rows) == 1:
                        y_min, y_max = 0.0, unit_depth
                    else:
                        y_min, y_max = unit_depth + corridor_width, plan_depth
                else:
                    y_min = 0.0
                    y_max = unit_depth

                unit = box(x_cursor, y_min, x_cursor + unit_width, y_max)
                is_row_end = spec is row[-1]
                solved_rooms, penalties, arrangement = solve_apartment(
                    spec["bedrooms"], unit_width, unit_depth, design_variant,
                    exterior_sides=("right",) if is_row_end else (),
                )
                hard_failures = [why for cost, why in penalties if cost >= 40]
                if hard_failures:
                    raise ValueError(
                        f"Apartment {spec['apartment_number']} ({spec['bedrooms']} BHK, "
                        f"{unit_width:.1f} m x {unit_depth:.1f} m) cannot be laid out: "
                        + "; ".join(hard_failures)
                        + ". Choose fewer flats per floor or a larger plot."
                    )
                variant_names.append(arrangement)
                apt_rooms = []
                for room_type, (rx0, ry0, rx1, ry1) in solved_rooms:
                    # Solver frame has the corridor at y=0; flip rows whose corridor is above.
                    if common_edge == "lower":
                        local = box(x_cursor + rx0, y_min + ry0, x_cursor + rx1, y_min + ry1)
                    else:
                        local = box(x_cursor + rx0, y_max - ry1, x_cursor + rx1, y_max - ry0)
                    apt_rooms.append(add_room_with_id(
                        room_type, local, ROOM_ZONES.get(room_type, "private")
                    ))
                bathroom_count = bathroom_count_for(spec["bedrooms"])

                apt_area = sum(room["area"] for room in apt_rooms)
                if abs(apt_area - unit.area) > 1e-5:
                    raise ValueError(
                        f"Apartment {spec['apartment_number']} room partition does not cover its floor area"
                    )
                apartments.append({
                    "apartment_number": spec["apartment_number"],
                    "rooms": apt_rooms,
                    "zone_boundary": list(to_world(unit).exterior.coords[:-1]),
                    "total_area": apt_area,
                    "bedrooms": spec["bedrooms"],
                    "bathrooms": bathroom_count,
                    "room_count": len(apt_rooms),
                    "arrangement": arrangement,
                    "design_issues": [why for _, why in penalties if _ >= 1.0],
                })
                x_cursor += unit_width

        apartments.sort(key=lambda apartment: apartment["apartment_number"])
        apartment_zones = [apartment["zone_boundary"] for apartment in apartments]
        all_rooms = [room for apartment in apartments for room in apartment["rooms"]]
        all_rooms.extend(circulation_elements)

        room_geometries = []
        for room in all_rooms:
            geometry = ShapelyPolygon(room["polygon"])
            if geometry.is_empty or not geometry.is_valid:
                raise ValueError(f"Generated invalid geometry for {room['type']}")
            if not envelope_poly.covers(geometry):
                raise ValueError(f"Generated {room['type']} extends outside the building envelope")
            if any(geometry.intersection(existing).area > 1e-6 for existing in room_geometries):
                raise ValueError(f"Generated {room['type']} overlaps another room or circulation space")
            room_geometries.append(geometry)

        floor_area = sum(room["area"] for room in all_rooms)
        total_built_area = floor_area * floors
        sizing_info = {
            "plot_area": plot_area,
            "max_ground_area": plot_area * ground_coverage,
            "max_total_buildable": plot_area * fsi,
            "floor_area": floor_area,
            "apartment_areas": [apartment["total_area"] for apartment in apartments]
        }
        layout = {
            "apartments": apartments,
            "all_rooms": all_rooms,
            "circulation_elements": circulation_elements,
            "has_circulation": True,
            "building_envelope": building_envelope,
            "plot_boundary": boundary_points,
            "num_apartments": num_apartments,
            "bedrooms_per_apartment": bedrooms_per_apt,
            "apartment_bedroom_counts": apartment_bedroom_counts,
            "design_variant": design_variant,
            "design_variant_name": f"Concept {design_variant + 1}: {variant_names[0]}",
            "floors": floors,
            "floor_area": floor_area,
            "total_built_area": total_built_area,
            "plot_area": plot_area,
            "fsi_utilized": total_built_area / plot_area,
            "ground_coverage_utilized": floor_area / plot_area,
            "apartment_zones": apartment_zones,
            "sizing_analysis": sizing_info
        }
        layout["architectural_review"] = build_geometry_review(layout)
        facade_failures = [
            (
                apartment["apartment_number"],
                [
                    room["room_type"]
                    for room in apartment["potential_facade_contacts"]
                    if not room["has_potential_facade"] and room["room_type"] not in SHAFT_OK
                ],
            )
            for apartment in layout["architectural_review"]["apartments"]
        ]
        facade_failures = [
            (apartment_number, room_types)
            for apartment_number, room_types in facade_failures
            if room_types
        ]
        if facade_failures:
            failure_details = "; ".join(
                f"Apartment {apartment_number}: {', '.join(room_types)}"
                for apartment_number, room_types in facade_failures
            )
            raise ValueError(
                "Strict facade-access check failed. Habitable rooms lack contact "
                f"with the building envelope ({failure_details}). This generator "
                "does not model lightwells; change the apartment mix or redesign "
                "the layout before generating a plan."
            )

        print(f"\n✅ Generated {len(apartments)} separate apartments")
        print(f"📊 Floor area: {floor_area:.1f} sq m; total built area: {total_built_area:.1f} sq m")
        print(f"📊 FSI utilized: {layout['fsi_utilized']:.2f}")
        print(f"📊 Ground coverage: {layout['ground_coverage_utilized'] * 100:.1f}%")
        return layout
    
    def _create_building_envelope(self, boundary_points: List[Tuple[float, float]], 
                                 coverage_ratio: float) -> List[Tuple[float, float]]:
        """Create building envelope within custom boundary"""
        
        boundary_poly = ShapelyPolygon(boundary_points)
        
        # Create inset boundary for building envelope
        envelope_poly = boundary_poly.buffer(-2.0)  # 2m setback from boundary
        
        if envelope_poly.area < boundary_poly.area * coverage_ratio:
            # If setback is too large, use smaller setback
            envelope_poly = boundary_poly.buffer(-1.0)
        
        if hasattr(envelope_poly, 'exterior'):
            envelope_coords = list(envelope_poly.exterior.coords[:-1])
        else:
            envelope_coords = boundary_points
        
        print(f"🏗️ Building envelope: {len(envelope_coords)} points, {envelope_poly.area:.1f} sq m")
        
        return envelope_coords
    
    def _create_apartment_zones_for_boundary(
        self, 
        building_envelope: List[Tuple[float, float]], 
        num_apartments: int, 
        area_per_apartment: float,
        circulation_zones: List[Dict] = None
    ) -> List[List[Tuple[float, float]]]:
        """Create apartment zones optimized for custom boundary shape"""
        
        envelope_poly = ShapelyPolygon(building_envelope)
        bounds = envelope_poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        print(f"🏗️ Dividing custom boundary ({width:.1f}m x {height:.1f}m) into {num_apartments} zones")
        
        # Create circulation exclusion areas if provided
        circulation_polygons = []
        if circulation_zones:
            for circ_zone in circulation_zones:
                circ_poly = ShapelyPolygon(circ_zone['coordinates'])
                circulation_polygons.append(circ_poly)
            print(f"📐 Excluding {len(circulation_polygons)} circulation areas from apartment zones")

        # Calculate remaining buildable area after circulation exclusion
        remaining_poly = envelope_poly
        for circ_poly in circulation_polygons:
            remaining_poly = remaining_poly.difference(circ_poly)
        
        print(f"📐 Remaining area for apartments: {remaining_poly.area:.1f} sq m")

        # Create apartment zones from remaining area
        zones = []
        
        if num_apartments == 1:
            # Single apartment gets all remaining space
            if hasattr(remaining_poly, 'exterior'):
                zones.append(list(remaining_poly.exterior.coords[:-1]))
            elif hasattr(remaining_poly, 'geoms'):
                # Take largest piece if fragmented
                largest_geom = max(remaining_poly.geoms, key=lambda g: g.area)
                zones.append(list(largest_geom.exterior.coords[:-1]))
            
        elif num_apartments == 2:
            # Two apartments - split remaining area intelligently
            if hasattr(remaining_poly, 'geoms') and len(remaining_poly.geoms) >= 2:
                # If circulation naturally split the building into 2 parts
                sorted_geoms = sorted(remaining_poly.geoms, key=lambda g: g.area, reverse=True)
                for i in range(min(2, len(sorted_geoms))):
                    if sorted_geoms[i].area > 50:  # Minimum apartment size
                        zones.append(list(sorted_geoms[i].exterior.coords[:-1]))
            else:
                # Split remaining area manually
                if hasattr(remaining_poly, 'exterior'):
                    # Create bounding box of remaining area
                    remaining_bounds = remaining_poly.bounds
                    remaining_width = remaining_bounds[2] - remaining_bounds[0]
                    remaining_height = remaining_bounds[3] - remaining_bounds[1]
                    
                    if remaining_width > remaining_height:
                        # Split vertically
                        mid_x = remaining_bounds[0] + remaining_width / 2
                        
                        # Create splitting line
                        splitter = ShapelyPolygon([
                            (mid_x - 0.1, remaining_bounds[1] - 1),
                            (mid_x + 0.1, remaining_bounds[1] - 1),
                            (mid_x + 0.1, remaining_bounds[3] + 1),
                            (mid_x - 0.1, remaining_bounds[3] + 1)
                        ])
                        
                        split_result = remaining_poly.difference(splitter)
                        
                        if hasattr(split_result, 'geoms') and len(split_result.geoms) >= 2:
                            sorted_parts = sorted(split_result.geoms, key=lambda g: g.area, reverse=True)
                            for i in range(min(2, len(sorted_parts))):
                                if sorted_parts[i].area > 50:
                                    zones.append(list(sorted_parts[i].exterior.coords[:-1]))
                        else:
                            # Fallback: use the whole remaining area
                            zones.append(list(remaining_poly.exterior.coords[:-1]))
                    else:
                        # Split horizontally
                        mid_y = remaining_bounds[1] + remaining_height / 2
                        
                        # Create splitting line
                        splitter = ShapelyPolygon([
                            (remaining_bounds[0] - 1, mid_y - 0.1),
                            (remaining_bounds[2] + 1, mid_y - 0.1),
                            (remaining_bounds[2] + 1, mid_y + 0.1),
                            (remaining_bounds[0] - 1, mid_y + 0.1)
                        ])
                        
                        split_result = remaining_poly.difference(splitter)
                        
                        if hasattr(split_result, 'geoms') and len(split_result.geoms) >= 2:
                            sorted_parts = sorted(split_result.geoms, key=lambda g: g.area, reverse=True)
                            for i in range(min(2, len(sorted_parts))):
                                if sorted_parts[i].area > 50:
                                    zones.append(list(sorted_parts[i].exterior.coords[:-1]))
                        else:
                            # Fallback: use the whole remaining area
                            zones.append(list(remaining_poly.exterior.coords[:-1]))
        
        else:
            # For more than 2 apartments, use the remaining area fragments
            if hasattr(remaining_poly, 'geoms'):
                sorted_geoms = sorted(remaining_poly.geoms, key=lambda g: g.area, reverse=True)
                for i in range(min(num_apartments, len(sorted_geoms))):
                    if sorted_geoms[i].area > 50:  # Minimum apartment size
                        zones.append(list(sorted_geoms[i].exterior.coords[:-1]))
            elif hasattr(remaining_poly, 'exterior'):
                # Single large remaining area - grid subdivision
                zones.append(list(remaining_poly.exterior.coords[:-1]))

        print(f"📐 Created {len(zones)} apartment zones for custom boundary")
        return zones
    
    def _plan_circulation_zones(self, building_envelope: List[Tuple[float, float]], 
                               num_apartments: int) -> List[Dict]:
        """Pre-plan circulation core that adapts to apartment partitioning pattern"""
        
        envelope_poly = ShapelyPolygon(building_envelope)
        bounds = envelope_poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        # Determine apartment partitioning pattern
        aspect_ratio = width / height
        print(f"🏗️ Building aspect ratio: {aspect_ratio:.2f} ({width:.1f}m × {height:.1f}m)")
        
        # Analyze how apartments will be arranged
        if num_apartments == 1:
            layout_type = "single"
        elif num_apartments == 2:
            if aspect_ratio > 1.2:
                layout_type = "horizontal_split"  # Wide building, split left-right
                circulation_orientation = "vertical"
            else:
                layout_type = "vertical_split"    # Tall building, split top-bottom
                circulation_orientation = "horizontal"
        elif num_apartments <= 4:
            layout_type = "grid_2x2"
            # For grid layouts, use the longer axis for circulation spine
            circulation_orientation = "vertical" if width > height else "horizontal"
        else:
            layout_type = "grid_large"
            circulation_orientation = "vertical" if width > height else "horizontal"
        
        print(f"📐 Detected layout: {layout_type}, circulation orientation: {circulation_orientation}")
        
        circulation_zones = []
        center_x = bounds[0] + width / 2
        center_y = bounds[1] + height / 2
        
        if layout_type == "single":
            # Single apartment - minimal circulation in corner
            core_size = 6.0
            circulation_core = [
                (bounds[0] + 1.0, bounds[1] + 1.0),
                (bounds[0] + 1.0 + core_size, bounds[1] + 1.0),
                (bounds[0] + 1.0 + core_size, bounds[1] + 1.0 + core_size),
                (bounds[0] + 1.0, bounds[1] + 1.0 + core_size)
            ]
            
        elif layout_type == "horizontal_split":
            # Apartments split left-right, create compact circulation cluster at building edge
            spine_width = max(8.0, min(12.0, width * 0.15))
            
            # Main circulation core positioned near building perimeter for staircase access
            circulation_core = [
                (center_x - spine_width/2, bounds[1] + 2.0),
                (center_x + spine_width/2, bounds[1] + 2.0),
                (center_x + spine_width/2, bounds[1] + 12.0),  # Compact height for cluster
                (center_x - spine_width/2, bounds[1] + 12.0)
            ]
            
            # Add the main circulation core
            circulation_zones.append({
                'type': 'circulation_core',
                'coordinates': circulation_core,
                'area': ShapelyPolygon(circulation_core).area
            })
            
            # Perimeter staircase directly adjacent to circulation core
            staircase_zone = [
                (center_x - spine_width/2 - 3.0, bounds[1]),  # Adjacent to core, touching perimeter
                (center_x - spine_width/2, bounds[1]),
                (center_x - spine_width/2, bounds[1] + 8.0),  # Match core height
                (center_x - spine_width/2 - 3.0, bounds[1] + 8.0)
            ]
            circulation_zones.append({
                'type': 'perimeter_staircase',
                'coordinates': staircase_zone,
                'area': ShapelyPolygon(staircase_zone).area
            })
            
        elif layout_type == "vertical_split":
            # Apartments split top-bottom, create compact circulation cluster at building edge
            spine_height = max(8.0, min(12.0, height * 0.15))
            
            # Main circulation core positioned near building perimeter for staircase access
            circulation_core = [
                (bounds[0] + 2.0, center_y - spine_height/2),
                (bounds[0] + 12.0, center_y - spine_height/2),  # Compact width for cluster
                (bounds[0] + 12.0, center_y + spine_height/2),
                (bounds[0] + 2.0, center_y + spine_height/2)
            ]
            
            # Add the main circulation core
            circulation_zones.append({
                'type': 'circulation_core',
                'coordinates': circulation_core,
                'area': ShapelyPolygon(circulation_core).area
            })
            
            # Perimeter staircase directly adjacent to circulation core
            staircase_zone = [
                (bounds[0], center_y - spine_height/2 - 3.0),  # Adjacent to core, touching perimeter
                (bounds[0] + 8.0, center_y - spine_height/2 - 3.0),  # Match core width
                (bounds[0] + 8.0, center_y - spine_height/2),
                (bounds[0], center_y - spine_height/2)
            ]
            circulation_zones.append({
                'type': 'perimeter_staircase',
                'coordinates': staircase_zone,
                'area': ShapelyPolygon(staircase_zone).area
            })
            
        elif layout_type == "grid_2x2":
            # 2x2 grid layout - cross-shaped circulation with perimeter staircase
            if circulation_orientation == "vertical":
                # Primary vertical spine
                spine_width = max(8.0, min(10.0, width * 0.12))
                primary_spine = [
                    (center_x - spine_width/2, bounds[1] + 2.0),
                    (center_x + spine_width/2, bounds[1] + 2.0),
                    (center_x + spine_width/2, bounds[3] - 2.0),
                    (center_x - spine_width/2, bounds[3] - 2.0)
                ]
                circulation_zones.append({
                    'type': 'circulation_spine_vertical',
                    'coordinates': primary_spine,
                    'area': ShapelyPolygon(primary_spine).area
                })
                
                # Horizontal connecting corridors
                corridor_height = 3.0
                horizontal_connector = [
                    (bounds[0] + 2.0, center_y - corridor_height/2),
                    (bounds[2] - 2.0, center_y - corridor_height/2),
                    (bounds[2] - 2.0, center_y + corridor_height/2),
                    (bounds[0] + 2.0, center_y + corridor_height/2)
                ]
                circulation_zones.append({
                    'type': 'circulation_connector_horizontal',
                    'coordinates': horizontal_connector,
                    'area': ShapelyPolygon(horizontal_connector).area
                })
                
                # Perimeter staircase for natural ventilation - positioned near circulation spine
                staircase_zone = [
                    (bounds[2] - 3.0, bounds[1] + 1.0),  # At right perimeter, near bottom
                    (bounds[2], bounds[1] + 1.0),
                    (bounds[2], bounds[1] + 7.0),  # Extended to be near central spine
                    (bounds[2] - 3.0, bounds[1] + 7.0)
                ]
                circulation_zones.append({
                    'type': 'perimeter_staircase',
                    'coordinates': staircase_zone,
                    'area': ShapelyPolygon(staircase_zone).area
                })
            else:
                # Primary horizontal spine
                spine_height = max(8.0, min(10.0, height * 0.12))
                primary_spine = [
                    (bounds[0] + 2.0, center_y - spine_height/2),
                    (bounds[2] - 2.0, center_y - spine_height/2),
                    (bounds[2] - 2.0, center_y + spine_height/2),
                    (bounds[0] + 2.0, center_y + spine_height/2)
                ]
                circulation_zones.append({
                    'type': 'circulation_spine_horizontal',
                    'coordinates': primary_spine,
                    'area': ShapelyPolygon(primary_spine).area
                })
                
                # Vertical connecting corridors
                corridor_width = 3.0
                vertical_connector = [
                    (center_x - corridor_width/2, bounds[1] + 2.0),
                    (center_x + corridor_width/2, bounds[1] + 2.0),
                    (center_x + corridor_width/2, bounds[3] - 2.0),
                    (center_x - corridor_width/2, bounds[3] - 2.0)
                ]
                circulation_zones.append({
                    'type': 'circulation_connector_vertical',
                    'coordinates': vertical_connector,
                    'area': ShapelyPolygon(vertical_connector).area
                })
                
                # Perimeter staircase for natural ventilation - positioned near circulation spine
                staircase_zone = [
                    (bounds[0] + 1.0, bounds[3] - 3.0),  # At top perimeter, near left
                    (bounds[0] + 7.0, bounds[3] - 3.0),  # Extended to be near central spine
                    (bounds[0] + 7.0, bounds[3]),
                    (bounds[0] + 1.0, bounds[3])
                ]
                circulation_zones.append({
                    'type': 'perimeter_staircase',
                    'coordinates': staircase_zone,
                    'area': ShapelyPolygon(staircase_zone).area
                })
        
        else:  # grid_large (5+ apartments)
            # Large grid - create comprehensive circulation network
            if circulation_orientation == "vertical":
                # Main vertical spine
                spine_width = max(10.0, min(14.0, width * 0.12))
                main_spine = [
                    (center_x - spine_width/2, bounds[1] + 2.0),
                    (center_x + spine_width/2, bounds[1] + 2.0),
                    (center_x + spine_width/2, bounds[3] - 2.0),
                    (center_x - spine_width/2, bounds[3] - 2.0)
                ]
                circulation_zones.append({
                    'type': 'circulation_main_spine_vertical',
                    'coordinates': main_spine,
                    'area': ShapelyPolygon(main_spine).area
                })
                
                # Multiple horizontal connectors
                corridor_height = 2.5
                num_connectors = min(3, int(height / 25))  # One connector per 25m height
                
                for i in range(num_connectors):
                    connector_y = bounds[1] + (i + 1) * height / (num_connectors + 1)
                    connector = [
                        (bounds[0] + 2.0, connector_y - corridor_height/2),
                        (bounds[2] - 2.0, connector_y - corridor_height/2),
                        (bounds[2] - 2.0, connector_y + corridor_height/2),
                        (bounds[0] + 2.0, connector_y + corridor_height/2)
                    ]
                    circulation_zones.append({
                        'type': f'circulation_connector_h{i+1}',
                        'coordinates': connector,
                        'area': ShapelyPolygon(connector).area
                    })
            else:
                # Main horizontal spine
                spine_height = max(10.0, min(14.0, height * 0.12))
                main_spine = [
                    (bounds[0] + 2.0, center_y - spine_height/2),
                    (bounds[2] - 2.0, center_y - spine_height/2),
                    (bounds[2] - 2.0, center_y + spine_height/2),
                    (bounds[0] + 2.0, center_y + spine_height/2)
                ]
                circulation_zones.append({
                    'type': 'circulation_main_spine_horizontal',
                    'coordinates': main_spine,
                    'area': ShapelyPolygon(main_spine).area
                })
                
                # Multiple vertical connectors
                corridor_width = 2.5
                num_connectors = min(3, int(width / 25))  # One connector per 25m width
                
                for i in range(num_connectors):
                    connector_x = bounds[0] + (i + 1) * width / (num_connectors + 1)
                    connector = [
                        (connector_x - corridor_width/2, bounds[1] + 2.0),
                        (connector_x + corridor_width/2, bounds[1] + 2.0),
                        (connector_x + corridor_width/2, bounds[3] - 2.0),
                        (connector_x - corridor_width/2, bounds[3] - 2.0)
                    ]
                    circulation_zones.append({
                        'type': f'circulation_connector_v{i+1}',
                        'coordinates': connector,
                        'area': ShapelyPolygon(connector).area
                    })
        
        # If single circulation core (for simple layouts)
        if not circulation_zones:
            circulation_zones.append({
                'type': 'circulation_core',
                'coordinates': circulation_core,
                'area': ShapelyPolygon(circulation_core).area
            })
        
        total_circulation_area = sum(zone['area'] for zone in circulation_zones)
        print(f"📐 Planned {len(circulation_zones)} circulation zones ({total_circulation_area:.1f} sq m total)")
        
        return circulation_zones
    
    def _generate_circulation_in_zones(self, circulation_zones: List[Dict], 
                                      num_apartments: int) -> List[Dict]:
        """Generate circulation elements with perimeter staircases and central lobby access"""
        
        if not circulation_zones:
            return []
            
        circulation_elements = []
        
        # Find the main circulation spine and perimeter staircase
        main_spine = None
        connector_zones = []
        perimeter_staircase = None
        
        for zone in circulation_zones:
            zone_type = zone['type']
            if any(keyword in zone_type for keyword in ['spine', 'core']):
                main_spine = zone
            elif 'perimeter_staircase' in zone_type:
                perimeter_staircase = zone
            else:
                connector_zones.append(zone)
        
        if not main_spine:
            return []
        
        spine_coords = main_spine['coordinates']
        spine_poly = ShapelyPolygon(spine_coords)
        bounds = spine_poly.bounds
        spine_width = bounds[2] - bounds[0]
        spine_height = bounds[3] - bounds[1]
        
        # Determine spine orientation
        is_vertical_spine = spine_height > spine_width
        spine_type = main_spine['type']
        
        print(f"🏗️ Creating circulation elements with perimeter staircase")
        print(f"   Central spine: {spine_type} ({spine_width:.1f}m × {spine_height:.1f}m)")
        
        # Position central lobby and lift within the spine in a compact cluster
        margin = 0.5
        
        if is_vertical_spine or "vertical" in spine_type:
            # Vertical spine - create compact cluster: lift at bottom, lobby above
            
            # Lift at bottom of circulation core
            lift_coords = [
                (bounds[0] + margin, bounds[1] + margin),
                (bounds[0] + margin + 2.0, bounds[1] + margin),
                (bounds[0] + margin + 2.0, bounds[1] + margin + 2.0),
                (bounds[0] + margin, bounds[1] + margin + 2.0)
            ]
            
            # Central lobby directly above lift, spanning full width for apartment access
            lobby_y_start = bounds[1] + margin + 2.5
            lobby_height = min(4.0, spine_height - 3.5)  # Use remaining space efficiently
            lobby_coords = [
                (bounds[0] + margin, lobby_y_start),
                (bounds[2] - margin, lobby_y_start),
                (bounds[2] - margin, lobby_y_start + lobby_height),
                (bounds[0] + margin, lobby_y_start + lobby_height)
            ]
                
        else:
            # Horizontal spine - create compact cluster: lift on left, lobby to right
            
            # Lift at left of circulation core
            lift_coords = [
                (bounds[0] + margin, bounds[1] + margin),
                (bounds[0] + margin + 2.0, bounds[1] + margin),
                (bounds[0] + margin + 2.0, bounds[1] + margin + 2.0),
                (bounds[0] + margin, bounds[1] + margin + 2.0)
            ]
            
            # Central lobby to the right of lift, spanning full height for apartment access
            lobby_x_start = bounds[0] + margin + 2.5
            lobby_width = min(4.0, spine_width - 3.5)  # Use remaining space efficiently
            lobby_coords = [
                (lobby_x_start, bounds[1] + margin),
                (lobby_x_start + lobby_width, bounds[1] + margin),
                (lobby_x_start + lobby_width, bounds[3] - margin),
                (lobby_x_start, bounds[3] - margin)
            ]
        
        # Create central lobby with adjacency information
        lobby_area = ShapelyPolygon(lobby_coords).area
        lobby_element = {
            'type': 'central_lobby',
            'polygon': lobby_coords,
            'area': lobby_area,
            'target_area': lobby_area,
            'zone': 'circulation',
            'is_touching': True,
            'nbc_compliant': True,
            'specifications': f"Central lobby: {lobby_area:.1f} sq m - Living rooms must be adjacent",
            'adjacency_requirement': 'living_rooms'  # Special flag for apartment generation
        }
        circulation_elements.append(lobby_element)
        
        # Create lift
        lift_area = ShapelyPolygon(lift_coords).area
        circulation_elements.append({
            'type': 'lift',
            'polygon': lift_coords,
            'area': lift_area,
            'target_area': 4.0,
            'zone': 'circulation',
            'is_touching': True,
            'nbc_compliant': True,
            'specifications': "2.0m x 2.0m, 8 person capacity",
            'capacity': '8 persons'
        })
        
        # Handle perimeter staircase if present
        if perimeter_staircase:
            stair_coords = perimeter_staircase['coordinates']
            stair_area = perimeter_staircase['area']
            
            circulation_elements.append({
                'type': 'staircase_perimeter',
                'polygon': stair_coords,
                'area': stair_area,
                'target_area': 7.2,
                'zone': 'circulation',
                'is_touching': True,
                'nbc_compliant': True,
                'specifications': f"Perimeter staircase: {stair_area:.1f} sq m with natural ventilation",
                'width': 1.8,
                'ventilation': 'natural_perimeter'
            })
            
            print(f"   ✅ Perimeter staircase: {stair_area:.1f} sq m (natural ventilation)")
        else:
            # Fallback: create staircase within spine if no perimeter staircase
            if is_vertical_spine:
                stair_coords = [
                    (bounds[0] + margin + 2.5, bounds[1] + margin),
                    (bounds[0] + margin + 4.3, bounds[1] + margin),
                    (bounds[0] + margin + 4.3, bounds[1] + margin + 4.0),
                    (bounds[0] + margin + 2.5, bounds[1] + margin + 4.0)
                ]
            else:
                stair_coords = [
                    (bounds[0] + margin, bounds[1] + margin + 2.5),
                    (bounds[0] + margin + 4.0, bounds[1] + margin + 2.5),
                    (bounds[0] + margin + 4.0, bounds[3] - margin),
                    (bounds[0] + margin, bounds[3] - margin)
                ]
            
            stair_area = ShapelyPolygon(stair_coords).area
            circulation_elements.append({
                'type': 'staircase',
                'polygon': stair_coords,
                'area': stair_area,
                'target_area': 7.2,
                'zone': 'circulation',
                'is_touching': True,
                'nbc_compliant': True,
                'specifications': "Width: 1.8m, Tread: 0.3m, Riser: 0.15m",
                'width': 1.8
            })
        
        # Store lobby location for apartment generation
        self.central_lobby_location = lobby_coords
        
        # Add connector corridors as circulation elements
        for connector_zone in connector_zones:
            connector_area = connector_zone['area']
            connector_type = connector_zone['type'].replace('_', ' ').title()
            
            circulation_elements.append({
                'type': connector_zone['type'],
                'polygon': connector_zone['coordinates'],
                'area': connector_area,
                'target_area': connector_area,
                'zone': 'circulation',
                'is_touching': True,
                'nbc_compliant': True,
                'specifications': f"{connector_type}: {connector_area:.1f} sq m (NBC compliant)",
                'width': 2.0
            })
        
        print(f"   ✅ Central lobby: {lobby_area:.1f} sq m (living room adjacency required)")
        
        return circulation_elements

    def _ensure_living_room_lobby_adjacency(self, apartments: List[Dict], 
                                          lobby_location: List[Tuple[float, float]]) -> None:
        """Ensure living rooms are positioned adjacent to the central lobby"""
        
        lobby_poly = ShapelyPolygon(lobby_location)
        lobby_bounds = lobby_poly.bounds
        
        print(f"🔗 Checking living room adjacency to central lobby...")
        
        for apt_idx, apartment in enumerate(apartments):
            living_room_found = False
            living_room_adjacent = False
            
            for room in apartment['rooms']:
                if room['type'] == 'living':
                    living_room_found = True
                    room_poly = ShapelyPolygon(room['polygon'])
                    
                    # Check if living room is adjacent to lobby (within 2m)
                    distance = lobby_poly.distance(room_poly)
                    
                    if distance < 2.0:  # Adjacent or very close
                        living_room_adjacent = True
                        print(f"   ✅ Apartment {apt_idx+1}: Living room adjacent to central lobby")
                        # Add adjacency information
                        room['adjacent_to_lobby'] = True
                        room['lobby_distance'] = distance
                    else:
                        print(f"   ⚠️  Apartment {apt_idx+1}: Living room {distance:.1f}m from lobby")
                        room['adjacent_to_lobby'] = False
                        room['lobby_distance'] = distance
                    break
            
            if not living_room_found:
                print(f"   ⚠️  Apartment {apt_idx+1}: No living room found")
            elif not living_room_adjacent:
                print(f"   📝 Note: Consider repositioning living room closer to lobby")

    def visualize_boundary_layout(self, layout: Dict, save_path: str = None) -> None:
        """Visualize the boundary-based natural layout"""
        
        fig, ax = plt.subplots(1, 1, figsize=(16, 12))
        
        # Plot custom boundary
        boundary_points = np.array(layout['plot_boundary'] + [layout['plot_boundary'][0]])
        ax.plot(boundary_points[:, 0], boundary_points[:, 1], 'k-', linewidth=3, label='Custom Boundary')
        
        # Plot building envelope
        building_envelope = np.array(layout['building_envelope'] + [layout['building_envelope'][0]])
        ax.plot(building_envelope[:, 0], building_envelope[:, 1], 'b--', linewidth=2, label='Building Envelope')
        
        # Plot apartment zones
        for zone in layout['apartment_zones']:
            zone_points = np.array(zone + [zone[0]])
            ax.plot(zone_points[:, 0], zone_points[:, 1], 'g:', linewidth=1, alpha=0.7)
        
        # Plot all rooms (including circulation elements)
        patches = []
        room_labels = []
        
        for apt_idx, apartment in enumerate(layout['apartments']):
            for room in apartment['rooms']:
                if 'polygon' in room and len(room['polygon']) >= 3:
                    # Create room patch
                    room_patch = Polygon(room['polygon'], closed=True)
                    patches.append(room_patch)
                    
                    # Add room label
                    room_poly = ShapelyPolygon(room['polygon'])
                    label_point = room_poly.representative_point()
                    
                    room_type = room['type']
                    if room_type == 'entrance' or (
                        room_type == 'corridor' and room.get('zone') == 'apartment_circulation'
                    ):
                        if room_type == 'entrance':
                            room_name = 'Entry'
                            room_labels.append(
                                (label_point.x, label_point.y, room_name, room_type)
                            )
                        continue
                    room_names = {
                        'living': 'Living',
                        'dining': 'Dining',
                        'kitchen': 'Kitchen',
                        'bedroom': 'Bed',
                        'master_bedroom': 'M. Bed',
                        'bathroom': 'Bath',
                        'master_bathroom': 'M. Bath',
                        'corridor': 'Hall',
                        'central_lobby': 'Lobby',
                        'staircase': 'Stair',
                        'balcony': 'Balcony',
                        'utility': 'Utility',
                        'foyer': 'Foyer'
                    }
                    room_name = room_names.get(room_type, room_type.replace('_', ' ').title())
                    area_text = "" if room_type == 'corridor' else f"{room['area']:.0f}m²"
                    label_text = f"{room_name}\n{area_text}" if area_text else room_name
                    
                    room_labels.append((label_point.x, label_point.y, label_text, room_type))
        
        # Add circulation elements if present
        if layout.get('has_circulation', False):
            for circ_elem in layout.get('circulation_elements', []):
                if 'polygon' in circ_elem and len(circ_elem['polygon']) >= 3:
                    # Create circulation element patch
                    circ_patch = Polygon(circ_elem['polygon'], closed=True)
                    patches.append(circ_patch)
                    
                    # Add circulation element label
                    circ_poly = ShapelyPolygon(circ_elem['polygon'])
                    label_point = circ_poly.representative_point()
                    
                    circ_type = circ_elem['type']
                    circ_names = {
                        'central_lobby': 'Lobby',
                        'staircase': 'Stair'
                    }
                    circ_name = circ_names.get(circ_type, circ_type.replace('_', ' ').title())
                    area_text = f"{circ_elem['area']:.0f}m²"
                    label_text = f"{circ_name}\n{area_text}"
                    
                    room_labels.append((label_point.x, label_point.y, label_text, circ_type))
        
        # Create patch collection
        patch_collection = PatchCollection(patches, alpha=0.7)
        
        # Set colors for rooms (including circulation elements)
        colors = []
        for apt in layout['apartments']:
            for room in apt['rooms']:
                room_type = room['type']
                color = self.natural_generator.colors.get(room_type, '#E0E0E0')
                colors.append(color)
        
        # Add colors for circulation elements
        if layout.get('has_circulation', False):
            for circ_elem in layout.get('circulation_elements', []):
                circ_type = circ_elem['type']
                color = self.natural_generator.colors.get(circ_type, '#D0D0D0')
                colors.append(color)
        
        patch_collection.set_facecolors(colors)
        patch_collection.set_edgecolors('black')
        patch_collection.set_linewidths(0.8)
        
        ax.add_collection(patch_collection)

        for candidate in layout.get("architectural_review", {}).get(
            "door_candidates", []
        ):
            start, end = candidate["segment"]
            ax.plot(
                [start[0], end[0]],
                [start[1], end[1]],
                color="#d97706",
                linewidth=2.2,
                solid_capstyle="butt",
                zorder=4,
            )
        ax.plot(
            [],
            [],
            color="#d97706",
            linewidth=2.2,
            label="Door candidates (not openings)",
        )
        
        # Add room labels
        for x, y, label, room_type in room_labels:
            font_size = 5.5 if room_type in ['bathroom', 'master_bathroom', 'utility'] else 6.5
            weight = 'bold' if room_type in ['living', 'master_bedroom'] else 'normal'
            
            ax.text(x, y, label, ha='center', va='center', 
                   fontsize=font_size, fontweight=weight,
                   bbox=dict(boxstyle='round,pad=0.12', facecolor='white', alpha=0.75))
        
        # Set equal aspect ratio and clean up
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right')
        
        # Title with metrics
        floor_area = layout['floor_area']
        total_area = layout['total_built_area']
        fsi = layout['fsi_utilized']
        coverage = layout['ground_coverage_utilized'] * 100
        boundary_type = layout.get('boundary_type', 'custom')
        
        title = (
            f"Boundary Natural Layout - {layout['num_apartments']} Apartments "
            f"({layout.get('design_variant_name', 'Concept')} | "
            f"{boundary_type.replace('_', ' ').title()})\n"
        )
        title += (
            f"Typical Floor: {floor_area:.0f} sq m | Total Built: {total_area:.0f} sq m | "
            f"FSI: {fsi:.2f} | Coverage: {coverage:.1f}%"
        )
        
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"💾 Layout visualization saved: {save_path}")
        
        # Don't show plot in web environment, just close it
        plt.close('all')
    
    def save_layout_data(self, layout: Dict, save_path: str) -> None:
        """Save layout data to JSON file"""
        
        # Prepare data for JSON serialization
        json_data = {
            'metadata': {
                'generation_timestamp': datetime.now().isoformat(),
                'generator_type': 'boundary_natural_generator',
                'design_variant': layout.get('design_variant'),
                'design_variant_name': layout.get('design_variant_name'),
                'boundary_source': layout.get('boundary_source', 'unknown'),
                'boundary_type': layout.get('boundary_type', 'custom'),
                'original_area_preserved': layout.get('original_area_preserved', False),
                'specified_target_area': layout.get('specified_target_area', None),
                'apartment_bedroom_counts': layout.get('apartment_bedroom_counts', [])
            },
            'building_info': {
                'num_apartments': layout['num_apartments'],
                'bedrooms_per_apartment': layout['bedrooms_per_apartment'],
                'apartment_bedroom_counts': layout.get('apartment_bedroom_counts', []),
                'floors': layout.get('floors', 1),
                'floor_area': layout.get('floor_area', layout['total_built_area']),
                'total_built_area': layout['total_built_area'],
                'plot_area': layout['plot_area'],
                'fsi_utilized': layout['fsi_utilized'],
                'ground_coverage_utilized': layout['ground_coverage_utilized'],
                'has_circulation': layout.get('has_circulation', False),
                'circulation_elements_count': len(layout.get('circulation_elements', []))
            },
            'boundaries': {
                'plot_boundary': layout['plot_boundary'],
                'building_envelope': layout['building_envelope'],
                'apartment_zones': layout['apartment_zones']
            },
            'architectural_review': layout.get('architectural_review', {}),
            'apartments': []
        }
        
        # Add apartment data
        for apt in layout['apartments']:
            apt_data = {
                'apartment_number': apt['apartment_number'],
                'total_area': apt['total_area'],
                'bedrooms': apt['bedrooms'],
                'bathrooms': apt['bathrooms'],
                'room_count': apt['room_count'],
                'arrangement': apt.get('arrangement'),
                'design_issues': apt.get('design_issues', []),
                'zone_boundary': apt['zone_boundary'],
                'rooms': []
            }
            
            # Add room data
            for room in apt['rooms']:
                room_data = {
                    'room_id': room.get('room_id'),
                    'type': room['type'],
                    'area': room['area'],
                    'target_area': room.get('target_area', 0),
                    'zone': room.get('zone', 'unknown'),
                    'polygon': room['polygon'],
                    'is_touching': room.get('is_touching', False)
                }
                apt_data['rooms'].append(room_data)
            
            json_data['apartments'].append(apt_data)
        
        # Add circulation elements data
        if layout.get('has_circulation', False):
            json_data['circulation_elements'] = []
            for circ_elem in layout.get('circulation_elements', []):
                circ_data = {
                    'type': circ_elem['type'],
                    'area': circ_elem['area'],
                    'target_area': circ_elem.get('target_area', 0),
                    'zone': circ_elem.get('zone', 'circulation'),
                    'polygon': circ_elem['polygon'],
                    'specifications': circ_elem.get('specifications', ''),
                    'nbc_compliant': circ_elem.get('nbc_compliant', True)
                }
                json_data['circulation_elements'].append(circ_data)

        json_data['architectural_review'] = layout.get('architectural_review', {})
        
        # Wall elements removed - were causing DXF display issues
        
        # Save to file
        with open(save_path, 'w') as f:
            json.dump(json_data, f, indent=2)
        
        print(f"💾 Layout data saved: {save_path}")
    
    def export_to_dxf(self, layout: Dict, save_path: str) -> None:
        """Export layout to DXF format"""
        
        if not DXF_AVAILABLE or FloorPlanDXFExporter is None:
            print("⚠️ DXF export module not available")
            return
        
        try:
            # Save layout as JSON first (required by DXF exporter)
            temp_json_path = save_path.replace('.dxf', '_temp.json')
            self.save_layout_data(layout, temp_json_path)
            
            # Create DXF exporter and export
            dxf_exporter = FloorPlanDXFExporter()
            dxf_exporter.export_apartment_layout_to_dxf(temp_json_path, save_path)
            
            # Clean up temporary JSON file
            if os.path.exists(temp_json_path):
                os.remove(temp_json_path)
                
            print(f"💾 DXF file exported: {save_path}")
        except Exception as e:
            print(f"❌ Error exporting DXF: {e}")


def main():
    """Test the boundary natural generator"""
    
    print("🏗️ Testing Boundary Natural Generator")
    
    # Initialize generator
    generator = BoundaryNaturalGenerator()
    
    # Test with different boundary shapes
    boundary_images = [
        ("Square.png", "square"),
        ("Rectangle.png", "rectangle"), 
        ("Circle.png", "circle"),
        ("Irregular.png", "irregular")
    ]
    
    # Test configuration - now supports different plot sizes
    test_configs = [
        {
            'num_apartments': 2,
            'bedrooms_per_apt': 2,
            'fsi': 1.8,
            'ground_coverage': 0.65,
            'floors': 1,
            'target_area': None  # Use natural plot size
        },
        {
            'num_apartments': 1,
            'bedrooms_per_apt': 3,
            'fsi': 2.0,
            'ground_coverage': 0.7,
            'floors': 1,
            'target_area': 500  # Force specific size for comparison
        }
    ]
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for image_name, shape_type in boundary_images:
        image_path = f"{image_name}"
        
        # Check if image exists
        if not os.path.exists(image_path):
            print(f"⚠️ Skipping {image_name} - file not found")
            continue
        
        # Test with multiple configurations for each shape
        for config_idx, test_config in enumerate(test_configs):
            try:
                config_name = f"config{config_idx+1}"
                print(f"\n{'='*60}")
                print(f"🏗️ Processing {shape_type.upper()} boundary - {config_name}")
                print(f"{'='*60}")
                
                # Generate layout
                layout = generator.generate_boundary_natural_layout(
                    boundary_image_path=image_path,
                    num_apartments=test_config['num_apartments'],
                    bedrooms_per_apt=test_config['bedrooms_per_apt'],
                    fsi=test_config['fsi'],
                    ground_coverage=test_config['ground_coverage'],
                    floors=test_config['floors'],
                    target_area=test_config.get('target_area')
                )
                
                # Create output filenames
                area_suffix = f"_fixed{int(test_config['target_area'])}" if test_config.get('target_area') else "_natural"
                base_name = f"boundary_natural_{shape_type}_{test_config['num_apartments']}apt_{test_config['bedrooms_per_apt']}bhk{area_suffix}_{timestamp}"
                
                # Save layout data
                json_path = f"{base_name}.json"
                generator.save_layout_data(layout, json_path)
                
                # Save visualization
                png_path = f"{base_name}.png"
                generator.visualize_boundary_layout(layout, png_path)
                
                # Export to DXF
                dxf_path = f"{base_name}.dxf"
                generator.export_to_dxf(layout, dxf_path)
                
                print(f"✅ {shape_type.upper()} boundary processing complete - {config_name}")
                print(f"   📁 Files: {base_name}.*")
                
            except Exception as e:
                print(f"❌ Error processing {shape_type} boundary - {config_name}: {e}")


if __name__ == "__main__":
    main()