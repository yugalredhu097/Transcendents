"""
Test script for Dispatch Gate Integration Point (P4: Shivansh)
"""
import json
from agents.dispatch_gate import should_escalate


def run_tests():
    print("--- Running Dispatch Gate Agent Tests ---\n")

    # Test Case 1: Normal fleet status & no verified threat (No Escalation)
    fleet1 = {
        "truck_id": "TRK-104",
        "location": {"lat": 19.076, "lng": 72.877, "name": "near Kalyan, MH"},
        "cargo_type": "perishable_produce",
        "destination": "Pune",
        "deadline": "2026-08-10T18:00:00",
        "status": "normal",
        "delay_minutes": 0,
        "last_updated": "2026-08-08T14:22:00"
    }
    threat1 = {
        "truck_id": "TRK-104",
        "disruption_type": "none",
        "description": "No active disruptions detected",
        "source": "mock",
        "confidence": 1.0,
        "verified": False,
        "disruption_stage": "none",
        "predicted_delay_hours": 0.0
    }

    out1 = should_escalate(fleet1, threat1)
    print("Test Case 1 (Expected: No Escalation):")
    print(json.dumps(out1, indent=2))
    assert out1["truck_id"] == "TRK-104", f"Expected TRK-104, got {out1['truck_id']}"
    assert out1["escalate"] is False, f"Expected escalate=False, got {out1['escalate']}"
    assert out1["reason"] == "no_disruption", f"Expected reason='no_disruption', got '{out1['reason']}'"
    assert out1["fleet_output"] == fleet1, "fleet_output passthrough mismatch"
    assert out1["threat_output"] == threat1, "threat_output passthrough mismatch"
    print("[PASS] Test Case 1 PASSED\n")

    # Test Case 2: Fleet-triggered escalation (abnormal_stop)
    fleet2 = {
        "truck_id": "TRK-105",
        "location": {"lat": 26.912, "lng": 75.787, "name": "near Jaipur, RJ"},
        "cargo_type": "electronics",
        "destination": "Delhi",
        "deadline": "2026-08-11T12:00:00",
        "status": "abnormal_stop",
        "delay_minutes": 45,
        "last_updated": "2026-08-10T16:00:00"
    }
    threat2 = {
        "truck_id": "TRK-105",
        "disruption_type": "none",
        "description": "No verified threat",
        "source": "mock",
        "confidence": 0.5,
        "verified": False,
        "disruption_stage": "none",
        "predicted_delay_hours": 0.0
    }

    out2 = should_escalate(fleet2, threat2)
    print("Test Case 2 (Expected: Fleet-Triggered Escalation):")
    print(json.dumps(out2, indent=2))
    assert out2["truck_id"] == "TRK-105"
    assert out2["escalate"] is True, f"Expected escalate=True, got {out2['escalate']}"
    assert out2["reason"] == "abnormal_stop", f"Expected reason='abnormal_stop', got '{out2['reason']}'"
    print("[PASS] Test Case 2 PASSED\n")

    # Test Case 3: Threat-triggered escalation (verified threat, upcoming stage)
    fleet3 = {
        "truck_id": "TRK-104",
        "location": {"lat": 19.076, "lng": 72.877, "name": "near Kalyan, MH"},
        "cargo_type": "perishable_produce",
        "destination": "Pune",
        "deadline": "2026-08-10T18:00:00",
        "status": "normal",
        "delay_minutes": 0,
        "last_updated": "2026-08-08T14:22:00"
    }
    threat3 = {
        "truck_id": "TRK-104",
        "disruption_type": "protest",
        "description": "Protest announced on NH-8 corridor near Jaipur",
        "source": "mock_or_url",
        "confidence": 0.8,
        "verified": True,
        "disruption_stage": "upcoming",
        "predicted_delay_hours": 5.0
    }

    out3 = should_escalate(fleet3, threat3)
    print("Test Case 3 (Expected: Threat-Triggered Escalation):")
    print(json.dumps(out3, indent=2))
    assert out3["truck_id"] == "TRK-104"
    assert out3["escalate"] is True, f"Expected escalate=True, got {out3['escalate']}"
    assert out3["reason"] == "threat_upcoming", f"Expected reason='threat_upcoming', got '{out3['reason']}'"
    assert out3["fleet_output"] == fleet3
    assert out3["threat_output"] == threat3
    print("[PASS] Test Case 3 PASSED\n")

    print("All Dispatch Gate Agent tests passed successfully!")


if __name__ == "__main__":
    run_tests()
