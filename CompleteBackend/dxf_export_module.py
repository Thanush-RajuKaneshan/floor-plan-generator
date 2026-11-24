#!/usr/bin/env python3
"""
DXF Export Module for Floor Plan Layouts
Converts JSON apartment layout data to AutoCAD DXF format
"""

import json
import os
from typing import Dict, List, Tuple, Optional
import ezdxf
from ezdxf import colors
import math

class FloorPlanDXFExporter:
    def __init__(self):
        """Initialize DXF exporter with predefined layers and colors"""
        
        # Layer definitions with uniform black color throughout
        self.layer_config = {
            'living': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'bedroom': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'master_bedroom': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'kitchen': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'dining': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'bathroom': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'master_bathroom': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'balcony': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'utility': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'corridor': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'central_lobby': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'lift': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'staircase_perimeter': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'doors': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'windows': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'dimensions': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'text': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'boundary': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'},
            'building_envelope': {'color': colors.BLACK, 'linetype': 'CONTINUOUS'}
        }
        
        # Text styles and sizes
        self.text_height = 1.2  # Reduced from 1.5 to prevent overlap
        self.dimension_text_height = 0.8  # Reduced from 1.0 to prevent overlap
        
    def export_apartment_layout_to_dxf(self, json_file_path: str, output_dxf_path: Optional[str] = None) -> str:
        """
        Export apartment layout from JSON to DXF format
        
        Args:
            json_file_path: Path to the JSON layout file
            output_dxf_path: Optional output DXF path (auto-generated if None)
            
        Returns:
            Path to the generated DXF file
        """
        
        print(f"📐 Loading apartment layout from: {json_file_path}")
        
        # Load JSON data
        with open(json_file_path, 'r') as f:
            layout_data = json.load(f)
        
        # Generate output path if not provided
        if output_dxf_path is None:
            base_name = os.path.splitext(os.path.basename(json_file_path))[0]
            output_dxf_path = os.path.join(
                os.path.dirname(json_file_path), 
                f"{base_name}.dxf"
            )
        
        print(f"🏗️ Creating DXF: {output_dxf_path}")
        
        # Create new DXF document
        doc = ezdxf.new('R2010')  # AutoCAD 2010 format for compatibility
        msp = doc.modelspace()
        
        # Setup layers
        self._setup_layers(doc)
        
        boundaries = layout_data.get('boundaries', {})
        if not isinstance(boundaries, dict):
            boundaries = {}

        plot_boundary = layout_data.get('plot_boundary')
        if plot_boundary is None:
            plot_boundary = boundaries.get('plot_boundary')
        building_envelope = layout_data.get('building_envelope')
        if building_envelope is None:
            building_envelope = boundaries.get('building_envelope')

        # Draw boundaries from either a live layout or the saved JSON structure.
        if plot_boundary:
            self._draw_plot_boundary(msp, plot_boundary)
        if building_envelope:
            self._draw_building_envelope(msp, building_envelope)
        
        # Draw apartments
        if 'apartments' in layout_data:
            self._draw_apartments(msp, layout_data['apartments'])
        elif 'all_rooms' in layout_data:
            # Handle single apartment case
            self._draw_single_apartment(msp, layout_data['all_rooms'])
        
        # Draw circulation elements (lobby, lift, staircase)
        if 'circulation_elements' in layout_data:
            self._draw_circulation_elements(msp, layout_data['circulation_elements'])

        review = layout_data.get('architectural_review', {})
        for candidate in review.get('door_candidates', []):
            segment = candidate.get('segment', [])
            if len(segment) == 2:
                msp.add_line(
                    segment[0],
                    segment[1],
                    dxfattribs={
                        'layer': 'doors',
                        'linetype': 'DASHED',
                        'lineweight': 50,
                    }
                )
        
        # Wall elements removed - causing display issues
        
        # Add title and layout information (commented out to avoid text outside plan)
        # self._add_title_block(msp, layout_data)
        
        # Add dimensions and annotations
        self._add_dimensions_and_annotations(msp, layout_data)
        
        # Save DXF file
        doc.saveas(output_dxf_path)
        
        print(f"✅ DXF exported successfully: {output_dxf_path}")
        return output_dxf_path
    
    def _setup_layers(self, doc):
        """Setup layers for different elements"""
        for layer_name, config in self.layer_config.items():
            layer = doc.layers.new(name=layer_name)
            layer.color = config['color']
            layer.linetype = config['linetype']
    
    def _draw_plot_boundary(self, msp, plot_boundary: List[Tuple[float, float]]):
        """Draw the plot boundary"""
        if len(plot_boundary) < 3:
            return
        
        # Close the polygon
        boundary_points = plot_boundary + [plot_boundary[0]]
        
        # Draw boundary lines
        for i in range(len(boundary_points) - 1):
            msp.add_line(
                boundary_points[i], 
                boundary_points[i + 1], 
                dxfattribs={'layer': 'boundary', 'lineweight': 70}
            )
        
        # Add boundary label - remove this entirely to reduce clutter
        # Commenting out plot boundary text as it adds unnecessary text at origin
        # center = self._calculate_polygon_center(plot_boundary)
        # msp.add_text(
        #     "PLOT BOUNDARY",
        #     dxfattribs={
        #         'layer': 'text',
        #         'height': self.text_height * 1.5,
        #         'style': 'Standard',
        #         'insert': center
        #     }
        # )
    
    def _draw_building_envelope(self, msp, building_envelope: List[Tuple[float, float]]):
        """Draw the building envelope"""
        if len(building_envelope) < 3:
            return
        
        # Close the polygon
        envelope_points = building_envelope + [building_envelope[0]]
        
        # Draw envelope lines
        for i in range(len(envelope_points) - 1):
            msp.add_line(
                envelope_points[i], 
                envelope_points[i + 1], 
                dxfattribs={'layer': 'building_envelope', 'lineweight': 50}
            )
    
    def _draw_apartments(self, msp, apartments: List[Dict]):
        """Draw multiple apartments"""
        for i, apartment in enumerate(apartments):
            apt_number = apartment.get('apartment_number', i + 1)
            rooms = apartment.get('rooms', [])
            
            print(f"  📐 Drawing Apartment {apt_number} with {len(rooms)} rooms")
            
            # Draw rooms
            for room in rooms:
                self._draw_room(msp, room)
            
            # Add apartment number label with manual positioning
            if rooms:
                apartment_center = self._calculate_apartment_center(rooms)
                # Calculate text width for manual centering
                apt_text = f"APT {apt_number}"
                char_width = self.text_height * 2 * 0.6
                text_width = len(apt_text) * char_width
                
                msp.add_text(
                    apt_text,
                    dxfattribs={
                        'layer': 'text',
                        'height': self.text_height * 2,
                        'style': 'Standard',
                        'insert': (apartment_center[0] - text_width/2, apartment_center[1])
                    }
                )
    
    def _draw_single_apartment(self, msp, rooms: List[Dict]):
        """Draw a single apartment"""
        print(f"  📐 Drawing single apartment with {len(rooms)} rooms")
        
        for room in rooms:
            self._draw_room(msp, room)
    
    def _draw_room(self, msp, room: Dict):
        """Draw a single room with measurements"""
        room_type = room.get('type', 'unknown')
        polygon = room.get('polygon', [])
        
        if len(polygon) < 3:
            return
        
        # Get layer for room type
        layer = room_type if room_type in self.layer_config else 'walls'
        
        # Draw room outline with measurements
        room_points = polygon + [polygon[0]]  # Close the polygon
        for i in range(len(room_points) - 1):
            msp.add_line(
                room_points[i], 
                room_points[i + 1], 
                dxfattribs={'layer': layer, 'lineweight': 30}
            )
        
        # Add wall dimensions
        self._add_wall_dimensions(msp, room_points)
        
        # Remove room hatch/fill to keep everything colorless
        # Commenting out colored hatches to maintain clean, colorless appearance
        # try:
        #     hatch = msp.add_hatch(color=self.layer_config[layer]['color'])
        #     hatch.paths.add_polyline_path(polygon, is_closed=True)
        #     hatch.dxf.layer = layer
        #     hatch.dxf.transparency = 0.8  # Semi-transparent fill
        # except:
        #     pass  # Skip hatch if it fails
        
        # Add room labels with advanced anti-overlap positioning
        center = self._calculate_polygon_center(polygon)
        area = room.get('area', 0)
        
        # Calculate room bounds for better text positioning
        min_x = min(p[0] for p in polygon)
        max_x = max(p[0] for p in polygon)
        min_y = min(p[1] for p in polygon)
        max_y = max(p[1] for p in polygon)
        room_width = max_x - min_x
        room_height = max_y - min_y
        
        # Calculate much smaller text sizes to prevent overlap
        min_dimension = min(room_width, room_height)
        
        # Aggressive text scaling - much smaller text
        if min_dimension < 3:
            text_scale = 0.3
        elif min_dimension < 5:
            text_scale = 0.4
        elif min_dimension < 8:
            text_scale = 0.6
        else:
            text_scale = 0.8
        
        base_text_height = 0.8  # Much smaller base size
        adjusted_text_height = base_text_height * text_scale
        adjusted_dim_height = base_text_height * text_scale * 0.8
        
        # Only add text if room is large enough
        if room_width > 2 and room_height > 2:
            
            # Room type label (positioned explicitly without alignment)
            room_name = room_type.upper().replace('_', ' ')
            # Truncate long room names for small rooms
            if min_dimension < 4 and len(room_name) > 8:
                room_name = room_name[:8]
            
            # Calculate text width approximately to center it manually
            char_width = adjusted_text_height * 0.6  # Approximate character width
            text_width = len(room_name) * char_width
            
            # Position text manually centered
            label_y_offset = room_height * 0.2  # Closer to center
            label_pos = (center[0] - text_width/2, center[1] + label_y_offset)
            
            msp.add_text(
                room_name,
                dxfattribs={
                    'layer': 'text',
                    'height': adjusted_text_height,
                    'style': 'Standard',
                    'insert': label_pos
                }
            )
            
            # Only add area if room is reasonably sized
            if room_width > 3 and room_height > 3:
                area_text = f"{area:.0f}m²"  # Shorter format
                area_char_width = adjusted_dim_height * 0.6
                area_text_width = len(area_text) * area_char_width
                
                area_y_offset = room_height * 0.05  # Very close to center
                area_pos = (center[0] - area_text_width/2, center[1] - area_y_offset)
                
                msp.add_text(
                    area_text,
                    dxfattribs={
                        'layer': 'text',
                        'height': adjusted_dim_height,
                        'style': 'Standard',
                        'insert': area_pos
                    }
                )
            
            # Only add dimensions for larger rooms
            if room_width > 4 and room_height > 4:
                dimensions_text = f"{room_width:.1f}×{room_height:.1f}"  # Compact format
                dim_char_width = adjusted_dim_height * 0.7 * 0.6
                dim_text_width = len(dimensions_text) * dim_char_width
                
                dim_y_offset = room_height * 0.25  # Below center
                dim_pos = (center[0] - dim_text_width/2, center[1] - dim_y_offset)
                
                msp.add_text(
                    dimensions_text,
                    dxfattribs={
                        'layer': 'dimensions',
                        'height': adjusted_dim_height * 0.7,  # Even smaller
                        'style': 'Standard',
                        'insert': dim_pos
                    }
                )
    
    def _add_wall_dimensions(self, msp, room_points: List[Tuple[float, float]]):
        """Add dimension lines and text for each wall - minimal and clean"""
        
        # Only show dimensions for major walls to avoid clutter
        significant_walls = []
        
        for i in range(len(room_points) - 1):
            start_point = room_points[i]
            end_point = room_points[i + 1]
            
            wall_length = math.sqrt(
                (end_point[0] - start_point[0])**2 + 
                (end_point[1] - start_point[1])**2
            )
            
            # Only show dimensions for significant walls (> 1.5m)
            if wall_length > 1.5:
                significant_walls.append((start_point, end_point, wall_length))
        
        # Limit to max 2 dimensions per room to avoid clutter
        significant_walls.sort(key=lambda x: x[2], reverse=True)  # Sort by length
        max_walls_to_dimension = min(2, len(significant_walls))
        
        for i in range(max_walls_to_dimension):
            start_point, end_point, wall_length = significant_walls[i]
            
            # Calculate midpoint of the wall
            mid_x = (start_point[0] + end_point[0]) / 2
            mid_y = (start_point[1] + end_point[1]) / 2
            
            # Calculate wall angle
            angle = math.atan2(end_point[1] - start_point[1], end_point[0] - start_point[0])
            
            # Smaller offset distance to keep dimensions close
            offset_distance = 0.8  # Reduced from 1.5
            perpendicular_angle = angle + math.pi / 2
            
            # Position dimension text offset from wall
            dim_x = mid_x + offset_distance * math.cos(perpendicular_angle)
            dim_y = mid_y + offset_distance * math.sin(perpendicular_angle)
            
            # Add dimension text - much smaller
            dimension_text = f"{wall_length:.1f}"  # Remove 'm' for brevity
            text_rotation = angle * 180 / math.pi
            
            # Adjust text rotation for readability
            if text_rotation > 90 or text_rotation < -90:
                text_rotation += 180
                dim_x = mid_x - offset_distance * math.cos(perpendicular_angle)
                dim_y = mid_y - offset_distance * math.sin(perpendicular_angle)
            
            msp.add_text(
                dimension_text,
                dxfattribs={
                    'layer': 'dimensions',
                    'height': 0.4,  # Much smaller text
                    'style': 'Standard',
                    'insert': (dim_x, dim_y),
                    'rotation': text_rotation
                }
            )
            
            # Add dimension line
            # Offset start and end points slightly from wall
            line_offset = 0.8
            line_start_x = mid_x + line_offset * math.cos(perpendicular_angle)
            line_start_y = mid_y + line_offset * math.sin(perpendicular_angle)
            line_end_x = mid_x + (offset_distance + 0.3) * math.cos(perpendicular_angle)
            line_end_y = mid_y + (offset_distance + 0.3) * math.sin(perpendicular_angle)
            
            # Add dimension leader line
            msp.add_line(
                (line_start_x, line_start_y),
                (line_end_x, line_end_y),
                dxfattribs={'layer': 'dimensions', 'lineweight': 10}
            )
    
    def _add_title_block(self, msp, layout_data: Dict):
        """Add title block with layout information"""
        
        # Get layout bounds
        all_points = []
        if 'plot_boundary' in layout_data:
            all_points.extend(layout_data['plot_boundary'])
        elif 'building_envelope' in layout_data:
            all_points.extend(layout_data['building_envelope'])
        
        if not all_points:
            return
        
        min_x = min(p[0] for p in all_points)
        max_x = max(p[0] for p in all_points)
        min_y = min(p[1] for p in all_points)
        max_y = max(p[1] for p in all_points)
        
        # Title block position (top-right)
        title_x = max_x - 10
        title_y = max_y + 5
        
        # Layout information
        config = layout_data.get('config', {})
        num_apartments = config.get('num_apartments', len(layout_data.get('apartments', [])))
        bedrooms = config.get('bedrooms', 'N/A')
        label = config.get('label', 'Floor Plan')
        
        total_area = layout_data.get('total_built_area', 0)
        fsi_utilized = layout_data.get('fsi_utilized', 0)
        
        # Title - remove to reduce clutter at origin
        # Commenting out title as it may appear at origin
        # msp.add_text(
        #     label,
        #     dxfattribs={
        #         'layer': 'text',
        #         'height': self.text_height * 2,
        #         'style': 'Standard',
        #         'insert': (title_x, title_y)
        #     }
        # )
        
        # Details
        details = [
            f"Apartments: {num_apartments}",
            f"Bedrooms: {bedrooms}",
            f"Total Area: {total_area:.0f} sq m",
            f"FSI Utilized: {fsi_utilized:.2f}"
        ]
        
        # Details - remove to reduce clutter
        # Commenting out detail text as it may appear at origin
        # for i, detail in enumerate(details):
        #     detail_y = title_y - (i + 2) * self.text_height * 1.2
        #     msp.add_text(
        #         detail,
        #         dxfattribs={
        #             'layer': 'text',
        #             'height': self.text_height,
        #             'style': 'Standard',
        #             'insert': (title_x, detail_y)
        #         }
        #     )
    
    def _add_dimensions_and_annotations(self, msp, layout_data: Dict):
        """Add basic dimensions and annotations"""
        
        # Add north arrow and scale
        if 'building_envelope' in layout_data:
            envelope = layout_data['building_envelope']
            if envelope:
                min_x = min(p[0] for p in envelope)
                max_x = max(p[0] for p in envelope)
                min_y = min(p[1] for p in envelope)
                
                # North arrow - remove to reduce clutter
                # Commenting out north arrow as it may appear at origin
                # north_pos = (min_x - 5, min_y + 10)
                # msp.add_text(
                #     "N ↑",
                #     dxfattribs={
                #         'layer': 'text',
                #         'height': self.text_height * 1.5,
                #         'style': 'Standard',
                #         'insert': north_pos
                #     }
                # )
                
                # Scale indicator - remove to reduce clutter
                # Commenting out scale as it may appear at origin
                # scale_pos = (min_x - 5, min_y + 5)
                # building_width = max_x - min_x
                # msp.add_text(
                #     f"Scale: 1m = {building_width/50:.1f}m",
                #     dxfattribs={
                #         'layer': 'text',
                #         'height': self.dimension_text_height,
                #         'style': 'Standard',
                #         'insert': scale_pos
                #     }
                # )
    
    def _calculate_polygon_center(self, polygon: List[Tuple[float, float]]) -> Tuple[float, float]:
        """Calculate the center point of a polygon"""
        if not polygon:
            return (0, 0)
        
        x_coords = [p[0] for p in polygon]
        y_coords = [p[1] for p in polygon]
        
        center_x = sum(x_coords) / len(x_coords)
        center_y = sum(y_coords) / len(y_coords)
        
        return (center_x, center_y)
    
    def _calculate_apartment_center(self, rooms: List[Dict]) -> Tuple[float, float]:
        """Calculate the center point of an apartment"""
        all_points = []
        for room in rooms:
            polygon = room.get('polygon', [])
            all_points.extend(polygon)
        
        return self._calculate_polygon_center(all_points)
    
    def _draw_circulation_elements(self, msp, circulation_elements: List[Dict]):
        """Draw circulation elements (lobby, lift, staircase)"""
        
        print(f"  📐 Drawing {len(circulation_elements)} circulation elements")
        
        for i, element in enumerate(circulation_elements):
            element_type = element.get('type', 'circulation')
            polygon = element.get('polygon', [])
            area = element.get('area', 0)
            
            if not polygon:
                continue
                
            # Draw the element outline
            layer_name = element_type if element_type in self.layer_config else 'corridor'
            
            # Create closed polygon
            polygon_points = polygon + [polygon[0]]  # Close the polygon
            
            # Draw outline with thicker lines for better visibility
            msp.add_lwpolyline(
                polygon_points,
                dxfattribs={
                    'layer': layer_name,
                    'closed': True,
                    'lineweight': 50  # Thicker line for circulation elements
                }
            )
            
            # Calculate element dimensions for text sizing
            min_x = min(p[0] for p in polygon)
            max_x = max(p[0] for p in polygon)
            min_y = min(p[1] for p in polygon)
            max_y = max(p[1] for p in polygon)
            
            element_width = max_x - min_x
            element_height = max_y - min_y
            min_dimension = min(element_width, element_height)
            
            # Scale text based on element size but ensure readability
            text_size = max(0.5, min(2.0, min_dimension / 5))
            
            # Add label with simplified positioning
            center = self._calculate_polygon_center(polygon)
            label = element_type.replace('_', ' ').title()
            
            # For very small elements, use abbreviated labels
            if min_dimension < 3:
                if element_type == 'central_lobby':
                    label = 'LOBBY'
                elif element_type == 'staircase_perimeter':
                    label = 'STAIR'
                elif element_type == 'lift':
                    label = 'LIFT'
            
            # Use simple center positioning
            msp.add_text(
                label,
                dxfattribs={
                    'layer': 'text',
                    'height': text_size,
                    'style': 'Standard',
                    'insert': center
                }
            )
            
            # Only add area if element is large enough
            if min_dimension > 2:
                area_pos = (center[0], center[1] - text_size * 1.2)
                msp.add_text(
                    f"{area:.0f}m²",
                    dxfattribs={
                        'layer': 'text',
                        'height': text_size * 0.7,
                        'style': 'Standard',
                        'insert': area_pos
                    }
                )
    


def export_latest_layouts_to_dxf():
    """Export the most recent apartment layout files to DXF"""
    
    # Find the most recent layout files
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_files = []
    
    for file in os.listdir(current_dir):
        if file.startswith('natural_multi_apt_') and file.endswith('.json'):
            json_files.append(os.path.join(current_dir, file))
    
    if not json_files:
        print("❌ No apartment layout JSON files found")
        return
    
    # Sort by modification time to get the latest files
    json_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    # Take the latest 5 files (one for each apartment configuration)
    latest_files = json_files[:5]
    
    print(f"🏗️ Found {len(latest_files)} recent layout files to export")
    
    exporter = FloorPlanDXFExporter()
    
    for json_file in latest_files:
        try:
            dxf_file = exporter.export_apartment_layout_to_dxf(json_file)
            print(f"✅ Exported: {os.path.basename(dxf_file)}")
        except Exception as e:
            print(f"❌ Failed to export {os.path.basename(json_file)}: {e}")

if __name__ == "__main__":
    export_latest_layouts_to_dxf()
