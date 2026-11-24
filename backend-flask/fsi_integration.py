"""
FSI Integration Module
Integrates DCPR vector database for FSI value retrieval and calculations
"""

import sys
import os
import logging
import threading
from typing import Dict, List, Optional, Tuple
import re

# Add the dcpr_parser directory to sys.path using relative imports
current_dir = os.path.dirname(__file__)
dcpr_parser_path = os.path.join(current_dir, 'dcpr_parser')
sys.path.append(dcpr_parser_path)

try:
    from vector_database import DCPRVectorDatabase
except ImportError as e:
    logging.error(f"Could not import DCPRVectorDatabase: {e}")
    DCPRVectorDatabase = None

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class FSICalculator:
    """Main class for FSI calculations and DCPR compliance checking"""
    
    def __init__(self):
        """Initialize FSI calculator with vector database connection"""
        self.vector_db = None
        self.fallback_fsi_table = self._get_fallback_fsi_table()
        
        # Get current directory for relative paths
        current_dir = os.path.dirname(__file__)
        
        if DCPRVectorDatabase:
            try:
                # Initialize vector database connection using relative path
                db_path = os.path.join(current_dir, "dcpr_parser", "dcpr_vector_db")
                if os.path.exists(db_path):
                    self.vector_db = DCPRVectorDatabase(db_path=db_path)
                    self.vector_db.create_collection(reset_if_exists=False)
                    logger.info("Successfully connected to DCPR vector database")
                else:
                    logger.warning(f"Vector database path not found: {db_path}")
            except Exception as e:
                logger.error(f"Failed to initialize vector database: {e}")
                self.vector_db = None
        else:
            logger.warning("DCPRVectorDatabase class not available, using fallback FSI calculations")
    
    def _get_fallback_fsi_table(self) -> Dict:
        """Fallback FSI table based on road width (from Table 12 DCPR)"""
        return {
            # Road width in meters: (Basic FSI, Additional FSI on premium, Max permissible FSI)
            "island_city": {
                4.0: {"basic": 1.33, "additional": 0.67, "max": 2.0},
                6.0: {"basic": 1.33, "additional": 0.67, "max": 2.0},
                9.0: {"basic": 1.33, "additional": 1.17, "max": 2.5},
                12.2: {"basic": 1.33, "additional": 1.67, "max": 3.0},
                18.3: {"basic": 1.33, "additional": 2.17, "max": 3.5},
                27.3: {"basic": 1.33, "additional": 2.67, "max": 4.0},
                30.0: {"basic": 1.33, "additional": 2.67, "max": 4.0}
            },
            "extended_suburbs": {
                4.0: {"basic": 1.0, "additional": 0.0, "max": 1.0},
                6.0: {"basic": 1.0, "additional": 0.5, "max": 1.5},
                9.0: {"basic": 1.0, "additional": 1.0, "max": 2.0},
                12.2: {"basic": 1.0, "additional": 1.5, "max": 2.5},
                18.3: {"basic": 1.0, "additional": 2.0, "max": 3.0},
                27.3: {"basic": 1.0, "additional": 2.5, "max": 3.5},
                30.0: {"basic": 1.0, "additional": 3.0, "max": 4.0}
            },
            "suburbs": {
                4.0: {"basic": 1.0, "additional": 0.0, "max": 1.0},
                6.0: {"basic": 1.0, "additional": 0.5, "max": 1.5},
                9.0: {"basic": 1.0, "additional": 1.0, "max": 2.0},
                12.2: {"basic": 1.0, "additional": 1.5, "max": 2.5},
                18.3: {"basic": 1.0, "additional": 2.0, "max": 3.0},
                27.3: {"basic": 1.0, "additional": 2.5, "max": 3.5},
                30.0: {"basic": 1.0, "additional": 3.0, "max": 4.0}
            }
        }
    
    def get_zone_type(self, location: str, jurisdiction: str) -> str:
        """Determine zone type based on location and jurisdiction"""
        location_lower = location.lower()
        jurisdiction_lower = jurisdiction.lower()
        
        # Island City areas
        island_city_areas = [
            'fort', 'churchgate', 'marine lines', 'charni road', 'grant road',
            'mumbai central', 'mahalaxmi', 'lower parel', 'elphinstone road',
            'dadar', 'matunga', 'sion', 'kurla', 'vidyavihar', 'ghatkopar',
            'vikhroli', 'kanjurmarg', 'bhandup', 'mulund', 'thane west',
            'colaba', 'nariman point', 'ballard estate', 'kala ghoda'
        ]
        
        # Extended Suburbs areas
        extended_suburbs_areas = [
            'andheri', 'jogeshwari', 'goregaon', 'malad', 'kandivali',
            'borivali', 'dahisar', 'mira road', 'bhayander', 'naigaon',
            'vasai', 'virar', 'nalasopara', 'nallasopara', 'palghar'
        ]
        
        # Check if location matches Island City
        if any(area in location_lower for area in island_city_areas):
            return "island_city"
        
        # Check if location matches Extended Suburbs
        if any(area in location_lower for area in extended_suburbs_areas):
            return "extended_suburbs"
        
        # Default to suburbs for Mumbai areas
        if 'mumbai' in jurisdiction_lower or 'mcgm' in jurisdiction_lower:
            return "suburbs"
        
        # Default fallback
        return "suburbs"
    
    def get_fsi_from_vector_db(self, building_type: str, road_widths: List[float], 
                               location: str, zone_type: str) -> Optional[Dict]:
        """Query vector database for FSI values based on parameters"""
        if not self.vector_db:
            return None
        
        try:
            # Create search query based on parameters
            max_road_width = max(road_widths) if road_widths else 9.0
            
            queries = [
                f"What is the basic FSI for {building_type.lower()} buildings with {max_road_width}m road width?",
                f"Floor Space Index FSI {building_type.lower()} {max_road_width}m road width basic additional permissible",
                f"Table 12 FSI values {building_type.lower()} buildings road width {max_road_width} meters",
                f"basic FSI {building_type.lower()} {zone_type.replace('_', ' ')} {max_road_width}m road"
            ]
            
            best_result = None
            max_similarity = 0.0
            
            for query in queries:
                try:
                    results = self.vector_db.search_regulations(query, n_results=5)
                    
                    if results and results.get('results'):
                        for result in results['results']:
                            similarity = result.get('similarity_score', 0.0)
                            text = result.get('text', '').lower()
                            
                            # Look for FSI numbers in the text
                            fsi_numbers = re.findall(r'\b(?:fsi|FSI)\s*[:\=]?\s*(\d+\.?\d*)', text)
                            general_numbers = re.findall(r'\b(\d+\.\d+|\d+)\b', text)
                            
                            if (similarity > max_similarity and 
                                (fsi_numbers or general_numbers) and 
                                building_type.lower() in text):
                                
                                max_similarity = similarity
                                best_result = {
                                    'text': result.get('text', ''),
                                    'similarity': similarity,
                                    'fsi_numbers': fsi_numbers,
                                    'general_numbers': general_numbers,
                                    'metadata': result.get('metadata', {})
                                }
                
                except Exception as e:
                    logger.warning(f"Query failed: {query} - {e}")
                    continue
            
            if best_result and max_similarity > 0.6:  # Good similarity threshold
                return self._extract_fsi_from_result(best_result, max_road_width)
            
        except Exception as e:
            logger.error(f"Vector database query failed: {e}")
        
        return None
    
    def _extract_fsi_from_result(self, result: Dict, road_width: float) -> Dict:
        """Extract FSI values from vector database result"""
        text = result['text'].lower()
        fsi_numbers = result.get('fsi_numbers', [])
        general_numbers = result.get('general_numbers', [])
        
        # Try to extract specific FSI values
        basic_fsi = None
        additional_fsi = None
        max_fsi = None
        
        # Look for explicit FSI mentions
        if fsi_numbers:
            # First FSI number is usually basic FSI
            try:
                basic_fsi = float(fsi_numbers[0])
            except (ValueError, IndexError):
                pass
        
        # Look for common FSI values in text
        common_fsi_values = []
        for num_str in general_numbers:
            try:
                num = float(num_str)
                if 0.5 <= num <= 5.0:  # Reasonable FSI range
                    common_fsi_values.append(num)
            except ValueError:
                continue
        
        # If we have common FSI values, try to identify them
        if common_fsi_values:
            common_fsi_values.sort()
            
            if basic_fsi is None and common_fsi_values:
                basic_fsi = common_fsi_values[0]  # Usually the lowest value
            
            if len(common_fsi_values) > 1:
                max_fsi = common_fsi_values[-1]  # Usually the highest value
                if len(common_fsi_values) > 2:
                    additional_fsi = max_fsi - basic_fsi if basic_fsi else None
        
        # Fallback to road width based calculation if extraction fails
        if basic_fsi is None:
            return self._get_fallback_fsi_for_road_width(road_width, "suburbs")  # Default zone
        
        return {
            'basic_fsi': basic_fsi or 1.0,
            'additional_fsi': additional_fsi or 0.5,
            'max_fsi': max_fsi or (basic_fsi + (additional_fsi or 0.5)),
            'source': 'vector_db',
            'similarity': result.get('similarity', 0.0),
            'confidence': 'high' if result.get('similarity', 0.0) > 0.8 else 'medium'
        }
    
    def _get_fallback_fsi_for_road_width(self, road_width: float, zone_type: str) -> Dict:
        """Get FSI values from fallback table based on road width"""
        zone_table = self.fallback_fsi_table.get(zone_type, self.fallback_fsi_table['suburbs'])
        
        # Find the closest road width in our table
        available_widths = sorted(zone_table.keys())
        closest_width = min(available_widths, key=lambda x: abs(x - road_width))
        
        fsi_data = zone_table[closest_width]
        
        return {
            'basic_fsi': fsi_data['basic'],
            'additional_fsi': fsi_data['additional'],
            'max_fsi': fsi_data['max'],
            'source': 'fallback_table',
            'road_width_used': closest_width,
            'confidence': 'fallback'
        }
    
    def calculate_fsi_and_bua(self, plot_size: float, building_type: str, 
                              road_widths: List[float], location: str = "",
                              jurisdiction: str = "", area_unit: str = "sqmt") -> Dict:
        """
        Main function to calculate FSI and BUA with per-floor height integration
        """
        try:
            # Determine zone type
            zone_type = self.get_zone_type(location, jurisdiction)
            
            # Get maximum road width (FSI is based on widest road)
            max_road_width = max(road_widths) if road_widths else 9.0
            
            # Try to get FSI from vector database first
            fsi_data = self.get_fsi_from_vector_db(building_type, road_widths, location, zone_type)
            
            # Fallback to table-based calculation
            if not fsi_data:
                fsi_data = self._get_fallback_fsi_for_road_width(max_road_width, zone_type)
            
            # Convert plot size to square meters if needed
            plot_size_sqmt = plot_size
            if area_unit == 'sqft':
                plot_size_sqmt = plot_size / 10.764
            
            # Calculate BUA (Built-up Area)
            basic_fsi = fsi_data['basic_fsi']
            max_fsi = fsi_data['max_fsi']
            
            basic_bua = plot_size_sqmt * basic_fsi
            max_bua = plot_size_sqmt * max_fsi
            
            # Convert back to original unit if needed
            if area_unit == 'sqft':
                basic_bua = basic_bua * 10.764
                max_bua = max_bua * 10.764
            
            return {
                'plot_size': plot_size,
                'plot_size_sqmt': plot_size_sqmt,
                'area_unit': area_unit,
                'zone_type': zone_type,
                'max_road_width': max_road_width,
                'basic_fsi': basic_fsi,
                'additional_fsi': fsi_data.get('additional_fsi', 0.0),
                'max_fsi': max_fsi,
                'basic_bua': basic_bua,
                'max_bua': max_bua,
                'fsi_source': fsi_data.get('source', 'unknown'),
                'confidence': fsi_data.get('confidence', 'unknown'),
                'similarity_score': fsi_data.get('similarity', 0.0)
            }
            
        except Exception as e:
            logger.error(f"FSI calculation failed: {e}")
            # Return basic fallback calculation
            basic_fsi = 1.0
            plot_size_sqmt = plot_size if area_unit == 'sqmt' else plot_size / 10.764
            basic_bua = plot_size_sqmt * basic_fsi
            if area_unit == 'sqft':
                basic_bua = basic_bua * 10.764
                
            return {
                'plot_size': plot_size,
                'plot_size_sqmt': plot_size_sqmt,
                'area_unit': area_unit,
                'zone_type': 'unknown',
                'max_road_width': max(road_widths) if road_widths else 9.0,
                'basic_fsi': basic_fsi,
                'additional_fsi': 0.0,
                'max_fsi': basic_fsi,
                'basic_bua': basic_bua,
                'max_bua': basic_bua,
                'fsi_source': 'error_fallback',
                'confidence': 'low',
                'error': str(e)
            }
    
    def calculate_floor_metrics(self, aai_height: float, per_floor_height: float, 
                                bua: float, area_unit: str = "sqmt") -> Dict:
        """
        Calculate floor-related metrics including number of floors and area per floor
        """
        try:
            if per_floor_height <= 0:
                per_floor_height = 3.0  # Default 3 meters per floor
            
            # Calculate number of floors
            floors = int(aai_height / per_floor_height) if aai_height > 0 else 0
            
            # Convert BUA to square feet for per-floor calculation (standard in Mumbai)
            bua_sqft = bua
            if area_unit == 'sqmt':
                bua_sqft = bua * 10.764
            
            # Calculate area per floor
            area_per_floor = bua_sqft / floors if floors > 0 else 0
            
            return {
                'aai_height': aai_height,
                'per_floor_height': per_floor_height,
                'total_floors': floors,
                'area_per_floor_sqft': area_per_floor,
                'total_bua_sqft': bua_sqft,
                'utilization_efficiency': (floors * per_floor_height) / aai_height if aai_height > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Floor metrics calculation failed: {e}")
            return {
                'aai_height': aai_height,
                'per_floor_height': per_floor_height,
                'total_floors': 0,
                'area_per_floor_sqft': 0,
                'total_bua_sqft': 0,
                'utilization_efficiency': 0,
                'error': str(e)
            }
    
    def calculate_bhk_layout(self, area_per_floor_sqft: float, bhk_config: Dict) -> Dict:
        """
        Calculate BHK layout and remaining area
        bhk_config: {'bhk_1': count, 'bhk_2': count, 'bhk_3': count, 'bhk_4': count}
        """
        try:
            # Standard BHK sizes in square feet
            bhk_sizes = {
                'bhk_1': 430,
                'bhk_2': 730,
                'bhk_3': 1100,
                'bhk_4': 1600
            }
            
            total_bhk_area = 0
            bhk_breakdown = {}
            
            for bhk_type, count in bhk_config.items():
                count = int(count) if count else 0
                if count > 0 and bhk_type in bhk_sizes:
                    area = bhk_sizes[bhk_type] * count
                    total_bhk_area += area
                    bhk_breakdown[bhk_type] = {
                        'count': count,
                        'unit_size_sqft': bhk_sizes[bhk_type],
                        'total_area_sqft': area
                    }
            
            remaining_area = area_per_floor_sqft - total_bhk_area
            utilization_percentage = (total_bhk_area / area_per_floor_sqft * 100) if area_per_floor_sqft > 0 else 0
            
            return {
                'bhk_breakdown': bhk_breakdown,
                'total_bhk_area_sqft': total_bhk_area,
                'remaining_area_sqft': remaining_area,
                'utilization_percentage': utilization_percentage,
                'is_overutilized': remaining_area < 0
            }
            
        except Exception as e:
            logger.error(f"BHK layout calculation failed: {e}")
            return {
                'bhk_breakdown': {},
                'total_bhk_area_sqft': 0,
                'remaining_area_sqft': 0,
                'utilization_percentage': 0,
                'is_overutilized': False,
                'error': str(e)
            }


# Keep server startup independent of the embedding model; FSI analysis initializes
# the calculator only when a submission actually requests it.
fsi_calculator: Optional[FSICalculator] = None
_fsi_calculator_lock = threading.Lock()


def _get_fsi_calculator() -> FSICalculator:
    global fsi_calculator
    if fsi_calculator is None:
        with _fsi_calculator_lock:
            if fsi_calculator is None:
                fsi_calculator = FSICalculator()
    return fsi_calculator


def get_comprehensive_building_analysis(form_data: Dict) -> Dict:
    """
    Main function to get comprehensive building analysis including FSI, BUA, floors, and layout
    """
    try:
        calculator = _get_fsi_calculator()

        # Extract form data
        plot_size = float(form_data.get('plot_size', 0))
        area_unit = form_data.get('area_unit', 'sqmt')
        building_type = form_data.get('building_type', 'Residential')
        location = form_data.get('location', '')
        jurisdiction = form_data.get('jurisdiction', '')
        aai_height = float(form_data.get('aai_height', 0))
        per_floor_height = float(form_data.get('per_floor_height', 3.0))
        
        # Extract road widths
        road_widths = []
        number_of_roads = int(form_data.get('number_of_roads', 1))
        
        if number_of_roads == 1:
            road_width = form_data.get('road_width')
            if road_width:
                road_widths.append(float(road_width))
        else:
            for i in range(1, number_of_roads + 1):
                road_width = form_data.get(f'road_width_{i}')
                if road_width:
                    road_widths.append(float(road_width))
        
        # Extract BHK configuration
        bhk_config = {
            'bhk_1': form_data.get('bhk_1', 0),
            'bhk_2': form_data.get('bhk_2', 0),
            'bhk_3': form_data.get('bhk_3', 0),
            'bhk_4': form_data.get('bhk_4', 0)
        }
        
        # Calculate FSI and BUA
        fsi_analysis = calculator.calculate_fsi_and_bua(
            plot_size, building_type, road_widths, location, jurisdiction, area_unit
        )
        
        # Calculate floor metrics
        floor_analysis = calculator.calculate_floor_metrics(
            aai_height, per_floor_height, fsi_analysis['basic_bua'], area_unit
        )
        
        # Calculate BHK layout
        bhk_analysis = calculator.calculate_bhk_layout(
            floor_analysis['area_per_floor_sqft'], bhk_config
        )
        
        # Combine all analyses
        comprehensive_analysis = {
            'fsi_analysis': fsi_analysis,
            'floor_analysis': floor_analysis,
            'bhk_analysis': bhk_analysis,
            'summary': {
                'basic_fsi': fsi_analysis['basic_fsi'],
                'max_fsi': fsi_analysis['max_fsi'],
                'basic_bua': fsi_analysis['basic_bua'],
                'max_bua': fsi_analysis['max_bua'],
                'total_floors': floor_analysis['total_floors'],
                'area_per_floor_sqft': floor_analysis['area_per_floor_sqft'],
                'bhk_utilization': bhk_analysis['utilization_percentage'],
                'remaining_area_sqft': bhk_analysis['remaining_area_sqft']
            },
            'compliance': {
                'zone_type': fsi_analysis['zone_type'],
                'fsi_source': fsi_analysis['fsi_source'],
                'confidence': fsi_analysis['confidence'],
                'is_layout_feasible': not bhk_analysis['is_overutilized']
            }
        }
        
        return comprehensive_analysis
        
    except Exception as e:
        logger.error(f"Comprehensive building analysis failed: {e}")
        return {
            'error': str(e),
            'fsi_analysis': {},
            'floor_analysis': {},
            'bhk_analysis': {},
            'summary': {},
            'compliance': {}
        }


if __name__ == "__main__":
    # Test the FSI integration
    test_data = {
        'plot_size': 1000,
        'area_unit': 'sqmt',
        'building_type': 'Residential',
        'location': 'Andheri West',
        'jurisdiction': 'Mumbai',
        'aai_height': 45,
        'per_floor_height': 3.0,
        'number_of_roads': 1,
        'road_width': 12.2,
        'bhk_1': 2,
        'bhk_2': 4,
        'bhk_3': 0,
        'bhk_4': 0
    }
    
    result = get_comprehensive_building_analysis(test_data)
    print("FSI Integration Test Result:")
    print("=" * 50)
    for key, value in result.items():
        print(f"{key}: {value}")