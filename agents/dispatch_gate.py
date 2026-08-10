"""
Dispatch Gate Integration Point (P4: Shivansh)
Determines whether a shipment disruption requires escalation to incident planning based on Fleet Monitor status and Threat Intel verification.
"""


def should_escalate(fleet_output: dict, threat_output: dict) -> dict:
    """
    Evaluates Fleet Monitor output and Threat Intel output to decide if escalation is required.

    Fleet Input (Contract 1):
    {
      "truck_id": "TRK-104",
      "location": {"lat": 19.076, "lng": 72.877, "name": "near Kalyan, MH"},
      "cargo_type": "perishable_produce",
      "destination": "Pune",
      "deadline": "2026-08-10T18:00:00",
      "status": "normal", # or "abnormal_stop"
      "delay_minutes": 0,
      "last_updated": "2026-08-08T14:22:00"
    }

    Threat Input (Contract 2):
    {
      "truck_id": "TRK-104",
      "disruption_type": "protest",
      "description": "Protest announced on NH-8 corridor near Jaipur",
      "source": "mock_or_url",
      "confidence": 0.8,
      "verified": true,
      "disruption_stage": "upcoming", # "current", "upcoming", "cleared", "none"
      "predicted_delay_hours": 5.0
    }

    Dispatch Gate Output (Contract 3):
    {
      "truck_id": "TRK-104",
      "escalate": true,
      "reason": "threat_upcoming",
      "fleet_output": { ... passthrough ... },
      "threat_output": { ... passthrough ... }
    }
    """
    truck_id = fleet_output.get("truck_id") or threat_output.get("truck_id", "")

    fleet_status = str(fleet_output.get("status", "")).lower()
    threat_verified = bool(threat_output.get("verified", False))
    disruption_stage = str(threat_output.get("disruption_stage", "")).lower()

    # Rule checks
    fleet_escalate = (fleet_status == "abnormal_stop")
    threat_escalate = threat_verified and (disruption_stage in ["current", "upcoming"])

    escalate = fleet_escalate or threat_escalate

    # Determine reason string
    if fleet_escalate and threat_escalate:
        reason = f"abnormal_stop_and_threat_{disruption_stage}"
    elif fleet_escalate:
        reason = "abnormal_stop"
    elif threat_escalate:
        reason = f"threat_{disruption_stage}"
    else:
        reason = "no_disruption"

    return {
        "truck_id": truck_id,
        "escalate": escalate,
        "reason": reason,
        "fleet_output": fleet_output,
        "threat_output": threat_output
    }
