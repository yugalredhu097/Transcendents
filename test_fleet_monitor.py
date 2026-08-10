"""
Standalone test script for Fleet Monitor Agent (agents/fleet_monitor.py)
"""

import json
import sys
from agents.fleet_monitor import detect_disruption, STOPPED_DURATION_THRESHOLD_MINUTES

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
    print(f" Testing Fleet Monitor Agent (Threshold: {STOPPED_DURATION_THRESHOLD_MINUTES} mins) ")
    print("==================================================\n")

    sample_inputs = [
        {
            "truck_id": "TRK-104",
            "location": {"lat": 19.076, "lng": 72.877, "name": "near Kalyan, MH"},
            "cargo_type": "perishable_produce",
            "destination": "Pune",
            "deadline": "2026-08-10T18:00:00",
            "stopped_duration_minutes": 10,  # <= 30 mins -> normal
            "delay_minutes": 0,
            "last_updated": "2026-08-08T14:22:00"
        },
        {
            "truck_id": "TRK-105",
            "lat": 19.218,
            "lng": 73.102,
            "location_name": "NH-48 near Thane, MH",
            "cargo_type": "pharmaceuticals",
            "destination": "Nashik",
            "deadline": "2026-08-11T12:00:00",
            "stop_duration_minutes": 45,  # > 30 mins -> abnormal_stop
            "last_updated": "2026-08-08T14:30:00"
        },
        {
            "truck_id": "TRK-201",
            "lat": 18.989,
            "lng": 73.117,
            "location_name": "Panvel Expressway, MH",
            "cargo_type": "electronics",
            "destination": "Satara",
            "deadline": "2026-08-11T12:00:00",
            "stop_duration_minutes": 0,  # <= 30 mins -> normal
            "last_updated": "2026-08-08T14:25:00"
        }
    ]

    expected_statuses = ["normal", "abnormal_stop", "normal"]

    for idx, (raw, exp_status) in enumerate(zip(sample_inputs, expected_statuses), 1):
        print(f"--- Mock Input {idx} (Truck: {raw['truck_id']}) ---")
        result = detect_disruption(raw)
        validate_contract(result)
        assert result["status"] == exp_status, (
            f"Test {idx} failed: expected status '{exp_status}', got '{result['status']}'"
        )
        print(json.dumps(result, indent=2))
        print(f"Result: PASSED (status: {result['status']})\n")

    print("SUCCESS: All outputs matched contract schema field for field!")


if __name__ == "__main__":
    main()
