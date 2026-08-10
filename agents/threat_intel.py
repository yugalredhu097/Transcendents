import json
import os
from typing import Dict, Any

MOCK_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mock_disruptions.json")


def load_mock_disruptions() -> Dict[str, Any]:
    """Loads mock disruptions from data/mock_disruptions.json if available."""
    if os.path.exists(MOCK_DATA_PATH):
        try:
            with open(MOCK_DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def assess_threat(truck_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assesses threat intelligence for a given truck independently of fleet monitor status.
    Analyzes both current stoppages and upcoming route disruptions.

    Contract Output:
    {
      "truck_id": str,
      "disruption_type": str,
      "description": str,
      "source": str,
      "confidence": float,
      "verified": bool,
      "disruption_stage": str, ("current", "upcoming", or "none")
      "predicted_delay_hours": float
    }
    """
    truck_id = truck_data.get("truck_id", "UNKNOWN")
    
    # 1. Check direct override/mock in truck_data if supplied
    if "disruption" in truck_data and isinstance(truck_data["disruption"], dict):
        d = truck_data["disruption"]
        return {
            "truck_id": truck_id,
            "disruption_type": str(d.get("disruption_type", "none")),
            "description": str(d.get("description", "No active or upcoming threats detected along route")),
            "source": str(d.get("source", "mock_or_url")),
            "confidence": float(d.get("confidence", 1.0)),
            "verified": bool(d.get("verified", True)),
            "disruption_stage": str(d.get("disruption_stage", "none")),
            "predicted_delay_hours": float(d.get("predicted_delay_hours", 0.0))
        }

    # 2. Check mock_disruptions.json by truck_id
    mock_disruptions = load_mock_disruptions()
    if truck_id in mock_disruptions:
        disruption_info = mock_disruptions[truck_id]
        return {
            "truck_id": truck_id,
            "disruption_type": str(disruption_info.get("disruption_type", "none")),
            "description": str(disruption_info.get("description", "")),
            "source": str(disruption_info.get("source", "mock_or_url")),
            "confidence": float(disruption_info.get("confidence", 0.8)),
            "verified": bool(disruption_info.get("verified", True)),
            "disruption_stage": str(disruption_info.get("disruption_stage", "none")),
            "predicted_delay_hours": float(disruption_info.get("predicted_delay_hours", 0.0))
        }

    # 3. Default case: No threat nearby or on route
    return {
        "truck_id": truck_id,
        "disruption_type": "none",
        "description": "No active or upcoming threats detected along route",
        "source": "mock_or_url",
        "confidence": 1.0,
        "verified": True,
        "disruption_stage": "none",
        "predicted_delay_hours": 0.0
    }
