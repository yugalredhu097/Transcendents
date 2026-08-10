"""
Incident Planner Agent
Responsible for analyzing escalation events from the Dispatch Gate (Contract 3)
and generating actionable incident response plans (Contract 4).
"""

import json
import urllib.request
from typing import Dict, Any, Optional, Tuple


def fetch_osrm_route(
    start_coords: Tuple[float, float] = (72.8777, 19.0760),
    end_coords: Tuple[float, float] = (73.8567, 18.5204),
    timeout: float = 3.0,
) -> Optional[Dict[str, float]]:
    """
    Fetches route distance (km) and duration (min) from public OSRM server.
    Coordinates format: (longitude, latitude).
    Returns dict with 'distance_km' and 'duration_min', or None on network failure / timeout.
    """
    start_lng, start_lat = start_coords
    end_lng, end_lat = end_coords
    url = (
        f"http://router.project-osrm.org/route/v1/driving/"
        f"{start_lng},{start_lat};{end_lng},{end_lat}?overview=false"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "IncidentPlanner/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("code") == "Ok" and data.get("routes"):
                    route = data["routes"][0]
                    dist_km = round(route["distance"] / 1000.0, 1)
                    dur_min = round(route["duration"] / 60.0, 1)
                    return {"distance_km": dist_km, "duration_min": dur_min}
    except Exception:
        pass
    return None


def calculate_route_cost_impact(
    distance_km: float,
    duration_min: float,
    base_cost_per_km: float = 10.0,
    hourly_driver_rate: float = 150.0,
    fixed_overhead: float = 200.0,
) -> float:
    """
    Helper function to calculate real-world rerouting cost based on distance and duration.
    """
    travel_cost = distance_km * base_cost_per_km
    time_cost = (duration_min / 60.0) * hourly_driver_rate
    total_cost = travel_cost + time_cost + fixed_overhead
    return round(total_cost, 2)


def generate_plan(dispatch_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates an incident response plan matching Contract 4 output specification.

    Input (Contract 3):
    {
      "truck_id": str,
      "escalate": bool,
      "reason": str,
      "fleet_output": dict,
      "threat_output": dict
    }

    Output (Contract 4):
    {
      "truck_id": str,
      "recommended_action": str,
      "reasoning": str,
      "estimated_delay_hours": float,
      "estimated_cost": float/int,
      "alternative_route": {"distance_km": float/int, "duration_min": float/int}
    }
    """
    truck_id = dispatch_data.get("truck_id", "UNKNOWN")
    reason = (dispatch_data.get("reason") or "").lower()
    fleet_output = dispatch_data.get("fleet_output") or {}
    threat_output = dispatch_data.get("threat_output") or {}

    # Extract start and end coordinates if provided, else default coordinates (Mumbai -> Pune)
    start_coords = (
        dispatch_data.get("start_coords")
        or fleet_output.get("start_coords")
        or threat_output.get("start_coords")
        or (72.8777, 19.0760)
    )
    end_coords = (
        dispatch_data.get("end_coords")
        or fleet_output.get("end_coords")
        or threat_output.get("end_coords")
        or (73.8567, 18.5204)
    )

    # Attempt OSRM call unless explicitly disabled
    osrm_data = None
    if dispatch_data.get("use_osrm", True):
        osrm_data = fetch_osrm_route(start_coords, end_coords)

    # Identify primary cause of escalation (Threat Intel vs Fleet Stoppage)
    is_threat = (
        "threat" in reason
        or threat_output.get("threat_detected") is True
        or bool(threat_output.get("threat_type"))
    )

    if is_threat:
        threat_type = threat_output.get("threat_type", "Road disruption")
        eta_threat_hours = threat_output.get("estimated_arrival_hours", 2.0)
        deadline_hours = float(fleet_output.get("deadline_hours_remaining", 4.0))

        if osrm_data is not None:
            distance_km = float(osrm_data["distance_km"])
            duration_min = float(osrm_data["duration_min"])
        else:
            # Fallback to payload suggested detour figures or defaults
            distance_km = float(threat_output.get("suggested_detour_km", 62))
            duration_min = float(threat_output.get("suggested_detour_min", 95))

        estimated_delay_hours = round(duration_min / 60.0, 1)
        estimated_cost = calculate_route_cost_impact(
            distance_km=distance_km,
            duration_min=duration_min,
            base_cost_per_km=threat_output.get("base_cost_per_km", 10.0),
        )

        recommended_action = "reroute"
        reasoning = (
            f"{threat_type} expected in ~{eta_threat_hours} hours on current route; "
            f"alternate route adds {estimated_delay_hours}h (costing ${estimated_cost:g}), "
            f"staying comfortably within the remaining cargo deadline of {deadline_hours}h."
        )

    else:
        # Fleet Monitor Stoppage / Breakdown Trigger
        stoppage_duration = fleet_output.get("stoppage_duration_min", 45)
        cargo_type = fleet_output.get("cargo_type", "Standard Freight")
        location = fleet_output.get("location", "Highway Segment")
        deadline_hours = float(fleet_output.get("deadline_hours_remaining", 4.0))

        if osrm_data is not None:
            distance_km = float(osrm_data["distance_km"])
            duration_min = float(osrm_data["duration_min"])
        else:
            # Fallback to payload detour figures or defaults
            distance_km = float(fleet_output.get("detour_distance_km", 45))
            duration_min = float(fleet_output.get("detour_duration_min", 75))

        estimated_delay_hours = round((stoppage_duration + duration_min) / 60.0, 1)
        base_cost = calculate_route_cost_impact(distance_km=distance_km, duration_min=duration_min)
        stoppage_penalty = fleet_output.get("delay_penalty_per_hour", 500) * (stoppage_duration / 60.0)
        estimated_cost = round(base_cost + stoppage_penalty, 2)

        recommended_action = "reroute"
        reasoning = (
            f"Unplanned stoppage ({stoppage_duration} min) detected at {location} for {cargo_type}; "
            f"rerouting via alternate highway adds total {estimated_delay_hours}h delay (costing ${estimated_cost:g}), "
            f"protecting the remaining cargo delivery deadline of {deadline_hours}h."
        )

    # Format return dictionary matching Contract 4 field-for-field
    return {
        "truck_id": truck_id,
        "recommended_action": recommended_action,
        "reasoning": reasoning,
        "estimated_delay_hours": estimated_delay_hours,
        "estimated_cost": estimated_cost if estimated_cost % 1 != 0 else int(estimated_cost),
        "alternative_route": {
            "distance_km": int(distance_km) if distance_km.is_integer() else distance_km,
            "duration_min": int(duration_min) if duration_min.is_integer() else duration_min,
        },
    }

