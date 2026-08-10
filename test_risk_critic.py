"""
Test script for Risk Critic Agent Round 2 (P4: Shivansh)
"""
import json
from agents.risk_critic import evaluate_risk


def run_tests():
    print("--- Running Risk Critic Agent Tests ---\n")

    # Test Case 1: Standard acceptable reroute plan (Contract 4 sample input)
    case1 = {
        "truck_id": "TRK-104",
        "recommended_action": "reroute",
        "reasoning": "Protest expected in ~2 hours on current route; alternate adds 1.5h, still within deadline",
        "estimated_delay_hours": 1.5,
        "estimated_cost": 850,
        "alternative_route": {"distance_km": 62, "duration_min": 95}
    }

    out1 = evaluate_risk(case1)
    print("Test Case 1 (Expected: ACCEPT):")
    print(json.dumps(out1, indent=2))
    assert out1["truck_id"] == "TRK-104", f"Expected TRK-104, got {out1['truck_id']}"
    assert out1["decision"] == "ACCEPT", f"Expected ACCEPT, got {out1['decision']}"
    assert out1["reasoning"] == "Cargo shelf-life margin (6h) exceeds new ETA delay (1.5h); cost within threshold"
    assert out1["risk_factors"]["shelf_life_ok"] is True
    assert out1["risk_factors"]["cost_ok"] is True
    assert out1["risk_factors"]["eta_ok"] is True
    assert out1["risk_factors"]["safety_ok"] is True
    print("[PASS] Test Case 1 PASSED\n")

    # Test Case 2: High cost plan (REJECT on cost)
    case2 = {
        "truck_id": "TRK-202",
        "recommended_action": "transfer_to_another_vehicle",
        "reasoning": "Major highway damage; transferring cargo to secondary truck",
        "estimated_delay_hours": 1.5,
        "estimated_cost": 8500,
        "alternative_route": {"distance_km": 110, "duration_min": 180}
    }

    out2 = evaluate_risk(case2)
    print("Test Case 2 (Expected: REJECT on cost):")
    print(json.dumps(out2, indent=2))
    assert out2["truck_id"] == "TRK-202", f"Expected TRK-202, got {out2['truck_id']}"
    assert out2["decision"] == "REJECT", f"Expected REJECT, got {out2['decision']}"
    assert out2["risk_factors"]["cost_ok"] is False
    assert out2["risk_factors"]["shelf_life_ok"] is True
    print("[PASS] Test Case 2 PASSED\n")

    # Test Case 3: Excessive delay plan (REJECT on shelf-life and ETA)
    case3 = {
        "truck_id": "TRK-309",
        "recommended_action": "wait",
        "reasoning": "Landslide blocking main route; waiting for clearing operations",
        "estimated_delay_hours": 14.0,
        "estimated_cost": 1200,
        "alternative_route": {"distance_km": 0, "duration_min": 840}
    }

    out3 = evaluate_risk(case3)
    print("Test Case 3 (Expected: REJECT on shelf-life and ETA):")
    print(json.dumps(out3, indent=2))
    assert out3["truck_id"] == "TRK-309", f"Expected TRK-309, got {out3['truck_id']}"
    assert out3["decision"] == "REJECT", f"Expected REJECT, got {out3['decision']}"
    assert out3["risk_factors"]["shelf_life_ok"] is False
    assert out3["risk_factors"]["eta_ok"] is False
    print("[PASS] Test Case 3 PASSED\n")

    print("All Risk Critic Agent tests passed successfully!")


if __name__ == "__main__":
    run_tests()
