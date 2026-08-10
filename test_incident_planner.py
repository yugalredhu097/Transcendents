"""
Unit tests for Incident Planner agent (agents/incident_planner.py).
Validates Contract 3 input handling and Contract 4 output compliance.
"""

import sys
from unittest.mock import patch
from agents.incident_planner import generate_plan, fetch_osrm_route


def verify_contract_4(output: dict) -> None:
    """Verifies that output dictionary matches Contract 4 field for field."""
    required_fields = {
        "truck_id": (str,),
        "recommended_action": (str,),
        "reasoning": (str,),
        "estimated_delay_hours": (int, float),
        "estimated_cost": (int, float),
        "alternative_route": (dict,),
    }

    for field, expected_types in required_fields.items():
        assert field in output, f"Missing required Contract 4 field: '{field}'"
        assert isinstance(output[field], expected_types), (
            f"Field '{field}' has type {type(output[field])}, expected {expected_types}"
        )

    alt_route = output["alternative_route"]
    assert "distance_km" in alt_route, "Missing 'distance_km' in alternative_route"
    assert "duration_min" in alt_route, "Missing 'duration_min' in alternative_route"
    assert isinstance(alt_route["distance_km"], (int, float)), "'distance_km' must be numeric"
    assert isinstance(alt_route["duration_min"], (int, float)), "'duration_min' must be numeric"
    assert len(output["reasoning"]) > 10, "Reasoning text must be non-empty and descriptive"


def test_fleet_stoppage_escalation():
    """Test Case 1: Incident plan triggered by a fleet stoppage event (Fallback Path)."""
    mock_contract_3_fleet = {
        "truck_id": "TRK-104",
        "escalate": True,
        "reason": "stoppage_detected",
        "use_osrm": False,
        "fleet_output": {
            "truck_id": "TRK-104",
            "status": "stopped",
            "stoppage_duration_min": 45,
            "location": "NH48 KM 120",
            "cargo_type": "Pharmaceuticals",
            "deadline_hours_remaining": 4.0,
            "delay_penalty_per_hour": 500,
            "detour_distance_km": 62,
            "detour_duration_min": 95,
        },
        "threat_output": {
            "threat_detected": False,
        },
    }

    plan = generate_plan(mock_contract_3_fleet)
    verify_contract_4(plan)
    assert plan["truck_id"] == "TRK-104"
    assert plan["recommended_action"] == "reroute"
    assert "Pharmaceuticals" in plan["reasoning"] or "stoppage" in plan["reasoning"].lower()
    print("[PASS] Test Case 1: Fleet Stoppage Escalation (Fallback Path)")
    print(f"  - truck_id: {plan['truck_id']}")
    print(f"  - recommended_action: {plan['recommended_action']}")
    print(f"  - reasoning: {plan['reasoning']}")
    print(f"  - estimated_delay_hours: {plan['estimated_delay_hours']}")
    print(f"  - estimated_cost: {plan['estimated_cost']}")
    print(f"  - alternative_route: {plan['alternative_route']}")


def test_upcoming_threat_escalation():
    """Test Case 2: Incident plan triggered by an upcoming threat intel event (Fallback Path)."""
    mock_contract_3_threat = {
        "truck_id": "TRK-202",
        "escalate": True,
        "reason": "threat_upcoming",
        "use_osrm": False,
        "fleet_output": {
            "truck_id": "TRK-202",
            "status": "moving",
            "cargo_type": "Perishable Foods",
            "deadline_hours_remaining": 5.5,
        },
        "threat_output": {
            "truck_id": "TRK-202",
            "threat_detected": True,
            "threat_type": "Protest",
            "estimated_arrival_hours": 2.0,
            "threat_location": "NH48 KM 150",
            "suggested_detour_km": 75,
            "suggested_detour_min": 108,
            "base_cost_per_km": 10.0,
        },
    }

    plan = generate_plan(mock_contract_3_threat)
    verify_contract_4(plan)
    assert plan["truck_id"] == "TRK-202"
    assert plan["recommended_action"] == "reroute"
    assert "Protest" in plan["reasoning"]
    print("\n[PASS] Test Case 2: Threat Upcoming Escalation (Fallback Path)")
    print(f"  - truck_id: {plan['truck_id']}")
    print(f"  - recommended_action: {plan['recommended_action']}")
    print(f"  - reasoning: {plan['reasoning']}")
    print(f"  - estimated_delay_hours: {plan['estimated_delay_hours']}")
    print(f"  - estimated_cost: {plan['estimated_cost']}")
    print(f"  - alternative_route: {plan['alternative_route']}")


def test_osrm_real_call():
    """Test Case 3: Incident plan with real OSRM API call."""
    mock_contract_3 = {
        "truck_id": "TRK-104",
        "escalate": True,
        "reason": "threat_upcoming",
        "use_osrm": True,
        "start_coords": (72.8777, 19.0760),
        "end_coords": (73.8567, 18.5204),
        "fleet_output": {
            "truck_id": "TRK-104",
            "cargo_type": "High Value Goods",
            "deadline_hours_remaining": 6.0,
        },
        "threat_output": {
            "threat_detected": True,
            "threat_type": "Protest",
            "estimated_arrival_hours": 2.0,
        },
    }

    plan = generate_plan(mock_contract_3)
    verify_contract_4(plan)
    assert plan["truck_id"] == "TRK-104"
    assert plan["alternative_route"]["distance_km"] > 0
    assert plan["alternative_route"]["duration_min"] > 0
    print("\n[PASS] Test Case 3: Real OSRM API Call Path")
    print(f"  - truck_id: {plan['truck_id']}")
    print(f"  - alternative_route (Live OSRM): {plan['alternative_route']}")
    print(f"  - estimated_cost: {plan['estimated_cost']}")


def test_osrm_fallback_on_failure():
    """Test Case 4: Graceful fallback when OSRM API network call fails/times out."""
    mock_contract_3 = {
        "truck_id": "TRK-303",
        "escalate": True,
        "reason": "stoppage_detected",
        "use_osrm": True,
        "fleet_output": {
            "truck_id": "TRK-303",
            "stoppage_duration_min": 30,
            "cargo_type": "Electronics",
            "detour_distance_km": 50,
            "detour_duration_min": 80,
        },
        "threat_output": {"threat_detected": False},
    }

    with patch("agents.incident_planner.fetch_osrm_route", return_value=None):
        plan = generate_plan(mock_contract_3)
        verify_contract_4(plan)
        assert plan["truck_id"] == "TRK-303"
        assert plan["alternative_route"]["distance_km"] == 50
        assert plan["alternative_route"]["duration_min"] == 80
        print("\n[PASS] Test Case 4: OSRM Failure Fallback Path")
        print(f"  - truck_id: {plan['truck_id']}")
        print(f"  - alternative_route (Fallback): {plan['alternative_route']}")


if __name__ == "__main__":
    print("=== Testing Incident Planner Agent ===")
    try:
        test_fleet_stoppage_escalation()
        test_upcoming_threat_escalation()
        test_osrm_real_call()
        test_osrm_fallback_on_failure()
        print("\nContract 4 Field Validation: ALL PASSED (6/6 fields matched exactly)")
    except AssertionError as e:
        print(f"\n[FAIL] Assertion Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

