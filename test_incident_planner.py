"""
Unit tests for Incident Planner agent (agents/incident_planner.py).
Validates Contract 3 input handling and Contract 4 output compliance.
"""

import sys
from agents.incident_planner import generate_plan


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
    """Test Case 1: Incident plan triggered by a fleet stoppage event."""
    mock_contract_3_fleet = {
        "truck_id": "TRK-104",
        "escalate": True,
        "reason": "stoppage_detected",
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
    print("[PASS] Test Case 1: Fleet Stoppage Escalation")
    print(f"  - truck_id: {plan['truck_id']}")
    print(f"  - recommended_action: {plan['recommended_action']}")
    print(f"  - reasoning: {plan['reasoning']}")
    print(f"  - estimated_delay_hours: {plan['estimated_delay_hours']}")
    print(f"  - estimated_cost: {plan['estimated_cost']}")
    print(f"  - alternative_route: {plan['alternative_route']}")


def test_upcoming_threat_escalation():
    """Test Case 2: Incident plan triggered by an upcoming threat intel event."""
    mock_contract_3_threat = {
        "truck_id": "TRK-202",
        "escalate": True,
        "reason": "threat_upcoming",
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
    print("\n[PASS] Test Case 2: Threat Upcoming Escalation")
    print(f"  - truck_id: {plan['truck_id']}")
    print(f"  - recommended_action: {plan['recommended_action']}")
    print(f"  - reasoning: {plan['reasoning']}")
    print(f"  - estimated_delay_hours: {plan['estimated_delay_hours']}")
    print(f"  - estimated_cost: {plan['estimated_cost']}")
    print(f"  - alternative_route: {plan['alternative_route']}")


if __name__ == "__main__":
    print("=== Testing Incident Planner Agent ===")
    try:
        test_fleet_stoppage_escalation()
        test_upcoming_threat_escalation()
        print("\nContract 4 Field Validation: ALL PASSED (6/6 fields matched exactly)")
    except AssertionError as e:
        print(f"\n[FAIL] Assertion Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
