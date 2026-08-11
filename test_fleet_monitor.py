"""
Standalone test script for Fleet Monitor Agent (agents/fleet_monitor.py) - Standardized Dataset.
Loads mock fleet telemetry from data/mock_fleet.json and validates Contract 1 output schema.
"""

import json
import os
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

# Expected status mapping by truck ID for demo scenarios
EXPECTED_SCENARIOS = {
    "T107": {"expected_status": "abnormal_stop", "description": "Scenario 1: Reactive Abnormal Stop (Jaipur -> Mumbai)"},
    "T112": {"expected_status": "normal", "description": "Scenario 2: Proactive Risk Zone (Delhi -> Jaipur)"},
    "T101": {"expected_status": "normal", "description": "Scenario 3: Fully Clean Truck (Mumbai -> Pune)"},
    "TRK-107": {"expected_status": "abnormal_stop", "description": "Scenario 1: Reactive Abnormal Stop (Alias)"},
    "TRK-112": {"expected_status": "normal", "description": "Scenario 2: Proactive Risk Zone (Alias)"},
    "TRK-101": {"expected_status": "normal", "description": "Scenario 3: Fully Clean Truck (Alias)"},
    "TRK-102": {"expected_status": "abnormal_stop", "description": "Flood Waterlogging Abnormal Stop (Kalyan -> Nashik)"},
    "TRK-104": {"expected_status": "normal", "description": "Proactive Risk Zone (Rewari -> Jaipur)"},
    "TRK-105": {"expected_status": "abnormal_stop", "description": "Breakdown Abnormal Stop (Thane -> Delhi)"},
    "TRK-106": {"expected_status": "normal", "description": "Clean Truck (Solapur -> Hyderabad)"}
}


def validate_contract(output: dict) -> None:
    """Verifies that the output dictionary matches the exact Contract 1 schema."""
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

    json_path = os.path.join("data", "mock_fleet.json")
    print(f"Loading dataset from {json_path}...")
    
    assert os.path.exists(json_path), f"File not found: {json_path}"
    with open(json_path, "r", encoding="utf-8") as f:
        fleet_data = json.load(f)

    assert len(fleet_data) >= 3, f"Expected at least 3 mock records, found {len(fleet_data)}"

    for raw in fleet_data:
        truck_id = raw.get("truck_id", "UNKNOWN")
        scenario = EXPECTED_SCENARIOS.get(
            truck_id,
            {"expected_status": "normal", "description": f"Truck {truck_id}"}
        )
        
        print(f"\n--- Truck {truck_id} ({scenario['description']}) ---")
        result = detect_disruption(raw)
        validate_contract(result)

        exp_status = scenario["expected_status"]
        assert result["status"] == exp_status, (
            f"Test failed for {truck_id}: expected status '{exp_status}', got '{result['status']}'"
        )

        print(json.dumps(result, indent=2))
        print(f"Status: {result['status']} | Delay: {result['delay_minutes']} mins")
        print("Contract match: PASSED")

    print("\nSUCCESS: All mock fleet records passed Contract 1 validation!")


if __name__ == "__main__":
    main()
