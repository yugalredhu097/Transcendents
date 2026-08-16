"""
Fleet Monitor Agent (P1 - Yugal)

Monitors raw fleet telemetry data and detects abnormal stops or operational anomalies.
Converts raw telemetry into a standardized incident disruption payload contract (Contract 1).
Deterministic analysis engine (sensor module).
"""

from typing import Dict, Any, Optional

# Named Constants & Operational Configuration Thresholds
STOPPED_DURATION_THRESHOLD_MINUTES: int = 30

# Default Fallback Values
DEFAULT_TRUCK_ID: str = "UNKNOWN"
DEFAULT_CARGO_TYPE: str = "general_cargo"
DEFAULT_DESTINATION: str = "Unknown Destination"
DEFAULT_LOCATION_NAME: str = "Unknown Location"

# Geographic Validation Bounds
MIN_LATITUDE: float = -90.0
MAX_LATITUDE: float = 90.0
MIN_LONGITUDE: float = -180.0
MAX_LONGITUDE: float = 180.0


def _sanitize_string(val: Any, default_str: str) -> str:
    """Safely extracts a non-empty string value."""
    if val is None:
        return default_str
    s_val = str(val).strip()
    return s_val if s_val else default_str


def _sanitize_float(val: Any, default_val: float = 0.0) -> float:
    """Safely parses float values without throwing ValueError or TypeError."""
    if val is None:
        return default_val
    try:
        f_val = float(val)
        return f_val
    except (ValueError, TypeError):
        return default_val


def _sanitize_non_negative_int(val: Any, default_val: int = 0) -> int:
    """Safely parses integer values and clamps negative inputs to 0."""
    if val is None:
        return default_val
    try:
        i_val = int(float(val))
        return max(0, i_val)
    except (ValueError, TypeError):
        return default_val


def _sanitize_location(location_input: Any, raw_telemetry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates and sanitizes location telemetry data.
    Supports both nested location objects and legacy flat key fields.
    Validates latitude and longitude within physical global boundaries.
    """
    if isinstance(location_input, dict):
        raw_lat = location_input.get("lat")
        raw_lng = location_input.get("lng")
        raw_name = location_input.get("name")
    else:
        raw_lat = raw_telemetry.get("lat")
        raw_lng = raw_telemetry.get("lng")
        raw_name = raw_telemetry.get("location_name", raw_telemetry.get("name"))

    lat = _sanitize_float(raw_lat, 0.0)
    lng = _sanitize_float(raw_lng, 0.0)
    name = _sanitize_string(raw_name, DEFAULT_LOCATION_NAME)

    # Bound check latitude and longitude
    if not (MIN_LATITUDE <= lat <= MAX_LATITUDE):
        lat = 0.0
    if not (MIN_LONGITUDE <= lng <= MAX_LONGITUDE):
        lng = 0.0

    return {
        "lat": lat,
        "lng": lng,
        "name": name
    }


def detect_disruption(raw_telemetry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyzes raw vehicle telemetry data and detects abnormal stoppage disruptions.

    Args:
        raw_telemetry (dict): Raw telemetry payload containing truck info, position,
                              speed, stop duration, cargo details, and timestamps.

    Returns:
        dict: Standardized Contract 1 disruption payload:
            {
                "truck_id": str,
                "location": {"lat": float, "lng": float, "name": str},
                "cargo_type": str,
                "destination": str,
                "deadline": str,
                "status": str,  # "abnormal_stop" or "normal"
                "delay_minutes": int,
                "last_updated": str
            }
    """
    if not isinstance(raw_telemetry, dict):
        raw_telemetry = {}

    # Extract & sanitize core telemetry parameters
    truck_id = _sanitize_string(raw_telemetry.get("truck_id"), DEFAULT_TRUCK_ID)
    shipment_id = _sanitize_string(raw_telemetry.get("shipment_id"), "UNKNOWN")
    cargo_type = _sanitize_string(raw_telemetry.get("cargo_type"), DEFAULT_CARGO_TYPE)
    quantity = _sanitize_non_negative_int(raw_telemetry.get("quantity"), 0)
    unit = _sanitize_string(raw_telemetry.get("unit"), "units")
    cargo_value = _sanitize_float(raw_telemetry.get("cargo_value"), 0.0)
    priority = _sanitize_string(raw_telemetry.get("priority"), "MEDIUM")
    destination = _sanitize_string(raw_telemetry.get("destination"), DEFAULT_DESTINATION)
    deadline = _sanitize_string(raw_telemetry.get("deadline", raw_telemetry.get("delivery_deadline")), "")
    last_updated = _sanitize_string(raw_telemetry.get("last_updated", raw_telemetry.get("timestamp")), "")

    location = _sanitize_location(raw_telemetry.get("location"), raw_telemetry)
    origin = raw_telemetry.get("origin")
    destination_location = raw_telemetry.get("destination_location")

    raw_shelf_life = raw_telemetry.get("remaining_shelf_life_hours")
    if raw_shelf_life is not None:
        try:
            remaining_shelf_life_hours = float(raw_shelf_life)
        except (ValueError, TypeError):
            remaining_shelf_life_hours = None
    else:
        remaining_shelf_life_hours = None

    temperature_requirement = raw_telemetry.get("temperature_requirement")
    speed_kmh = _sanitize_float(raw_telemetry.get("speed_kmh"), 0.0)

    # Extract & sanitize stop duration
    raw_stop_duration = raw_telemetry.get(
        "stopped_duration_minutes",
        raw_telemetry.get("stop_duration_minutes", raw_telemetry.get("stopped_duration", 0))
    )
    stop_duration = _sanitize_non_negative_int(raw_stop_duration, 0)
    delay_minutes = _sanitize_non_negative_int(raw_telemetry.get("delay_minutes", stop_duration), stop_duration)

    # Status evaluation logic
    raw_status = _sanitize_string(raw_telemetry.get("status"), "").lower()
    if raw_status == "abnormal_stop":
        status = "abnormal_stop"
    elif stop_duration > STOPPED_DURATION_THRESHOLD_MINUTES:
        status = "abnormal_stop"
    else:
        status = "normal"

    return {
        "truck_id": truck_id,
        "shipment_id": shipment_id,
        "location": location,
        "current_location": location,
        "origin": origin,
        "destination": destination,
        "destination_location": destination_location,
        "cargo_type": cargo_type,
        "quantity": quantity,
        "unit": unit,
        "cargo_value": cargo_value,
        "priority": priority,
        "remaining_shelf_life_hours": remaining_shelf_life_hours,
        "temperature_requirement": temperature_requirement,
        "speed_kmh": speed_kmh,
        "deadline": deadline,
        "delivery_deadline": deadline,
        "status": status,
        "delay_minutes": delay_minutes,
        "stopped_duration_minutes": stop_duration,
        "last_updated": last_updated,
        "scenario_timestamp": last_updated,
    }
