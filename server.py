import os
import csv
import time
from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_cors import CORS

app = Flask(__name__)
# Enable CORS for all routes
CORS(app)

# Configuration
DATA_FOLDER = './uploads'
STREET_GEOJSON = 'street_data.geojson'
METRO_CSV = 'metro_stations_exit_shadow_results.csv'
FOUNTAIN_CSV = 'water_fountains.csv'
BENCH_CSV = 'benches.csv'

# We only load CSVs into memory because they are small. 
# We DO NOT load the 300MB GeoJSON.
csv_data_store = {
    'metro': [],
    'fountains': [],
    'benches': []
}

def load_csv_data(filename):
    path = os.path.join(DATA_FOLDER, filename)
    if not os.path.exists(path):
        print(f"⚠️ Warning: {filename} not found.")
        return []
    
    try:
        data = []
        with open(path, 'r', encoding='utf-8-sig') as f:
            # Simple delimiter detection
            line = f.readline()
            delim = ';' if ';' in line else ','
            f.seek(0)
            reader = csv.DictReader(f, delimiter=delim)
            for row in reader:
                # Clean BOM and whitespace
                cleaned = {k.replace('\ufeff', '').strip(): v.strip() if v else v for k, v in row.items()}
                data.append(cleaned)
        print(f"✅ Loaded {len(data)} rows from {filename}")
        return data
    except Exception as e:
        print(f"❌ Error loading {filename}: {e}")
        return []

# Load CSVs on startup (Small files only)
csv_data_store['metro'] = load_csv_data(METRO_CSV)
csv_data_store['fountains'] = load_csv_data(FOUNTAIN_CSV)
csv_data_store['benches'] = load_csv_data(BENCH_CSV)

# --- ROUTES ---

@app.route('/')
def index():
    # Serves your frontend
    return send_file('index35.html')

@app.route('/api/all-data')
def get_all_data():
    """Serves small data and provides the link for the large GeoJSON"""
    return jsonify({
        'success': True,
        'metro': csv_data_store['metro'],
        'fountains': csv_data_store['fountains'],
        'benches': csv_data_store['benches'],
        'street_geojson_url': '/api/data/street-segments'
    })

@app.route('/api/data/street-segments')
def stream_geojson():
    """The 'Magic' Route: Sends 300MB+ without using Server RAM"""
    return send_from_directory(
        DATA_FOLDER, 
        STREET_GEOJSON, 
        mimetype='application/json',
        as_attachment=False
    )

@app.route('/api/data-status')
def get_status():
    return jsonify({
        'server_status': 'online',
        'files': {
            'geojson': os.path.exists(os.path.join(DATA_FOLDER, STREET_GEOJSON)),
            'metro': len(csv_data_store['metro']),
            'fountains': len(csv_data_store['fountains']),
            'benches': len(csv_data_store['benches'])
        }
    })

if __name__ == '__main__':
    # Ensure folder exists
    os.makedirs(DATA_FOLDER, exist_ok=True)
    
    # Handle Render's Port requirement
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)