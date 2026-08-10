"""
Standalone test script for Fleet Monitor agent (agents/fleet_monitor.py).
Tests contract field compliance and status determination for normal vs abnormal stoppage.
"""

import sys
from agents.fleet_monitor import detect_disruption, STOPPED_DURATION_THRESHOLD_MINUTES

REQUIRED_CONTRACT_KEYS = {
    "truck_id",
    "location",
    "cargo_type",
    "destination",
    "deadline",
    "status",
    "delay_minutes",
    "last_updated",
}

REQUIRED_LOCATION_KEYS = {"lat", "lng", "name"}


def validate_contract_shape(result: dict):
    """Verifies that the returned dictionary matches the exact shape of Contract 1."""
    missing_keys = REQUIRED_CONTRACT_KEYS - set(result.keys())
    assert not missing_keys, f"Contract validation failed: missing keys {missing_keys}"
    
    assert isinstance(result["truck_id"], str), "truck_id must be str"
    assert isinstance(result["location"], dict), "location must be dict"
    
    missing_loc_keys = REQUIRED_LOCATION_KEYS - set(result["location"].keys())
    assert not missing_loc_keys, f"Location structure missing keys: {missing_loc_keys}"
    assert isinstance(result["location"]["lat"], (int, float)), "lat must be float/int"
    assert isinstance(result["location"]["lng"], (int, float)), "lng must be float/int"
    assert isinstance(result["location"]["name"], str), "name must be str"
    
    assert isinstance(result["cargo_type"], str), "cargo_type must be str"
    assert isinstance(result["destination"], str), "destination must be str"
    assert isinstance(result["deadline"], str), "deadline must be str"
    assert result["status"] in ("normal", "abnormal_stop"), f"Invalid status: {result['status']}"
    assert isinstance(result["delay_minutes"], int), "delay_minutes must be int"
    assert isinstance(result["last_updated"], str), "last_updated must be str"


def test_normal_telemetry():
    raw_telemetry = {
        "truck_id": "TRK-104",
        "location": {"lat": 19.076, "lng": 72.877, "name": "near Kalyan, MH"},
        "cargo_type": "perishable_produce",
        "destination": "Pune",
        "deadline": "2026-08-10T18:00:00",
        "stopped_duration_minutes": 10,  # Below threshold of 30 mins
        "delay_minutes": 0,
        "last_updated": "2026-08-08T14:22:00",
    }
    
    result = detect_disruption(raw_telemetry)
    validate_contract_shape(result)
    assert result["status"] == "normal", f"Expected 'normal', got '{result['status']}'"
    assert result["truck_id"] == "TRK-104"
    assert result["delay_minutes"] == 0
    
    print("=== Test Case 1: Normal Telemetry ===")
    print(f"Status: {result['status']}")
    print(f"Delay (mins): {result['delay_minutes']}")
    print("Contract match: PASSED\n")


def test_abnormal_stop_telemetry():
    raw_telemetry = {
        "truck_id": "TRK-105",
        "location": {"lat": 19.218, "lng": 73.102, "name": "NH-48 near Thane, MH"},
        "cargo_type": "pharmaceuticals",
        "destination": "Nashik",
        "deadline": "2026-08-11T12:00:00",
        "stopped_duration_minutes": 45,  # Exceeds threshold of 30 mins
        "delay_minutes": 45,
        "last_updated": "2026-08-08T14:30:00",
    }
    
    result = detect_disruption(raw_telemetry)
    validate_contract_shape(result)
    assert result["status"] == "abnormal_stop", f"Expected 'abnormal_stop', got '{result['status']}'"
    assert result["truck_id"] == "TRK-105"
    assert result["delay_minutes"] == 45
    
    print("=== Test Case 2: Abnormal Stop Telemetry ===")
    print(f"Status: {result['status']}")
    print(f"Delay (mins): {result['delay_minutes']}")
    print("Contract match: PASSED\n")


def run_all_tests():
    print(f"Running Fleet Monitor Agent Tests (Threshold: {STOPPED_DURATION_THRESHOLD_MINUTES} mins)...\n")
    test_normal_telemetry()
    test_abnormal_stop_telemetry()
    print("All fleet monitor contract tests passed!")


if __name__ == "__main__":
    run_all_tests()
