"""
Standalone test script for Fleet Monitor Agent (agents/fleet_monitor.py)
"""

import json
import sys
from agents.fleet_monitor import detect_disruption

# Define required contract keys and expected types
REQUIRED_CONTRACT = {
    "truck_id": str,
    "location": dict,
    "cargo_type": str,
    "destination": str,
    "deadline": str,
    "status": str,
    "delay_minutes": int,
    "last_updated": str
}

LOCATION_CONTRACT = {
    "lat": (float, int),
    "lng": (float, int),
    "name": str
}


def validate_contract(output: dict) -> None:
    """Verifies that the output dictionary matches the exact contract schema."""
    for key, expected_type in REQUIRED_CONTRACT.items():
        assert key in output, f"Missing required key in contract: {key}"
        assert isinstance(output[key], expected_type), (
            f"Key '{key}' expected type {expected_type}, got {type(output[key])}"
        )

    loc = output["location"]
    for loc_key, loc_type in LOCATION_CONTRACT.items():
        assert loc_key in loc, f"Missing location key: {loc_key}"
        assert isinstance(loc[loc_key], loc_type), (
            f"Location key '{loc_key}' expected type {loc_type}, got {type(loc[loc_key])}"
        )


def main():
    print("==================================================")
    print(" Testing Fleet Monitor Agent: detect_disruption() ")
    print("==================================================\n")

    # Mock inputs
    sample_inputs = [
        {
            "truck_id": "TRK-104",
            "lat": 19.076,
            "lng": 72.877,
            "location_name": "near Kalyan, MH",
            "cargo_type": "perishable_produce",
            "destination": "Pune",
            "deadline": "2026-08-10T18:00:00",
            "speed_kmh": 0,
            "stop_duration_minutes": 47,
            "last_updated": "2026-08-08T14:22:00"
        },
        {
            "truck_id": "TRK-201",
            "lat": 18.989,
            "lng": 73.117,
            "location_name": "Panvel Expressway, MH",
            "cargo_type": "pharmaceuticals",
            "destination": "Satara",
            "deadline": "2026-08-11T12:00:00",
            "speed_kmh": 65,
            "stop_duration_minutes": 0,
            "last_updated": "2026-08-08T14:25:00"
        },
        {
            "truck_id": "TRK-305",
            "lat": 18.755,
            "lng": 73.409,
            "location_name": "near Lonavala, MH",
            "cargo_type": "industrial_machinery",
            "destination": "Solapur",
            "deadline": "2026-08-12T09:00:00",
            "speed_kmh": 5,
            "stop_duration_minutes": 35,
            "last_updated": "2026-08-08T14:20:00"
        }
    ]

    for idx, raw in enumerate(sample_inputs, 1):
        print(f"--- Mock Input {idx} (Truck: {raw['truck_id']}) ---")
        result = detect_disruption(raw)
        validate_contract(result)
        print(json.dumps(result, indent=2))
        print()

    print("SUCCESS: All outputs matched contract schema field for field!")


if __name__ == "__main__":
    main()
