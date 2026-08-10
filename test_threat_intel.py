import sys
import unittest.mock as mock
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
    print("=" * 65)
    print("Running Threat Intelligence Agent Round 2 Test Suite")
    print("=" * 65)

    # -------------------------------------------------------------
    # Test Path 1: Successful Web Search API Integration Path
    # -------------------------------------------------------------
    truck_api_case = {
        "truck_id": "TRK-104",
        "status": "moving",
        "current_location": "Gurugram",
        "destination": "Jaipur",
        "deadline": "2026-08-11T18:00:00Z"
    }

    mock_api_response = {
        "disruption_type": "protest",
        "description": "Protest announced on NH-8 corridor near Jaipur",
        "source": "web_search_api",
        "confidence": 0.8,
        "verified": True,
        "disruption_stage": "upcoming",
        "predicted_delay_hours": 5.0
    }

    with mock.patch("agents.threat_intel.query_web_search_api", return_value=mock_api_response):
        result_api = assess_threat(truck_api_case, force_api_failure=False)
        validate_contract(result_api)
        assert result_api["source"] == "web_search_api", f"Expected 'web_search_api', got {result_api['source']}"
        assert result_api["disruption_stage"] == "upcoming"
        assert result_api["predicted_delay_hours"] == 5.0
        print("\n[PASS] Test Path 1: Web Search API Integration Path")
        print(f"  Output: {result_api}")

    # -------------------------------------------------------------
    # Test Path 2: API Failure & Hard Fallback to mock_disruptions.json
    # -------------------------------------------------------------
    truck_fallback_case = {
        "truck_id": "TRK-102",
        "status": "stopped",
        "current_location": "Kalyan",
        "destination": "Nashik",
        "deadline": "2026-08-11T14:00:00Z"
    }

    # Force API failure via force_api_failure=True flag AND via simulated API exception
    with mock.patch("agents.threat_intel.query_web_search_api", side_effect=RuntimeError("Web Search API timeout / connection error")):
        result_fallback = assess_threat(truck_fallback_case, force_api_failure=True)
        validate_contract(result_fallback)
        assert result_fallback["disruption_stage"] == "current"
        assert result_fallback["source"] == "mock_weather_api"
        assert result_fallback["predicted_delay_hours"] == 2.5
        print("\n[PASS] Test Path 2: API Failure & Hard Fallback to mock_disruptions.json")
        print(f"  Fallback Output: {result_fallback}")

    # -------------------------------------------------------------
    # Test Case 3: Default No Threat Fallback
    # -------------------------------------------------------------
    truck_no_threat = {
        "truck_id": "TRK-101",
        "status": "moving",
        "current_location": "Mumbai",
        "destination": "Pune",
        "deadline": "2026-08-11T10:00:00Z"
    }
    result_none = assess_threat(truck_no_threat, force_api_failure=True)
    validate_contract(result_none)
    assert result_none["disruption_stage"] == "none"
    assert result_none["predicted_delay_hours"] == 0.0
    print("\n[PASS] Test Case 3: Default No Threat Fallback")
    print(f"  Output: {result_none}")

    print("\n" + "=" * 65)
    print("ALL THREAT INTEL ROUND 2 TEST CASES PASSED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    run_tests()
