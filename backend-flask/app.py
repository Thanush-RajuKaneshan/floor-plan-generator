from flask import send_file
from flask import Flask, request, jsonify, session, redirect, render_template, url_for, flash, send_from_directory
from flask_cors import CORS
import sqlite3
import json
import os
import importlib.util
import sys
import uuid
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from llm_chat import chat

# Set matplotlib to non-GUI backend for web server environment
import matplotlib
matplotlib.use('Agg')

# Import FSI integration functionality
try:
    import logging
    # Suppress chromadb warnings since we expect it might not be available
    logging.getLogger('chromadb').setLevel(logging.ERROR)
    from fsi_integration import get_comprehensive_building_analysis
except ImportError as e:
    print(f"Info: FSI integration using fallback calculations (chromadb not available)")
    get_comprehensive_building_analysis = None


app = Flask(__name__)
# Set SECRET_KEY in production; the random fallback logs everyone out on restart.
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)
CORS(app)

DATABASE = os.path.join(os.path.dirname(__file__), 'users.db')
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    
    # Users table for authentication
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username VARCHAR(255) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL
    )''')
    conn.commit()

    conn.execute('''CREATE TABLE IF NOT EXISTS submission_floorplan_variants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id INTEGER NOT NULL,
        variant_number INTEGER NOT NULL,
        variant_name TEXT NOT NULL,
        image_path TEXT NOT NULL,
        json_path TEXT NOT NULL,
        dxf_path TEXT,
        UNIQUE (submission_id, variant_number)
    )''')
    conn.commit()
    
    # Comprehensive user_data table for form submissions
    conn.execute('''CREATE TABLE IF NOT EXISTS user_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        
        -- Basic form fields
        area_unit TEXT DEFAULT 'sqmt',
        plot_size REAL,
        location TEXT,
        jurisdiction TEXT,
        rrr TEXT,
        number_of_roads INTEGER,
        building_type TEXT,
        
        -- BHK selections
        bhk_1 INTEGER DEFAULT 0,
        bhk_2 INTEGER DEFAULT 0,
        bhk_3 INTEGER DEFAULT 0,
        bhk_4 INTEGER DEFAULT 0,
        
        -- Road width fields (supporting up to 4 roads)
        road_width REAL,           -- Single road width
        road_width_1 REAL,         -- Multi-road width 1
        road_width_2 REAL,         -- Multi-road width 2
        road_width_3 REAL,         -- Multi-road width 3
        road_width_4 REAL,         -- Multi-road width 4
        
        -- AAI and calculated values
        aai_height REAL,
        per_floor_height REAL DEFAULT 3.0,
        fsi REAL,
        max_fsi REAL,
        bua REAL,
        max_bua REAL,
        floors INTEGER,
        fsi_per_floor REAL,
        area_left REAL,
        
        -- FSI analysis data
        zone_type TEXT,
        fsi_source TEXT,
        fsi_confidence TEXT,
        similarity_score REAL,
        
        -- Image processing
        image_path TEXT,
        output_image_path TEXT,
    output_dxf_path TEXT,
        
        -- AI model results
        length REAL,
        breadth REAL,
        angle REAL,
        
        -- Metadata
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    
    # Migration: Add missing columns if they don't exist
    try:
        # Check which columns exist in the current table
        cursor = conn.execute("PRAGMA table_info(user_data)")
        existing_columns = [column[1] for column in cursor.fetchall()]
        
        # Define all required columns with their types and defaults
        required_columns = {
            'per_floor_height': 'REAL DEFAULT 3.0',
            'max_fsi': 'REAL',
            'max_bua': 'REAL', 
            'fsi_per_floor': 'REAL',
            'area_left': 'REAL',
            'zone_type': 'TEXT',
            'fsi_source': 'TEXT',
            'fsi_confidence': 'TEXT',
            'similarity_score': 'REAL',
            'output_dxf_path': 'TEXT'
        }
        
        # Add missing columns
        for column_name, column_definition in required_columns.items():
            if column_name not in existing_columns:
                alter_query = f'ALTER TABLE user_data ADD COLUMN {column_name} {column_definition}'
                conn.execute(alter_query)
                print(f"Added missing column: {column_name}")
        
        conn.commit()
            
    except Exception as e:
        print(f"Migration warning: {e}")
    
    conn.close()


def generate_submission_floorplan(
    image_path, plot_area_sqm, apartment_bedroom_counts, fsi, floors,
    design_variant=0
):
    project_root = os.path.dirname(os.path.dirname(__file__))
    generator_dir = os.path.join(project_root, 'CompleteBackend')
    generator_path = os.path.join(generator_dir, 'boundary_natural_generator.py')
    if not os.path.isfile(generator_path):
        raise FileNotFoundError(f'Floor-plan generator not found: {generator_path}')
    if generator_dir not in sys.path:
        sys.path.insert(0, generator_dir)

    spec = importlib.util.spec_from_file_location(
        'capstone_boundary_natural_generator', generator_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f'Could not load floor-plan generator from {generator_path}')
    generator_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator_module)
    generator = generator_module.BoundaryNaturalGenerator()

    output_dir = os.path.join(UPLOAD_FOLDER, 'outputs')
    os.makedirs(output_dir, exist_ok=True)
    output_name = (
        f"boundary_{os.path.splitext(os.path.basename(image_path))[0]}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    )
    image_output_path = os.path.join(output_dir, output_name + '.png')
    json_output_path = os.path.join(output_dir, output_name + '.json')
    dxf_output_path = os.path.join(output_dir, output_name + '.dxf')

    layout = generator.generate_boundary_natural_layout(
        boundary_image_path=image_path,
        num_apartments=len(apartment_bedroom_counts),
        bedrooms_per_apt=apartment_bedroom_counts[0],
        apartment_bedroom_counts=apartment_bedroom_counts,
        fsi=float(fsi),
        ground_coverage=0.65,
        floors=int(floors),
        target_area=float(plot_area_sqm),
        design_variant=design_variant
    )
    generator.save_layout_data(layout, json_output_path)
    generator.visualize_boundary_layout(layout, save_path=image_output_path)
    if not os.path.isfile(image_output_path):
        raise RuntimeError('Floor-plan generator did not create its PNG output')

    dxf_path = None
    try:
        generator.export_to_dxf(layout, dxf_output_path)
        if os.path.isfile(dxf_output_path):
            dxf_path = dxf_output_path
    except Exception as exc:
        app.logger.warning('DXF export failed: %s', exc)

    return layout, image_output_path, json_output_path, dxf_path


# Run DB initialization at startup
with app.app_context():
    init_db()

@app.route('/register', methods=['POST'])
def register():
    data = request.form
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'success': False, 'message': 'Missing fields'}), 400
    hashed_password = generate_password_hash(password)
    try:
        conn = get_db()
        conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
        conn.commit()
        conn.close()
        return redirect(url_for('login_page'))
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Username already exists'}), 409

@app.route('/login', methods=['POST'])
def login():
    data = request.form
    username = data.get('username')
    password = data.get('password')
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    if user and check_password_hash(user['password'], password):
        session['username'] = username
        return redirect(url_for('main_form_page'))
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/predict', methods=['POST'])
def predict():
    import traceback
    debug_info = {}
    try:
        if not session.get('username'):
            debug_info['session'] = dict(session)
            return jsonify({'error': 'You must be logged in to submit the form.', 'debug': debug_info}), 401
        
        username = session.get('username')
        
        # Extract all form fields
        area_unit = request.form.get('area_unit', 'sqmt')
        plot_size = float(request.form.get('plot_size', 0))
        location = request.form.get('location')
        jurisdiction = request.form.get('jurisdiction')
        rrr = request.form.get('rrr')
        number_of_roads = int(request.form.get('number_of_roads', 0))
        building_type = request.form.get('building_type')
        
        # Extract BHK selections
        bhk_1 = int(request.form.get('bhk_1', 0))
        bhk_2 = int(request.form.get('bhk_2', 0))
        bhk_3 = int(request.form.get('bhk_3', 0))
        bhk_4 = int(request.form.get('bhk_4', 0))

        apartment_specifications = (
            [{'bedrooms': 1, 'type': '1BHK'}] * bhk_1
            + [{'bedrooms': 2, 'type': '2BHK'}] * bhk_2
            + [{'bedrooms': 3, 'type': '3BHK'}] * bhk_3
            + [{'bedrooms': 4, 'type': '4BHK'}] * bhk_4
        )
        if not apartment_specifications:
            return jsonify({
                'success': False,
                'error': 'Select at least one apartment for the typical floor.'
            }), 400
        if len(apartment_specifications) > 10:
            return jsonify({
                'success': False,
                'error': 'Select no more than 10 apartments per typical floor.'
            }), 400
        num_apartments = len(apartment_specifications)
        
        # Extract road width fields
        road_width = request.form.get('road_width')  # Single road
        road_width_1 = request.form.get('road_width_1')
        road_width_2 = request.form.get('road_width_2') 
        road_width_3 = request.form.get('road_width_3')
        road_width_4 = request.form.get('road_width_4')
        
        # Convert road widths to float or None
        road_width = float(road_width) if road_width else None
        road_width_1 = float(road_width_1) if road_width_1 else None
        road_width_2 = float(road_width_2) if road_width_2 else None
        road_width_3 = float(road_width_3) if road_width_3 else None
        road_width_4 = float(road_width_4) if road_width_4 else None
        
        # Extract AAI and calculated values
        aai_height = float(request.form.get('aai_height', 0))
        per_floor_height = float(request.form.get('per_floor_height', 3.0))
        
        # Enhanced FSI calculation using vector database integration
        fsi_analysis_data = {}
        if get_comprehensive_building_analysis:
            try:
                # Prepare comprehensive form data for FSI analysis
                analysis_form_data = {
                    'plot_size': plot_size,
                    'area_unit': area_unit,
                    'building_type': building_type,
                    'location': location,
                    'jurisdiction': jurisdiction,
                    'aai_height': aai_height,
                    'per_floor_height': per_floor_height,
                    'number_of_roads': number_of_roads,
                    'bhk_1': bhk_1,
                    'bhk_2': bhk_2,
                    'bhk_3': bhk_3,
                    'bhk_4': bhk_4
                }
                
                # Add road width data
                if number_of_roads == 1 and road_width:
                    analysis_form_data['road_width'] = road_width
                else:
                    for i in range(1, number_of_roads + 1):
                        road_width_key = f'road_width_{i}'
                        if road_width_key in request.form:
                            analysis_form_data[road_width_key] = request.form.get(road_width_key)
                
                # Get comprehensive building analysis
                fsi_analysis_data = get_comprehensive_building_analysis(analysis_form_data)
                
            except Exception as e:
                debug_info['fsi_analysis_error'] = str(e)
                fsi_analysis_data = {}
        
        # Extract calculated values from analysis or use fallback
        if fsi_analysis_data and 'summary' in fsi_analysis_data:
            summary = fsi_analysis_data['summary']
            fsi = summary.get('basic_fsi', 1.0)
            max_fsi = summary.get('max_fsi', fsi)
            bua = summary.get('basic_bua', plot_size * fsi)
            max_bua = summary.get('max_bua', bua)
            floors = summary.get('total_floors', int(aai_height / per_floor_height) if aai_height > 0 else 0)
            fsi_per_floor = summary.get('area_per_floor_sqft', 0)
            area_left = summary.get('remaining_area_sqft', 0)
            
            # FSI metadata
            compliance = fsi_analysis_data.get('compliance', {})
            zone_type = compliance.get('zone_type', 'unknown')
            fsi_source = compliance.get('fsi_source', 'fallback')
            fsi_confidence = compliance.get('confidence', 'unknown')
            similarity_score = fsi_analysis_data.get('fsi_analysis', {}).get('similarity_score', 0.0)
        else:
            # Fallback calculation
            fsi = float(request.form.get('fsi', 1.0))
            max_fsi = fsi * 1.5  # Approximate additional FSI
            bua = float(request.form.get('bua', plot_size * fsi))
            max_bua = plot_size * max_fsi
            floors = int(aai_height / per_floor_height) if aai_height > 0 and per_floor_height > 0 else 0
            fsi_per_floor = float(request.form.get('fsi_per_floor', 0))
            area_left = float(request.form.get('area_left', 0))
            
            zone_type = 'unknown'
            fsi_source = 'manual_input'
            fsi_confidence = 'low'
            similarity_score = 0.0
        
        debug_info['form'] = {
            'area_unit': area_unit, 'plot_size': plot_size, 'location': location,
            'jurisdiction': jurisdiction, 'rrr': rrr, 'number_of_roads': number_of_roads,
            'building_type': building_type, 'bhk_1': bhk_1, 'bhk_2': bhk_2, 'bhk_3': bhk_3, 'bhk_4': bhk_4,
            'aai_height': aai_height, 'per_floor_height': per_floor_height, 'fsi': fsi, 'max_fsi': max_fsi,
            'bua': bua, 'max_bua': max_bua, 'floors': floors, 'fsi_per_floor': fsi_per_floor, 'area_left': area_left,
            'zone_type': zone_type, 'fsi_source': fsi_source, 'fsi_confidence': fsi_confidence
        }
        
        # Add FSI analysis data to debug info
        if fsi_analysis_data:
            debug_info['fsi_analysis'] = fsi_analysis_data
        
        # Handle image upload and AI processing
        image = request.files.get('image')
        image_path = None
        output_image_path = None
        output_dxf_path = None
        length = breadth = angle = None

        if area_unit == 'sqft':
            plot_size_sqm = plot_size * 0.092903
        elif area_unit in {'sqmt', 'sqm'}:
            plot_size_sqm = plot_size
        else:
            return jsonify({'success': False, 'error': 'Unsupported plot area unit.'}), 400

        if not 50 <= plot_size_sqm <= 20000:
            return jsonify({
                'success': False,
                'error': f'Plot area must be between 50 and 20,000 sq m; received {plot_size_sqm:.1f} sq m.'
            }), 400
        if floors < 1:
            return jsonify({
                'success': False,
                'error': 'The entered building height and floor height must allow at least one floor.'
            }), 400
        
        if not image or not image.filename:
            return jsonify({
                'success': False,
                'error': 'Upload a plot boundary image to generate a floor plan.'
            }), 400

        if image:
            filename = secure_filename(image.filename or '')
            if not filename:
                return jsonify({'success': False, 'error': 'Choose a valid plot image.'}), 400
            filename = f'{uuid.uuid4().hex[:8]}_{filename}'
            image_path = os.path.join(UPLOAD_FOLDER, filename)
            image.save(image_path)
            debug_info['image_path'] = image_path
            
            # Generate the submission with the dimensioned boundary layout helper.
            try:
                try:
                    apartment_bedroom_counts = [
                        specification['bedrooms']
                        for specification in apartment_specifications
                    ]
                    variant_results = []
                    variant_rejections = []
                    for design_variant in range(3):
                        try:
                            variant_results.append(generate_submission_floorplan(
                                image_path,
                                plot_size_sqm,
                                apartment_bedroom_counts,
                                fsi,
                                floors,
                                design_variant=design_variant
                            ))
                        except ValueError as variant_exc:
                            variant_rejections.append(str(variant_exc))
                            app.logger.info(
                                'Design variant %s rejected: %s',
                                design_variant,
                                variant_exc,
                            )
                    if not variant_results:
                        raise ValueError(
                            'No design variant passed the strict geometry checks. '
                            + variant_rejections[0]
                        )
                    layout, output_image_path, json_path, output_dxf_path = variant_results[0]
                    debug_info['boundary_natural'] = {
                        'num_apartments': layout['num_apartments'],
                        'apartment_specifications': apartment_specifications,
                        'apartment_bedroom_counts': apartment_bedroom_counts,
                        'has_circulation': layout['has_circulation'],
                        'circulation_types': [
                            element['type']
                            for element in layout['circulation_elements']
                        ],
                        'floor_area': layout['floor_area'],
                        'total_built_area': layout['total_built_area'],
                        'plot_area': layout['plot_area'],
                        'fsi_utilized': layout['fsi_utilized'],
                        'ground_coverage_utilized': layout['ground_coverage_utilized'],
                        'design_variants': [
                            result[0]['design_variant_name'] for result in variant_results
                        ],
                        'png': output_image_path,
                        'json': json_path,
                        'dxf': output_dxf_path
                    }
                except ValueError as model_exc:
                    app.logger.info('Floor-plan generation rejected: %s', model_exc)
                    return jsonify({
                        'success': False,
                        'error': f'Floor-plan generation failed: {model_exc}'
                    }), 422
                except Exception as model_exc:
                    app.logger.exception('Floor-plan generation failed')
                    return jsonify({
                        'success': False,
                        'error': 'Floor-plan generation failed unexpectedly. Check the server log.'
                    }), 500
                    import importlib.util
                    import sys
                    project_root = os.path.dirname(os.path.dirname(__file__))
                    completebackend_dir = os.path.join(project_root, 'CompleteBackend')
                    generator_path = os.path.join(completebackend_dir, 'boundary_natural_generator.py')
                    
                    # Add CompleteBackend to Python path temporarily for imports
                    if completebackend_dir not in sys.path:
                        sys.path.insert(0, completebackend_dir)

                    if os.path.exists(generator_path) and os.path.exists(completebackend_dir):
                        spec = importlib.util.spec_from_file_location('boundary_natural_generator', generator_path)
                        gen_mod = importlib.util.module_from_spec(spec)
                        
                        # Execute module in context where it can find its dependencies
                        try:
                            spec.loader.exec_module(gen_mod)
                        except ImportError as import_err:
                            debug_info['generator_import_error'] = str(import_err)
                            # Specific handling for missing dependencies
                            if 'NaturalMultiApartmentFloorPlanGenerator' in str(import_err):
                                raise RuntimeError('Missing natural_multi_apartment_generator.py dependency')
                            elif 'shapely' in str(import_err).lower():
                                raise RuntimeError('Missing Shapely package: pip install shapely')
                            elif 'cv2' in str(import_err) or 'opencv' in str(import_err).lower():
                                raise RuntimeError('Missing OpenCV package: pip install opencv-python')
                            elif 'matplotlib' in str(import_err).lower():
                                raise RuntimeError('Missing matplotlib package: pip install matplotlib')
                            else:
                                raise RuntimeError(f'Failed to import boundary_natural_generator: {import_err}')
                        except Exception as import_err:
                            debug_info['generator_import_error'] = str(import_err)
                            raise RuntimeError(f'Failed to import boundary_natural_generator: {import_err}')

                        # Instantiate generator
                        try:
                            GeneratorClass = getattr(gen_mod, 'BoundaryNaturalGenerator')
                        except Exception as e:
                            raise RuntimeError(f'BoundaryNaturalGenerator not found in module: {e}')

                        generator = GeneratorClass()

                                                # Process exact BHK specifications from user input
                        apartment_specifications = []
                        
                        # Add apartments based on exact user input
                        for _ in range(bhk_1):
                            apartment_specifications.append({'bedrooms': 1, 'type': '1BHK'})
                        for _ in range(bhk_2):
                            apartment_specifications.append({'bedrooms': 2, 'type': '2BHK'})
                        for _ in range(bhk_3):
                            apartment_specifications.append({'bedrooms': 3, 'type': '3BHK'})
                        for _ in range(bhk_4):
                            apartment_specifications.append({'bedrooms': 4, 'type': '4BHK'})
                        
                        num_apartments = len(apartment_specifications)
                        if num_apartments <= 0:
                            raise ValueError(
                                'Select at least one apartment for the typical floor.'
                            )

                        # Validate apartment configuration
                        if num_apartments > 10:
                            raise ValueError(f"Too many apartments: {num_apartments} (maximum 10)")

                        # Log the exact specifications being used
                        print(f"🏗️ Frontend Inputs:")
                        print(f"   📐 Plot size: {plot_size} {area_unit}")
                        print(f"   🏠 Total apartments: {num_apartments}")
                        print(f"   📊 Exact specifications: {[spec['type'] for spec in apartment_specifications]}")
                        print(f"   🛏️ Bedroom distribution: {[spec['bedrooms'] for spec in apartment_specifications]}")
                        print(f"   🏗️ FSI: {fsi}, Floors: {floors}")
                        
                        # Convert area to square meters if needed
                        plot_size_sqm = plot_size
                        if area_unit == 'sqft':
                            plot_size_sqm = plot_size * 0.092903  # Convert sq ft to sq m
                            print(f"   🔄 Converted {plot_size} sq ft to {plot_size_sqm:.1f} sq m")
                        elif area_unit == 'acres':
                            plot_size_sqm = plot_size * 4046.86  # Convert acres to sq m
                            print(f"   🔄 Converted {plot_size} acres to {plot_size_sqm:.1f} sq m")
                        
                        # Validate plot size is reasonable
                        if plot_size_sqm < 50:
                            raise ValueError(f"Plot size too small: {plot_size_sqm:.1f} sq m (minimum 50 sq m)")
                        elif plot_size_sqm > 20000:
                            raise ValueError(f"Plot size too large: {plot_size_sqm:.1f} sq m (maximum 20,000 sq m)")
                        
                        print(f"   ✅ Using plot area: {plot_size_sqm:.1f} sq m")

                        print(f"   ✅ Using plot area: {plot_size_sqm:.1f} sq m")

                        # Create outputs folder
                        outputs_dir = os.path.join(UPLOAD_FOLDER, 'outputs')
                        os.makedirs(outputs_dir, exist_ok=True)

                        timestamp = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
                        base_name = f"boundary_{os.path.splitext(filename)[0]}_{timestamp}"
                        png_path = os.path.join(outputs_dir, base_name + '.png')
                        json_path = os.path.join(outputs_dir, base_name + '.json')
                        dxf_path = os.path.join(outputs_dir, base_name + '.dxf')

                        print(f"🎯 Generating layout with user specifications:")
                        print(f"   🖼️ Shape from: {filename}")
                        print(f"   📐 Exact area: {plot_size_sqm:.1f} sq m")
                        print(f"   🏠 Apartments: {num_apartments}")
                        print(f"   🏗️ Specifications: {', '.join([spec['type'] for spec in apartment_specifications])}")
                        print(f"   🏗️ Floors: {floors}, FSI: {fsi}")
                        
                        print(f"   🛗 Will include: Lift, Staircase, Lobby, Corridors")

                        apartment_bedroom_counts = [
                            specification['bedrooms'] for specification in apartment_specifications
                        ]
                        bedrooms_per_apt = apartment_bedroom_counts[0]
                        print(f"   ✅ Exact apartment mix: {apartment_bedroom_counts}")

                        layout = generator.generate_boundary_natural_layout(
                            boundary_image_path=image_path,
                            num_apartments=num_apartments,
                            bedrooms_per_apt=bedrooms_per_apt,
                            fsi=float(fsi) if fsi else 1.8,
                            ground_coverage=0.65,
                            floors=int(floors) if floors else 1,
                            target_area=float(plot_size_sqm),
                            apartment_bedroom_counts=apartment_bedroom_counts
                        )
                        
                        if layout:
                            print(f"✅ Layout generation successful!")
                            print(f"   📊 Built area: {layout.get('total_built_area', 0):.1f} sq m")
                            print(f"   📊 FSI utilized: {layout.get('fsi_utilized', 0):.2f}")
                            print(f"   📊 Coverage: {layout.get('ground_coverage_utilized', 0)*100:.1f}%")
                        else:
                            raise ValueError("Failed to generate apartment layout")

                        # Save layout JSON, visualization PNG and attempt DXF export
                        try:
                            generator.save_layout_data(layout, json_path)
                        except Exception as e:
                            debug_info['layout_save_error'] = str(e)

                        try:
                            generator.visualize_boundary_layout(layout, save_path=png_path)
                            output_image_path = png_path
                        except Exception as e:
                            debug_info['visualize_error'] = str(e)

                        try:
                            generator.export_to_dxf(layout, dxf_path)
                            output_dxf_path = dxf_path
                        except Exception as e:
                            # exporter may not be available, log error but continue
                            debug_info['dxf_export_error'] = str(e)
                            output_dxf_path = None

                        # set some basic layout metadata in debug
                        debug_info['boundary_natural'] = {
                            'num_apartments': layout.get('num_apartments') if layout else num_apartments,
                            'apartment_specifications': apartment_specifications,
                            'uniform_apartment_type': len(set(spec['bedrooms'] for spec in apartment_specifications)) == 1,
                            'has_circulation': layout.get('has_circulation', False) if layout else False,
                            'circulation_elements_count': len(layout.get('circulation_elements', [])) if layout else 0,
                            'circulation_types': [elem['type'] for elem in layout.get('circulation_elements', [])] if layout else [],
                            'total_built_area': layout.get('total_built_area') if layout else 0,
                            'plot_area': layout.get('plot_area') if layout else plot_size_sqm,
                            'input_plot_size': plot_size,
                            'input_area_unit': area_unit,
                            'converted_plot_size_sqm': plot_size_sqm,
                            'fsi_utilized': layout.get('fsi_utilized') if layout else 0,
                            'ground_coverage_utilized': layout.get('ground_coverage_utilized') if layout else 0,
                            'original_area_preserved': layout.get('original_area_preserved') if layout else False,
                            'specified_target_area': layout.get('specified_target_area') if layout else plot_size_sqm,
                            'png': output_image_path,
                            'json': json_path,
                            'dxf': output_dxf_path if 'output_dxf_path' in locals() else None
                        }
                    else:
                        missing_parts = []
                        if not os.path.exists(completebackend_dir):
                            missing_parts.append(f'CompleteBackend directory: {completebackend_dir}')
                        if not os.path.exists(generator_path):
                            missing_parts.append(f'Generator file: {generator_path}')
                        raise FileNotFoundError(f'Missing: {", ".join(missing_parts)}')
            except Exception as model_exc:
                debug_info['model_error'] = str(model_exc)
                output_image_path = None
                output_dxf_path = None

        if image and (
            not output_image_path
            or not os.path.isfile(output_image_path)
        ):
            generation_error = (
                debug_info.get('model_error')
                or debug_info.get('visualize_error')
                or 'The floor-plan generator did not create an output image.'
            )
            return jsonify({
                'success': False,
                'error': f'Floor-plan generation failed: {generation_error}',
                'debug': debug_info
            }), 422
        
        # Store all data in database
        conn = get_db()
        cursor = conn.execute('''INSERT INTO user_data (
            username, area_unit, plot_size, location, jurisdiction, rrr, number_of_roads,
            building_type, bhk_1, bhk_2, bhk_3, bhk_4, road_width, road_width_1, road_width_2, road_width_3, road_width_4,
            aai_height, per_floor_height, fsi, max_fsi, bua, max_bua, floors, fsi_per_floor, area_left, 
            zone_type, fsi_source, fsi_confidence, similarity_score,
            image_path, output_image_path, output_dxf_path, length, breadth, angle
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (username, area_unit, plot_size, location, jurisdiction, rrr, number_of_roads,
         building_type, bhk_1, bhk_2, bhk_3, bhk_4, road_width, road_width_1, road_width_2, road_width_3, road_width_4,
         aai_height, per_floor_height, fsi, max_fsi, bua, max_bua, floors, fsi_per_floor, area_left,
         zone_type, fsi_source, fsi_confidence, similarity_score,
         image_path, output_image_path, output_dxf_path, length, breadth, angle))
        
        submission_id = cursor.lastrowid
        conn.executemany(
            '''INSERT INTO submission_floorplan_variants (
                submission_id, variant_number, variant_name, image_path, json_path, dxf_path
            ) VALUES (?, ?, ?, ?, ?, ?)''',
            [
                (
                    submission_id,
                    result[0].get('design_variant', index),
                    result[0]['design_variant_name'],
                    result[1],
                    result[2],
                    result[3],
                )
                for index, result in enumerate(variant_results)
            ]
        )
        conn.commit()
        conn.close()
        
        # Construct accessible URLs for produced files (if any)
        image_url = None
        dxf_url = None
        try:
            if output_image_path and os.path.exists(output_image_path):
                rel_img = os.path.relpath(output_image_path, UPLOAD_FOLDER)
                image_url = url_for('serve_uploaded_file', filename=rel_img)
        except Exception:
            image_url = None

        try:
            if output_dxf_path and os.path.exists(output_dxf_path):
                rel_dxf = os.path.relpath(output_dxf_path, UPLOAD_FOLDER)
                dxf_url = url_for('serve_uploaded_file', filename=rel_dxf)
        except Exception:
            dxf_url = None

        return jsonify({
            'success': True,
            'message': 'Form submitted successfully!',
            'data': {
                'plot_size': plot_size,
                'plot_size_unit': area_unit,
                'plot_size_sqm': plot_size_sqm if 'plot_size_sqm' in locals() else plot_size,
                'num_apartments': num_apartments if 'num_apartments' in locals() else 0,
                'apartment_specifications': apartment_specifications if 'apartment_specifications' in locals() else [],
                'fsi': fsi,
                'max_fsi': max_fsi,
                'bua': bua,
                'max_bua': max_bua,
                'floors': floors,
                'per_floor_height': per_floor_height,
                'fsi_per_floor': fsi_per_floor,
                'area_left': area_left,
                'zone_type': zone_type,
                'fsi_source': fsi_source,
                'length': length,
                'breadth': breadth,
                'angle': angle,
                'output_image_url': image_url,
                'output_dxf_url': dxf_url,
                'output_page_url': url_for(
                    'output_submission_page', submission_id=submission_id
                )
            },
            'debug': debug_info
        })
        
    except Exception as e:
        debug_info['exception'] = str(e)
        debug_info['traceback'] = traceback.format_exc()
        return jsonify({'success': False, 'error': 'Internal server error', 'debug': debug_info}), 500

@app.route('/')
def home():
    return render_template('index.html')

# Page routes for navigation
@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')

@app.route('/register', methods=['GET'])
def register_page():
    return render_template('register.html')

@app.route('/main_form', methods=['GET'])
def main_form_page():
    return render_template('main_form.html')

# Profile page route
@app.route('/profile', methods=['GET'])
def profile_page():
    if not session.get('username'):
        return redirect(url_for('login_page'))
    username = session['username']
    conn = get_db()
    rows = conn.execute('''SELECT id, submission_date, area_unit, plot_size, location, jurisdiction, 
                          rrr, number_of_roads, building_type, bhk_1, bhk_2, bhk_3, bhk_4, aai_height, per_floor_height,
                          fsi, max_fsi, bua, max_bua, floors, fsi_per_floor, area_left, 
                          zone_type, fsi_source, fsi_confidence, image_path, output_image_path, output_dxf_path 
                          FROM user_data WHERE username = ? ORDER BY submission_date DESC''', (username,)).fetchall()
    conn.close()
    user_data = [dict(row) for row in rows]
    return render_template('profile.html', user_data=user_data)

# Logout route
@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('home'))

# Chatbot page route
@app.route('/chatbot', methods=['GET'])
def chatbot_page():
    return render_template('chatbot.html')

@app.route('/api/chatbot', methods=['POST'])
def chatbot_api():
    if not session.get('username'):
        return jsonify({'error': 'You must be logged in to use the chatbot.'}), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get('message'), str):
        return jsonify({'error': 'Send a JSON object with a message string.'}), 400

    message = payload['message'].strip()
    if not message:
        return jsonify({'error': 'Enter a question before sending.'}), 400
    if len(message) > 500:
        return jsonify({'error': 'Questions must be 500 characters or fewer.'}), 413

    history = [
        {'role': 'assistant' if turn.get('sender') == 'bot' else 'user',
         'content': str(turn.get('text', ''))[:2000]}
        for turn in payload.get('history', [])[-6:]
        if isinstance(turn, dict)
    ] if isinstance(payload.get('history'), list) else []

    # Ground answers in the user's most recent generated plan, when there is one.
    plan_facts = None
    conn = get_db()
    latest = conn.execute(
        'SELECT id FROM user_data WHERE username = ? AND output_image_path IS NOT NULL '
        'ORDER BY id DESC LIMIT 1',
        (session['username'],),
    ).fetchone()
    conn.close()
    if latest:
        layout, _ = _load_selected_layout(latest['id'], session['username'])
        if layout:
            plan_facts = _plan_facts(layout)

    return jsonify(chat(message, history, plan_facts))

# Route to get user's main_form data in JSON format
@app.route('/user_data_json')
def user_data_json():
    username = session.get('username')
    if not username:
        return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    rows = conn.execute('''SELECT * FROM user_data WHERE username = ? 
                          ORDER BY submission_date DESC''', (username,)).fetchall()
    conn.close()
    data = [dict(row) for row in rows]
    return jsonify(data)

@app.route('/uploads/<path:filename>')
def serve_uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# Download output image or text summary
@app.route('/download_output/<int:submission_id>', methods=['GET'])
def download_output(submission_id):
    if not session.get('username'):
        return redirect(url_for('login_page'))
    conn = get_db()
    entry = conn.execute(
        'SELECT * FROM user_data WHERE id = ? AND username = ?',
        (submission_id, session['username'])
    ).fetchone()
    conn.close()
    if not entry:
        return redirect(url_for('profile_page'))
    # Only download output image
    if entry['output_image_path'] and os.path.exists(entry['output_image_path']):
        return send_file(entry['output_image_path'], as_attachment=True)
    return "No output image available for download.", 404

# Output page route using location
@app.route('/output/<location>', methods=['GET'])
def output_page(location):
    if not session.get('username'):
        return redirect(url_for('login_page'))
    username = session['username']
    conn = get_db()
    entry = conn.execute('SELECT * FROM user_data WHERE username = ? AND location = ?', (username, location)).fetchone()
    conn.close()
    if not entry:
        return redirect(url_for('profile_page'))
    return _render_submission(entry)


def _render_submission(entry):
    entry = dict(entry)
    for path_field in ('image_path', 'output_image_path', 'output_dxf_path'):
        file_path = entry.get(path_field)
        if file_path and not os.path.isfile(file_path):
            entry[path_field] = None
    conn = get_db()
    rows = conn.execute(
        '''SELECT id, variant_number, variant_name, image_path, json_path, dxf_path
           FROM submission_floorplan_variants
           WHERE submission_id = ?
           ORDER BY variant_number''',
        (entry['id'],)
    ).fetchall()
    conn.close()
    variants = [
        dict(row) for row in rows
        if os.path.isfile(row['image_path'])
    ]
    active_image = entry.get('output_image_path')
    for variant in variants:
        variant['is_active'] = variant['image_path'] == active_image
        if variant['dxf_path'] and not os.path.isfile(variant['dxf_path']):
            variant['dxf_path'] = None
    active_variant = next(
        (variant for variant in variants if variant['is_active']),
        None,
    )
    architectural_review = None
    if active_variant and os.path.isfile(active_variant['json_path']):
        try:
            with open(active_variant['json_path'], encoding='utf-8') as layout_file:
                layout_data = json.load(layout_file)
            architectural_review = layout_data.get('architectural_review')
        except (OSError, json.JSONDecodeError) as exc:
            app.logger.warning(
                'Could not load generated-plan review for submission %s: %s',
                entry['id'],
                exc,
            )
    return render_template(
        'output.html',
        entry=entry,
        variants=variants,
        architectural_review=architectural_review,
    )


@app.route('/submission/<int:submission_id>', methods=['GET'])
def output_submission_page(submission_id):
    username = session.get('username')
    if not username:
        return redirect(url_for('login_page'))
    conn = get_db()
    entry = conn.execute(
        'SELECT * FROM user_data WHERE id = ? AND username = ?',
        (submission_id, username)
    ).fetchone()
    conn.close()
    if not entry:
        return redirect(url_for('profile_page'))
    return _render_submission(entry)


@app.route('/submission/<int:submission_id>/variant/<int:variant_id>', methods=['POST'])
def select_submission_variant(submission_id, variant_id):
    username = session.get('username')
    if not username:
        return redirect(url_for('login_page'))
    conn = get_db()
    variant = conn.execute(
        '''SELECT v.image_path, v.dxf_path
           FROM submission_floorplan_variants AS v
           JOIN user_data AS u ON u.id = v.submission_id
           WHERE v.id = ? AND v.submission_id = ? AND u.username = ?''',
        (variant_id, submission_id, username)
    ).fetchone()
    if not variant:
        conn.close()
        return redirect(url_for('profile_page'))
    if not os.path.isfile(variant['image_path']):
        conn.close()
        flash('That generated layout is no longer available.', 'error')
        return redirect(url_for('output_submission_page', submission_id=submission_id))
    conn.execute(
        '''UPDATE user_data
           SET output_image_path = ?, output_dxf_path = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ? AND username = ?''',
        (variant['image_path'], variant['dxf_path'], submission_id, username)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('output_submission_page', submission_id=submission_id))


def _load_selected_layout(submission_id, username):
    """Return (layout, None) for the user's selected variant, or (None, error response)."""
    conn = get_db()
    entry = conn.execute(
        '''SELECT id, output_image_path
           FROM user_data
           WHERE id = ? AND username = ?''',
        (submission_id, username),
    ).fetchone()
    if not entry:
        conn.close()
        return None, (jsonify({'error': 'Submission not found.'}), 404)

    variant = conn.execute(
        '''SELECT json_path
           FROM submission_floorplan_variants
           WHERE submission_id = ? AND image_path = ?''',
        (submission_id, entry['output_image_path']),
    ).fetchone()
    conn.close()
    if not variant or not variant['json_path']:
        return None, (jsonify({'error': 'No generated plan data is available for this submission.'}), 404)

    output_root = os.path.realpath(os.path.join(UPLOAD_FOLDER, 'outputs'))
    layout_path = os.path.realpath(variant['json_path'])
    if os.path.commonpath((output_root, layout_path)) != output_root:
        app.logger.error('Refusing to review layout outside generated output directory')
        return None, (jsonify({'error': 'The generated plan file is unavailable.'}), 404)

    try:
        with open(layout_path, encoding='utf-8') as layout_file:
            layout = json.load(layout_file)
    except (OSError, json.JSONDecodeError):
        app.logger.exception('Could not read generated plan for AI review')
        return None, (jsonify({'error': 'Could not read the generated plan data.'}), 500)

    return layout, None


def _plan_facts(layout):
    generator_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'CompleteBackend',
    )
    if generator_dir not in sys.path:
        sys.path.insert(0, generator_dir)
    from plan_quality import build_local_ai_input
    return build_local_ai_input(layout)


@app.route('/api/submission/<int:submission_id>/ai-review', methods=['POST'])
def review_submission_with_local_ai(submission_id):
    username = session.get('username')
    if not username:
        return jsonify({'error': 'You must be logged in to request a plan review.'}), 401

    layout, error = _load_selected_layout(submission_id, username)
    if error:
        return error

    from local_plan_ai import review_plan_locally

    try:
        review = review_plan_locally(_plan_facts(layout))
    except RuntimeError as exc:
        return jsonify({'error': str(exc)}), 503
    except Exception:
        app.logger.exception('Local AI floor-plan review failed')
        return jsonify({'error': 'Local AI review failed. Check the server log.'}), 500

    return jsonify({'review': review})


# Edit entry page route
@app.route('/edit/<location>', methods=['GET', 'POST'])
def edit_entry_page(location):
    if not session.get('username'):
        return redirect(url_for('login_page'))
    username = session['username']
    conn = get_db()
    entry = conn.execute('SELECT * FROM user_data WHERE username = ? AND location = ?', (username, location)).fetchone()
    
    if request.method == 'POST':
        # Extract all form fields
        area_unit = request.form.get('area_unit', 'sqmt')
        plot_size = float(request.form.get('plot_size', 0))
        new_location = request.form.get('location')
        jurisdiction = request.form.get('jurisdiction')
        rrr = request.form.get('rrr')
        number_of_roads = int(request.form.get('number_of_roads', 0))
        building_type = request.form.get('building_type')
        
        # Extract BHK selections
        bhk_1 = int(request.form.get('bhk_1', 0))
        bhk_2 = int(request.form.get('bhk_2', 0))
        bhk_3 = int(request.form.get('bhk_3', 0))
        bhk_4 = int(request.form.get('bhk_4', 0))
        
        # Extract road width fields
        road_width = request.form.get('road_width')
        road_width_1 = request.form.get('road_width_1')
        road_width_2 = request.form.get('road_width_2')
        road_width_3 = request.form.get('road_width_3')
        road_width_4 = request.form.get('road_width_4')
        
        # Convert road widths to float or None
        road_width = float(road_width) if road_width else None
        road_width_1 = float(road_width_1) if road_width_1 else None
        road_width_2 = float(road_width_2) if road_width_2 else None
        road_width_3 = float(road_width_3) if road_width_3 else None
        road_width_4 = float(road_width_4) if road_width_4 else None
        
        aai_height = float(request.form.get('aai_height', 0))
        per_floor_height = float(request.form.get('per_floor_height', 3.0))
        
        # Recalculate FSI, BUA, floors based on updated values
        # Simple FSI calculation based on road widths
        def get_fsi(road_width_val):
            if road_width_val < 6: return 1.0
            if road_width_val < 9: return 1.1
            if road_width_val < 12: return 1.3
            if road_width_val < 13.2: return 1.5
            if road_width_val < 18.3: return 1.8
            if road_width_val < 27.3: return 2.0
            if road_width_val < 37.3: return 2.5
            return 3.0
        
        # Calculate FSI based on widest road (fallback method)
        road_widths = [w for w in [road_width, road_width_1, road_width_2, road_width_3, road_width_4] if w is not None]
        fsi = get_fsi(max(road_widths)) if road_widths else 0
        max_fsi = fsi * 1.5  # Approximate additional FSI
        bua = plot_size * fsi
        max_bua = plot_size * max_fsi
        floors = int(aai_height / per_floor_height) if aai_height > 0 and per_floor_height > 0 else 0
        
        # Calculate FSI per floor and area left
        fsi_per_floor = 0
        area_left = 0
        if floors > 0:
            bua_in_sqft = bua * 10.764  # Always convert to sq ft
            fsi_per_floor = bua_in_sqft / floors
            total_bhk_area = (bhk_1 * 430) + (bhk_2 * 730) + (bhk_3 * 1100) + (bhk_4 * 1600)
            area_left = fsi_per_floor - total_bhk_area

        # Update all fields in database
        if new_location and building_type:
            # Check if there are significant changes that require regenerating floor plan
            significant_changes = (
                entry['area_unit'] != area_unit or
                entry['plot_size'] != plot_size or
                entry['location'] != new_location or
                entry['jurisdiction'] != jurisdiction or
                entry['bhk_1'] != bhk_1 or entry['bhk_2'] != bhk_2 or 
                entry['bhk_3'] != bhk_3 or entry['bhk_4'] != bhk_4 or
                entry['building_type'] != building_type or
                entry['number_of_roads'] != number_of_roads or
                entry['road_width'] != road_width or
                entry['road_width_1'] != road_width_1 or
                entry['road_width_2'] != road_width_2 or
                entry['road_width_3'] != road_width_3 or
                entry['road_width_4'] != road_width_4 or
                entry['rrr'] != rrr or
                entry['aai_height'] != aai_height or
                entry['per_floor_height'] != per_floor_height
            )
            
            # Variables for new floor plan generation
            new_output_image_path = (
                None if significant_changes else entry['output_image_path']
            )
            new_output_dxf_path = (
                None if significant_changes else entry['output_dxf_path']
            )
            new_variant_results = []
            
                    # If significant changes detected and original image exists, regenerate floor plan
            if significant_changes and entry['image_path'] and os.path.exists(entry['image_path']):
                print(f"🔄 Significant changes detected, regenerating floor plan...")
                print(f"   📐 New plot size: {plot_size} {area_unit}")
                print(f"   🏠 New apartments: {(bhk_1 + bhk_2 + bhk_3 + bhk_4)}")
                print(f"   🛏️ New BHK breakdown: 1BHK={bhk_1}, 2BHK={bhk_2}, 3BHK={bhk_3}, 4BHK={bhk_4}")
                
                # Convert area to square meters for consistency
                plot_size_sqm = plot_size
                if area_unit == 'sqft':
                    plot_size_sqm = plot_size * 0.092903
                    print(f"   🔄 Converted {plot_size} sq ft to {plot_size_sqm:.1f} sq m")
                elif area_unit == 'acres':
                    plot_size_sqm = plot_size * 4046.86
                    print(f"   🔄 Converted {plot_size} acres to {plot_size_sqm:.1f} sq m")
                elif area_unit not in {'sqmt', 'sqm'}:
                    raise ValueError('Unsupported plot area unit.')
                
                try:
                    # Use same logic as main form to regenerate floor plan
                    import importlib.util
                    import sys
                    project_root = os.path.dirname(os.path.dirname(__file__))
                    completebackend_dir = os.path.join(project_root, 'CompleteBackend')
                    generator_path = os.path.join(completebackend_dir, 'boundary_natural_generator.py')
                    
                    # Add CompleteBackend to Python path temporarily for imports
                    if completebackend_dir not in sys.path:
                        sys.path.insert(0, completebackend_dir)

                    if os.path.exists(generator_path) and os.path.exists(completebackend_dir):
                        spec = importlib.util.spec_from_file_location('boundary_natural_generator', generator_path)
                        gen_mod = importlib.util.module_from_spec(spec)
                        
                        try:
                            spec.loader.exec_module(gen_mod)
                            GeneratorClass = getattr(gen_mod, 'BoundaryNaturalGenerator')
                            generator = GeneratorClass()

                            # Calculate exact apartment configuration from edit form
                            apartment_specifications = []
                            
                            # Add apartments based on exact user input
                            for _ in range(bhk_1):
                                apartment_specifications.append({'bedrooms': 1, 'type': '1BHK'})
                            for _ in range(bhk_2):
                                apartment_specifications.append({'bedrooms': 2, 'type': '2BHK'})
                            for _ in range(bhk_3):
                                apartment_specifications.append({'bedrooms': 3, 'type': '3BHK'})
                            for _ in range(bhk_4):
                                apartment_specifications.append({'bedrooms': 4, 'type': '4BHK'})
                            
                            num_apartments = len(apartment_specifications)
                            if num_apartments <= 0:
                                raise ValueError(
                                    'Select at least one apartment for the typical floor.'
                                )
                            if num_apartments > 10:
                                raise ValueError(
                                    'Select no more than 10 apartments per typical floor.'
                                )

                            print(f"🔄 Regenerating with exact specifications: {[spec['type'] for spec in apartment_specifications]}")

                            # For regeneration, use the first apartment specification as representative
                            # TODO: Future enhancement for mixed apartment types in single layout
                            representative_bedrooms = apartment_specifications[0]['bedrooms']

                            # Create outputs folder
                            outputs_dir = os.path.join(UPLOAD_FOLDER, 'outputs')
                            os.makedirs(outputs_dir, exist_ok=True)

                            timestamp = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
                            original_filename = os.path.splitext(os.path.basename(entry['image_path']))[0]
                            base_name = f"boundary_{original_filename}_updated_{timestamp}"
                            png_path = os.path.join(outputs_dir, base_name + '.png')
                            json_path = os.path.join(outputs_dir, base_name + '.json')
                            dxf_path = os.path.join(outputs_dir, base_name + '.dxf')

                            # Generate layout using the original boundary image with exact area
                            layout = generator.generate_boundary_natural_layout(
                                boundary_image_path=entry['image_path'],
                                num_apartments=num_apartments,
                                bedrooms_per_apt=representative_bedrooms,
                                fsi=float(fsi),
                                ground_coverage=0.65,
                                floors=int(floors),
                                target_area=float(plot_size_sqm),
                                apartment_bedroom_counts=[
                                    specification['bedrooms']
                                    for specification in apartment_specifications
                                ],
                                design_variant=0
                            )

                            # Save layout JSON, visualization PNG and attempt DXF export
                            try:
                                generator.save_layout_data(layout, json_path)
                                generator.visualize_boundary_layout(layout, save_path=png_path)
                                new_output_image_path = png_path
                                print(f"✅ New floor plan image generated: {png_path}")
                            except Exception as e:
                                print(f"⚠️ Error generating PNG: {e}")

                            try:
                                generator.export_to_dxf(layout, dxf_path)
                                new_output_dxf_path = dxf_path
                                print(f"✅ New DXF file generated: {dxf_path}")
                            except Exception as e:
                                print(f"⚠️ Error generating DXF: {e}")

                            if not new_output_image_path or not os.path.isfile(new_output_image_path):
                                raise RuntimeError('The regenerated floor-plan image was not created.')
                            new_variant_results.append(
                                (layout, new_output_image_path, json_path, new_output_dxf_path)
                            )
                            for variant_number in (1, 2):
                                try:
                                    new_variant_results.append(generate_submission_floorplan(
                                        entry['image_path'],
                                        plot_size_sqm,
                                        [
                                            specification['bedrooms']
                                            for specification in apartment_specifications
                                        ],
                                        fsi,
                                        floors,
                                        design_variant=variant_number
                                    ))
                                except ValueError as variant_exc:
                                    app.logger.info(
                                        'Edited design variant %s rejected: %s',
                                        variant_number,
                                        variant_exc,
                                    )

                        except Exception as e:
                            print(f"❌ Error regenerating floor plan: {e}")
                            flash(f'Changes were not saved: {e}', 'error')
                    
                except Exception as e:
                    print(f"❌ Error during floor plan regeneration: {e}")
                    flash('Changes were not saved because floor-plan regeneration failed.', 'error')
                
                # Success message for regeneration
                if significant_changes and new_output_image_path:
                    flash('Floor plan regenerated successfully based on your changes!', 'success')
            
            elif significant_changes:
                print(f"⚠️ Significant changes detected but no original image found for regeneration")
                flash('Changes were not saved because the original plot image is unavailable.', 'error')
            else:
                flash('Changes saved successfully!', 'success')

            if significant_changes and (
                not new_output_image_path or not os.path.isfile(new_output_image_path)
            ):
                conn.close()
                return redirect(url_for('edit_entry_page', location=location))
            
            # Update database with new values and potentially new file paths
            conn.execute('''UPDATE user_data SET 
                area_unit = ?, plot_size = ?, location = ?, jurisdiction = ?, rrr = ?, 
                number_of_roads = ?, building_type = ?, bhk_1 = ?, bhk_2 = ?, bhk_3 = ?, bhk_4 = ?,
                road_width = ?, road_width_1 = ?, road_width_2 = ?, road_width_3 = ?, road_width_4 = ?,
                aai_height = ?, per_floor_height = ?, fsi = ?, max_fsi = ?, bua = ?, max_bua = ?, 
                floors = ?, fsi_per_floor = ?, area_left = ?, output_image_path = ?, output_dxf_path = ?, 
                updated_at = CURRENT_TIMESTAMP
                WHERE username = ? AND location = ?''',
                (area_unit, plot_size, new_location, jurisdiction, rrr, number_of_roads, building_type,
                 bhk_1, bhk_2, bhk_3, bhk_4, road_width, road_width_1, road_width_2, road_width_3, road_width_4,
                 aai_height, per_floor_height, fsi, max_fsi, bua, max_bua, floors, fsi_per_floor, area_left,
                 new_output_image_path, new_output_dxf_path, username, location))
            if significant_changes:
                conn.execute(
                    'DELETE FROM submission_floorplan_variants WHERE submission_id = ?',
                    (entry['id'],)
                )
                conn.executemany(
                    '''INSERT INTO submission_floorplan_variants (
                        submission_id, variant_number, variant_name, image_path, json_path, dxf_path
                    ) VALUES (?, ?, ?, ?, ?, ?)''',
                    [
                        (
                            entry['id'],
                            result[0].get('design_variant', index),
                            result[0]['design_variant_name'],
                            result[1],
                            result[2],
                            result[3],
                        )
                        for index, result in enumerate(new_variant_results)
                    ]
                )
            conn.commit()
            conn.close()
            return redirect(url_for('profile_page'))
    
    conn.close()
    return render_template('edit_entry.html', entry=entry)

# Delete entry route
@app.route('/delete/<location>', methods=['POST'])
def delete_entry(location):
    if not session.get('username'):
        return redirect(url_for('login_page'))
    username = session['username']
    conn = get_db()
    conn.execute('DELETE FROM user_data WHERE username = ? AND location = ?', (username, location))
    conn.commit()
    conn.close()
    return redirect(url_for('profile_page'))

if __name__ == '__main__':
    # Use debug=False for production or debug=True for development
    app.run(debug=False, host='127.0.0.1', port=5000)
