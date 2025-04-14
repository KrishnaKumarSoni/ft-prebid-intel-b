from flask import Flask, render_template, jsonify, send_file, request, session
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
import csv
import io
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from functools import lru_cache
import time
from datetime import datetime

load_dotenv()

app = Flask(__name__, 
            template_folder='app/templates',
            static_folder='app/static')
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')  # Add this line for session support

# Google Sheets API setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SERVICE_ACCOUNT_FILE = 'credentials.json'
SHEET_ID = os.getenv('GOOGLE_SHEET_ID')
SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME')
CACHE_TIMEOUT = 300  # Cache timeout in seconds (5 minutes)

# Sample file path
SAMPLE_FILE_PATH = 'PRE BID INTEL SAMPLE.csv'

# Cache for sheet data
sheet_data_cache = {
    'data': None,
    'timestamp': 0
}

def get_google_sheets_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('sheets', 'v4', credentials=creds, cache_discovery=True)
    return service

def get_sheet_data():
    # Check if cache is valid
    current_time = time.time()
    if sheet_data_cache['data'] is not None and current_time - sheet_data_cache['timestamp'] < CACHE_TIMEOUT:
        return sheet_data_cache['data']
    
    # Fetch new data if cache is invalid
    service = get_google_sheets_service()
    sheet = service.spreadsheets()
    
    # Get header row first
    header_result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range=f'{SHEET_NAME}!A1:Z1',
        majorDimension='ROWS'
    ).execute()
    
    headers = header_result.get('values', [[]])[0]
    print(f"Headers from sheet: {headers}")  # Debug log
    
    # Now get all data
    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range=f'{SHEET_NAME}!A2:Z',
        majorDimension='ROWS',
        valueRenderOption='UNFORMATTED_VALUE'
    ).execute()
    
    data = result.get('values', [])
    print(f"Total rows fetched from sheet: {len(data)}")  # Debug log
    
    # Create a list of dictionaries for easier data manipulation
    processed_data = []
    skipped_rows = 0
    target_odvt_rows = []
    
    for row in data:
        # Skip rows that are too short
        if len(row) < len(headers):
            skipped_rows += 1
            print(f"Skipping short row, got {len(row)} columns, need {len(headers)}")  # Debug log
            continue
            
        row_dict = {}
        for i, header in enumerate(headers):
            if i < len(row):
                row_dict[header] = row[i]
            else:
                row_dict[header] = None
        
        # Debug logging for our target ODVT
        if (row_dict.get('Origin cluster name') == 'Delhi' and 
            row_dict.get('Destination cluster name') == 'Chennai' and 
            row_dict.get('Vehicle Type (New)') == '32 FT_MXL_Close Body_Container_15 MT to 18 MT'):
            target_odvt_rows.append(row_dict)
            print(f"Found target ODVT row: {row_dict}")  # Debug log
        
        processed_data.append(row_dict)
    
    print(f"Processed {len(processed_data)} rows, skipped {skipped_rows} rows")  # Debug log
    if target_odvt_rows:
        print(f"\nFound {len(target_odvt_rows)} rows for target ODVT")
        for idx, row in enumerate(target_odvt_rows, 1):
            print(f"{idx}. Rate: {row.get('Shipper')}")
    
    # Update cache
    sheet_data_cache['data'] = processed_data
    sheet_data_cache['timestamp'] = current_time
    
    return processed_data

# Use lru_cache for frequently accessed filter data
@lru_cache(maxsize=128)
def get_origins():
    data = get_sheet_data()
    return sorted(list(set(row.get('Origin cluster name', '') for row in data 
                          if row.get('Origin cluster name') and row.get('Origin cluster name') != '#N/A')))

@lru_cache(maxsize=128)
def get_destinations_for_origin(origin):
    data = get_sheet_data()
    return sorted(list(set(
        row.get('Destination cluster name', '') for row in data 
        if row.get('Origin cluster name') == origin 
        and row.get('Destination cluster name') 
        and row.get('Destination cluster name') != '#N/A'
    )))

@lru_cache(maxsize=128)
def get_vehicle_types_for_origin_destination(origin, destination):
    data = get_sheet_data()
    return sorted(list(set(
        row.get('Vehicle Type (New)', '') for row in data 
        if row.get('Origin cluster name') == origin 
        and row.get('Destination cluster name') == destination 
        and row.get('Vehicle Type (New)') 
        and row.get('Vehicle Type (New)') != '#N/A'
    )))

def parse_csv_file(file_data):
    """Parse CSV file data into a list of dictionaries"""
    csv_data = []
    csv_file = io.StringIO(file_data.decode('utf-8'))
    csv_reader = csv.DictReader(csv_file)
    for row in csv_reader:
        csv_data.append(row)
    return csv_data

def analyze_rate_data(uploaded_data):
    """Analyze uploaded rate data compared to benchmark data from Google Sheets"""
    benchmark_data = get_sheet_data()
    
    # Create lookup key for both datasets (Origin + Destination + Vehicle Type)
    uploaded_lookup = {}
    for row in uploaded_data:
        lookup_key = f"{row.get('Origin cluster name')}|{row.get('Destination cluster name')}|{row.get('Vehicle Type (New)')}"
        
        # Convert shipper rate to numeric
        try:
            shipper_rate = float(row.get('Shipper', 0))
        except (ValueError, TypeError):
            shipper_rate = 0
            
        # Calculate running average for uploaded rates per ODVT
        if shipper_rate > 0:
            if lookup_key in uploaded_lookup:
                existing_count = uploaded_lookup[lookup_key]['count']
                existing_avg = uploaded_lookup[lookup_key]['Shipper']
                new_avg = (existing_avg * existing_count + shipper_rate) / (existing_count + 1)
                uploaded_lookup[lookup_key]['Shipper'] = new_avg
                uploaded_lookup[lookup_key]['count'] = existing_count + 1
            else:
                uploaded_lookup[lookup_key] = {
                    'Shipper': shipper_rate,
                    'count': 1,
                    'Origin cluster name': row.get('Origin cluster name'),
                    'Destination cluster name': row.get('Destination cluster name'),
                    'Vehicle Type (New)': row.get('Vehicle Type (New)')
                }
    
    # Create a benchmark lookup dictionary with averages
    benchmark_lookup = {}
    debug_rates = []  # For debugging specific ODVT
    target_odvt = "Delhi|Chennai|32 FT_MXL_Close Body_Container_15 MT to 18 MT"
    
    for row in benchmark_data:
        lookup_key = f"{row.get('Origin cluster name')}|{row.get('Destination cluster name')}|{row.get('Vehicle Type (New)')}"
        
        # Debug logging for our target ODVT
        if lookup_key == target_odvt:
            try:
                rate = float(row.get('Shipper', 0))
                if rate > 0:
                    debug_rates.append(rate)
                    print(f"Found rate for {lookup_key}: {rate}")
            except (ValueError, TypeError) as e:
                print(f"Error processing rate for {lookup_key}: {e}")
                print(f"Raw value: {row.get('Shipper')}")
        
        # Convert shipper rate to numeric
        try:
            shipper_rate = float(row.get('Shipper', 0))
        except (ValueError, TypeError):
            shipper_rate = 0
            continue  # Skip this row entirely if rate conversion fails
            
        # Only add to lookup if we have a valid shipper rate
        if shipper_rate > 0:
            if lookup_key in benchmark_lookup:
                existing_count = benchmark_lookup[lookup_key]['count']
                existing_avg = benchmark_lookup[lookup_key]['Shipper']
                # Fix average calculation
                new_avg = (existing_avg * existing_count + shipper_rate) / (existing_count + 1)
                benchmark_lookup[lookup_key]['Shipper'] = new_avg
                benchmark_lookup[lookup_key]['count'] = existing_count + 1
                
                # Debug logging for our target ODVT
                if lookup_key == target_odvt:
                    print(f"Updated average for {lookup_key}: {new_avg} (count: {existing_count + 1})")
            else:
                benchmark_lookup[lookup_key] = {
                    'Shipper': shipper_rate,
                    'count': 1,
                    'Origin cluster name': row.get('Origin cluster name'),
                    'Destination cluster name': row.get('Destination cluster name'),
                    'Vehicle Type (New)': row.get('Vehicle Type (New)')
                }
                
                # Debug logging for our target ODVT
                if lookup_key == target_odvt:
                    print(f"First rate for {lookup_key}: {shipper_rate}")
    
    # Debug summary for our target ODVT
    if debug_rates:
        print(f"\nDebug Summary for {target_odvt}:")
        print(f"Total rates found: {len(debug_rates)}")
        print(f"All rates: {sorted(debug_rates)}")
        print(f"Manual average: {sum(debug_rates)/len(debug_rates)}")
        if target_odvt in benchmark_lookup:
            print(f"Calculated average in lookup: {benchmark_lookup[target_odvt]['Shipper']}")
            print(f"Count in lookup: {benchmark_lookup[target_odvt]['count']}")
    
    # Analyze the data
    analysis_results = {
        'avg_uploaded_shipper': 0,
        'avg_benchmark_shipper': 0,
        'total_matches': 0,
        'lane_differences': [],
        'savings_percent': 0,
        'savings_amount': 0,
        'insights': []
    }
    
    # Calculate differences for matching lanes using averages
    total_uploaded = 0
    total_benchmark = 0
    
    # Compare averages for each ODVT
    for lookup_key, uploaded_data in uploaded_lookup.items():
        if lookup_key in benchmark_lookup:
            uploaded_avg = uploaded_data['Shipper']
            benchmark_avg = benchmark_lookup[lookup_key]['Shipper']
            
            if uploaded_avg > 0 and benchmark_avg > 0:
                total_uploaded += uploaded_avg
                total_benchmark += benchmark_avg
                analysis_results['total_matches'] += 1
                
                # Calculate difference between averages
                diff_amount = uploaded_avg - benchmark_avg
                diff_percent = (diff_amount / uploaded_avg * 100) if uploaded_avg > 0 else 0
                
                # Store lane difference for top differences analysis
                analysis_results['lane_differences'].append({
                    'origin': uploaded_data['Origin cluster name'],
                    'destination': uploaded_data['Destination cluster name'],
                    'vehicle_type': uploaded_data['Vehicle Type (New)'],
                    'uploaded_rate': uploaded_avg,
                    'benchmark_rate': benchmark_avg,
                    'difference': diff_amount,
                    'difference_percent': diff_percent,
                    'uploaded_count': uploaded_data['count'],
                    'benchmark_count': benchmark_lookup[lookup_key]['count']
                })
    
    # Calculate average rates
    if analysis_results['total_matches'] > 0:
        analysis_results['avg_uploaded_shipper'] = total_uploaded / analysis_results['total_matches']
        analysis_results['avg_benchmark_shipper'] = total_benchmark / analysis_results['total_matches']
    
    # Calculate total savings based on averages
    if analysis_results['avg_uploaded_shipper'] > 0:
        analysis_results['savings_amount'] = analysis_results['avg_uploaded_shipper'] - analysis_results['avg_benchmark_shipper']
        analysis_results['savings_percent'] = (analysis_results['savings_amount'] / analysis_results['avg_uploaded_shipper'] * 100)
    
    # Sort lane differences by absolute difference amount
    analysis_results['lane_differences'].sort(key=lambda x: abs(x['difference']), reverse=True)
    analysis_results['lane_differences'] = analysis_results['lane_differences'][:5]  # Keep top 5
    
    # Generate insights
    # 1. Overall savings insight
    if analysis_results['savings_amount'] > 0:
        analysis_results['insights'].append({
            'type': 'positive',
            'message': f"Overall potential savings of ₹{analysis_results['savings_amount']:,.2f} ({abs(analysis_results['savings_percent']):.2f}%) identified across all analyzed lanes."
        })
    else:
        analysis_results['insights'].append({
            'type': 'negative',
            'message': f"Your rates are lower than benchmark by ₹{abs(analysis_results['savings_amount']):,.2f} ({abs(analysis_results['savings_percent']):.2f}%) across all analyzed lanes."
        })
    
    # 2. Match rate insight
    match_percent = (analysis_results['total_matches'] / len(uploaded_data) * 100) if len(uploaded_data) > 0 else 0
    analysis_results['insights'].append({
        'type': 'neutral',
        'message': f"Analysis matched {analysis_results['total_matches']} out of {len(uploaded_data)} uploaded lanes ({match_percent:.2f}%)."
    })
    
    # 3. Top savings lanes insight
    if len(analysis_results['lane_differences']) > 0:
        top_lane = analysis_results['lane_differences'][0]
        analysis_results['insights'].append({
            'type': 'positive' if top_lane['difference'] > 0 else 'negative',
            'message': f"Highest rate differential found on {top_lane['origin']} to {top_lane['destination']} lane with {top_lane['vehicle_type']} ({abs(top_lane['difference_percent']):.2f}% difference)."
        })
    
    # 4. Distribution insight
    positive_diffs = [lane for lane in analysis_results['lane_differences'] if lane['difference'] > 0]
    negative_diffs = [lane for lane in analysis_results['lane_differences'] if lane['difference'] < 0]
    
    if len(positive_diffs) > 0 and len(negative_diffs) > 0:
        pos_percent = (len(positive_diffs) / len(analysis_results['lane_differences']) * 100)
        analysis_results['insights'].append({
            'type': 'neutral',
            'message': f"{len(positive_diffs)} lanes ({pos_percent:.1f}%) show potential savings, while {len(negative_diffs)} lanes have rates below benchmark."
        })
    
    # 5. Average savings per lane insight
    if analysis_results['total_matches'] > 0:
        avg_saving = analysis_results['savings_amount'] / analysis_results['total_matches']
        analysis_results['insights'].append({
            'type': 'positive' if avg_saving > 0 else 'negative',
            'message': f"Average {'saving' if avg_saving > 0 else 'cost difference'} per lane: ₹{abs(avg_saving):,.2f}."
        })
    
    return analysis_results

@app.route('/')
def index():
    origins = get_origins()
    return render_template('index.html', origins=origins)

@app.route('/get_destinations/<origin>')
def get_destinations(origin):
    if 'uploaded_data' not in session:
        return jsonify({'error': 'No uploaded data found'}), 400

    # Get destinations from uploaded data for this origin
    uploaded_destinations = set(
        row['Destination cluster name'] 
        for row in session['uploaded_data'] 
        if row['Origin cluster name'] == origin 
        and row['Destination cluster name'] 
        and row['Destination cluster name'] != '#N/A'
    )

    # Get destinations from Google Sheets for this origin
    google_sheet_destinations = get_destinations_for_origin(origin)

    # Return only destinations that exist in both sets
    common_destinations = sorted(list(uploaded_destinations.intersection(set(google_sheet_destinations))))
    
    return jsonify(common_destinations)

@app.route('/get_vehicle_types/<origin>/<destination>')
def get_vehicle_types(origin, destination):
    if 'uploaded_data' not in session:
        return jsonify({'error': 'No uploaded data found'}), 400

    # Get vehicle types from uploaded data for this origin-destination pair
    uploaded_vehicle_types = set(
        row['Vehicle Type (New)']  # Using the correct column name from your CSV
        for row in session['uploaded_data'] 
        if row['Origin cluster name'] == origin 
        and row['Destination cluster name'] == destination
        and row['Vehicle Type (New)'] 
        and row['Vehicle Type (New)'] != '#N/A'
    )

    # Get vehicle types from Google Sheets for this origin-destination pair
    google_sheet_vehicle_types = get_vehicle_types_for_origin_destination(origin, destination)

    # Return only vehicle types that exist in both sets
    common_vehicle_types = sorted(list(uploaded_vehicle_types.intersection(set(google_sheet_vehicle_types))))
    
    return jsonify(common_vehicle_types)

@app.route('/analyze_rates', methods=['POST'])
def analyze_rates():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'Please upload a CSV file'}), 400
    
    try:
        file_data = file.read()
        uploaded_data = parse_csv_file(file_data)
        
        # Store uploaded data in session for filter endpoints
        session['uploaded_data'] = uploaded_data
        
        results = analyze_rate_data(uploaded_data)
        
        # Get unique origins from uploaded data
        origins = sorted(list(set(row.get('Origin cluster name', '') for row in uploaded_data 
                              if row.get('Origin cluster name') and row.get('Origin cluster name') != '#N/A')))
        
        return jsonify({
            'results': results,
            'origins': origins
        })
    except Exception as e:
        print(f"Error processing file: {str(e)}")
        return jsonify({'error': 'Error processing file'}), 500

@app.route('/get_uploaded_destinations/<origin>')
def get_uploaded_destinations(origin):
    if 'uploaded_data' not in session:
        return jsonify({'error': 'No uploaded data found'}), 400
    
    uploaded_data = session['uploaded_data']
    destinations = sorted(list(set(
        row.get('Destination cluster name', '') 
        for row in uploaded_data 
        if row.get('Origin cluster name') == origin 
        and row.get('Destination cluster name') 
        and row.get('Destination cluster name') != '#N/A'
    )))
    
    return jsonify(destinations)

@app.route('/get_uploaded_vehicle_types/<origin>/<destination>')
def get_uploaded_vehicle_types(origin, destination):
    if 'uploaded_data' not in session:
        return jsonify({'error': 'No uploaded data found'}), 400
    
    uploaded_data = session['uploaded_data']
    vehicle_types = sorted(list(set(
        row.get('Vehicle Type', '') 
        for row in uploaded_data 
        if row.get('Origin cluster name') == origin 
        and row.get('Destination cluster name') == destination
        and row.get('Vehicle Type') 
        and row.get('Vehicle Type') != '#N/A'
    )))
    
    return jsonify(vehicle_types)

@app.route('/download_sample')
def download_sample():
    """Download the sample freight data file"""
    try:
        return send_file(SAMPLE_FILE_PATH, 
                         mimetype='text/csv',
                         as_attachment=True,
                         download_name='freight_data_sample.csv')
    except Exception as e:
        return str(e), 500

@app.route('/clear_cache')
def clear_cache():
    """Admin endpoint to clear the cache if needed"""
    get_origins.cache_clear()
    get_destinations_for_origin.cache_clear()
    get_vehicle_types_for_origin_destination.cache_clear()
    sheet_data_cache['data'] = None
    sheet_data_cache['timestamp'] = 0
    return jsonify({"status": "Cache cleared successfully"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5004) 