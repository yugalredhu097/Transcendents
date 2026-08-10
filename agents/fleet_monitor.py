"""
Fleet Monitor Agent
Monitors vehicle telemetry and detects abnormal stoppages.
"""

# Named constant threshold for stopped duration (in minutes)
STOPPED_DURATION_THRESHOLD_MINUTES = 30


def detect_disruption(raw_telemetry: dict) -> dict:
    """
    Processes raw vehicle telemetry and returns the fleet monitor output dictionary matching Contract 1.
    
    Args:
        raw_telemetry (dict): Raw vehicle telemetry data containing truck_id, location, cargo_type,
                              destination, deadline, stopped_duration_minutes, delay_minutes, last_updated.
                              
    Returns:
        dict: Standardized Fleet Monitor response object.
              Fields:
                - truck_id (str)
                - location (dict): {"lat": float, "lng": float, "name": str}
                - cargo_type (str)
                - destination (str)
                - deadline (str)
                - status (str): "abnormal_stop" if stopped_duration_minutes > STOPPED_DURATION_THRESHOLD_MINUTES else "normal"
                - delay_minutes (int)
                - last_updated (str)
    """
    stopped_duration = raw_telemetry.get("stopped_duration_minutes", 0)

    if stopped_duration > STOPPED_DURATION_THRESHOLD_MINUTES:
        status = "abnormal_stop"
    else:
        status = "normal"

    return {
        "truck_id": raw_telemetry.get("truck_id", "TRK-000"),
        "location": raw_telemetry.get("location", {"lat": 0.0, "lng": 0.0, "name": "Unknown"}),
        "cargo_type": raw_telemetry.get("cargo_type", "general"),
        "destination": raw_telemetry.get("destination", "Unknown"),
        "deadline": raw_telemetry.get("deadline", ""),
        "status": status,
        "delay_minutes": int(raw_telemetry.get("delay_minutes", 0)),
        "last_updated": raw_telemetry.get("last_updated", "")
    }
