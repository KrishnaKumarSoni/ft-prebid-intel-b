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

# Required columns for analysis
REQUIRED_COLUMNS = {
    'Origin cluster name': None,
    'Destination cluster name': None,
    'Vehicle Type (New)': None,
    'Shipper': None,
    'Transporter': None,
    'Rating': None
}

# Rating categories
RATING_CATEGORIES = {
    'Gold': 4.0,
    'Silver': 3.0,
    'Bronze': 0.0
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
    
    # Find indices of required columns
    column_indices = {}
    missing_columns = []
    for required_col in REQUIRED_COLUMNS:
        try:
            column_indices[required_col] = headers.index(required_col)
        except ValueError:
            missing_columns.append(required_col)
    
    if missing_columns:
        raise ValueError(f"Required columns missing in sheet: {', '.join(missing_columns)}")
    
    # Now get all data
    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range=f'{SHEET_NAME}!A2:Z',
        majorDimension='ROWS',
        valueRenderOption='UNFORMATTED_VALUE'
    ).execute()
    
    data = result.get('values', [])
    processed_data = []
    
    for row in data:
        # Skip empty rows
        if not row:
            continue
            
        # Create row dict with only required columns
        row_dict = {}
        valid_row = True
        
        for col_name, col_index in column_indices.items():
            # Check if the row has enough columns
            if col_index < len(row):
                row_dict[col_name] = row[col_index]
            else:
                # If a required column is missing in this row, skip the row
                valid_row = False
                break
        
        if valid_row:
            processed_data.append(row_dict)
    
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
    
    # Analyze the data
    analysis_results = {
        'avg_uploaded_shipper': 0,
        'avg_benchmark_shipper': 0,
        'total_matches': 0,
        'lane_differences': [],  # For top 5 display
        'all_lane_differences': [],  # Store all differences
        'savings_percent': 0,
        'savings_amount': 0,
        'insights': []
    }
    
    # Initialize totals for average calculations
    total_uploaded = 0
    total_benchmark = 0
    
    # Create lookup dictionaries and process data
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
    for row in benchmark_data:
        lookup_key = f"{row.get('Origin cluster name')}|{row.get('Destination cluster name')}|{row.get('Vehicle Type (New)')}"
        
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
                new_avg = (existing_avg * existing_count + shipper_rate) / (existing_count + 1)
                benchmark_lookup[lookup_key]['Shipper'] = new_avg
                benchmark_lookup[lookup_key]['count'] = existing_count + 1
            else:
                benchmark_lookup[lookup_key] = {
                    'Shipper': shipper_rate,
                    'count': 1,
                    'Origin cluster name': row.get('Origin cluster name'),
                    'Destination cluster name': row.get('Destination cluster name'),
                    'Vehicle Type (New)': row.get('Vehicle Type (New)')
                }
    
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
                
                # Create lane difference object
                lane_diff = {
                    'origin': uploaded_data['Origin cluster name'],
                    'destination': uploaded_data['Destination cluster name'],
                    'vehicle_type': uploaded_data['Vehicle Type (New)'],
                    'uploaded_rate': uploaded_avg,
                    'benchmark_rate': benchmark_avg,
                    'difference': diff_amount,
                    'difference_percent': diff_percent,
                    'uploaded_count': uploaded_data['count'],
                    'benchmark_count': benchmark_lookup[lookup_key]['count']
                }
                
                # Store in all lane differences
                analysis_results['all_lane_differences'].append(lane_diff)
                # Also store in lane_differences for top 5 display
                analysis_results['lane_differences'].append(lane_diff.copy())
    
    # Calculate average rates
    if analysis_results['total_matches'] > 0:
        analysis_results['avg_uploaded_shipper'] = total_uploaded / analysis_results['total_matches']
        analysis_results['avg_benchmark_shipper'] = total_benchmark / analysis_results['total_matches']
    
    # Calculate total savings based on averages
    if analysis_results['avg_uploaded_shipper'] > 0:
        analysis_results['savings_amount'] = analysis_results['avg_uploaded_shipper'] - analysis_results['avg_benchmark_shipper']
        analysis_results['savings_percent'] = (analysis_results['savings_amount'] / analysis_results['avg_uploaded_shipper'] * 100)
    
    # Sort and keep top 5 for display, but keep all differences in all_lane_differences
    analysis_results['lane_differences'].sort(key=lambda x: abs(x['difference']), reverse=True)
    analysis_results['lane_differences'] = analysis_results['lane_differences'][:5]
    
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
    positive_diffs = [lane for lane in analysis_results['all_lane_differences'] if lane['difference'] > 0]
    negative_diffs = [lane for lane in analysis_results['all_lane_differences'] if lane['difference'] < 0]
    
    if len(positive_diffs) > 0 and len(negative_diffs) > 0:
        pos_percent = (len(positive_diffs) / len(analysis_results['all_lane_differences']) * 100)
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

def get_transporters_for_lane(origin, destination):
    """Get top 5 transporters with their ratings and metrics for a specific lane"""
    data = get_sheet_data()
    
    # Filter data for the specific lane
    lane_data = [
        row for row in data 
        if row.get('Origin cluster name') == origin 
        and row.get('Destination cluster name') == destination
        and row.get('Transporter')
    ]
    
    # Create transporter summary
    transporter_summary = {}
    for row in lane_data:
        transporter = row['Transporter']
        try:
            rate = float(row['Shipper'])
            if rate <= 0:  # Skip invalid rates
                continue
            
            # Handle rating - could be empty or invalid
            rating = None
            try:
                if row.get('Rating'):
                    rating = float(row['Rating'])
                    if rating <= 0:  # Skip invalid ratings but keep the row
                        rating = None
            except (ValueError, TypeError):
                rating = None
                
        except (ValueError, TypeError):
            continue
            
        if transporter in transporter_summary:
            existing = transporter_summary[transporter]
            if rating is not None:
                existing['total_rating'] += rating
                existing['valid_ratings'] += 1
                existing['avg_rating'] = existing['total_rating'] / existing['valid_ratings']
            existing['total_rate'] += rate
            existing['trip_count'] += 1
            existing['avg_rate'] = existing['total_rate'] / existing['trip_count']
        else:
            summary = {
                'name': transporter,
                'total_rate': rate,
                'trip_count': 1,
                'avg_rate': rate,
                'total_rating': rating if rating is not None else 0,
                'valid_ratings': 1 if rating is not None else 0,
                'avg_rating': rating if rating is not None else None
            }
            transporter_summary[transporter] = summary
    
    # Convert to list and sort by average rating (if available) then by trip count
    transporters = list(transporter_summary.values())
    transporters.sort(key=lambda x: (x['avg_rating'] if x['avg_rating'] is not None else -1, x['trip_count']), reverse=True)
    
    # Get top 5 transporters and add tier
    top_transporters = transporters[:5]
    for t in top_transporters:
        if t['avg_rating'] is None:
            t['tier'] = 'Unrated'
        elif t['avg_rating'] > 4:
            t['tier'] = 'Gold'
        elif t['avg_rating'] >= 3:
            t['tier'] = 'Silver'
        else:
            t['tier'] = 'Bronze'
    
    return top_transporters

def get_vehicle_type_analysis(origin, destination):
    """Get detailed analysis by vehicle type for the lane"""
    data = get_sheet_data()
    
    # Filter data for the specific lane
    lane_data = [
        row for row in data 
        if row.get('Origin cluster name') == origin 
        and row.get('Destination cluster name') == destination
        and row.get('Vehicle Type (New)')
        and row.get('Transporter')
    ]
    
    # Analyze by vehicle type
    vehicle_analysis = {}
    for row in lane_data:
        vehicle_type = row['Vehicle Type (New)']
        transporter = row['Transporter']
        
        try:
            rate = float(row['Shipper'])
            if rate <= 0:  # Skip invalid rates
                continue
                
            # Handle rating - could be empty or invalid
            rating = None
            try:
                if row.get('Rating'):
                    rating = float(row['Rating'])
                    if rating <= 0:  # Skip invalid ratings but keep the row
                        rating = None
            except (ValueError, TypeError):
                rating = None
            
        except (ValueError, TypeError):
            continue
        
        if vehicle_type not in vehicle_analysis:
            vehicle_analysis[vehicle_type] = {
                'vehicle_type': vehicle_type,
                'transporters': set(),
                'total_trips': 0,
                'total_rating': 0,
                'total_rate': 0,
                'valid_ratings': 0  # Count for average rating calculation
            }
        
        analysis = vehicle_analysis[vehicle_type]
        analysis['transporters'].add(transporter)
        analysis['total_trips'] += 1
        if rating is not None:
            analysis['total_rating'] += rating
            analysis['valid_ratings'] += 1
        analysis['total_rate'] += rate
    
    # Calculate averages and convert sets to counts
    result = []
    for analysis in vehicle_analysis.values():
        result.append({
            'vehicle_type': analysis['vehicle_type'],
            'transporter_count': len(analysis['transporters']),
            'total_trips': analysis['total_trips'],
            'avg_rating': round(analysis['total_rating'] / analysis['valid_ratings'], 2) if analysis['valid_ratings'] > 0 else None,
            'avg_rate': round(analysis['total_rate'] / analysis['total_trips'], 2)
        })
    
    # Sort by total trips
    result.sort(key=lambda x: x['total_trips'], reverse=True)
    return result

@app.route('/get_transporter_analysis/<origin>/<destination>')
def get_transporter_analysis(origin, destination):
    try:
        data = get_sheet_data()
        
        # Filter data for the selected lane
        lane_data = [
            row for row in data 
            if row['Origin cluster name'] == origin 
            and row['Destination cluster name'] == destination
            and row['Transporter'] 
            and row['Rating']
        ]
        
        # Calculate transporter metrics
        transporter_metrics = {}
        for row in lane_data:
            transporter = row['Transporter']
            try:
                rate = float(row['Shipper'])
                rating = float(row['Rating'])
                vehicle_type = row['Vehicle Type (New)']
            except (ValueError, TypeError):
                continue
                
            if transporter not in transporter_metrics:
                transporter_metrics[transporter] = {
                    'trips': 0,
                    'total_rate': 0,
                    'total_rating': 0,
                    'rating': 0,
                    'avg_rate': 0,
                    'vehicle_types': set(),
                    'latest_rating': rating
                }
            
            metrics = transporter_metrics[transporter]
            metrics['trips'] += 1
            metrics['total_rate'] += rate
            metrics['total_rating'] += rating
            metrics['vehicle_types'].add(vehicle_type)
            metrics['rating'] = metrics['total_rating'] / metrics['trips']
            metrics['avg_rate'] = metrics['total_rate'] / metrics['trips']
        
        # Get top 5 transporters by rating
        top_transporters = []
        for transporter, metrics in transporter_metrics.items():
            rating = metrics['rating']
            category = 'Bronze'
            for cat, min_rating in RATING_CATEGORIES.items():
                if rating >= min_rating:
                    category = cat
                    break
                    
            top_transporters.append({
                'name': transporter,
                'rating': rating,
                'category': category,
                'trips': metrics['trips'],
                'avg_rate': metrics['avg_rate'],
                'vehicle_types': list(metrics['vehicle_types'])  # Add vehicle types to response
            })
        
        # Sort by rating and get top 5
        top_transporters.sort(key=lambda x: x['rating'], reverse=True)
        top_transporters = top_transporters[:5]
        
        # Calculate vehicle type metrics
        vehicle_type_metrics = {}
        for row in lane_data:
            vehicle_type = row['Vehicle Type (New)']
            if vehicle_type not in vehicle_type_metrics:
                vehicle_type_metrics[vehicle_type] = {
                    'transporters': set(),
                    'trips': 0,
                    'total_rating': 0,
                    'total_rate': 0
                }
            
            try:
                rate = float(row['Shipper'])
                rating = float(row['Rating'])
            except (ValueError, TypeError):
                continue
                
            metrics = vehicle_type_metrics[vehicle_type]
            metrics['transporters'].add(row['Transporter'])
            metrics['trips'] += 1
            metrics['total_rating'] += rating
            metrics['total_rate'] += rate
        
        # Calculate averages for vehicle types
        vehicle_type_summary = []
        for vehicle_type, metrics in vehicle_type_metrics.items():
            vehicle_type_summary.append({
                'vehicle_type': vehicle_type,
                'transporter_count': len(metrics['transporters']),
                'trips': metrics['trips'],
                'avg_rating': metrics['total_rating'] / metrics['trips'] if metrics['trips'] > 0 else 0,
                'avg_rate': metrics['total_rate'] / metrics['trips'] if metrics['trips'] > 0 else 0
            })
        
        # Sort vehicle type summary by number of trips
        vehicle_type_summary.sort(key=lambda x: x['trips'], reverse=True)
        
        # Add an "All Vehicle Types" summary
        total_trips = sum(vt['trips'] for vt in vehicle_type_summary)
        total_rate = sum(vt['avg_rate'] * vt['trips'] for vt in vehicle_type_summary)
        total_rating = sum(vt['avg_rating'] * vt['trips'] for vt in vehicle_type_summary)
        unique_transporters = set()
        for vt in vehicle_type_metrics.values():
            unique_transporters.update(vt['transporters'])
            
        if total_trips > 0:
            all_vehicle_types_summary = {
                'vehicle_type': 'All Vehicle Types',
                'transporter_count': len(unique_transporters),
                'trips': total_trips,
                'avg_rating': total_rating / total_trips,
                'avg_rate': total_rate / total_trips
            }
            vehicle_type_summary.insert(0, all_vehicle_types_summary)
        
        return jsonify({
            'top_transporters': top_transporters,
            'vehicle_type_summary': vehicle_type_summary
        })
        
    except Exception as e:
        print(f"Error in transporter analysis: {str(e)}")
        return jsonify({'error': 'Error analyzing transporter data'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5004) 