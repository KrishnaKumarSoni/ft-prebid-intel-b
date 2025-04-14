from app import get_sheet_data

def debug_benchmark_data():
    print("Fetching benchmark data...")
    benchmark_data = get_sheet_data()
    print(f"Total benchmark rows: {len(benchmark_data)}")
    
    # Get unique vehicle types
    vehicle_types = set()
    for row in benchmark_data:
        vtype = row.get('Vehicle Type (New)')
        if vtype:
            vehicle_types.add(vtype)
    
    print(f"Total unique vehicle types: {len(vehicle_types)}")
    print("Sample vehicle types:")
    for vtype in sorted(list(vehicle_types))[:20]:
        print(f"  - {vtype}")
    
    # Check for cities
    origins = set()
    destinations = set()
    for row in benchmark_data:
        origin = row.get('Origin cluster name')
        dest = row.get('Destination cluster name')
        if origin:
            origins.add(origin)
        if dest:
            destinations.add(dest)
    
    print(f"\nTotal unique origins: {len(origins)}")
    print("Sample origins:")
    for origin in sorted(list(origins))[:10]:
        print(f"  - {origin}")
    
    print(f"\nTotal unique destinations: {len(destinations)}")
    print("Sample destinations:")
    for dest in sorted(list(destinations))[:10]:
        print(f"  - {dest}")
    
    # Find specific city keys
    print("\nSearching for Alwar and Amritsar related entries:")
    alwar_entries = 0
    amritsar_entries = 0
    
    for row in benchmark_data:
        origin = row.get('Origin cluster name', '').strip()
        if origin.lower() == 'alwar':
            alwar_entries += 1
        elif origin.lower() == 'amritsar':
            amritsar_entries += 1
    
    print(f"Alwar as origin: {alwar_entries} entries")
    print(f"Amritsar as origin: {amritsar_entries} entries")
    
    # Look for our specific truck types
    print("\nSearching for specific truck types:")
    truck_types_to_find = [
        '10W Truck 16 MT',
        '4W Pick Up 1.5 MT',
        'Truck_Open Body_10W_16 MT',
        'Pick Up Truck_Open Body_4W_1.5 MT'
    ]
    
    for truck_type in truck_types_to_find:
        count = sum(1 for row in benchmark_data if row.get('Vehicle Type (New)') == truck_type)
        print(f"  - {truck_type}: {count} entries")

if __name__ == "__main__":
    debug_benchmark_data() 