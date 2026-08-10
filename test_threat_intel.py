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
}
VALID_STAGES = {"current", "upcoming", "none"}


def validate_contract(result: dict) -> None:
    """Validates that output dictionary matches contract schema exactly."""
    missing = REQUIRED_KEYS - set(result.keys())
    assert not missing, f"Missing contract keys: {missing}"
    assert result["disruption_stage"] in VALID_STAGES, f"Invalid stage: {result['disruption_stage']}"
    assert isinstance(result["predicted_delay_hours"], (int, float)), "predicted_delay_hours must be numeric"
    assert isinstance(result["confidence"], (int, float)), "confidence must be numeric"
    assert isinstance(result["verified"], bool), "verified must be boolean"


def run_tests():
    print("=" * 60)
    print("Running Threat Intelligence Agent Test Suite")
    print("=" * 60)

    # -------------------------------------------------------------
    # Case 1: No threat nearby or on route
    # -------------------------------------------------------------
    truck_case_1 = {
        "truck_id": "TRK-101",
        "status": "moving",
        "current_location": "Mumbai",
        "destination": "Pune",
        "deadline": "2026-08-11T10:00:00Z"
    }
    result_1 = assess_threat(truck_case_1)
    validate_contract(result_1)
    assert result_1["disruption_stage"] == "none", f"Expected stage 'none', got '{result_1['disruption_stage']}'"
    assert result_1["predicted_delay_hours"] == 0.0, f"Expected 0.0 delay, got {result_1['predicted_delay_hours']}"
    print("\n[PASS] Case 1: No Threat Nearby / On Route")
    print(f"  Output: {result_1}")

    # -------------------------------------------------------------
    # Case 2: Truck already stopped with a confirmed nearby issue
    # -------------------------------------------------------------
    truck_case_2 = {
        "truck_id": "TRK-102",
        "status": "stopped",
        "current_location": "Kalyan",
        "destination": "Nashik",
        "deadline": "2026-08-11T14:00:00Z"
    }
    result_2 = assess_threat(truck_case_2)
    validate_contract(result_2)
    assert result_2["disruption_stage"] == "current", f"Expected stage 'current', got '{result_2['disruption_stage']}'"
    assert result_2["predicted_delay_hours"] > 0, "Expected positive predicted delay hours"
    print("\n[PASS] Case 2: Current Disruption (Stopped Truck)")
    print(f"  Output: {result_2}")

    # -------------------------------------------------------------
    # Case 3: Truck moving fine but a threat found further down route
    # -------------------------------------------------------------
    truck_case_3 = {
        "truck_id": "TRK-104",
        "status": "moving",
        "current_location": "Gurugram",
        "destination": "Jaipur",
        "deadline": "2026-08-11T18:00:00Z"
    }
    result_3 = assess_threat(truck_case_3)
    validate_contract(result_3)
    assert result_3["disruption_stage"] == "upcoming", f"Expected stage 'upcoming', got '{result_3['disruption_stage']}'"
    assert result_3["predicted_delay_hours"] > 0, "Expected positive predicted delay hours"
    print("\n[PASS] Case 3: Upcoming Disruption (Moving Truck, Threat Ahead)")
    print(f"  Output: {result_3}")

    print("\n" + "=" * 60)
    print("ALL 3 TEST CASES PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
