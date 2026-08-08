"""
Fleet Monitor Agent (P1 - Yugal)

Monitors raw fleet telemetry data and detects abnormal stops or delays.
Converts raw telemetry into a standardized incident disruption payload contract.
"""

from typing import Dict, Any


def detect_disruption(raw_telemetry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyzes raw telemetry data for a truck and detects potential disruptions.

    Args:
        raw_telemetry (dict): Raw telemetry data containing truck info, position, 
                              speed, stop duration, cargo details, and timestamps.

    Returns:
        dict: Standardized disruption payload matching contract:
            {
                "truck_id": str,
                "location": {"lat": float, "lng": float, "name": str},
                "cargo_type": str,
                "destination": str,
                "deadline": str,
                "status": str,
                "delay_minutes": int,
                "last_updated": str
            }
    """
    # Extract location parameters (supports nested or flat key structures)
    location_info = raw_telemetry.get("location")
    if isinstance(location_info, dict):
        lat = location_info.get("lat", 0.0)
        lng = location_info.get("lng", 0.0)
        name = location_info.get("name", "Unknown Location")
    else:
        lat = raw_telemetry.get("lat", 0.0)
        lng = raw_telemetry.get("lng", 0.0)
        name = raw_telemetry.get("location_name", "Unknown Location")

    location = {
        "lat": lat,
        "lng": lng,
        "name": name
    }

    # Determine status and delay_minutes
    speed_kmh = raw_telemetry.get("speed_kmh", 0)
    stop_duration = raw_telemetry.get("stop_duration_minutes", raw_telemetry.get("delay_minutes", 0))
    
    status = raw_telemetry.get("status")
    if not status:
        if speed_kmh == 0 and stop_duration > 15:
            status = "abnormal_stop"
        elif stop_duration > 30 or speed_kmh < 10:
            status = "delayed"
        else:
            status = "normal"

    delay_minutes = raw_telemetry.get("delay_minutes", stop_duration)

    return {
        "truck_id": raw_telemetry.get("truck_id", "UNKNOWN"),
        "location": location,
        "cargo_type": raw_telemetry.get("cargo_type", "general_cargo"),
        "destination": raw_telemetry.get("destination", "Unknown Destination"),
        "deadline": raw_telemetry.get("deadline", ""),
        "status": status,
        "delay_minutes": delay_minutes,
        "last_updated": raw_telemetry.get("last_updated", raw_telemetry.get("timestamp", ""))
    }
