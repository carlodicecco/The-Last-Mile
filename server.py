# server.py - Serve ALL data from ./data/ folder automatically
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import json
import os
import math
import time
import csv

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Define data folder path
DATA_FOLDER = './uploads'

# File paths - ALL in the data folder
STREET_GEOJSON_PATH = os.path.join(DATA_FOLDER, 'street_data.geojson')
METRO_CSV_PATH = os.path.join(DATA_FOLDER, 'metro_stations_exit_shadow_results.csv')
FOUNTAIN_CSV_PATH = os.path.join(DATA_FOLDER, 'water_fountains.csv')
BENCH_CSV_PATH = os.path.join(DATA_FOLDER, 'benches.csv')

# Global variables
street_data = []
data_loaded = False

def load_geojson(file_path):
    """Load and preprocess GeoJSON data"""
    global street_data, data_loaded
    
    if not os.path.exists(file_path):
        print(f"No GeoJSON file found at {file_path}")
        data_loaded = False
        return 0
    
    print(f"Loading GeoJSON from {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        street_data = []
        feature_count = 0
        start_time = time.time()
        
        for idx, feature in enumerate(data['features']):
            try:
                props = feature['properties']
                geom = feature['geometry']
                
                if geom['type'] == 'LineString':
                    coords = geom['coordinates']
                    
                    if len(coords) >= 2:
                        # Calculate midpoint
                        lon1, lat1 = coords[0]
                        lon2, lat2 = coords[-1]
                        mid_lon = (lon1 + lon2) / 2
                        mid_lat = (lat1 + lat2) / 2
                        
                        # Store full data including coordinates
                        street_data.append({
                            'id': idx,
                            'mid_lon': mid_lon,
                            'mid_lat': mid_lat,
                            'coordinates': coords,  # Full line coordinates
                            'props': props
                        })
                        
                        feature_count += 1
                        
                        # Progress update for large files
                        if feature_count % 100000 == 0:
                            elapsed = time.time() - start_time
                            print(f"Loaded {feature_count} features... ({elapsed:.1f}s)")
                            
            except Exception as e:
                print(f"Error processing feature {idx}: {e}")
                continue
        
        elapsed = time.time() - start_time
        data_loaded = True
        print(f"✅ Successfully loaded {feature_count} street segments in {elapsed:.1f} seconds")
        return feature_count
        
    except Exception as e:
        print(f"❌ Error loading file: {e}")
        data_loaded = False
        return 0

def load_csv_data(file_path):
    """Load and process CSV file data"""
    if not os.path.exists(file_path):
        print(f"❌ CSV file not found: {file_path}")
        return None
    
    try:
        data = []
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            # Detect delimiter
            first_line = f.readline()
            delimiter = ';' if ';' in first_line else ','
            f.seek(0)  # Reset to beginning
            
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                # Clean up column names (remove BOM if present)
                cleaned_row = {}
                for key, value in row.items():
                    # Remove BOM character from column names
                    cleaned_key = key.replace('\ufeff', '').strip()
                    cleaned_row[cleaned_key] = value.strip() if value else value
                data.append(cleaned_row)
        
        print(f"✅ Loaded {len(data)} rows from {os.path.basename(file_path)}")
        if len(data) > 0:
            print(f"   Columns: {list(data[0].keys())}")
        return data
        
    except Exception as e:
        print(f"❌ Error loading CSV {file_path}: {e}")
        return None

# Load ALL data on startup
street_data_count = load_geojson(STREET_GEOJSON_PATH)
metro_data = load_csv_data(METRO_CSV_PATH)
fountain_data = load_csv_data(FOUNTAIN_CSV_PATH)
bench_data = load_csv_data(BENCH_CSV_PATH)

@app.route('/api/debug-metro-columns')
def debug_metro_columns():
    """Debug endpoint to check metro CSV columns"""
    if metro_data and len(metro_data) > 0:
        return jsonify({
            'columns': list(metro_data[0].keys()),
            'sample': metro_data[0],
            'count': len(metro_data)
        })
    return jsonify({'error': 'No metro data'})

@app.route('/api/street-data/summary')
def get_data_summary():
    """Get summary of loaded street data"""
    return jsonify({
        'loaded': data_loaded,
        'total_segments': len(street_data) if data_loaded else 0,
        'has_data': data_loaded,
        'file_exists': os.path.exists(STREET_GEOJSON_PATH)
    })

@app.route('/api/street-heatmap-points')
def get_heatmap_points():
    """Get points for heatmap visualization with current filter"""
    try:
        if not data_loaded or len(street_data) == 0:
            return jsonify({'points': [], 'error': 'No street data loaded'})
        
        # Get parameters
        time = request.args.get('time', '08:00')
        bounds = request.args.get('bounds')
        max_points = int(request.args.get('max', 10000))
        
        # Map time to field name
        time_field_map = {
            '08:00': 's_0621_08',
            '10:00': 's_0621_10',
            '12:00': 's_0621_12',
            '14:00': 's_0621_14',
            '16:00': 's_0621_16',
            '18:00': 's_0621_18'
        }
        
        field_name = time_field_map.get(time, 's_0621_08')
        filtered_data = street_data
        
        # Filter by bounds if provided
        if bounds:
            try:
                bounds_parts = [float(x) for x in bounds.split(',')]
                if len(bounds_parts) == 4:
                    min_lng, min_lat, max_lng, max_lat = bounds_parts
                    
                    filtered_data = [
                        d for d in street_data 
                        if min_lng <= d['mid_lon'] <= max_lng and min_lat <= d['mid_lat'] <= max_lat
                    ]
            except Exception as e:
                print(f"Bounds parsing error: {e}")
        
        # Prepare points
        points = []
        for data in filtered_data:
            try:
                shade_value = float(data['props'].get(field_name, 0))
                weight = shade_value / 36
                display_weight = max(weight, 0.001)
                
                points.append({
                    'lng': data['mid_lon'],
                    'lat': data['mid_lat'],
                    'count': display_weight,
                    'original_value': shade_value
                })
            except:
                continue
        
        # Smart sampling if too many points
        if len(points) > max_points:
            non_zero_points = [p for p in points if p['original_value'] > 0]
            zero_points = [p for p in points if p['original_value'] == 0]
            
            if non_zero_points:
                non_zero_sample = min(len(non_zero_points), max_points * 2 // 3)
                step_nz = max(1, len(non_zero_points) // non_zero_sample)
                sampled_nz = non_zero_points[::step_nz]
            else:
                sampled_nz = []
            
            zero_sample = min(len(zero_points), max_points - len(sampled_nz))
            if zero_points and zero_sample > 0:
                step_z = max(1, len(zero_points) // zero_sample)
                sampled_z = zero_points[::step_z]
            else:
                sampled_z = []
            
            points = sampled_nz + sampled_z
        
        # Prepare final response
        response_points = []
        for p in points:
            response_points.append({
                'lng': p['lng'],
                'lat': p['lat'],
                'count': p['count']
            })
        
        return jsonify({
            'points': response_points,
            'total': len(street_data),
            'displayed': len(response_points),
            'time': time,
            'bounds_filtered': bounds is not None,
            'sampled': len(response_points) != len(filtered_data),
            'field': field_name,
            'zero_count': len([p for p in points if p['original_value'] == 0])
        })
        
    except Exception as e:
        return jsonify({'error': str(e), 'points': []}), 500

@app.route('/api/street-segments')
def get_street_segments():
    """Get street segments for line visualization within radius of a point"""
    try:
        if not data_loaded or len(street_data) == 0:
            return jsonify({'segments': [], 'error': 'No street data loaded'})
        
        # Get parameters
        time = request.args.get('time', '08:00')
        center = request.args.get('center')
        radius = float(request.args.get('radius', 1000))  # Default 1km
        
        # Map time to field name
        time_field_map = {
            '08:00': 's_0621_08',
            '10:00': 's_0621_10',
            '12:00': 's_0621_12',
            '14:00': 's_0621_14',
            '16:00': 's_0621_16',
            '18:00': 's_0621_18'
        }
        
        field_name = time_field_map.get(time, 's_0621_08')
        
        # Parse center coordinates
        if not center:
            return jsonify({'error': 'Center coordinates required', 'segments': []})
        
        try:
            center_lng, center_lat = [float(x) for x in center.split(',')]
        except:
            return jsonify({'error': 'Invalid center coordinates format', 'segments': []})
        
        segments = []
        
        for data in street_data:
            try:
                # Calculate distance from center to segment midpoint
                distance = calculate_distance(center_lng, center_lat, data['mid_lon'], data['mid_lat'])
                
                if distance <= radius:
                    shade_value = float(data['props'].get(field_name, 0))
                    
                    segments.append({
                        'id': data['id'],
                        'coordinates': data['coordinates'],
                        'shade_coverage': shade_value,
                        'distance': distance
                    })
                    
            except Exception as e:
                print(f"Error processing segment {data.get('id', 'unknown')}: {e}")
                continue
        
        # Sort by distance (closest first)
        segments.sort(key=lambda x: x['distance'])
        
        # Limit to reasonable number for performance
        max_segments = 500
        if len(segments) > max_segments:
            segments = segments[:max_segments]
        
        return jsonify({
            'segments': segments,
            'total': len(street_data),
            'displayed': len(segments),
            'time': time,
            'center': {'lng': center_lng, 'lat': center_lat},
            'radius': radius,
            'field': field_name
        })
        
    except Exception as e:
        return jsonify({'error': str(e), 'segments': []}), 500

def calculate_distance(lng1, lat1, lng2, lat2):
    """Calculate distance between two points using Haversine formula"""
    from math import radians, sin, cos, sqrt, atan2
    
    R = 6371000  # Earth's radius in meters
    
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lng = radians(lng2 - lng1)
    
    a = sin(delta_lat/2) * sin(delta_lat/2) + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lng/2) * sin(delta_lng/2)
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c

# API endpoints for CSV data
@app.route('/api/metro-exits')
def get_metro_exits():
    """Serve metro exits CSV data"""
    if metro_data:
        return jsonify({
            'success': True,
            'data': metro_data,
            'count': len(metro_data)
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Metro data not loaded',
            'file_exists': os.path.exists(METRO_CSV_PATH)
        }), 404

@app.route('/api/water-fountains')
def get_water_fountains():
    """Serve water fountains CSV data"""
    if fountain_data:
        return jsonify({
            'success': True,
            'data': fountain_data,
            'count': len(fountain_data)
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Fountain data not loaded',
            'file_exists': os.path.exists(FOUNTAIN_CSV_PATH)
        }), 404

@app.route('/api/benches')
def get_benches():
    """Serve benches CSV data"""
    if bench_data:
        return jsonify({
            'success': True,
            'data': bench_data,
            'count': len(bench_data)
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Bench data not loaded',
            'file_exists': os.path.exists(BENCH_CSV_PATH)
        }), 404

@app.route('/api/data-status')
def get_data_status():
    """Check status of all data files"""
    return jsonify({
        'metro_data': {
            'loaded': metro_data is not None,
            'count': len(metro_data) if metro_data else 0,
            'file_exists': os.path.exists(METRO_CSV_PATH)
        },
        'fountain_data': {
            'loaded': fountain_data is not None,
            'count': len(fountain_data) if fountain_data else 0,
            'file_exists': os.path.exists(FOUNTAIN_CSV_PATH)
        },
        'bench_data': {
            'loaded': bench_data is not None,
            'count': len(bench_data) if bench_data else 0,
            'file_exists': os.path.exists(BENCH_CSV_PATH)
        },
        'street_data': {
            'loaded': data_loaded,
            'count': len(street_data) if data_loaded else 0,
            'file_exists': os.path.exists(STREET_GEOJSON_PATH)
        }
    })

# NEW: Endpoint to get ALL data at once
@app.route('/api/all-data')
def get_all_data():
    """Get all data at once for auto-loading"""
    return jsonify({
        'success': True,
        'metro': {
            'loaded': metro_data is not None,
            'data': metro_data if metro_data else [],
            'count': len(metro_data) if metro_data else 0
        },
        'fountains': {
            'loaded': fountain_data is not None,
            'data': fountain_data if fountain_data else [],
            'count': len(fountain_data) if fountain_data else 0
        },
        'benches': {
            'loaded': bench_data is not None,
            'data': bench_data if bench_data else [],
            'count': len(bench_data) if bench_data else 0
        },
        'street': {
            'loaded': data_loaded,
            'count': len(street_data) if data_loaded else 0,
            'available_times': ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00']
        }
    })

@app.route('/api/test')
def test_endpoint():
    """Simple test endpoint to verify server is running"""
    return jsonify({
        'status': 'ok',
        'message': 'Server is running',
        'timestamp': time.time()
    })

@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_file('index35.html')

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/debug-data')
def debug_data():
    """Debug endpoint to see what data is actually loaded"""
    return jsonify({
        'metro_actual_count': len(metro_data) if metro_data else 0,
        'metro_sample': metro_data[:3] if metro_data and len(metro_data) > 0 else [],
        'fountains_count': len(fountain_data) if fountain_data else 0,
        'benches_count': len(bench_data) if bench_data else 0,
        'street_count': len(street_data) if street_data else 0
    })

if __name__ == '__main__':
    os.makedirs(DATA_FOLDER, exist_ok=True)
    
    print("\n" + "="*50)
    print("Automatic Data Server")
    print("="*50)
    
    print("\nLoading data from ./data/ folder:")
    print(f"  Street data: {'✅ Loaded' if data_loaded else '❌ Not found'}")
    print(f"  Metro exits: {'✅ Loaded' if metro_data else '❌ Not found'}")
    print(f"  Water fountains: {'✅ Loaded' if fountain_data else '❌ Not found'}")
    print(f"  Benches: {'✅ Loaded' if bench_data else '❌ Not found'}")
    
    print("\nAPI Endpoints:")
    print("  GET /api/all-data             - Get all data at once")
    print("  GET /api/data-status          - Check data status")
    print("  GET /api/street-heatmap-points - Get heatmap points")
    print("\nInstructions:")
    print("  1. Place all data files in ./data/ folder")
    print("  2. Start server: python server.py")
    print("  3. Data loads automatically when page loads")
    print("="*50 + "\n")
    
    # Get the port from the environment variable 'PORT', default to 5000
    port = int(os.environ.get("PORT", 5000))
    # In production, we don't use app.run, but this keeps it working locally too
    app.run(host='0.0.0.0', port=port)
