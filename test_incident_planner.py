"""
Unit tests for Incident Planner agent (agents/incident_planner.py).
Validates Contract 3 input handling, candidate evaluation, Gemini mocking,
fallback paths, and Contract 4 output compliance across all operational scenarios.
"""

import sys
import json
from unittest.mock import patch
from agents.incident_planner import (
    generate_plan,
    fetch_osrm_route,
    calculate_route_cost_impact,
    PlanningService,
    LLMClient,
    JSONValidator,
    ContextBuilder,
    CandidateEvaluator,
)


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

    action = output["recommended_action"]
    valid_actions = {"reroute", "wait", "transfer_to_storage", "transfer_to_another_vehicle"}
    assert action in valid_actions, f"Invalid recommended_action '{action}', expected one of {valid_actions}"

    alt_route = output["alternative_route"]
    assert "distance_km" in alt_route, "Missing 'distance_km' in alternative_route"
    assert "duration_min" in alt_route, "Missing 'duration_min' in alternative_route"
    assert isinstance(alt_route["distance_km"], (int, float)), "'distance_km' must be numeric"
    assert isinstance(alt_route["duration_min"], (int, float)), "'duration_min' must be numeric"
    assert len(output["reasoning"]) > 10, "Reasoning text must be non-empty and descriptive"


# ============================================================================
# Original Contract Preservation Tests
# ============================================================================

def test_fleet_stoppage_escalation():
    """Test Case 1: Incident plan triggered by a fleet stoppage event."""
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
    assert "Pharmaceuticals" in plan["reasoning"] or "stoppage" in plan["reasoning"].lower()
    print("[PASS] Test Case 1: Fleet Stoppage Escalation")


def test_upcoming_threat_escalation():
    """Test Case 2: Incident plan triggered by an upcoming threat intel event."""
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
    assert "Protest" in plan["reasoning"] or "protest" in plan["reasoning"].lower()
    print("[PASS] Test Case 2: Threat Upcoming Escalation")


def test_osrm_real_call():
    """Test Case 3: Incident plan with real OSRM API call or live routing."""
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
    print("[PASS] Test Case 3: Real/Mocked OSRM API Call Path")


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
        print("[PASS] Test Case 4: OSRM Failure Fallback Path")


# ============================================================================
# Disruption Type & Cargo Sensitivity Tests
# ============================================================================

def test_disruption_scenarios():
    """Test Case 5: Various disruption types (Flood, Bridge collapse, Protest, Accident, Heavy Rain)."""
    disruptions = [
        ("flood", "Flood / Waterlogging"),
        ("bridge_collapse", "Bridge Collapse"),
        ("protest", "Political Protest"),
        ("accident", "Severe Highway Accident"),
        ("heavy_rain", "Heavy Rain & Low Visibility"),
    ]

    for d_code, d_name in disruptions:
        payload = {
            "truck_id": f"TRK-{d_code.upper()}",
            "escalate": True,
            "reason": f"threat_{d_code}",
            "use_osrm": False,
            "fleet_output": {
                "truck_id": f"TRK-{d_code.upper()}",
                "cargo_type": "General Cargo",
                "deadline_hours_remaining": 5.0,
            },
            "threat_output": {
                "threat_detected": True,
                "threat_type": d_name,
                "predicted_delay_hours": 4.0,
                "suggested_detour_km": 55,
                "suggested_detour_min": 85,
            },
        }

        plan = generate_plan(payload)
        verify_contract_4(plan)
        assert plan["truck_id"] == f"TRK-{d_code.upper()}"
        print(f"[PASS] Disruption Scenario: {d_name}")


def test_cargo_sensitivity_scenarios():
    """Test Case 6: Sensitive cargo types (Vaccines, Frozen Seafood, Hazardous Chemicals)."""
    cargo_test_cases = [
        ("Vaccines", 6.0, "high"),
        ("Frozen Seafood", 5.0, "high"),
        ("Hazardous Chemicals", 12.0, "high"),
    ]

    for cargo_name, shelf_h, priority in cargo_test_cases:
        payload = {
            "truck_id": "TRK-CARGO-TEST",
            "escalate": True,
            "reason": "threat_upcoming",
            "use_osrm": False,
            "fleet_output": {
                "truck_id": "TRK-CARGO-TEST",
                "cargo_type": cargo_name,
                "shelf_life_hours": shelf_h,
                "customer_priority": priority,
                "deadline_hours_remaining": 4.0,
            },
            "threat_output": {
                "threat_detected": True,
                "threat_type": "Bridge Damage",
                "predicted_delay_hours": 6.0,
                "suggested_detour_km": 40,
                "suggested_detour_min": 60,
            },
        }

        plan = generate_plan(payload)
        verify_contract_4(plan)
        print(f"[PASS] Cargo Sensitivity Scenario: {cargo_name}")


def test_warehouse_scenarios():
    """Test Case 7: Warehouse available vs unavailable for offloading."""
    payload_warehouse = {
        "truck_id": "TRK-WH-TEST",
        "escalate": True,
        "reason": "stoppage_detected",
        "use_osrm": False,
        "fleet_output": {
            "truck_id": "TRK-WH-TEST",
            "cargo_type": "Perishable Produce",
            "stoppage_duration_min": 180,
            "deadline_hours_remaining": 2.0,
            "shelf_life_hours": 3.0,
        },
        "threat_output": {"threat_detected": False},
    }

    plan = generate_plan(payload_warehouse)
    verify_contract_4(plan)
    print("[PASS] Warehouse Available/Storage Diversion Scenario")


def test_priority_and_deadline_scenarios():
    """Test Case 8: Low vs High Priority & Tight/Impossible Deadlines."""
    test_params = [
        ("TRK-TIGHT", 1.0, "high"),
        ("TRK-GENEROUS", 10.0, "low"),
    ]

    for tid, deadline_h, prio in test_params:
        payload = {
            "truck_id": tid,
            "escalate": True,
            "reason": "threat_upcoming",
            "use_osrm": False,
            "fleet_output": {
                "truck_id": tid,
                "cargo_type": "Industrial Spares",
                "customer_priority": prio,
                "deadline_hours_remaining": deadline_h,
            },
            "threat_output": {
                "threat_detected": True,
                "threat_type": "Protest",
                "predicted_delay_hours": 3.0,
                "suggested_detour_km": 45,
                "suggested_detour_min": 70,
            },
        }

        plan = generate_plan(payload)
        verify_contract_4(plan)
        assert plan["truck_id"] == tid
        print(f"[PASS] Priority/Deadline Scenario: {tid} (Priority={prio}, Deadline={deadline_h}h)")


# ============================================================================
# Gemini Mocking & Robustness Tests
# ============================================================================

def test_gemini_mock_success():
    """Test Case 9: Mock Gemini returning valid Contract 4 JSON output."""
    mock_llm_json = json.dumps({
        "truck_id": "TRK-GEMINI-01",
        "recommended_action": "reroute",
        "reasoning": "High-confidence Gemini analysis: Rerouting via secondary highway bypasses the protest while protecting cold-chain integrity.",
        "estimated_delay_hours": 1.5,
        "estimated_cost": 950,
        "alternative_route": {
            "distance_km": 60,
            "duration_min": 90
        }
    })

    payload = {
        "truck_id": "TRK-GEMINI-01",
        "escalate": True,
        "reason": "threat_upcoming",
        "use_osrm": False,
        "fleet_output": {
            "truck_id": "TRK-GEMINI-01",
            "cargo_type": "Vaccines",
            "deadline_hours_remaining": 6.0,
        },
        "threat_output": {
            "threat_detected": True,
            "threat_type": "Protest",
            "suggested_detour_km": 60,
            "suggested_detour_min": 90,
        },
    }

    with patch.object(LLMClient, "call_gemini", return_value=mock_llm_json):
        plan = generate_plan(payload)
        verify_contract_4(plan)
        assert plan["truck_id"] == "TRK-GEMINI-01"
        assert plan["recommended_action"] == "reroute"
        assert "Gemini" in plan["reasoning"]
        print("[PASS] Gemini Mock Success Scenario")


def test_gemini_mock_malformed_json_retry_and_fallback():
    """Test Case 10: Mock Gemini returning malformed JSON, triggering retry/fallback cleanly."""
    malformed_llm = "This is not valid JSON string"

    payload = {
        "truck_id": "TRK-MALFORMED-01",
        "escalate": True,
        "reason": "threat_upcoming",
        "use_osrm": False,
        "fleet_output": {
            "truck_id": "TRK-MALFORMED-01",
            "cargo_type": "Electronics",
            "deadline_hours_remaining": 5.0,
        },
        "threat_output": {
            "threat_detected": True,
            "threat_type": "Landslide",
            "suggested_detour_km": 50,
            "suggested_detour_min": 75,
        },
    }

    with patch.object(LLMClient, "call_gemini", return_value=malformed_llm):
        plan = generate_plan(payload)
        verify_contract_4(plan)
        assert plan["truck_id"] == "TRK-MALFORMED-01"
        print("[PASS] Gemini Malformed JSON Fallback Scenario")


if __name__ == "__main__":
    print("=== Running Incident Planner Comprehensive Unit Test Suite ===")
    try:
        test_fleet_stoppage_escalation()
        test_upcoming_threat_escalation()
        test_osrm_real_call()
        test_osrm_fallback_on_failure()
        test_disruption_scenarios()
        test_cargo_sensitivity_scenarios()
        test_warehouse_scenarios()
        test_priority_and_deadline_scenarios()
        test_gemini_mock_success()
        test_gemini_mock_malformed_json_retry_and_fallback()
        print("\n===================================================================")
        print(" ALL INCIDENT PLANNER UNIT TESTS PASSED SUCCESSFULLY! (10/10 Cases)")
        print("===================================================================")
    except AssertionError as e:
        print(f"\n[FAIL] Assertion Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


