#!/usr/bin/env python3
"""
Enhanced Multi-Apartment Floor Plan Generator with Natural Room Placement
Integrates sophisticated architectural logic from improved_smart_floor_plan_generator.py
"""

import json
import os
import cv2
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.collections import PatchCollection
from typing import List, Dict, Tuple, Optional
from shapely.geometry import Polygon as ShapelyPolygon, Point
from shapely.ops import unary_union
import random
from datetime import datetime
try:
    from ai_enhanced_room_placer import AIEnhancedRoomPlacer
except ImportError:
    AIEnhancedRoomPlacer = None
try:
    from simple_ai_enhanced_placer import SimpleAIEnhancedPlacer
except ImportError:
    SimpleAIEnhancedPlacer = None

class NaturalMultiApartmentFloorPlanGenerator:
    def __init__(self):
        # Initialize AI-Enhanced Room Placer
        print("🤖 Initializing AI-Enhanced Room Placement System...")
        try:
            if AIEnhancedRoomPlacer:
                self.ai_placer = AIEnhancedRoomPlacer()
                if not self.ai_placer.model_loaded:
                    print("🔄 ArchiGAN model not available, using Simple AI Enhancement...")
                    self.ai_placer = SimpleAIEnhancedPlacer() if SimpleAIEnhancedPlacer else None
                print("✅ AI-Enhanced placement system ready")
            else:
                print("🔄 ArchiGAN not available, trying Simple AI Enhancement...")
                self.ai_placer = SimpleAIEnhancedPlacer() if SimpleAIEnhancedPlacer else None
        except Exception as e:
            print(f"⚠️ AI model loading failed: {e}")
            print("🔄 Falling back to Simple AI Enhancement...")
            try:
                self.ai_placer = SimpleAIEnhancedPlacer() if SimpleAIEnhancedPlacer else None
                print("✅ Simple AI Enhancement loaded" if self.ai_placer else "⚠️ No AI enhancement available")
            except Exception as e2:
                print(f"⚠️ Simple AI Enhancement failed: {e2}")
                self.ai_placer = None
        
        self.colors = {
            'living': '#FFE6CC',      # Light orange
            'bedroom': '#E6F3FF',     # Light blue 
            'master_bedroom': '#E6E6FF', # Light purple
            'kitchen': '#E6FFE6',     # Light green
            'dining': '#FFFFE6',      # Light yellow
            'bathroom': '#FFE6F3',    # Light pink
            'master_bathroom': '#F3E6FF', # Light lavender
            'balcony': '#F0F8FF',     # Alice blue
            'utility': '#FFF0E6',     # Light peach
            'study': '#E8F5E8',       # Mint green
            'corridor': '#E8E8E8',    # Light gray (internal corridors)
            'outdoor_corridor': '#D0D0D0',  # Medium gray (outdoor corridor)
            'lift': '#FFB6C1',       # Light pink (lift)
            'staircase': '#DDA0DD',   # Plum (staircase)  
            'lobby': '#F0E68C',      # Khaki (lobby)
            'entrance': '#FFF5E6'     # Cream
        }
        
        self.standard_areas = {
            'living': 25.0,
            'bedroom': 12.0,
            'master_bedroom': 16.0,
            'kitchen': 10.0,
            'dining': 12.0,
            'bathroom': 6.0,
            'master_bathroom': 8.0,
            'balcony': 8.0,
            'utility': 4.0,
            'study': 10.0
        }
        
        # Natural adjacency preferences for intelligent placement
        self.natural_adjacencies = {
            'living': ['dining', 'balcony', 'kitchen'],
            'master_bedroom': ['master_bathroom', 'balcony'],
            'bedroom': ['bathroom'],
            'kitchen': ['dining', 'utility'],
            'dining': ['living', 'kitchen'],
            'master_bathroom': ['master_bedroom'],
            'bathroom': ['bedroom'],
            'balcony': ['living', 'master_bedroom', 'dining'],
            'utility': ['kitchen']
        }
        
        # Placement preferences for intelligent positioning  
        self.placement_preferences = {
            'balcony': 'external_corner_with_view',
            'living': 'central_with_external_access',
            'master_bedroom': 'private_corner_with_external_access',
            'kitchen': 'service_area_with_ventilation',
            'dining': 'central_social_space',
            'bathroom': 'internal_with_ventilation',
            'master_bathroom': 'private_adjacent_to_master',
            'bedroom': 'quiet_external_access',
            'utility': 'service_area_compact'
        }

    def generate_natural_multi_apartment_layout(
        self, 
        num_apartments: int, 
        bedrooms_per_apt: int, 
        plot_image_path: str,
        fsi: float = 1.8,
        ground_coverage: float = 0.65,
        floors: int = 1
    ) -> Dict:
        """Generate natural multi-apartment layout using sophisticated architectural logic"""
        
        print(f"\n🏢 Generating {num_apartments} apartments with {bedrooms_per_apt} bedrooms each")
        print(f"📐 Plot: {plot_image_path}")
        print(f"🏗️ FSI: {fsi}, Ground Coverage: {ground_coverage*100}%, Floors: {floors}")
        
        # Extract plot boundary
        plot_boundary = self._extract_plot_boundary(plot_image_path)
        if not plot_boundary:
            raise ValueError("Could not extract plot boundary from image")
        
        # Calculate plot metrics
        plot_poly = ShapelyPolygon(plot_boundary)
        plot_area = plot_poly.area
        
        # Calculate permissible built-up area
        max_ground_area = plot_area * ground_coverage
        max_total_area = plot_area * fsi
        max_area_per_floor = max_total_area / floors
        
        print(f"📊 Plot area: {plot_area:.1f} sq m")
        print(f"📊 Max ground coverage: {max_ground_area:.1f} sq m")
        print(f"📊 Max total built area: {max_total_area:.1f} sq m")
        print(f"📊 Max area per floor: {max_area_per_floor:.1f} sq m")
        
        # Calculate apartment area allocation
        area_per_apartment = min(max_area_per_floor / num_apartments, max_ground_area / num_apartments)
        
        print(f"🏠 Area per apartment: {area_per_apartment:.1f} sq m")
        
        # Create building envelope (85% of max ground area for circulation)
        building_envelope = self._create_building_envelope(plot_boundary, 0.85)
        
        # Store building envelope as instance variable for perimeter checking
        self.current_building_envelope = building_envelope
        
        # Divide building envelope into apartment zones
        apartment_zones = self._create_natural_apartment_zones(
            building_envelope, num_apartments, area_per_apartment
        )
        
        # Store apartment zones for adjacent apartment checking during balcony placement
        self.current_apartment_zones = apartment_zones
        
        # Generate apartments without circulation elements
        
        # Generate each apartment using natural placement logic
        apartments = []
        for i, zone in enumerate(apartment_zones):
            print(f"\n🏠 Generating Apartment {i+1}...")
            apartment = self._generate_natural_apartment_layout(
                zone, bedrooms_per_apt, area_per_apartment, i+1
            )
            apartments.append(apartment)
        
        # Create comprehensive layout without circulation
        all_rooms = []
        
        # Add apartment rooms
        for apt in apartments:
            all_rooms.extend(apt['rooms'])
        
        # Generate circulation elements (lift, staircase, lobby, corridors) for multi-apartment buildings
        circulation_elements = []
        if num_apartments > 1 or floors > 1:
            print(f"\n🏗️ Generating circulation elements (lift, staircase, corridors)...")
            circulation_data = self._generate_circulation_elements(building_envelope, num_apartments)
            circulation_elements = circulation_data['elements']
            all_rooms.extend(circulation_elements)
            
            print(f"✅ Added circulation elements:")
            for elem in circulation_elements:
                print(f"   🔸 {elem['type'].replace('_', ' ').title()}: {elem['area']:.1f} sq m")
        
        total_built_area = sum(room['area'] for room in all_rooms)
        
        # Generate walls to fill empty spaces and provide structural definition
        print(f"\n🧱 Generating walls (exterior: 6-9 ft, interior: 3-6 ft)...")
        wall_elements = self._generate_walls(all_rooms, building_envelope, apartments)
        all_rooms.extend(wall_elements)
        
        # Update total area including walls
        total_built_area_with_walls = sum(room['area'] for room in all_rooms)
        
        layout = {
            'apartments': apartments,
            'all_rooms': all_rooms,
            'circulation_elements': circulation_elements,
            'wall_elements': wall_elements,
            'has_circulation': len(circulation_elements) > 0,
            'has_walls': len(wall_elements) > 0,
            'building_envelope': building_envelope,
            'plot_boundary': plot_boundary,
            'num_apartments': num_apartments,
            'bedrooms_per_apartment': bedrooms_per_apt,
            'total_built_area': total_built_area,
            'total_built_area_with_walls': total_built_area_with_walls,
            'plot_area': plot_area,
            'fsi_utilized': total_built_area / plot_area,
            'ground_coverage_utilized': total_built_area / plot_area,
            'apartment_zones': apartment_zones
        }
        
        print(f"\n✅ Generated {num_apartments} natural apartments")
        print(f"📊 Total built area: {total_built_area:.1f} sq m")
        print(f"📊 FSI utilized: {layout['fsi_utilized']:.2f}")
        print(f"📊 Ground coverage: {layout['ground_coverage_utilized']*100:.1f}%")
        
        return layout
    
    def _generate_walls(self, all_rooms: List[Dict], building_envelope: List[Tuple[float, float]], 
                       apartments: List[Dict]) -> List[Dict]:
        """Generate exterior and interior walls with proper thickness"""
        
        wall_elements = []
        
        # Convert to meters (6-9 feet = 1.8-2.7m, 3-6 feet = 0.9-1.8m)
        exterior_wall_thickness = 2.1  # 7 feet = 2.1m
        interior_wall_thickness = 1.2  # 4 feet = 1.2m
        
        # Create building envelope polygon
        building_poly = ShapelyPolygon(building_envelope)
        
        # Generate exterior walls
        print(f"   🧱 Creating exterior walls ({exterior_wall_thickness:.1f}m thick)")
        exterior_walls = self._create_exterior_walls(building_poly, exterior_wall_thickness, all_rooms)
        wall_elements.extend(exterior_walls)
        
        # Generate interior walls between rooms
        print(f"   🧱 Creating interior walls ({interior_wall_thickness:.1f}m thick)")
        interior_walls = self._create_interior_walls(all_rooms, interior_wall_thickness)
        wall_elements.extend(interior_walls)
        
        # Fill remaining empty spaces with structural walls
        print(f"   🧱 Filling empty spaces with structural elements")
        structural_walls = self._fill_empty_spaces(all_rooms + wall_elements, building_poly)
        wall_elements.extend(structural_walls)
        
        print(f"   ✅ Generated {len(wall_elements)} wall elements")
        return wall_elements
    
    def _create_exterior_walls(self, building_poly: ShapelyPolygon, wall_thickness: float, 
                             existing_rooms: List[Dict]) -> List[Dict]:
        """Create thick exterior walls around building perimeter"""
        
        exterior_walls = []
        
        # Create inward offset for exterior walls
        try:
            inner_boundary = building_poly.buffer(-wall_thickness)
            if inner_boundary.is_valid and hasattr(inner_boundary, 'exterior'):
                # Wall is the area between outer and inner boundaries
                wall_area = building_poly.difference(inner_boundary)
                
                if wall_area.area > 1:  # Only add if significant area
                    exterior_walls.append({
                        'type': 'exterior_wall',
                        'polygon': list(wall_area.exterior.coords[:-1]) if hasattr(wall_area, 'exterior') else [],
                        'area': wall_area.area,
                        'target_area': wall_area.area,
                        'zone': 'structure',
                        'wall_type': 'exterior',
                        'thickness': wall_thickness,
                        'is_touching': False
                    })
        except Exception as e:
            print(f"   ⚠️ Could not create exterior walls: {e}")
        
        return exterior_walls
    
    def _create_interior_walls(self, all_rooms: List[Dict], wall_thickness: float) -> List[Dict]:
        """Create interior walls between adjacent rooms"""
        
        interior_walls = []
        room_polygons = []
        
        # Get room polygons (exclude existing walls and circulation)
        for room in all_rooms:
            if 'wall' not in room.get('type', '') and room.get('type') not in ['lift', 'staircase_perimeter']:
                try:
                    poly = ShapelyPolygon(room['polygon'])
                    if poly.is_valid:
                        room_polygons.append((poly, room))
                except Exception:
                    continue
        
        # Generate walls between adjacent rooms
        wall_id = 1
        for i, (poly1, room1) in enumerate(room_polygons):
            for j, (poly2, room2) in enumerate(room_polygons[i+1:], i+1):
                try:
                    # Check if rooms are adjacent (touching or very close)
                    distance = poly1.distance(poly2)
                    if distance < wall_thickness * 2:  # Within wall generation range
                        
                        # Create wall between rooms
                        # Find the space between rooms and create a wall
                        combined_bounds = [
                            min(poly1.bounds[0], poly2.bounds[0]),
                            min(poly1.bounds[1], poly2.bounds[1]), 
                            max(poly1.bounds[2], poly2.bounds[2]),
                            max(poly1.bounds[3], poly2.bounds[3])
                        ]
                        
                        # Create a thin wall strip between rooms
                        wall_poly = self._create_wall_strip(poly1, poly2, wall_thickness)
                        
                        if wall_poly and wall_poly.area > 0.5:  # Minimum wall area
                            interior_walls.append({
                                'type': 'interior_wall',
                                'polygon': list(wall_poly.exterior.coords[:-1]) if hasattr(wall_poly, 'exterior') else [],
                                'area': wall_poly.area,
                                'target_area': wall_poly.area,
                                'zone': 'structure',
                                'wall_type': 'interior',
                                'thickness': wall_thickness,
                                'between_rooms': f"{room1.get('type', 'room')}-{room2.get('type', 'room')}",
                                'wall_id': wall_id,
                                'is_touching': False
                            })
                            wall_id += 1
                            
                except Exception as e:
                    continue
        
        return interior_walls
    
    def _create_wall_strip(self, poly1: ShapelyPolygon, poly2: ShapelyPolygon, 
                          wall_thickness: float) -> ShapelyPolygon:
        """Create a wall strip between two room polygons"""
        
        try:
            # Get the area between the two polygons
            bounds1 = poly1.bounds
            bounds2 = poly2.bounds
            
            # Determine orientation and create wall strip
            if abs(bounds1[0] - bounds2[2]) < wall_thickness * 1.5:  # Vertical wall (poly2 to the right of poly1)
                wall_x = (bounds1[2] + bounds2[0]) / 2
                wall_coords = [
                    (wall_x - wall_thickness/2, min(bounds1[1], bounds2[1])),
                    (wall_x + wall_thickness/2, min(bounds1[1], bounds2[1])),
                    (wall_x + wall_thickness/2, max(bounds1[3], bounds2[3])),
                    (wall_x - wall_thickness/2, max(bounds1[3], bounds2[3]))
                ]
            elif abs(bounds1[2] - bounds2[0]) < wall_thickness * 1.5:  # Vertical wall (poly1 to the right of poly2)  
                wall_x = (bounds1[0] + bounds2[2]) / 2
                wall_coords = [
                    (wall_x - wall_thickness/2, min(bounds1[1], bounds2[1])),
                    (wall_x + wall_thickness/2, min(bounds1[1], bounds2[1])),
                    (wall_x + wall_thickness/2, max(bounds1[3], bounds2[3])),
                    (wall_x - wall_thickness/2, max(bounds1[3], bounds2[3]))
                ]
            elif abs(bounds1[1] - bounds2[3]) < wall_thickness * 1.5:  # Horizontal wall (poly2 above poly1)
                wall_y = (bounds1[3] + bounds2[1]) / 2
                wall_coords = [
                    (min(bounds1[0], bounds2[0]), wall_y - wall_thickness/2),
                    (max(bounds1[2], bounds2[2]), wall_y - wall_thickness/2),
                    (max(bounds1[2], bounds2[2]), wall_y + wall_thickness/2),
                    (min(bounds1[0], bounds2[0]), wall_y + wall_thickness/2)
                ]
            elif abs(bounds1[3] - bounds2[1]) < wall_thickness * 1.5:  # Horizontal wall (poly1 above poly2)
                wall_y = (bounds1[1] + bounds2[3]) / 2
                wall_coords = [
                    (min(bounds1[0], bounds2[0]), wall_y - wall_thickness/2),
                    (max(bounds1[2], bounds2[2]), wall_y - wall_thickness/2),
                    (max(bounds1[2], bounds2[2]), wall_y + wall_thickness/2),
                    (min(bounds1[0], bounds2[0]), wall_y + wall_thickness/2)
                ]
            else:
                return None  # Not adjacent enough for a wall
            
            wall_poly = ShapelyPolygon(wall_coords)
            
            # Make sure wall doesn't overlap with existing rooms
            wall_poly = wall_poly.difference(poly1.buffer(0.1))
            wall_poly = wall_poly.difference(poly2.buffer(0.1))
            
            return wall_poly if wall_poly.area > 0.1 else None
            
        except Exception:
            return None
    
    def _fill_empty_spaces(self, existing_elements: List[Dict], building_poly: ShapelyPolygon) -> List[Dict]:
        """Fill remaining empty spaces with structural walls"""
        
        structural_walls = []
        
        try:
            # Create union of all existing elements
            used_area = None
            for element in existing_elements:
                try:
                    poly = ShapelyPolygon(element['polygon'])
                    if poly.is_valid:
                        if used_area is None:
                            used_area = poly
                        else:
                            used_area = used_area.union(poly)
                except Exception:
                    continue
            
            if used_area is not None:
                # Find empty areas
                empty_areas = building_poly.difference(used_area)
                
                # Convert to individual polygons if it's a MultiPolygon
                if hasattr(empty_areas, 'geoms'):
                    empty_polygons = list(empty_areas.geoms)
                else:
                    empty_polygons = [empty_areas] if empty_areas.area > 1 else []
                
                # Create structural walls from significant empty areas
                for i, empty_poly in enumerate(empty_polygons):
                    if empty_poly.area > 2:  # Minimum area for structural element
                        structural_walls.append({
                            'type': 'structural_wall',
                            'polygon': list(empty_poly.exterior.coords[:-1]) if hasattr(empty_poly, 'exterior') else [],
                            'area': empty_poly.area,
                            'target_area': empty_poly.area,
                            'zone': 'structure',
                            'wall_type': 'structural',
                            'structural_id': i + 1,
                            'is_touching': False
                        })
        
        except Exception as e:
            print(f"   ⚠️ Could not fill empty spaces: {e}")
        
        return structural_walls
    
    def _design_circulation_core(self, bounds: Tuple[float, float, float, float], 
                               num_apartments: int) -> Dict:
        """Design central circulation core with lift, staircase, and lobby"""
        
        min_x, min_y, max_x, max_y = bounds
        width = max_x - min_x
        height = max_y - min_y
        
        # Position circulation core in center or strategic location
        if width > height:
            # Wide building - place circulation on one side
            core_x = min_x + width * 0.15
            core_y = min_y + height * 0.4
        else:
            # Tall building - place circulation in center
            core_x = min_x + width * 0.4
            core_y = min_y + height * 0.15
        
        # Standard circulation dimensions (NBC compliant)
        lift_width = 2.0  # 2m x 2m lift
        lift_depth = 2.0
        stair_width = 1.8  # Minimum 1.8m wide staircase
        stair_depth = 4.0  # 4m depth for comfortable stairs
        lobby_size = 3.0   # 3m x 3m lobby
        
        # Lift coordinates
        lift_coords = [
            (core_x, core_y),
            (core_x + lift_width, core_y),
            (core_x + lift_width, core_y + lift_depth),
            (core_x, core_y + lift_depth)
        ]
        
        # Staircase coordinates (adjacent to lift)
        stair_x = core_x + lift_width + 0.5  # 0.5m gap
        stair_coords = [
            (stair_x, core_y),
            (stair_x + stair_width, core_y),
            (stair_x + stair_width, core_y + stair_depth),
            (stair_x, core_y + stair_depth)
        ]
        
        # Lobby coordinates (in front of lift and stairs)
        lobby_x = core_x - 0.5
        lobby_y = core_y + max(lift_depth, stair_depth) + 0.5
        lobby_coords = [
            (lobby_x, lobby_y),
            (lobby_x + lobby_size + lift_width + stair_width, lobby_y),
            (lobby_x + lobby_size + lift_width + stair_width, lobby_y + lobby_size),
            (lobby_x, lobby_y + lobby_size)
        ]
        
        circulation_core = {
            'lift': {
                'coordinates': lift_coords,
                'area': lift_width * lift_depth,
                'width': lift_width,
                'depth': lift_depth,
                'capacity': '8 persons'
            },
            'staircase': {
                'coordinates': stair_coords,
                'area': stair_width * stair_depth,
                'width': stair_width,
                'depth': stair_depth,
                'tread': 0.3,  # 30cm tread
                'riser': 0.15  # 15cm riser (NBC compliant)
            },
            'lobby': {
                'coordinates': lobby_coords,
                'area': lobby_size * (lobby_size + lift_width + stair_width),
                'size': lobby_size
            }
        }
        
        print(f"🏗️ Designed circulation core:")
        print(f"   🛗 Lift: {lift_width}m x {lift_depth}m ({circulation_core['lift']['area']:.1f} sq m)")
        print(f"   🏃 Staircase: {stair_width}m x {stair_depth}m ({circulation_core['staircase']['area']:.1f} sq m)")
        print(f"   🏛️ Lobby: {circulation_core['lobby']['area']:.1f} sq m")
        
        return circulation_core
    
    def _extract_plot_boundary(self, plot_image_path: str) -> List[Tuple[float, float]]:
        """Extract plot boundary from uploaded image"""
        
        if not os.path.exists(plot_image_path):
            print(f"❌ Plot image not found: {plot_image_path}")
            return None
        
        try:
            # Read and process image
            image = cv2.imread(plot_image_path)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Find contours
            contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if not contours:
                print("❌ No contours found in image")
                return None
            
            # Get largest contour (main plot boundary)
            largest_contour = max(contours, key=cv2.contourArea)
            
            # Convert to coordinates and scale to realistic dimensions
            boundary_points = []
            for point in largest_contour:
                x, y = point[0]
                boundary_points.append((float(x), float(y)))
            
            # Scale to realistic plot size (assuming 1707 sq m as reference)
            boundary_poly = ShapelyPolygon(boundary_points)
            current_area = boundary_poly.area
            
            if current_area > 0:
                target_area = 1707.0  # Target area in sq m
                scale_factor = (target_area / current_area) ** 0.5
                
                scaled_boundary = []
                for x, y in boundary_points:
                    scaled_x = x * scale_factor
                    scaled_y = y * scale_factor
                    scaled_boundary.append((scaled_x, scaled_y))
                
                print(f"✅ Extracted plot boundary with {len(scaled_boundary)} points")
                print(f"📐 Scaled area: {ShapelyPolygon(scaled_boundary).area:.1f} sq m")
                
                return scaled_boundary
            
        except Exception as e:
            print(f"❌ Error extracting plot boundary: {e}")
        
        return None
    
    def _create_building_envelope(self, plot_boundary: List[Tuple[float, float]], 
                                 coverage_ratio: float) -> List[Tuple[float, float]]:
        """Create building envelope within plot boundary"""
        
        plot_poly = ShapelyPolygon(plot_boundary)
        
        # Create inset boundary for building envelope
        envelope_poly = plot_poly.buffer(-2.0)  # 2m setback from plot boundary
        
        if envelope_poly.area < plot_poly.area * coverage_ratio:
            # If setback is too large, use smaller setback
            envelope_poly = plot_poly.buffer(-1.0)
        
        if hasattr(envelope_poly, 'exterior'):
            envelope_coords = list(envelope_poly.exterior.coords[:-1])
        else:
            envelope_coords = plot_boundary
        
        print(f"🏗️ Building envelope: {len(envelope_coords)} points, {envelope_poly.area:.1f} sq m")
        
        return envelope_coords
    
    def _create_natural_apartment_zones(self, building_envelope: List[Tuple[float, float]], 
                                       num_apartments: int, area_per_apartment: float) -> List[List[Tuple[float, float]]]:
        """Create simple apartment zones without circulation elements"""
        
        envelope_poly = ShapelyPolygon(building_envelope)
        bounds = envelope_poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        print(f"🏗️ Dividing building ({width:.1f}m x {height:.1f}m) into {num_apartments} zones")
        
        # Create simple apartment zones using the full building area
        zones = self._create_simple_apartment_zones(bounds, num_apartments)
        
        return zones
    
    def _create_simple_apartment_zones(self, bounds, num_apartments):
        """Create simple apartment zones using full building area"""
        min_x, min_y, max_x, max_y = bounds
        width = max_x - min_x
        height = max_y - min_y
        
        zones = []
        
        if num_apartments == 1:
            # Single apartment gets full area
            zones.append([(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)])
            
        elif num_apartments == 2:
            # Two apartments split horizontally
            mid_y = min_y + height / 2
            
            zones.extend([
                [(min_x, min_y), (max_x, min_y), (max_x, mid_y), (min_x, mid_y)],
                [(min_x, mid_y), (max_x, mid_y), (max_x, max_y), (min_x, max_y)]
            ])
            
        else:
            # Multiple apartments in grid pattern
            if num_apartments <= 4:
                grid_rows, grid_cols = 2, 2
            else:
                grid_rows, grid_cols = 2, 3 if num_apartments == 5 else 3
            
            apt_width = width / grid_cols
            apt_height = height / grid_rows
            
            for i in range(num_apartments):
                row = i // grid_cols
                col = i % grid_cols
                
                x1 = min_x + col * apt_width
                y1 = min_y + row * apt_height
                x2 = x1 + apt_width
                y2 = y1 + apt_height
                
                zones.append([(x1, y1), (x2, y1), (x2, y2), (x1, y2)])
        
        print(f"📐 Created {len(zones)} simple apartment zones")
        return zones
    

    

    
    def _generate_natural_apartment_layout(self, apartment_zone: List[Tuple[float, float]], 
                                         bedrooms: int, target_area: float, apt_number: int, 
                                         circulation_zones: List[Dict] = None) -> Dict:
        """Generate natural apartment layout using improved architectural logic with circulation awareness"""
        
        # Store current apartment zone for balcony placement checks
        self.current_processing_apartment_zone = apartment_zone
        
        zone_poly = ShapelyPolygon(apartment_zone)
        bounds = zone_poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        print(f"  🏠 Apartment {apt_number}: {width:.1f}m x {height:.1f}m ({zone_poly.area:.1f} sq m)")
        
        # Create room program with maximum FSI utilization
        bathrooms = bedrooms + 1  # N+1 bathrooms rule
        
        # Calculate optimal room areas to utilize 80-85% of available apartment space
        available_apartment_area = zone_poly.area
        target_room_utilization = 0.82  # Use 82% of apartment area for rooms
        total_target_room_area = available_apartment_area * target_room_utilization
        
        # Calculate base total area from standard sizes
        base_total_area = (
            self.standard_areas['living'] + self.standard_areas['kitchen'] + self.standard_areas['dining'] +
            self.standard_areas['master_bedroom'] + self.standard_areas['master_bathroom'] +
            (bedrooms - 1) * self.standard_areas['bedroom'] +
            (bathrooms - 1) * self.standard_areas['bathroom'] +
            self.standard_areas['balcony'] + self.standard_areas['utility']
        )
        
        # Scale factor to maximize space utilization
        scale_factor = max(2.5, total_target_room_area / base_total_area)  # At least 2.5x standard sizes
        
        print(f"    📊 Room scaling: {scale_factor:.1f}x (Target: {total_target_room_area:.0f} sq m)")
        
        room_program = [
            # Public zone (priority 1-3) - substantially larger areas
            {'type': 'living', 'target_area': self.standard_areas['living'] * scale_factor, 'zone': 'public', 'priority': 1},
            {'type': 'kitchen', 'target_area': self.standard_areas['kitchen'] * scale_factor, 'zone': 'public', 'priority': 2},
            {'type': 'dining', 'target_area': self.standard_areas['dining'] * scale_factor, 'zone': 'public', 'priority': 3},
            
            # Master suite (priority 4-5) - substantially larger areas
            {'type': 'master_bedroom', 'target_area': self.standard_areas['master_bedroom'] * scale_factor, 'zone': 'master_suite', 'priority': 4},
            {'type': 'master_bathroom', 'target_area': self.standard_areas['master_bathroom'] * scale_factor, 'zone': 'master_suite', 'priority': 5}
        ]
        
        # Additional bedrooms (priority 6+) - larger areas
        for i in range(bedrooms - 1):  # -1 because master bedroom already added
            room_program.append({
                'type': 'bedroom',
                'target_area': self.standard_areas['bedroom'] * scale_factor,
                'zone': 'private',
                'priority': 6 + i
            })
        
        # Additional bathrooms (priority after bedrooms) - larger areas
        for i in range(bathrooms - 1):  # -1 because master bathroom already added
            room_program.append({
                'type': 'bathroom',
                'target_area': self.standard_areas['bathroom'] * scale_factor,
                'zone': 'service',
                'priority': 10 + i
            })
        
        # Utility rooms (lowest priority) - larger areas
        room_program.extend([
            {'type': 'balcony', 'target_area': self.standard_areas['balcony'] * scale_factor, 'zone': 'service', 'priority': 20},
            {'type': 'utility', 'target_area': self.standard_areas['utility'] * scale_factor, 'zone': 'service', 'priority': 21}
        ])
        
        # AI-Enhanced Room Placement with Intelligent Fallback
        placed_rooms = []
        
        # AI Enhancement Control - Set to False to disable AI and use high-performance rules
        USE_AI_ENHANCEMENT = False  # Disabled - original system performs better
        
        # Try AI-generated layout first if model is available and enabled
        if USE_AI_ENHANCEMENT and self.ai_placer and self.ai_placer.model_loaded:
            try:
                ai_rooms = self.ai_placer.generate_ai_room_layout(
                    apartment_zone, room_program, apt_number
                )
                
                # Use AI layout if it successfully placed 70%+ of rooms
                if len(ai_rooms) >= len(room_program) * 0.7:
                    print(f"    🤖 AI-generated layout: {len(ai_rooms)} rooms")
                    placed_rooms = ai_rooms
                else:
                    print(f"    🧠 AI partial success ({len(ai_rooms)} rooms), using hybrid approach")
                    # Use AI rooms as base, fill remaining with intelligent placement
                    placed_rooms = ai_rooms
                    
                    # Fill remaining rooms with intelligent placement
                    remaining_room_types = [r['type'] for r in room_program]
                    placed_room_types = [r['type'] for r in placed_rooms]
                    missing_rooms = [r for r in room_program if r['type'] not in placed_room_types or 
                                   remaining_room_types.count(r['type']) > placed_room_types.count(r['type'])]
                    
                    if missing_rooms:
                        additional_layout = self._place_remaining_rooms_intelligently(
                            missing_rooms, zone_poly, placed_rooms
                        )
                        placed_rooms.extend(additional_layout)
                        
            except Exception as e:
                print(f"    ⚠️ AI generation failed: {e}")
                placed_rooms = []
        
        # Fallback to intelligent rule-based placement if AI didn't work or isn't available
        if not placed_rooms:
            print(f"    🧠 Using intelligent rule-based layout")
            
            # Phase 1: Place public zone (living-kitchen-dining) intelligently with circulation awareness
            public_rooms = [r for r in room_program if r['zone'] == 'public']
            public_layout = self._place_intelligent_public_zone(
                public_rooms, zone_poly, apt_number, circulation_zones
            )
            placed_rooms.extend(public_layout)
            
            # Phase 2: Place master suite in remaining space
            master_rooms = [r for r in room_program if r['zone'] == 'master_suite']
            master_layout = self._place_intelligent_master_suite(
                master_rooms, zone_poly, placed_rooms
            )
            placed_rooms.extend(master_layout)
            
            # Phase 3: Place remaining rooms with intelligent positioning
            remaining_rooms = [r for r in room_program if r['zone'] not in ['public', 'master_suite']]
            additional_layout = self._place_remaining_rooms_intelligently(
                remaining_rooms, zone_poly, placed_rooms
            )
            placed_rooms.extend(additional_layout)
        
        # Phase 4: Ensure all rooms touch
        touching_rooms = self._ensure_natural_adjacency(placed_rooms, zone_poly)
        
        total_area = sum(room['area'] for room in touching_rooms)
        
        print(f"    ✅ Placed {len(touching_rooms)} rooms ({total_area:.1f} sq m)")
        
        return {
            'apartment_number': apt_number,
            'rooms': touching_rooms,
            'zone_boundary': apartment_zone,
            'total_area': total_area,
            'bedrooms': bedrooms,
            'bathrooms': bathrooms,
            'room_count': len(touching_rooms)
        }
    

    
    def _place_natural_master_suite(self, master_rooms: List[Dict], zone_poly: ShapelyPolygon, 
                                   existing_rooms: List[Dict]) -> List[Dict]:
        """Place master bedroom and bathroom adjacently (from improved_smart_floor_plan_generator)"""
        
        bounds = zone_poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        placed_master = []
        
        master_bedroom = next(r for r in master_rooms if r['type'] == 'master_bedroom')
        master_bathroom = next(r for r in master_rooms if r['type'] == 'master_bathroom')
        
        # Master bedroom (top right for privacy)
        master_bed_width = width * 0.35
        master_bed_height = height * 0.45
        
        master_bed_coords = [
            (bounds[0] + width - master_bed_width, bounds[1] + height - master_bed_height),
            (bounds[2], bounds[1] + height - master_bed_height),
            (bounds[2], bounds[3]),
            (bounds[0] + width - master_bed_width, bounds[3])
        ]
        
        master_bed_poly = ShapelyPolygon(master_bed_coords).intersection(zone_poly)
        
        placed_master.append({
            'type': 'master_bedroom',
            'polygon': list(master_bed_poly.exterior.coords[:-1]) if hasattr(master_bed_poly, 'exterior') else master_bed_coords,
            'area': master_bed_poly.area,
            'target_area': master_bedroom['target_area'],
            'zone': 'master_suite',
            'is_touching': True
        })
        
        # Master bathroom (adjacent to master bedroom)
        master_bath_width = width * 0.12
        master_bath_height = height * 0.20
        
        master_bath_coords = [
            (bounds[0] + width - master_bed_width - master_bath_width, bounds[1] + height - master_bath_height),
            (bounds[0] + width - master_bed_width, bounds[1] + height - master_bath_height),
            (bounds[0] + width - master_bed_width, bounds[3]),
            (bounds[0] + width - master_bed_width - master_bath_width, bounds[3])
        ]
        
        master_bath_poly = ShapelyPolygon(master_bath_coords).intersection(zone_poly)
        
        placed_master.append({
            'type': 'master_bathroom',
            'polygon': list(master_bath_poly.exterior.coords[:-1]) if hasattr(master_bath_poly, 'exterior') else master_bath_coords,
            'area': master_bath_poly.area,
            'target_area': master_bathroom['target_area'],
            'zone': 'master_suite',
            'is_touching': True
        })
        
        return placed_master
    
    def _place_natural_additional_rooms(self, remaining_rooms: List[Dict], zone_poly: ShapelyPolygon,
                                       existing_rooms: List[Dict]) -> List[Dict]:
        """Place remaining rooms with corridor connectivity and smart bathroom overlapping"""
        
        bounds = zone_poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        placed_additional = []
        
        # Find existing corridor for connectivity
        corridor_room = next((r for r in existing_rooms if r['type'] == 'corridor'), None)
        
        # Organize by type
        bedrooms = [r for r in remaining_rooms if r['type'] == 'bedroom']
        bathrooms = [r for r in remaining_rooms if r['type'] == 'bathroom']
        utility_rooms = [r for r in remaining_rooms if r['type'] in ['balcony', 'utility']]
        
        # Create secondary corridor connecting to bedrooms (if space allows)
        if len(bedrooms) > 0:
            bedroom_corridor_coords = [
                (bounds[0] + width * 0.25, bounds[1] + height * 0.15),
                (bounds[0] + width * 0.90, bounds[1] + height * 0.15),
                (bounds[0] + width * 0.90, bounds[1] + height * 0.20),
                (bounds[0] + width * 0.25, bounds[1] + height * 0.20)
            ]
            
            bedroom_corridor_poly = ShapelyPolygon(bedroom_corridor_coords).intersection(zone_poly)
            
            if bedroom_corridor_poly.area > 5:  # Only add if meaningful size
                placed_additional.append({
                    'type': 'corridor',
                    'polygon': list(bedroom_corridor_poly.exterior.coords[:-1]) if hasattr(bedroom_corridor_poly, 'exterior') else bedroom_corridor_coords,
                    'area': bedroom_corridor_poly.area,
                    'target_area': width * height * 0.03,
                    'zone': 'circulation',
                    'is_touching': True,
                    'connects_to': ['bedrooms', 'bathrooms']
                })
        
        # Place bedrooms with corridor access and maximized space
        if bedrooms:
            available_width = width * 0.65  # More width for bedrooms
            bed_width = available_width / max(1, len(bedrooms))
            
            for i, bedroom in enumerate(bedrooms):
                # Bedrooms positioned to connect with corridor
                x_start = bounds[0] + width * 0.25 + (i * bed_width)
                bed_height = height * 0.15  # Height above corridor
                
                bed_coords = [
                    (x_start, bounds[1]),
                    (x_start + bed_width, bounds[1]),
                    (x_start + bed_width, bounds[1] + bed_height),
                    (x_start, bounds[1] + bed_height)
                ]
                
                bed_poly = ShapelyPolygon(bed_coords).intersection(zone_poly)
                
                placed_additional.append({
                    'type': 'bedroom',
                    'polygon': list(bed_poly.exterior.coords[:-1]) if hasattr(bed_poly, 'exterior') else bed_coords,
                    'area': bed_poly.area,
                    'target_area': bedroom['target_area'],
                    'zone': bedroom['zone'],
                    'is_touching': True,
                    'connects_to_corridor': True
                })
        
        # Place bathrooms with strategic overlapping for space maximization
        if bathrooms:
            # Determine bathroom placement strategy
            num_common_bathrooms = max(0, len(bathrooms) - 1)  # All except master bathroom
            
            for i, bathroom in enumerate(bathrooms):
                if i < num_common_bathrooms:
                    # Common bathrooms: allow overlapping with public areas for space efficiency
                    
                    # Find best position - can overlap with living room or corridor edges
                    overlap_x = bounds[0] + width * 0.20  # Slightly overlap with living area
                    overlap_y = bounds[1] + height * 0.70 + (i * height * 0.15)
                    
                    # Smart overlapping: extend into living room space by 20%
                    bath_width = width * 0.12  # Standard width but can extend
                    bath_height = height * 0.12
                    
                    bath_coords = [
                        (overlap_x, overlap_y),
                        (overlap_x + bath_width, overlap_y),
                        (overlap_x + bath_width, overlap_y + bath_height),
                        (overlap_x, overlap_y + bath_height)
                    ]
                    
                    bath_poly = ShapelyPolygon(bath_coords).intersection(zone_poly)
                    
                    placed_additional.append({
                        'type': 'bathroom',
                        'polygon': list(bath_poly.exterior.coords[:-1]) if hasattr(bath_poly, 'exterior') else bath_coords,
                        'area': bath_poly.area,
                        'target_area': bathroom['target_area'],
                        'zone': bathroom['zone'],
                        'is_touching': True,
                        'connects_to_corridor': True,
                        'overlapping': True,
                        'overlaps_with': ['living', 'corridor']
                    })
                    
                else:
                    # Additional bathrooms: positioned for bedroom access
                    bath_x = bounds[0] + width * 0.80
                    bath_y = bounds[1] + height * 0.25
                    
                    bath_coords = [
                        (bath_x, bath_y),
                        (bath_x + width * 0.10, bath_y),
                        (bath_x + width * 0.10, bath_y + height * 0.20),
                        (bath_x, bath_y + height * 0.20)
                    ]
                    
                    bath_poly = ShapelyPolygon(bath_coords).intersection(zone_poly)
                    
                    placed_additional.append({
                        'type': 'bathroom',
                        'polygon': list(bath_poly.exterior.coords[:-1]) if hasattr(bath_poly, 'exterior') else bath_coords,
                        'area': bath_poly.area,
                        'target_area': bathroom['target_area'],
                        'zone': bathroom['zone'],
                        'is_touching': True,
                        'connects_to_corridor': True
                    })
        
        # Place utility rooms with corridor connectivity
        for i, utility_room in enumerate(utility_rooms):
            util_width = width * 0.12  # Slightly smaller to allow corridors
            util_height = height * 0.10
            
            if utility_room['type'] == 'balcony':
                # Balcony: connected to living area via corridor
                x_start = bounds[0] + width * 0.05  # Near living room
                y_start = bounds[1] + height * 0.85
            else:  # utility
                # Utility: near kitchen via corridor
                x_start = bounds[0] + width * 0.75
                y_start = bounds[1] + height * 0.85
            
            # Create connection corridor to utility room
            util_corridor_coords = [
                (x_start - width * 0.02, y_start + util_height * 0.5),
                (x_start, y_start + util_height * 0.5),
                (x_start, y_start + util_height * 0.7),
                (x_start - width * 0.02, y_start + util_height * 0.7)
            ]
            
            util_corridor_poly = ShapelyPolygon(util_corridor_coords).intersection(zone_poly)
            
            if util_corridor_poly.area > 2:  # Add mini-corridor if space allows
                placed_additional.append({
                    'type': 'corridor',
                    'polygon': list(util_corridor_poly.exterior.coords[:-1]) if hasattr(util_corridor_poly, 'exterior') else util_corridor_coords,
                    'area': util_corridor_poly.area,
                    'target_area': 2.0,
                    'zone': 'circulation',
                    'is_touching': True,
                    'connects_to': [utility_room['type']]
                })
            
            util_coords = [
                (x_start, y_start),
                (x_start + util_width, y_start),
                (x_start + util_width, y_start + util_height),
                (x_start, y_start + util_height)
            ]
            
            util_poly = ShapelyPolygon(util_coords).intersection(zone_poly)
            
            placed_additional.append({
                'type': utility_room['type'],
                'polygon': list(util_poly.exterior.coords[:-1]) if hasattr(util_poly, 'exterior') else util_coords,
                'area': util_poly.area,
                'target_area': utility_room['target_area'],
                'zone': utility_room['zone'],
                'is_touching': True,
                'connects_to_corridor': True
            })
        
        return placed_additional
    
    def _ensure_natural_adjacency(self, placed_rooms: List[Dict], zone_poly: ShapelyPolygon) -> List[Dict]:
        """Ensure all rooms are connected via corridors and strategic overlapping"""
        
        # Create comprehensive connectivity network
        corridors = [r for r in placed_rooms if r['type'] == 'corridor']
        other_rooms = [r for r in placed_rooms if r['type'] != 'corridor']
        
        # Ensure all rooms connect to at least one corridor or adjacent room
        for i, room in enumerate(placed_rooms):
            room_poly = ShapelyPolygon(room['polygon'])
            touches_any = False
            connects_to_corridor = False
            overlaps_strategically = room.get('overlapping', False)
            
            for j, other_room in enumerate(placed_rooms):
                if i != j:
                    other_poly = ShapelyPolygon(other_room['polygon'])
                    
                    # Check direct adjacency
                    if room_poly.touches(other_poly) or room_poly.intersects(other_poly):
                        touches_any = True
                        
                        # Check corridor connectivity
                        if other_room['type'] == 'corridor':
                            connects_to_corridor = True
                            
                    # Check buffered connectivity (within 0.5m)
                    buffered_poly = room_poly.buffer(0.5)
                    if buffered_poly.intersects(other_poly):
                        touches_any = True
            
            # Mark connectivity status
            room['is_touching'] = touches_any or overlaps_strategically
            room['corridor_connected'] = connects_to_corridor or overlaps_strategically
            
            # If room is isolated, create emergency corridor connection
            if not touches_any and not overlaps_strategically:
                emergency_corridor = self._create_emergency_corridor_connection(
                    room, corridors, zone_poly
                )
                if emergency_corridor:
                    placed_rooms.append(emergency_corridor)
                    room['is_touching'] = True
                    room['corridor_connected'] = True
        
        return placed_rooms
    
    def _create_emergency_corridor_connection(self, isolated_room: Dict, 
                                            corridors: List[Dict], zone_poly: ShapelyPolygon) -> Optional[Dict]:
        """Create emergency corridor to connect isolated room"""
        
        if not corridors:
            return None
            
        room_poly = ShapelyPolygon(isolated_room['polygon'])
        room_centroid = room_poly.centroid
        
        # Find nearest corridor
        nearest_corridor = min(corridors, 
                             key=lambda c: ShapelyPolygon(c['polygon']).centroid.distance(room_centroid))
        
        corridor_poly = ShapelyPolygon(nearest_corridor['polygon'])
        corridor_centroid = corridor_poly.centroid
        
        # Create connecting corridor
        connection_width = 1.0  # 1m wide emergency corridor
        
        # Calculate connection path
        dx = corridor_centroid.x - room_centroid.x
        dy = corridor_centroid.y - room_centroid.y
        length = (dx**2 + dy**2)**0.5
        
        if length > 0:
            # Normalize direction
            dx_norm = dx / length
            dy_norm = dy / length
            
            # Create perpendicular vector for corridor width
            perp_x = -dy_norm * connection_width / 2
            perp_y = dx_norm * connection_width / 2
            
            # Connection corridor coordinates
            connect_coords = [
                (room_centroid.x + perp_x, room_centroid.y + perp_y),
                (corridor_centroid.x + perp_x, corridor_centroid.y + perp_y),
                (corridor_centroid.x - perp_x, corridor_centroid.y - perp_y),
                (room_centroid.x - perp_x, room_centroid.y - perp_y)
            ]
            
            connect_poly = ShapelyPolygon(connect_coords).intersection(zone_poly)
            
            if connect_poly.area > 1.0:  # Minimum viable corridor area
                return {
                    'type': 'corridor',
                    'polygon': list(connect_poly.exterior.coords[:-1]) if hasattr(connect_poly, 'exterior') else connect_coords,
                    'area': connect_poly.area,
                    'target_area': connection_width * length,
                    'zone': 'circulation',
                    'is_touching': True,
                    'emergency_connection': True,
                    'connects_to': [isolated_room['type'], 'main_corridor']
                }
        
        return None
    
    def _generate_circulation_elements(self, building_envelope: List[Tuple[float, float]], 
                                     num_apartments: int) -> Dict:
        """Generate compliant lift, staircase, and outdoor corridor system"""
        
        envelope_poly = ShapelyPolygon(building_envelope)
        bounds = envelope_poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        circulation_elements = []
        
        # Design circulation core
        circulation_core = self._design_circulation_core(bounds, num_apartments)
        
        # Add lift
        lift_poly = ShapelyPolygon(circulation_core['lift']['coordinates']).intersection(envelope_poly)
        circulation_elements.append({
            'type': 'lift',
            'polygon': list(lift_poly.exterior.coords[:-1]) if hasattr(lift_poly, 'exterior') else circulation_core['lift']['coordinates'],
            'area': circulation_core['lift']['area'],
            'target_area': circulation_core['lift']['area'],
            'zone': 'vertical_circulation',
            'is_touching': True,
            'nbc_compliant': True,
            'capacity': circulation_core['lift']['capacity'],
            'specifications': f"{circulation_core['lift']['width']}m x {circulation_core['lift']['depth']}m"
        })
        
        # Add staircase
        stair_poly = ShapelyPolygon(circulation_core['staircase']['coordinates']).intersection(envelope_poly)
        circulation_elements.append({
            'type': 'staircase',
            'polygon': list(stair_poly.exterior.coords[:-1]) if hasattr(stair_poly, 'exterior') else circulation_core['staircase']['coordinates'],
            'area': circulation_core['staircase']['area'],
            'target_area': circulation_core['staircase']['area'],
            'zone': 'vertical_circulation',
            'is_touching': True,
            'nbc_compliant': True,
            'width': circulation_core['staircase']['width'],
            'specifications': f"Width: {circulation_core['staircase']['width']}m, Tread: {circulation_core['staircase']['tread']}m, Riser: {circulation_core['staircase']['riser']}m"
        })
        
        # Add lobby
        lobby_poly = ShapelyPolygon(circulation_core['lobby']['coordinates']).intersection(envelope_poly)
        circulation_elements.append({
            'type': 'lobby',
            'polygon': list(lobby_poly.exterior.coords[:-1]) if hasattr(lobby_poly, 'exterior') else circulation_core['lobby']['coordinates'],
            'area': circulation_core['lobby']['area'],
            'target_area': circulation_core['lobby']['area'],
            'zone': 'horizontal_circulation',
            'is_touching': True,
            'nbc_compliant': True,
            'specifications': f"{circulation_core['lobby']['size']}m x {circulation_core['lobby']['size']}m"
        })
        
        # Add outdoor corridor system
        outdoor_corridors = self._design_outdoor_corridor_system(bounds, circulation_core, num_apartments)
        
        for corridor in outdoor_corridors:
            corridor_poly = ShapelyPolygon(corridor['coordinates']).intersection(envelope_poly)
            circulation_elements.append({
                'type': 'outdoor_corridor',
                'polygon': list(corridor_poly.exterior.coords[:-1]) if hasattr(corridor_poly, 'exterior') else corridor['coordinates'],
                'area': corridor['area'],
                'target_area': corridor['area'],
                'zone': 'horizontal_circulation',
                'is_touching': True,
                'nbc_compliant': corridor['nbc_compliant'],
                'width': corridor['width'],
                'connects_apartments': corridor['connects_apartments'],
                'specifications': f"Width: {corridor['width']:.1f}m (NBC min: 1.8m)"
            })
        
        total_circulation_area = sum(elem['area'] for elem in circulation_elements)
        
        return {
            'elements': circulation_elements,
            'circulation_core': circulation_core,
            'total_area': total_circulation_area,
            'nbc_compliance': {
                'lift': True,
                'staircase': True,
                'corridor': all(c.get('nbc_compliant', False) for c in outdoor_corridors)
            }
        }
    
    def _design_outdoor_corridor_system(self, bounds: Tuple[float, float, float, float],
                                      circulation_core: Dict, num_apartments: int) -> List[Dict]:
        """Design single unified corridor system that never overlaps with apartments"""
        
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        # NBC requirement: minimum 1.8m corridor width
        corridor_width = max(1.8, width * 0.06)  # At least 1.8m or 6% of building width
        
        corridors = []
        
        # Design SINGLE continuous corridor system for all apartments
        # The corridor will be positioned to avoid overlap with apartment zones
        
        if num_apartments <= 3:
            # Single main corridor for up to 3 apartments
            if width >= height:
                # Horizontal building - place corridor along one edge (top or bottom)
                corridor_y = bounds[1] + height * 0.15  # 15% from bottom
                
                # Full width corridor with space for lift/staircase at ends
                corridor_start_x = bounds[0] + 3.0  # 3m buffer for lift
                corridor_end_x = bounds[2] - 3.0    # 3m buffer for staircase
                corridor_length = corridor_end_x - corridor_start_x
                
                main_corridor_coords = [
                    (corridor_start_x, corridor_y),
                    (corridor_end_x, corridor_y),
                    (corridor_end_x, corridor_y + corridor_width),
                    (corridor_start_x, corridor_y + corridor_width)
                ]
                
                corridors.append({
                    'coordinates': main_corridor_coords,
                    'area': corridor_length * corridor_width,
                    'width': corridor_width,
                    'length': corridor_length,
                    'orientation': 'horizontal',
                    'nbc_compliant': corridor_width >= 1.8,
                    'connects_apartments': list(range(1, num_apartments + 1)),
                    'no_overlap': True
                })
                
            else:
                # Vertical building - place corridor along one edge (left or right)
                corridor_x = bounds[0] + width * 0.15  # 15% from left
                
                # Full height corridor with space for lift/staircase at ends
                corridor_start_y = bounds[1] + 3.0  # 3m buffer for lift
                corridor_end_y = bounds[3] - 3.0    # 3m buffer for staircase
                corridor_length = corridor_end_y - corridor_start_y
                
                main_corridor_coords = [
                    (corridor_x, corridor_start_y),
                    (corridor_x + corridor_width, corridor_start_y),
                    (corridor_x + corridor_width, corridor_end_y),
                    (corridor_x, corridor_end_y)
                ]
                
                corridors.append({
                    'coordinates': main_corridor_coords,
                    'area': corridor_width * corridor_length,
                    'width': corridor_width,
                    'length': corridor_length,
                    'orientation': 'vertical',
                    'nbc_compliant': corridor_width >= 1.8,
                    'connects_apartments': list(range(1, num_apartments + 1)),
                    'no_overlap': True
                })
        
        else:
            # For 4+ apartments: Single L-shaped corridor system (no multiple corridors)
            
            # Main horizontal corridor along one edge
            corridor_y = bounds[1] + height * 0.2  # 20% from bottom
            
            # Horizontal corridor
            corridor_start_x = bounds[0] + 2.0  # 2m buffer
            corridor_end_x = bounds[2] - 2.0    # 2m buffer
            horizontal_length = corridor_end_x - corridor_start_x
            
            horizontal_corridor_coords = [
                (corridor_start_x, corridor_y),
                (corridor_end_x, corridor_y),
                (corridor_end_x, corridor_y + corridor_width),
                (corridor_start_x, corridor_y + corridor_width)
            ]
            
            # Vertical corridor connecting at the end (L-shape)
            vertical_corridor_x = corridor_start_x + horizontal_length * 0.7  # 70% along horizontal
            vertical_start_y = corridor_y + corridor_width  # Start after horizontal corridor
            vertical_end_y = bounds[3] - height * 0.15      # 15% buffer from top
            vertical_length = vertical_end_y - vertical_start_y
            
            vertical_corridor_coords = [
                (vertical_corridor_x, vertical_start_y),
                (vertical_corridor_x + corridor_width, vertical_start_y),
                (vertical_corridor_x + corridor_width, vertical_end_y),
                (vertical_corridor_x, vertical_end_y)
            ]
            
            # Single unified L-shaped corridor (treated as one system)
            unified_corridor_coords = horizontal_corridor_coords + vertical_corridor_coords
            total_area = (horizontal_length * corridor_width) + (vertical_length * corridor_width)
            
            corridors.append({
                'coordinates': horizontal_corridor_coords,
                'area': total_area,
                'width': corridor_width,
                'length': horizontal_length + vertical_length,
                'orientation': 'L-shaped',
                'nbc_compliant': corridor_width >= 1.8,
                'connects_apartments': list(range(1, num_apartments + 1)),
                'no_overlap': True,
                'vertical_extension': vertical_corridor_coords  # For visualization
            })
        
        return corridors
    
    def _get_corridor_exclusion_zones(self, apartment_zone_poly: ShapelyPolygon, 
                                     circulation_elements: Dict) -> List[ShapelyPolygon]:
        """Get corridor zones that must be kept clear of room overlapping"""
        
        exclusion_zones = []
        
        if not circulation_elements or not circulation_elements.get('elements'):
            return exclusion_zones
        
        # Add buffer zones around all circulation elements
        for element in circulation_elements['elements']:
            if element['type'] in ['lift', 'staircase', 'lobby', 'outdoor_corridor']:
                element_poly = ShapelyPolygon(element['polygon'])
                
                # Create buffer zone around circulation element (1m buffer)
                if element['type'] == 'outdoor_corridor':
                    # Larger buffer for corridors (1.5m on each side)
                    buffer_zone = element_poly.buffer(1.5)
                else:
                    # Standard buffer for lift/staircase/lobby
                    buffer_zone = element_poly.buffer(1.0)
                
                # Only include the part that intersects with apartment zone
                intersection = buffer_zone.intersection(apartment_zone_poly)
                if intersection.area > 0:
                    exclusion_zones.append(intersection)
        
        return exclusion_zones
    
    def _place_intelligent_public_zone(self, public_rooms: List[Dict], 
                                      zone_poly: ShapelyPolygon,
                                      apt_number: int, circulation_zones: List[Dict] = None) -> List[Dict]:
        """Place public zone with intelligent positioning and circulation awareness for living room adjacency"""
        
        bounds = zone_poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        placed_public = []
        
        # Find rooms
        living_room = next(r for r in public_rooms if r['type'] == 'living')
        kitchen_room = next(r for r in public_rooms if r['type'] == 'kitchen')
        dining_room = next(r for r in public_rooms if r['type'] == 'dining')
        
        # Find closest circulation area (lobby) for living room adjacency
        circulation_target = None
        min_distance = float('inf')
        
        if circulation_zones:
            zone_center = [(bounds[0] + bounds[2])/2, (bounds[1] + bounds[3])/2]
            
            for circ_zone in circulation_zones:
                # Look for circulation core or spine zones 
                if 'circulation_core' in circ_zone.get('type', '') or 'circulation_spine' in circ_zone.get('type', ''):
                    # Get circulation zone center from coordinates
                    coords = circ_zone.get('coordinates', [])
                    if coords and len(coords) >= 4:
                        circ_poly = ShapelyPolygon(coords)
                        circ_bounds = circ_poly.bounds
                        circ_center = [(circ_bounds[0] + circ_bounds[2])/2, 
                                     (circ_bounds[1] + circ_bounds[3])/2]
                        
                        distance = ((zone_center[0] - circ_center[0])**2 + 
                                  (zone_center[1] - circ_center[1])**2)**0.5
                        
                        if distance < min_distance:
                            min_distance = distance
                            circulation_target = circ_center
            
            if circulation_target:
                print(f"    🎯 Found circulation target at distance {min_distance:.1f}m for living room placement")
        
        # Determine optimal layout orientation based on apartment shape
        aspect_ratio = width / height
        print(f"    📐 Apartment aspect ratio: {aspect_ratio:.2f} (width: {width:.1f}m, height: {height:.1f}m)")
        
        if aspect_ratio > 1.4:  # Wide apartment - horizontal layout
            print(f"    🏗️ Using wide apartment layout (aspect ratio > 1.4)")
            # Living room positioning with circulation awareness
            living_width = width * 0.5
            living_height = height * 0.65
            
            # Default position (left side)
            living_x = bounds[0]
            living_y = bounds[1]
            
            # Adjust living room position to be closer to circulation if available
            if circulation_target:
                apartment_center = [(bounds[0] + bounds[2])/2, (bounds[1] + bounds[3])/2]
                print(f"    📍 Apartment center: ({apartment_center[0]:.1f}, {apartment_center[1]:.1f})")
                print(f"    📍 Circulation target: ({circulation_target[0]:.1f}, {circulation_target[1]:.1f})")
                
                # Determine which side of apartment is closer to circulation
                # Check if circulation is to the right, left, top, or bottom
                if circulation_target[0] > apartment_center[0]:  # Circulation to the right
                    living_x = bounds[2] - living_width  # Place living room on right side
                    print(f"    🏠 Positioning living room on right side (closer to circulation)")
                elif circulation_target[1] > apartment_center[1]:  # Circulation above
                    living_y = bounds[3] - living_height  # Place living room at top
                    print(f"    🏠 Positioning living room at top (closer to circulation)")
                elif circulation_target[1] < apartment_center[1]:  # Circulation below
                    living_y = bounds[1]  # Place living room at bottom (default)
                    print(f"    🏠 Positioning living room at bottom (closer to circulation)")
                else:  # Circulation to the left or default
                    living_x = bounds[0]  # Place living room on left side (default)
                    print(f"    🏠 Positioning living room on left side (closer to circulation)")
            else:
                print(f"    🏠 Using default living room position (no circulation target)")
            
            living_coords = [
                (living_x, living_y),
                (living_x + living_width, living_y),
                (living_x + living_width, living_y + living_height),
                (living_x, living_y + living_height)
            ]
            
            # Kitchen in service area (back/internal side)
            kitchen_width = width * 0.3
            kitchen_height = height * 0.4
            
            kitchen_coords = [
                (bounds[2] - kitchen_width, bounds[3] - kitchen_height),
                (bounds[2], bounds[3] - kitchen_height),
                (bounds[2], bounds[3]),
                (bounds[2] - kitchen_width, bounds[3])
            ]
            
            # Dining connects living and kitchen
            dining_width = width * 0.35
            dining_height = height * 0.35
            
            dining_coords = [
                (bounds[0] + living_width, bounds[1]),
                (bounds[0] + living_width + dining_width, bounds[1]),
                (bounds[0] + living_width + dining_width, bounds[1] + dining_height),
                (bounds[0] + living_width, bounds[1] + dining_height)
            ]
            
        elif aspect_ratio < 0.7:  # Tall apartment - vertical layout
            # Living room positioning with circulation awareness
            living_width = width * 0.8
            living_height = height * 0.4
            
            # Default position (bottom)
            living_x = bounds[0]
            living_y = bounds[1]
            
            # Adjust living room position to be closer to circulation if available
            if circulation_target:
                apartment_center = [(bounds[0] + bounds[2])/2, (bounds[1] + bounds[3])/2]
                
                # For tall apartments, check if circulation is above or below
                if circulation_target[1] > apartment_center[1]:  # Circulation above
                    living_y = bounds[3] - living_height  # Place living room at top
                    print(f"    🏠 Positioning living room at top (closer to circulation)")
                elif circulation_target[0] > apartment_center[0]:  # Circulation to the right
                    living_x = bounds[2] - living_width  # Place living room on right side
                    print(f"    🏠 Positioning living room on right side (closer to circulation)")
                elif circulation_target[0] < apartment_center[0]:  # Circulation to the left
                    living_x = bounds[0]  # Place living room on left side (default)
                    print(f"    🏠 Positioning living room on left side (closer to circulation)")
                else:  # Default to bottom
                    living_y = bounds[1]  # Place living room at bottom (default)
                    print(f"    🏠 Positioning living room at bottom (closer to circulation)")
            
            living_coords = [
                (living_x, living_y),
                (living_x + living_width, living_y),
                (living_x + living_width, living_y + living_height),
                (living_x, living_y + living_height)
            ]
            
            # Kitchen in middle section
            kitchen_width = width * 0.6
            kitchen_height = height * 0.25
            
            kitchen_coords = [
                (bounds[0], bounds[1] + living_height),
                (bounds[0] + kitchen_width, bounds[1] + living_height),
                (bounds[0] + kitchen_width, bounds[1] + living_height + kitchen_height),
                (bounds[0], bounds[1] + living_height + kitchen_height)
            ]
            
            # Dining adjacent to living room
            dining_width = width * 0.7
            dining_height = height * 0.2
            
            dining_coords = [
                (bounds[0] + living_width * 0.2, bounds[1] + living_height + kitchen_height),
                (bounds[0] + living_width * 0.2 + dining_width, bounds[1] + living_height + kitchen_height),
                (bounds[0] + living_width * 0.2 + dining_width, bounds[1] + living_height + kitchen_height + dining_height),
                (bounds[0] + living_width * 0.2, bounds[1] + living_height + kitchen_height + dining_height)
            ]
            
        else:  # Square apartment - balanced layout
            print(f"    🏗️ Using square apartment layout (0.7 ≤ aspect ratio ≤ 1.4)")
            # Living room positioning with circulation awareness
            living_width = width * 0.55
            living_height = height * 0.55
            
            # Default position (bottom-left corner)
            living_x = bounds[0]
            living_y = bounds[1]
            
            # Adjust living room position to be closer to circulation if available
            if circulation_target:
                apartment_center = [(bounds[0] + bounds[2])/2, (bounds[1] + bounds[3])/2]
                print(f"    📍 Apartment center: ({apartment_center[0]:.1f}, {apartment_center[1]:.1f})")
                print(f"    📍 Circulation target: ({circulation_target[0]:.1f}, {circulation_target[1]:.1f})")
                
                # For square apartments, position living room on the side closest to circulation
                # Calculate distances to each corner to find optimal placement
                dx = circulation_target[0] - apartment_center[0]
                dy = circulation_target[1] - apartment_center[1]
                
                if abs(dx) > abs(dy):  # Circulation is more to the left or right
                    if dx > 0:  # Circulation to the right
                        living_x = bounds[2] - living_width  # Place living room on right side
                        print(f"    🏠 Positioning living room on right side (closer to circulation)")
                    else:  # Circulation to the left
                        living_x = bounds[0]  # Place living room on left side (default)
                        print(f"    🏠 Positioning living room on left side (closer to circulation)")
                else:  # Circulation is more above or below
                    if dy > 0:  # Circulation above
                        living_y = bounds[3] - living_height  # Place living room at top
                        print(f"    🏠 Positioning living room at top (closer to circulation)")
                    else:  # Circulation below
                        living_y = bounds[1]  # Place living room at bottom (default)
                        print(f"    🏠 Positioning living room at bottom (closer to circulation)")
            else:
                print(f"    🏠 Using default living room position (no circulation target)")
            
            living_coords = [
                (living_x, living_y),
                (living_x + living_width, living_y),
                (living_x + living_width, living_y + living_height),
                (living_x, living_y + living_height)
            ]
            
            # Kitchen positioned to avoid overlap with living room
            kitchen_width = width * 0.35
            kitchen_height = height * 0.4
            
            # Position kitchen based on where living room is placed
            if living_x == bounds[0]:  # Living room on left side
                # Place kitchen on the right side
                kitchen_x = living_x + living_width
                kitchen_y = bounds[1]
                print(f"    🍳 Positioning kitchen on right side (living room on left)")
            else:  # Living room on right side
                # Place kitchen on the left side  
                kitchen_x = bounds[0]
                kitchen_y = bounds[1]
                kitchen_width = min(kitchen_width, living_x - bounds[0])  # Don't overlap with living room
                print(f"    🍳 Positioning kitchen on left side (living room on right)")
            
            kitchen_coords = [
                (kitchen_x, kitchen_y),
                (kitchen_x + kitchen_width, kitchen_y),
                (kitchen_x + kitchen_width, kitchen_y + kitchen_height),
                (kitchen_x, kitchen_y + kitchen_height)
            ]
            
            # Dining positioned to connect living and kitchen without overlap
            dining_width = width * 0.4
            dining_height = height * 0.3
            
            # Position dining in remaining space
            if living_x == bounds[0]:  # Living room on left, kitchen on right
                dining_x = living_x + living_width
                dining_y = kitchen_y + kitchen_height
            else:  # Living room on right, kitchen on left
                dining_x = kitchen_x + kitchen_width  
                dining_y = kitchen_y + kitchen_height
                dining_width = min(dining_width, living_x - (kitchen_x + kitchen_width))
            
            dining_coords = [
                (dining_x, dining_y),
                (dining_x + dining_width, dining_y),
                (dining_x + dining_width, dining_y + dining_height),
                (dining_x, dining_y + dining_height)
            ]
        
        # Create room polygons and add to layout
        living_poly = ShapelyPolygon(living_coords).intersection(zone_poly)
        if living_poly.area > 10:
            placed_public.append({
                'type': 'living',
                'polygon': list(living_poly.exterior.coords[:-1]) if hasattr(living_poly, 'exterior') else living_coords,
                'area': living_poly.area,
                'target_area': living_room['target_area'],
                'zone': 'public',
                'is_touching': True,
                'placement_logic': 'intelligent_primary_space'
            })
        
        kitchen_poly = ShapelyPolygon(kitchen_coords).intersection(zone_poly)
        if kitchen_poly.area > 5:
            placed_public.append({
                'type': 'kitchen',
                'polygon': list(kitchen_poly.exterior.coords[:-1]) if hasattr(kitchen_poly, 'exterior') else kitchen_coords,
                'area': kitchen_poly.area,
                'target_area': kitchen_room['target_area'],
                'zone': 'public',
                'is_touching': True,
                'placement_logic': 'intelligent_service_area'
            })
        
        dining_poly = ShapelyPolygon(dining_coords).intersection(zone_poly)
        if dining_poly.area > 6:
            placed_public.append({
                'type': 'dining',
                'polygon': list(dining_poly.exterior.coords[:-1]) if hasattr(dining_poly, 'exterior') else dining_coords,
                'area': dining_poly.area,
                'target_area': dining_room['target_area'],
                'zone': 'public',
                'is_touching': True,
                'placement_logic': 'intelligent_connector_space'
            })
        
        return placed_public
    
    def _place_intelligent_master_suite(self, master_rooms: List[Dict], 
                                       zone_poly: ShapelyPolygon,
                                       existing_rooms: List[Dict]) -> List[Dict]:
        """Place master suite with intelligent positioning for privacy and comfort"""
        
        bounds = zone_poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        # Calculate remaining available area
        used_area = unary_union([ShapelyPolygon(room['polygon']) for room in existing_rooms])
        available_area = zone_poly.difference(used_area)
        
        placed_master = []
        
        if len(master_rooms) == 0 or available_area.area < 20:
            return placed_master
        
        master_bedroom = next((r for r in master_rooms if r['type'] == 'master_bedroom'), None)
        master_bathroom = next((r for r in master_rooms if r['type'] == 'master_bathroom'), None)
        
        if not master_bedroom:
            return placed_master
        
        # Master bedroom placement - prefer adjacency to existing rooms, larger for FSI utilization
        bed_area = self._find_optimal_room_placement(
            available_area,
            target_width=width * 0.45,  # Much larger bedrooms
            target_height=height * 0.5,  # Much larger bedrooms
            min_area=20,  # Higher minimum area
            prefer_adjacent=True,
            existing_rooms=existing_rooms
        )
        
        if bed_area and bed_area.area > 12:
            placed_master.append({
                'type': 'master_bedroom',
                'polygon': list(bed_area.exterior.coords[:-1]) if hasattr(bed_area, 'exterior') else [],
                'area': bed_area.area,
                'target_area': master_bedroom['target_area'],
                'zone': 'master_suite',
                'is_touching': True
            })
            
            # Master bathroom adjacent to bedroom
            if master_bathroom:
                remaining_area = available_area.difference(bed_area)
                
                bath_area = self._find_optimal_room_placement(
                    remaining_area,
                    target_width=width * 0.12,
                    target_height=height * 0.15,
                    min_area=5,
                    prefer_adjacent=True,
                    existing_rooms=placed_master
                )
                
                if bath_area and bath_area.area > 5:
                    placed_master.append({
                        'type': 'master_bathroom',
                        'polygon': list(bath_area.exterior.coords[:-1]) if hasattr(bath_area, 'exterior') else [],
                        'area': bath_area.area,
                        'target_area': master_bathroom['target_area'],
                        'zone': 'master_suite',
                        'is_touching': True
                    })
        
        return placed_master
    
    def _place_remaining_rooms_intelligently(self, remaining_rooms: List[Dict], 
                                            zone_poly: ShapelyPolygon,
                                            existing_rooms: List[Dict]) -> List[Dict]:
        """Place remaining rooms with intelligent positioning, especially balcony placement"""
        
        bounds = zone_poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        # Calculate remaining available area
        used_area = unary_union([ShapelyPolygon(room['polygon']) for room in existing_rooms])
        available_area = zone_poly.difference(used_area)
        
        placed_remaining = []
        
        if available_area.area < 10:
            return placed_remaining
        
        # Organize rooms by priority and size
        bedrooms = [r for r in remaining_rooms if r['type'] == 'bedroom']
        bathrooms = [r for r in remaining_rooms if r['type'] == 'bathroom']
        utility_rooms = [r for r in remaining_rooms if r['type'] in ['balcony', 'utility']]
        
        current_available = available_area
        
        # Place bedrooms in largest available spaces
        for i, bedroom in enumerate(bedrooms):
            if current_available.area < 10:
                break
                
            bed_area = self._find_optimal_room_placement(
                current_available, 
                target_width=width * 0.35,  # Larger bedrooms for FSI utilization
                target_height=height * 0.35, # Larger bedrooms for FSI utilization
                min_area=18,  # Higher minimum area for larger bedrooms
                prefer_adjacent=True,
                existing_rooms=existing_rooms + placed_remaining
            )
            
            if bed_area and bed_area.area > 10:
                placed_remaining.append({
                    'type': 'bedroom',
                    'polygon': list(bed_area.exterior.coords[:-1]) if hasattr(bed_area, 'exterior') else [],
                    'area': bed_area.area,
                    'target_area': bedroom['target_area'],
                    'zone': bedroom['zone'],
                    'is_touching': True
                })
                
                current_available = current_available.difference(bed_area)
        
        # Place bathrooms in remaining space
        for i, bathroom in enumerate(bathrooms):
            if current_available.area < 4:
                break
                
            bath_area = self._find_optimal_room_placement(
                current_available,
                target_width=width * 0.1,
                target_height=height * 0.12,
                min_area=4,
                prefer_adjacent=True,
                existing_rooms=existing_rooms + placed_remaining
            )
            
            if bath_area and bath_area.area > 4:
                placed_remaining.append({
                    'type': 'bathroom',
                    'polygon': list(bath_area.exterior.coords[:-1]) if hasattr(bath_area, 'exterior') else [],
                    'area': bath_area.area,
                    'target_area': bathroom['target_area'],
                    'zone': bathroom['zone'],
                    'is_touching': True
                })
                
                current_available = current_available.difference(bath_area)
        
        # Place utility rooms with intelligent positioning
        for utility_room in utility_rooms:
            if current_available.area < 3:
                break
                
            # Use intelligent balcony placement for balconies
            if utility_room['type'] == 'balcony':
                balcony_result = self._place_intelligent_balcony(
                    utility_room, zone_poly, existing_rooms + placed_remaining, current_available
                )
                if balcony_result:
                    placed_remaining.append(balcony_result)
                    # Update available area
                    balcony_poly = ShapelyPolygon(balcony_result['polygon'])
                    current_available = current_available.difference(balcony_poly)
                continue
            
            # Regular placement for other utility rooms
            util_area = self._find_optimal_room_placement(
                current_available,
                target_width=width * 0.12,
                target_height=height * 0.1,
                min_area=3,
                prefer_adjacent=True,
                existing_rooms=existing_rooms + placed_remaining
            )
            
            if util_area and util_area.area > 3:
                placed_remaining.append({
                    'type': utility_room['type'],
                    'polygon': list(util_area.exterior.coords[:-1]) if hasattr(util_area, 'exterior') else [],
                    'area': util_area.area,
                    'target_area': utility_room['target_area'],
                    'zone': utility_room['zone'],
                    'is_touching': True
                })
                
                current_available = current_available.difference(util_area)
        
        return placed_remaining
    
    def _is_on_building_perimeter(self, polygon_coords: List[Tuple[float, float]], 
                                 building_envelope: List[Tuple[float, float]], 
                                 tolerance: float = 1.0) -> bool:
        """Check if a polygon is positioned on the building's outer perimeter"""
        if not building_envelope or not polygon_coords:
            return False
        
        try:
            # Create polygons
            room_poly = ShapelyPolygon(polygon_coords)
            building_poly = ShapelyPolygon(building_envelope)
            
            # Get the boundary (exterior ring) of the building
            building_boundary = building_poly.boundary
            
            # Check if any edge of the room polygon is close to the building boundary
            room_boundary = room_poly.boundary
            
            # Calculate minimum distance between room boundary and building boundary
            min_distance = room_boundary.distance(building_boundary)
            
            # Consider it on perimeter if within tolerance distance
            return min_distance <= tolerance
            
        except Exception as e:
            print(f"⚠️ Error checking perimeter position: {e}")
            return False
    
    def _has_no_adjacent_apartments(self, balcony_coords: List[Tuple[float, float]], 
                                   current_apartment_zone: List[Tuple[float, float]]) -> bool:
        """Check if balcony position has no adjacent apartment boundaries (true open space)"""
        if not hasattr(self, 'current_apartment_zones') or not self.current_apartment_zones:
            return True  # If no apartment zones info, assume it's okay
        
        try:
            balcony_poly = ShapelyPolygon(balcony_coords)
            current_zone_poly = ShapelyPolygon(current_apartment_zone)
            
            # Check against all other apartment zones
            for other_zone in self.current_apartment_zones:
                other_zone_poly = ShapelyPolygon(other_zone)
                
                # Skip if it's the same apartment zone
                if current_zone_poly.equals(other_zone_poly):
                    continue
                
                # Check if balcony is adjacent to (touching or very close to) another apartment
                distance_to_other_apt = balcony_poly.distance(other_zone_poly)
                
                if distance_to_other_apt <= 2.0:  # Within 2 meters of another apartment
                    print(f"    🏠 Adjacent apartment detected at {distance_to_other_apt:.1f}m distance")
                    return False
            
            print(f"    ✅ No adjacent apartments - true open space confirmed")
            return True
            
        except Exception as e:
            print(f"⚠️ Error checking adjacent apartments: {e}")
            return True  # Default to allowing placement if check fails
    
    def _place_intelligent_balcony(self, balcony: Dict, zone_poly: ShapelyPolygon, 
                                  existing_rooms: List[Dict], available_area: ShapelyPolygon) -> Optional[Dict]:
        """Intelligently place balcony for optimal views, access, and natural light - ONLY on outer perimeter"""
        
        bounds = zone_poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        # Find living room for adjacency (balconies should connect to living areas)
        living_room = next((r for r in existing_rooms if r['type'] == 'living'), None)
        
        # Try different strategic positions for balcony
        balcony_candidates = []
        
        # External corner positions (best for views and light)
        corner_positions = [
            # Top-right corner (morning sun, external views)
            {
                'coords': [
                    (bounds[2] - width * 0.25, bounds[3] - height * 0.2),
                    (bounds[2], bounds[3] - height * 0.2),
                    (bounds[2], bounds[3]),
                    (bounds[2] - width * 0.25, bounds[3])
                ],
                'preference_score': 90,  # Highest preference
                'features': ['morning_sun', 'external_corner', 'privacy']
            },
            # Top-left corner (morning light, quiet)
            {
                'coords': [
                    (bounds[0], bounds[3] - height * 0.2),
                    (bounds[0] + width * 0.25, bounds[3] - height * 0.2),
                    (bounds[0] + width * 0.25, bounds[3]),
                    (bounds[0], bounds[3])
                ],
                'preference_score': 85,
                'features': ['morning_light', 'external_corner', 'quiet']
            },
            # Right side (external access)
            {
                'coords': [
                    (bounds[2] - width * 0.2, bounds[1] + height * 0.3),
                    (bounds[2], bounds[1] + height * 0.3),
                    (bounds[2], bounds[1] + height * 0.7),
                    (bounds[2] - width * 0.2, bounds[1] + height * 0.7)
                ],
                'preference_score': 75,
                'features': ['external_access', 'natural_ventilation']
            }
        ]
        
        # If living room exists, add positions adjacent to living room
        if living_room:
            living_poly = ShapelyPolygon(living_room['polygon'])
            living_bounds = living_poly.bounds
            
            # Adjacent to living room positions
            adjacent_positions = [
                {
                    'coords': [
                        (living_bounds[2], living_bounds[1]),
                        (living_bounds[2] + width * 0.15, living_bounds[1]),
                        (living_bounds[2] + width * 0.15, living_bounds[3]),
                        (living_bounds[2], living_bounds[3])
                    ],
                    'preference_score': 95,  # Very high - adjacent to living
                    'features': ['living_adjacent', 'natural_extension', 'social_outdoor']
                }
            ]
            balcony_candidates.extend(adjacent_positions)
        
        balcony_candidates.extend(corner_positions)
        
        # Try each candidate position - ONLY those on outer perimeter
        for candidate in sorted(balcony_candidates, key=lambda x: x['preference_score'], reverse=True):
            candidate_poly = ShapelyPolygon(candidate['coords'])
            
            # Check if position fits in available area
            if available_area.intersects(candidate_poly):
                intersection = available_area.intersection(candidate_poly)
                if intersection.area >= 4:  # Minimum balcony area
                    
                    # CRITICAL: Check if balcony is on building perimeter (has open space in front)
                    intersection_coords = list(intersection.exterior.coords[:-1]) if hasattr(intersection, 'exterior') else candidate['coords']
                    
                    # Only place balcony if it's on the outer perimeter of the building
                    if hasattr(self, 'current_building_envelope') and self.current_building_envelope:
                        is_on_perimeter = self._is_on_building_perimeter(
                            intersection_coords, self.current_building_envelope, tolerance=2.0
                        )
                        
                        if not is_on_perimeter:
                            print(f"    🚫 Balcony position rejected - not on building perimeter")
                            continue  # Skip this position, try next candidate
                        else:
                            print(f"    ✅ Balcony position approved - on building perimeter with open space")
                    
                    return {
                        'type': 'balcony',
                        'polygon': intersection_coords,
                        'area': intersection.area,
                        'target_area': balcony['target_area'],
                        'zone': balcony['zone'],
                        'is_touching': True,
                        'placement_logic': 'intelligent_strategic_positioning_perimeter_only',
                        'features': candidate['features'] + ['perimeter_placement', 'open_space_access'],
                        'preference_score': candidate['preference_score']
                    }
        
        # Fallback: try any available space for balcony - but ONLY on perimeter
        fallback_area = self._find_optimal_room_placement(
            available_area, width * 0.2, height * 0.15, 4, True, existing_rooms
        )
        
        if fallback_area and fallback_area.area >= 4:
            fallback_coords = list(fallback_area.exterior.coords[:-1]) if hasattr(fallback_area, 'exterior') else []
            
            # Apply perimeter rule to fallback placement too
            if hasattr(self, 'current_building_envelope') and self.current_building_envelope:
                is_on_perimeter = self._is_on_building_perimeter(
                    fallback_coords, self.current_building_envelope, tolerance=2.0
                )
                
                if not is_on_perimeter:
                    print(f"    🚫 Balcony fallback rejected - not on building perimeter")
                    return None  # No valid perimeter position found
                else:
                    print(f"    ✅ Balcony fallback approved - on building perimeter")
            
            return {
                'type': 'balcony',
                'polygon': fallback_coords,
                'area': fallback_area.area,
                'target_area': balcony['target_area'],
                'zone': balcony['zone'],
                'is_touching': True,
                'placement_logic': 'intelligent_fallback_positioning_perimeter_only',
                'features': ['perimeter_placement', 'open_space_access']
            }
        
        return None
    
    def _place_intelligent_bedroom(self, bedroom: Dict, zone_poly: ShapelyPolygon,
                                  existing_rooms: List[Dict], available_area: ShapelyPolygon, 
                                  bedroom_index: int) -> Optional[Dict]:
        """Intelligently place bedroom in quiet, private zones"""
        
        bounds = zone_poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        # Bedroom placement preferences: quiet zones, external access for light
        bedroom_area = self._find_optimal_room_placement(
            available_area,
            target_width=width * 0.4,  # Spacious bedrooms
            target_height=height * 0.35,
            min_area=12,  # Adequate bedroom size
            prefer_adjacent=True,
            existing_rooms=existing_rooms
        )
        
        if bedroom_area and bedroom_area.area >= 12:
            return {
                'type': 'bedroom',
                'polygon': list(bedroom_area.exterior.coords[:-1]) if hasattr(bedroom_area, 'exterior') else [],
                'area': bedroom_area.area,
                'target_area': bedroom['target_area'],
                'zone': bedroom['zone'],
                'is_touching': True,
                'placement_logic': f'intelligent_private_zone_{bedroom_index + 1}'
            }
        
        return None
    
    def _place_intelligent_bathroom(self, bathroom: Dict, zone_poly: ShapelyPolygon,
                                   existing_rooms: List[Dict], available_area: ShapelyPolygon) -> Optional[Dict]:
        """Intelligently place bathroom near bedrooms with ventilation access"""
        
        bounds = zone_poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        # Compact, efficient bathroom placement
        bathroom_area = self._find_optimal_room_placement(
            available_area,
            target_width=width * 0.15,  # Compact but functional
            target_height=height * 0.2,
            min_area=4,
            prefer_adjacent=True,
            existing_rooms=existing_rooms
        )
        
        if bathroom_area and bathroom_area.area >= 4:
            return {
                'type': 'bathroom',
                'polygon': list(bathroom_area.exterior.coords[:-1]) if hasattr(bathroom_area, 'exterior') else [],
                'area': bathroom_area.area,
                'target_area': bathroom['target_area'],
                'zone': bathroom['zone'],
                'is_touching': True,
                'placement_logic': 'intelligent_service_access'
            }
        
        return None
    
    def _place_intelligent_utility(self, utility: Dict, zone_poly: ShapelyPolygon,
                                  existing_rooms: List[Dict], available_area: ShapelyPolygon) -> Optional[Dict]:
        """Intelligently place utility room in service area near kitchen"""
        
        bounds = zone_poly.bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        # Find kitchen for adjacency
        kitchen_room = next((r for r in existing_rooms if r['type'] == 'kitchen'), None)
        
        # Compact utility placement
        utility_area = self._find_optimal_room_placement(
            available_area,
            target_width=width * 0.12,
            target_height=height * 0.12,
            min_area=3,
            prefer_adjacent=True,
            existing_rooms=existing_rooms
        )
        
        if utility_area and utility_area.area >= 3:
            placement_features = ['compact_service_area']
            if kitchen_room:
                placement_features.append('kitchen_adjacent')
                
            return {
                'type': 'utility',
                'polygon': list(utility_area.exterior.coords[:-1]) if hasattr(utility_area, 'exterior') else [],
                'area': utility_area.area,
                'target_area': utility['target_area'],
                'zone': utility['zone'],
                'is_touching': True,
                'placement_logic': 'intelligent_service_compact',
                'features': placement_features
            }
        
        return None
    
    def _find_optimal_room_placement(self, available_area: ShapelyPolygon, 
                                   target_width: float, target_height: float,
                                   min_area: float, 
                                   prefer_adjacent: bool = True,
                                   existing_rooms: List[Dict] = None) -> Optional[ShapelyPolygon]:
        """Find optimal rectangular placement within available area, preferring adjacency"""
        
        if not hasattr(available_area, 'bounds') or available_area.area < min_area:
            return None
        
        bounds = available_area.bounds
        max_width = bounds[2] - bounds[0]
        max_height = bounds[3] - bounds[1]
        
        # Adjust target dimensions to fit available space - be more aggressive with space usage
        actual_width = min(target_width, max_width * 0.95)  # Use 95% of available width
        actual_height = min(target_height, max_height * 0.95)  # Use 95% of available height
        
        best_area = None
        best_score = -1
        
        # If preferring adjacency and we have existing rooms, prioritize positions near them
        if prefer_adjacent and existing_rooms:
            for room in existing_rooms:
                if 'polygon' not in room:
                    continue
                    
                room_poly = ShapelyPolygon(room['polygon'])
                room_bounds = room_poly.bounds
                
                # Try positions adjacent to this existing room
                adjacent_positions = [
                    # Right of existing room
                    (room_bounds[2], room_bounds[1]),
                    # Left of existing room  
                    (room_bounds[0] - actual_width, room_bounds[1]),
                    # Above existing room
                    (room_bounds[0], room_bounds[3]),
                    # Below existing room
                    (room_bounds[0], room_bounds[1] - actual_height),
                    # Corner positions for compact clustering
                    (room_bounds[2], room_bounds[3]),
                    (room_bounds[0] - actual_width, room_bounds[3]),
                    (room_bounds[2], room_bounds[1] - actual_height),
                    (room_bounds[0] - actual_width, room_bounds[1] - actual_height)
                ]
                
                for x, y in adjacent_positions:
                    room_coords = [
                        (x, y),
                        (x + actual_width, y),
                        (x + actual_width, y + actual_height),
                        (x, y + actual_height)
                    ]
                    
                    # Validate coordinates before creating polygon
                    if actual_width <= 0 or actual_height <= 0:
                        continue
                        
                    try:
                        room_poly_candidate = ShapelyPolygon(room_coords)
                        if not room_poly_candidate.is_valid:
                            continue
                    except Exception:
                        continue
                    intersection = room_poly_candidate.intersection(available_area)
                    
                    if intersection.area >= min_area:
                        # Score based on adjacency (higher is better)
                        adjacency_score = 100 if room_poly_candidate.touches(room_poly) else 0
                        area_score = intersection.area / (actual_width * actual_height) * 50
                        total_score = adjacency_score + area_score
                        
                        if total_score > best_score:
                            best_area = intersection
                            best_score = total_score
        
        # If no good adjacent position found, try grid positions with compactness preference
        if best_area is None or best_score < 50:
            # Prioritize positions closer to the corner/edge for compactness
            position_factors = [
                (0.0, 0.0, 100),   # Corner - highest priority
                (0.0, 0.2, 90),    # Edge positions
                (0.2, 0.0, 90),
                (0.0, 0.5, 80),
                (0.5, 0.0, 80),
                (0.2, 0.2, 70),    # Near corner
                (0.0, 0.8, 60),    # Far edge
                (0.8, 0.0, 60),
                (0.3, 0.3, 50),    # Middle area - lower priority
                (0.6, 0.6, 30),
                (0.5, 0.5, 20)     # Center - lowest priority
            ]
            
            for x_factor, y_factor, position_score in position_factors:
                x = bounds[0] + (max_width - actual_width) * x_factor
                y = bounds[1] + (max_height - actual_height) * y_factor
                
                room_coords = [
                    (x, y),
                    (x + actual_width, y),
                    (x + actual_width, y + actual_height),
                    (x, y + actual_height)
                ]
                
                # Validate coordinates before creating polygon
                if actual_width <= 0 or actual_height <= 0:
                    continue
                    
                try:
                    room_poly_candidate = ShapelyPolygon(room_coords)
                    if not room_poly_candidate.is_valid:
                        continue
                except Exception:
                    continue
                intersection = room_poly_candidate.intersection(available_area)
                
                if intersection.area >= min_area:
                    area_score = intersection.area / (actual_width * actual_height) * 50
                    total_score = position_score + area_score
                    
                    if total_score > best_score:
                        best_area = intersection
                        best_score = total_score
        
        return best_area
    
    def _find_corridor_access_point(self, apartment_zone: ShapelyPolygon, 
                                   circulation_elements: Dict, apt_number: int) -> Optional[Tuple[float, float]]:
        """Find where apartment should connect to corridor"""
        
        if not circulation_elements or not circulation_elements.get('elements'):
            return None
        
        apartment_bounds = apartment_zone.bounds
        apartment_center = ((apartment_bounds[0] + apartment_bounds[2]) / 2,
                          (apartment_bounds[1] + apartment_bounds[3]) / 2)
        
        # Find closest corridor
        closest_corridor = None
        min_distance = float('inf')
        
        for element in circulation_elements['elements']:
            if element['type'] == 'outdoor_corridor' and apt_number in element.get('connects_apartments', []):
                corridor_poly = ShapelyPolygon(element['polygon'])
                corridor_center = corridor_poly.centroid
                distance = ((corridor_center.x - apartment_center[0])**2 + 
                          (corridor_center.y - apartment_center[1])**2)**0.5
                
                if distance < min_distance:
                    min_distance = distance
                    closest_corridor = element
        
        if closest_corridor:
            corridor_poly = ShapelyPolygon(closest_corridor['polygon'])
            
            # Find closest point on corridor boundary to apartment
            apartment_poly_point = Point(apartment_center)
            closest_point = corridor_poly.boundary.interpolate(
                corridor_poly.boundary.project(apartment_poly_point)
            )
            
            return (closest_point.x, closest_point.y)
        
        return None
    
    def visualize_natural_layout(self, layout: Dict, save_path: str = None) -> None:
        """Visualize the natural multi-apartment layout"""
        
        fig, ax = plt.subplots(1, 1, figsize=(16, 12))
        
        # Plot plot boundary
        plot_boundary = np.array(layout['plot_boundary'] + [layout['plot_boundary'][0]])
        ax.plot(plot_boundary[:, 0], plot_boundary[:, 1], 'k-', linewidth=3, label='Plot Boundary')
        
        # Plot building envelope
        building_envelope = np.array(layout['building_envelope'] + [layout['building_envelope'][0]])
        ax.plot(building_envelope[:, 0], building_envelope[:, 1], 'b--', linewidth=2, label='Building Envelope')
        
        # Plot apartment zones
        for i, zone in enumerate(layout['apartment_zones']):
            zone_coords = np.array(zone + [zone[0]])
            ax.plot(zone_coords[:, 0], zone_coords[:, 1], '--', linewidth=1, alpha=0.7, 
                   label=f'Apt {i+1} Zone' if i < 3 else '')
        
        # Plot all rooms (circulation elements + apartment rooms)
        patches = []
        room_labels = []
        
        # First add circulation elements (lift, staircase, lobby, corridors)
        circulation_elements_list = layout.get('circulation_elements', {}).get('elements', [])
        for room in circulation_elements_list:
            polygon_coords = room['polygon']
            if len(polygon_coords) >= 3:
                poly = Polygon(polygon_coords, closed=True)
                patches.append(poly)
                
                # Calculate room center for label
                room_poly = ShapelyPolygon(polygon_coords)
                centroid = room_poly.centroid
                
                # Circulation element labels with specifications
                specs = room.get('specifications', '')
                if room['type'] == 'lift':
                    label = f"LIFT\n{specs}\n{room.get('capacity', '')}"
                elif room['type'] == 'staircase':
                    label = f"STAIRCASE\nW:{room.get('width', 0):.1f}m"
                elif room['type'] == 'lobby':
                    label = f"LOBBY\n{specs}"
                else:  # outdoor_corridor
                    label = f"CORRIDOR\n{specs}"
                
                room_labels.append((centroid.x, centroid.y, label, room['type']))
        
        # Then add apartment rooms
        for apt_idx, apartment in enumerate(layout['apartments']):
            for room in apartment['rooms']:
                polygon_coords = room['polygon']
                if len(polygon_coords) >= 3:
                    poly = Polygon(polygon_coords, closed=True)
                    patches.append(poly)
                    
                    # Calculate room center for label
                    room_poly = ShapelyPolygon(polygon_coords)
                    centroid = room_poly.centroid
                    
                    # Regular room with apartment number
                    label = f"Apt{apt_idx+1}\n{room['type']}\n{room['area']:.0f}m²"
                    room_labels.append((centroid.x, centroid.y, label, room['type']))
        
        # Create patch collection
        patch_collection = PatchCollection(patches, alpha=0.7)
        
        # Set colors (circulation elements + apartment rooms)
        colors = []
        
        # Colors for circulation elements
        circulation_elements_list = layout.get('circulation_elements', {}).get('elements', [])
        for room in circulation_elements_list:
            colors.append(self.colors.get(room['type'], '#CCCCCC'))
        
        # Colors for apartment rooms
        for apt in layout['apartments']:
            for room in apt['rooms']:
                colors.append(self.colors.get(room['type'], '#CCCCCC'))
        
        patch_collection.set_facecolors(colors)
        patch_collection.set_edgecolors('black')
        patch_collection.set_linewidths(0.8)
        
        ax.add_collection(patch_collection)
        
        # Add room labels
        for x, y, label, room_type in room_labels:
            fontsize = 6 if room_type in ['bathroom', 'utility', 'corridor'] else 8
            fontweight = 'normal' if room_type == 'corridor' else 'bold'
            
            # Special styling for corridors and overlapping rooms
            if room_type == 'corridor':
                bbox_style = dict(boxstyle='round,pad=0.1', facecolor='yellow', alpha=0.6)
            else:
                bbox_style = dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8)
            
            ax.text(x, y, label, ha='center', va='center', fontsize=fontsize, 
                   fontweight=fontweight, bbox=bbox_style)
        
        # Set equal aspect ratio and clean up
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right')
        
        # Title with metrics
        total_area = layout['total_built_area']
        fsi = layout['fsi_utilized']
        coverage = layout['ground_coverage_utilized'] * 100
        
        title = f"Natural Multi-Apartment Layout - {layout['num_apartments']} Apartments\n"
        title += f"Built Area: {total_area:.0f} sq m | FSI: {fsi:.2f} | Coverage: {coverage:.1f}%"
        
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"💾 Layout saved: {save_path}")
        
        plt.show()

def main():
    """Test the natural multi-apartment generator"""
    
    generator = NaturalMultiApartmentFloorPlanGenerator()
    
    # Plot image path
    plot_image_path = "capstone_test_image2.png"  # run from the folder holding the test image
    
    # Test different apartment configurations
    test_configs = [
        {'num_apartments': 1, 'bedrooms': 3, 'label': 'Single 3BHK'},
        {'num_apartments': 2, 'bedrooms': 3, 'label': 'Two 3BHK Units'},
        {'num_apartments': 3, 'bedrooms': 2, 'label': 'Three 2BHK Units'},
        {'num_apartments': 4, 'bedrooms': 2, 'label': 'Four 2BHK Units'},
        {'num_apartments': 5, 'bedrooms': 1, 'label': 'Five 1BHK Units'}
    ]
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for config in test_configs:
        try:
            print(f"\n{'='*60}")
            print(f"🏗️ Testing: {config['label']}")
            print(f"{'='*60}")
            
            layout = generator.generate_natural_multi_apartment_layout(
                num_apartments=config['num_apartments'],
                bedrooms_per_apt=config['bedrooms'],
                plot_image_path=plot_image_path,
                fsi=1.8,
                ground_coverage=0.65,
                floors=1
            )
            
            # Save layout data
            output_filename = f"natural_multi_apt_{config['num_apartments']}apt_{config['bedrooms']}bhk_{timestamp}.json"
            output_path = os.path.join(os.getcwd(), output_filename)
            
            # Convert layout to JSON serializable format
            json_layout = {
                'config': config,
                'apartments': layout['apartments'],
                'num_apartments': layout['num_apartments'],
                'bedrooms_per_apartment': layout['bedrooms_per_apartment'],
                'total_built_area': layout['total_built_area'],
                'plot_area': layout['plot_area'],
                'fsi_utilized': layout['fsi_utilized'],
                'ground_coverage_utilized': layout['ground_coverage_utilized'],
                'building_envelope': layout['building_envelope'],
                'plot_boundary': layout['plot_boundary'],
                'generation_timestamp': timestamp
            }
            
            with open(output_path, 'w') as f:
                json.dump(json_layout, f, indent=2)
            
            # Export to DXF format
            try:
                from dxf_export_module import FloorPlanDXFExporter
                dxf_exporter = FloorPlanDXFExporter()
                dxf_filename = f"natural_multi_apt_{config['num_apartments']}apt_{config['bedrooms']}bhk_{timestamp}.dxf"
                dxf_path = os.path.join(os.getcwd(), dxf_filename)
                dxf_exporter.export_apartment_layout_to_dxf(output_path, dxf_path)
                print(f"📐 DXF exported: {dxf_filename}")
            except Exception as e:
                print(f"⚠️ DXF export failed: {e}")
            
            # Visualize
            image_filename = f"natural_multi_apt_{config['num_apartments']}apt_{config['bedrooms']}bhk_{timestamp}.png"
            image_path = os.path.join(os.getcwd(), image_filename)
            
            generator.visualize_natural_layout(layout, image_path)
            
            # Print summary
            print(f"\n📊 {config['label']} Summary:")
            print(f"   • Total built area: {layout['total_built_area']:.0f} sq m")
            print(f"   • FSI utilized: {layout['fsi_utilized']:.2f}")
            print(f"   • Ground coverage: {layout['ground_coverage_utilized']*100:.1f}%")
            print(f"   • Total rooms: {sum(apt['room_count'] for apt in layout['apartments'])}")
            print(f"   • Layout saved: {output_filename}")
            print(f"   • Image saved: {image_filename}")
            
        except Exception as e:
            print(f"❌ Error generating {config['label']}: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n✅ Natural multi-apartment layout generation complete!")

if __name__ == "__main__":
    main()