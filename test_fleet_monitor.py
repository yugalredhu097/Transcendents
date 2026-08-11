"""
Comprehensive test suite for Fleet Monitor Agent (agents/fleet_monitor.py).
Tests Contract 1 compliance, mock dataset integration, and edge-case boundary sanitization.
"""

import json
import os
import sys
from agents.fleet_monitor import (
    detect_disruption,
    STOPPED_DURATION_THRESHOLD_MINUTES,
    DEFAULT_TRUCK_ID,
    DEFAULT_CARGO_TYPE,
    DEFAULT_DESTINATION,
    DEFAULT_LOCATION_NAME
)

# Contract 1 validation schema
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

EXPECTED_DATASET_SCENARIOS = {
    "T107": {"expected_status": "abnormal_stop", "description": "Scenario 1: Reactive Abnormal Stop (Jaipur -> Mumbai)"},
    "T112": {"expected_status": "normal", "description": "Scenario 2: Proactive Risk Zone (Delhi -> Jaipur)"},
    "T101": {"expected_status": "normal", "description": "Scenario 3: Fully Clean Truck (Mumbai -> Pune)"},
    "TRK-107": {"expected_status": "abnormal_stop", "description": "Scenario 1: Reactive Abnormal Stop (Alias)"},
    "TRK-112": {"expected_status": "normal", "description": "Scenario 2: Proactive Risk Zone (Alias)"},
    "TRK-101": {"expected_status": "normal", "description": "Scenario 3: Fully Clean Truck (Alias)"},
    "TRK-102": {"expected_status": "abnormal_stop", "description": "Flood Waterlogging Abnormal Stop"},
    "TRK-104": {"expected_status": "normal", "description": "Proactive Risk Zone (Rewari -> Jaipur)"},
    "TRK-105": {"expected_status": "abnormal_stop", "description": "Breakdown Abnormal Stop"},
    "TRK-106": {"expected_status": "normal", "description": "Clean Truck (Solapur -> Hyderabad)"}
}


def validate_contract_schema(output: dict) -> None:
    """Validates Contract 1 shape and types strictly."""
    assert isinstance(output, dict), "Output must be a dictionary"
    for key, expected_type in REQUIRED_CONTRACT.items():
        assert key in output, f"Missing contract key: '{key}'"
        assert isinstance(output[key], expected_type), (
            f"Key '{key}' expected type {expected_type}, got {type(output[key])}"
        )

    loc = output["location"]
    for loc_key, loc_type in LOCATION_CONTRACT.items():
        assert loc_key in loc, f"Missing location contract key: '{loc_key}'"
        assert isinstance(loc[loc_key], loc_type), (
            f"Location key '{loc_key}' expected type {loc_type}, got {type(loc[loc_key])}"
        )


def test_mock_dataset_integration():
    """Validates all records in data/mock_fleet.json against Contract 1."""
    print("--- Test 1: Mock Dataset Integration (data/mock_fleet.json) ---")
    json_path = os.path.join("data", "mock_fleet.json")
    assert os.path.exists(json_path), f"File not found: {json_path}"
    with open(json_path, "r", encoding="utf-8") as f:
        fleet_data = json.load(f)

    assert len(fleet_data) >= 3, f"Expected at least 3 mock records, found {len(fleet_data)}"

    for raw in fleet_data:
        truck_id = raw.get("truck_id", "UNKNOWN")
        scenario = EXPECTED_DATASET_SCENARIOS.get(
            truck_id,
            {"expected_status": "normal", "description": f"Truck {truck_id}"}
        )

        result = detect_disruption(raw)
        validate_contract_schema(result)

        exp_status = scenario["expected_status"]
        assert result["status"] == exp_status, (
            f"Test failed for {truck_id}: expected '{exp_status}', got '{result['status']}'"
        )
        print(f"  [PASS] {truck_id} ({scenario['description']}) -> status: '{result['status']}'")

    print("[PASS] Mock dataset integration test passed!\n")


def test_boundary_thresholds():
    """Tests exact boundary thresholds (30 mins -> normal, 31 mins -> abnormal_stop)."""
    print("--- Test 2: Boundary Threshold Evaluation ---")

    # Exactly 30 mins (threshold) -> normal
    at_threshold = {
        "truck_id": "TRK-BOUND-30",
        "stopped_duration_minutes": 30,
        "location": {"lat": 19.076, "lng": 72.877, "name": "Kalyan Toll"}
    }
    res30 = detect_disruption(at_threshold)
    validate_contract_schema(res30)
    assert res30["status"] == "normal", f"Expected 'normal', got '{res30['status']}'"
    print("  [PASS] Exactly 30 mins stopped duration -> status: 'normal'")

    # Exceeding threshold (31 mins) -> abnormal_stop
    above_threshold = {
        "truck_id": "TRK-BOUND-31",
        "stopped_duration_minutes": 31,
        "location": {"lat": 19.076, "lng": 72.877, "name": "Kalyan Toll"}
    }
    res31 = detect_disruption(above_threshold)
    validate_contract_schema(res31)
    assert res31["status"] == "abnormal_stop", f"Expected 'abnormal_stop', got '{res31['status']}'"
    print("  [PASS] 31 mins stopped duration -> status: 'abnormal_stop'\n")


def test_corrupted_and_out_of_bounds_gps():
    """Tests resilience against non-numeric and out-of-bounds GPS coordinates."""
    print("--- Test 3: Corrupted & Out-of-Bounds Geolocation Sanitization ---")

    corrupted_gps = {
        "truck_id": "TRK-BAD-GPS",
        "location": {"lat": "invalid_string", "lng": "corrupted", "name": "Unknown Bridge"},
        "stopped_duration_minutes": 0
    }
    res_bad = detect_disruption(corrupted_gps)
    validate_contract_schema(res_bad)
    assert res_bad["location"]["lat"] == 0.0
    assert res_bad["location"]["lng"] == 0.0
    print("  [PASS] Non-numeric lat/lng safely sanitized to 0.0")

    out_of_bounds_gps = {
        "truck_id": "TRK-OOB-GPS",
        "lat": 999.0,
        "lng": -500.0,
        "location_name": "Out of Bounds Node",
        "stopped_duration_minutes": 0
    }
    res_oob = detect_disruption(out_of_bounds_gps)
    validate_contract_schema(res_oob)
    assert res_oob["location"]["lat"] == 0.0
    assert res_oob["location"]["lng"] == 0.0
    print("  [PASS] Out-of-bounds lat/lng (999.0, -500.0) safely clamped to 0.0\n")


def test_negative_values_and_malformed_input():
    """Tests negative delays/stop durations and null/empty inputs."""
    print("--- Test 4: Negative Values & Malformed Inputs ---")

    negative_input = {
        "truck_id": "TRK-NEG",
        "stopped_duration_minutes": -45,
        "delay_minutes": -20,
        "location": {"lat": 19.0, "lng": 72.0, "name": "Expressway Point"}
    }
    res_neg = detect_disruption(negative_input)
    validate_contract_schema(res_neg)
    assert res_neg["delay_minutes"] == 0
    assert res_neg["status"] == "normal"
    print("  [PASS] Negative stop duration and delay clamped to 0")

    # Null / Empty telemetry dictionary
    res_null = detect_disruption(None)
    validate_contract_schema(res_null)
    assert res_null["truck_id"] == DEFAULT_TRUCK_ID
    assert res_null["cargo_type"] == DEFAULT_CARGO_TYPE
    assert res_null["destination"] == DEFAULT_DESTINATION
    assert res_null["status"] == "normal"
    print("  [PASS] None telemetry input handled safely with defaults without crashing\n")


def run_all_tests():
    print("==================================================")
    print(f" Testing Upgraded Fleet Monitor Agent (Threshold: {STOPPED_DURATION_THRESHOLD_MINUTES} mins) ")
    print("==================================================\n")

    test_mock_dataset_integration()
    test_boundary_thresholds()
    test_corrupted_and_out_of_bounds_gps()
    test_negative_values_and_malformed_input()

    print("==================================================")
    print(" ALL FLEET MONITOR UNIT & INTEGRATION TESTS PASSED ")
    print("==================================================")


if __name__ == "__main__":
    run_all_tests()
