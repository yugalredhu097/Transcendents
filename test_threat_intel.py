import json
import sys
from agents.threat_intel import assess_threat

REQUIRED_KEYS = {
    "truck_id",
    "disruption_type",
    "description",
    "source",
    "confidence",
    "verified",
    "disruption_stage",
    "predicted_delay_hours",
    "start_time",
    "expected_end_time",
    "affected_corridor",
    "severity",
}
VALID_STAGES = {"current", "upcoming", "none"}


def validate_12_field_contract(result: dict) -> None:
    """Validates that output dictionary matches the 12-field contract schema exactly."""
    missing = REQUIRED_KEYS - set(result.keys())
    assert not missing, f"Missing contract keys: {missing}"
    assert len(result.keys()) == 12, f"Expected exactly 12 fields in contract, found {len(result.keys())}: {list(result.keys())}"
    
    assert result["disruption_stage"] in VALID_STAGES, f"Invalid stage: {result['disruption_stage']}"
    assert isinstance(result["truck_id"], str), "truck_id must be str"
    assert isinstance(result["disruption_type"], str), "disruption_type must be str"
    assert isinstance(result["description"], str), "description must be str"
    assert isinstance(result["source"], str), "source must be str"
    assert isinstance(result["confidence"], (int, float)), "confidence must be numeric"
    assert isinstance(result["verified"], bool), "verified must be boolean"
    assert isinstance(result["predicted_delay_hours"], (int, float)), "predicted_delay_hours must be numeric"
    assert isinstance(result["start_time"], str), "start_time must be str"
    assert isinstance(result["expected_end_time"], str), "expected_end_time must be str"
    assert isinstance(result["affected_corridor"], str), "affected_corridor must be str"
    assert isinstance(result["severity"], str), "severity must be str"


def run_tests():
    print("=" * 67)
    print(" Running Threat Intelligence Agent 12-Field Contract Test Suite ")
    print("=" * 67)

    # -------------------------------------------------------------
    # Case 1: No threat nearby -> returns "disruption_stage": "none"
    # -------------------------------------------------------------
    truck_case_1 = {
        "truck_id": "TRK-999",
        "status": "moving",
        "current_location": "Mumbai",
        "destination": "Pune",
        "deadline": "2026-08-11T20:00:00Z"
    }

    result_case_1 = assess_threat(truck_case_1, force_api_failure=True)
    validate_12_field_contract(result_case_1)
    assert result_case_1["disruption_stage"] == "none", f"Expected 'none', got {result_case_1['disruption_stage']}"
    assert result_case_1["severity"] == "none"
    assert result_case_1["affected_corridor"] == "none"
    print("\n[PASS] Case 1: No Threat Nearby")
    print(f"  Output: {json.dumps(result_case_1, indent=2)}")

    # -------------------------------------------------------------
    # Case 2: Truck already stopped with a confirmed nearby issue -> "current"
    # -------------------------------------------------------------
    truck_case_2 = {
        "truck_id": "TRK-102",
        "status": "stopped",
        "current_location": "Kalyan",
        "destination": "Nashik",
        "deadline": "2026-08-11T14:00:00Z"
    }

    result_case_2 = assess_threat(truck_case_2, force_api_failure=True)
    validate_12_field_contract(result_case_2)
    assert result_case_2["disruption_stage"] == "current", f"Expected 'current', got {result_case_2['disruption_stage']}"
    assert result_case_2["disruption_type"] == "flood"
    assert result_case_2["severity"] == "high"
    assert result_case_2["affected_corridor"] == "NH-60"
    assert result_case_2["start_time"] == "2026-08-11T08:00:00"
    assert result_case_2["expected_end_time"] == "2026-08-12T12:00:00"
    print("\n[PASS] Case 2: Truck Already Stopped with Confirmed Nearby Issue")
    print(f"  Output: {json.dumps(result_case_2, indent=2)}")

    # -------------------------------------------------------------
    # Case 3: Truck moving fine but a threat found further down the route -> "upcoming"
    # -------------------------------------------------------------
    truck_case_3 = {
        "truck_id": "TRK-104",
        "status": "moving",
        "current_location": "Kalyan",
        "destination": "Pune",
        "deadline": "2026-08-11T18:00:00Z"
    }

    result_case_3 = assess_threat(truck_case_3, force_api_failure=True)
    validate_12_field_contract(result_case_3)
    assert result_case_3["disruption_stage"] == "upcoming", f"Expected 'upcoming', got {result_case_3['disruption_stage']}"
    assert result_case_3["disruption_type"] == "protest"
    assert result_case_3["severity"] == "high"
    assert result_case_3["affected_corridor"] == "NH-48 Mumbai-Pune Expressway"
    assert result_case_3["start_time"] == "2026-08-11T12:00:00"
    assert result_case_3["expected_end_time"] == "2026-08-11T17:00:00"
    print("\n[PASS] Case 3: Truck Moving Fine but Threat Found Further Down Route")
    print(f"  Output: {json.dumps(result_case_3, indent=2)}")

    print("\n" + "=" * 67)
    print(" ALL 3 THREAT INTEL 12-FIELD CONTRACT TEST CASES PASSED SUCCESSFULLY! ")
    print("=" * 67)


if __name__ == "__main__":
    run_tests()
