"""
Dispatch Gate Orchestration Module (Agent 3 - Escalation Gate)

Determines whether a shipment disruption requires escalation to incident planning based on 
Fleet Monitor telemetry status and Threat Intelligence verification.

This component is purely deterministic. No AI/LLM models are integrated here.
"""

from typing import Dict, Any, Tuple


def _eval_fleet_trigger(fleet_output: Dict[str, Any]) -> bool:
    """Evaluates whether fleet monitor telemetry requires escalation."""
    if not isinstance(fleet_output, dict):
        return False
    fleet_status = str(fleet_output.get("status", "")).strip().lower()
    return fleet_status == "abnormal_stop"


def _eval_threat_trigger(threat_output: Dict[str, Any]) -> Tuple[bool, str]:
    """Evaluates whether threat intelligence findings require escalation."""
    if not isinstance(threat_output, dict):
        return False, "none"
    
    verified = bool(threat_output.get("verified", False))
    disruption_stage = str(threat_output.get("disruption_stage", "")).strip().lower()
    
    is_escalate = verified and (disruption_stage in ["current", "upcoming"])
    return is_escalate, disruption_stage


def _determine_reason(fleet_escalate: bool, threat_escalate: bool, disruption_stage: str) -> str:
    """Determines the standardized escalation reason string."""
    if fleet_escalate and threat_escalate:
        return f"abnormal_stop_and_threat_{disruption_stage}"
    elif fleet_escalate:
        return "abnormal_stop"
    elif threat_escalate:
        return f"threat_{disruption_stage}"
    else:
        return "no_disruption"


def should_escalate(fleet_output: Dict[str, Any], threat_output: Dict[str, Any]) -> Dict[str, Any]:
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
    fleet_dict = fleet_output if isinstance(fleet_output, dict) else {}
    threat_dict = threat_output if isinstance(threat_output, dict) else {}

    truck_id = str(
        fleet_dict.get("truck_id")
        or threat_dict.get("truck_id")
        or "UNKNOWN"
    )

    fleet_escalate = _eval_fleet_trigger(fleet_dict)
    threat_escalate, disruption_stage = _eval_threat_trigger(threat_dict)

    escalate = fleet_escalate or threat_escalate
    reason = _determine_reason(fleet_escalate, threat_escalate, disruption_stage)

    return {
        "truck_id": truck_id,
        "escalate": escalate,
        "reason": reason,
        "fleet_output": fleet_dict,
        "threat_output": threat_dict
    }

