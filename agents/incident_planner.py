"""
Incident Planner Agent
Responsible for analyzing escalation events from the Dispatch Gate (Contract 3)
and generating actionable incident response plans (Contract 4) using deterministic
trade-off evaluation combined with Gemini LLM reasoning.
"""

import os
import json
import logging
import urllib.request
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Constants & Defaults
DEFAULT_OSRM_TIMEOUT = 3.0
DEFAULT_BASE_COST_PER_KM = 10.0
DEFAULT_HOURLY_DRIVER_RATE = 150.0
DEFAULT_FIXED_OVERHEAD = 200.0
DEFAULT_STOPPAGE_PENALTY_PER_HOUR = 500.0
DEFAULT_STORAGE_COST_PER_HOUR = 300.0
DEFAULT_HANDLING_COST = 1000.0

VALID_RECOMMENDED_ACTIONS = {
    "reroute",
    "wait",
    "transfer_to_storage",
    "no_feasible_action",
}

FACILITIES_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "facilities.json"
)


# ============================================================================
# 1. Deterministic Helpers (Public API preservation)
# ============================================================================

def haversine_distance_km(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Calculates haversine distance in km between two (longitude, latitude) tuples."""
    import math
    lng1, lat1 = coord1
    lng2, lat2 = coord2
    r = 6371.0  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(r * c, 1)


def fetch_osrm_route(
    start_coords: Tuple[float, float] = (72.8777, 19.0760),
    end_coords: Tuple[float, float] = (73.8567, 18.5204),
    timeout: float = DEFAULT_OSRM_TIMEOUT,
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
        req = urllib.request.Request(url, headers={"User-Agent": "IncidentPlanner/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("code") == "Ok" and data.get("routes"):
                    route = data["routes"][0]
                    dist_km = round(route["distance"] / 1000.0, 1)
                    dur_min = round(route["duration"] / 60.0, 1)
                    return {"distance_km": dist_km, "duration_min": dur_min}
    except Exception as e:
        logger.debug(f"OSRM route fetch failed/timed out: {e}")
    return None


def fetch_osrm_detour_route(
    start_coords: Tuple[float, float],
    end_coords: Tuple[float, float],
    disruption_coords: Tuple[float, float],
    timeout: float = DEFAULT_OSRM_TIMEOUT,
) -> Optional[Dict[str, float]]:
    """
    Fetches detour route around disruption via an offset waypoint.
    Coordinates format: (longitude, latitude).
    """
    start_lng, start_lat = start_coords
    end_lng, end_lat = end_coords
    dis_lng, dis_lat = disruption_coords

    dx = end_lng - start_lng
    dy = end_lat - start_lat
    mag = (dx**2 + dy**2)**0.5
    if mag > 0:
        offset_lng = dis_lng - (dy / mag) * 0.15
        offset_lat = dis_lat + (dx / mag) * 0.15
    else:
        offset_lng = dis_lng + 0.15
        offset_lat = dis_lat + 0.15

    url = (
        f"http://router.project-osrm.org/route/v1/driving/"
        f"{start_lng},{start_lat};{round(offset_lng, 4)},{round(offset_lat, 4)};{end_lng},{end_lat}?overview=false"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "IncidentPlanner/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("code") == "Ok" and data.get("routes"):
                    route = data["routes"][0]
                    dist_km = round(route["distance"] / 1000.0, 1)
                    dur_min = round(route["duration"] / 60.0, 1)
                    return {"distance_km": dist_km, "duration_min": dur_min}
    except Exception as e:
        logger.debug(f"OSRM detour route fetch failed: {e}")
    return None


def calculate_route_cost_impact(
    distance_km: float,
    duration_min: float,
    base_cost_per_km: float = DEFAULT_BASE_COST_PER_KM,
    hourly_driver_rate: float = DEFAULT_HOURLY_DRIVER_RATE,
    fixed_overhead: float = DEFAULT_FIXED_OVERHEAD,
) -> float:
    """
    Helper function to calculate real-world rerouting cost based on distance and duration.
    """
    travel_cost = distance_km * base_cost_per_km
    time_cost = (duration_min / 60.0) * hourly_driver_rate
    total_cost = travel_cost + time_cost + fixed_overhead
    return round(total_cost, 2)


# ============================================================================
# 2. Data Models & Context Builder
# ============================================================================

@dataclass
class CandidateOption:
    """Deterministic candidate plan option evaluated prior to LLM reasoning."""
    action: str
    distance_km: float
    duration_min: float
    estimated_delay_hours: float
    estimated_cost: float
    description: str
    shelf_life_ok: bool
    deadline_ok: bool
    score: float  # Lower score indicates better candidate deterministically
    baseline_duration_hours: float = 0.0
    candidate_duration_hours: float = 0.0
    additional_delay_hours: float = 0.0
    candidate_distance_km: float = 0.0
    deadline_margin_hours: float = 0.0
    shelf_life_margin_hours: float = 0.0
    feasible: bool = True
    feasibility_reasons: List[str] = None

    def __post_init__(self):
        if self.feasibility_reasons is None:
            self.feasibility_reasons = []


class ContextBuilder:
    """Prepares structured operational context from Contract 3 payload."""

    @staticmethod
    def load_facilities() -> List[Dict[str, Any]]:
        """Loads warehouse and cold storage facility database."""
        if os.path.exists(FACILITIES_FILE_PATH):
            try:
                with open(FACILITIES_FILE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return [
            {
                "facility_id": "FAC-GEN-01",
                "name": "Regional Logistics Warehouse",
                "type": "warehouse",
                "supports_perishable_cargo": False,
                "storage_cost_per_hour": 150.0,
                "handling_cost": 500.0,
            },
            {
                "facility_id": "FAC-COLD-01",
                "name": "Regional Pharma & Produce Cold Hub",
                "type": "cold_storage",
                "supports_perishable_cargo": True,
                "storage_cost_per_hour": 350.0,
                "handling_cost": 1200.0,
            },
        ]

    @classmethod
    def build_context(cls, dispatch_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parses Contract 3 payload into structured operational planning context."""
        truck_id = dispatch_data.get("truck_id", "UNKNOWN")
        reason = (dispatch_data.get("reason") or "").lower()
        fleet_output = dispatch_data.get("fleet_output") or {}
        threat_output = dispatch_data.get("threat_output") or {}

        shipment_id = fleet_output.get("shipment_id") or dispatch_data.get("shipment_id") or "UNKNOWN"
        cargo_type = fleet_output.get("cargo_type") or dispatch_data.get("cargo_type") or "Standard Freight"
        quantity = fleet_output.get("quantity") or dispatch_data.get("quantity") or 0
        unit = fleet_output.get("unit") or dispatch_data.get("unit") or "units"
        cargo_value = float(fleet_output.get("cargo_value") or dispatch_data.get("cargo_value") or 100000.0)

        # Flag temperature sensitivity and hazmat
        is_temp_sensitive = (
            "perishable" in cargo_type.lower()
            or "pharma" in cargo_type.lower()
            or "produce" in cargo_type.lower()
            or bool(fleet_output.get("temperature_requirement"))
        )
        is_hazmat = "hazmat" in cargo_type.lower() or "chemical" in cargo_type.lower()

        # Deterministic SLA Remaining Hours calculation against scenario timestamp
        scenario_ts_str = fleet_output.get("scenario_timestamp") or fleet_output.get("last_updated") or "2026-08-11T10:00:00"
        delivery_deadline_str = (
            fleet_output.get("delivery_deadline")
            or fleet_output.get("deadline")
            or dispatch_data.get("delivery_deadline")
            or "2026-08-11T18:00:00"
        )

        from datetime import datetime
        try:
            ts_dt = datetime.fromisoformat(scenario_ts_str.replace("Z", "+00:00"))
            dl_dt = datetime.fromisoformat(delivery_deadline_str.replace("Z", "+00:00"))
            deadline_hours = max(0.0, round((dl_dt - ts_dt).total_seconds() / 3600.0, 1))
        except (ValueError, TypeError):
            raw_dl = fleet_output.get("deadline_hours_remaining") or dispatch_data.get("deadline_hours_remaining")
            if raw_dl is not None:
                try:
                    deadline_hours = float(raw_dl)
                except (ValueError, TypeError):
                    deadline_hours = 4.0
            else:
                deadline_hours = 4.0

        customer_priority = str(
            fleet_output.get("priority")
            or fleet_output.get("customer_priority")
            or dispatch_data.get("priority")
            or dispatch_data.get("customer_priority")
            or "medium"
        )

        raw_shelf_life = (
            fleet_output.get("remaining_shelf_life_hours")
            if fleet_output.get("remaining_shelf_life_hours") is not None
            else fleet_output.get("shelf_life_hours")
        )
        shelf_life_hours: Optional[float] = None
        if raw_shelf_life is not None:
            try:
                shelf_life_hours = float(raw_shelf_life)
            except (ValueError, TypeError):
                shelf_life_hours = None

        is_threat = (
            "threat" in reason
            or threat_output.get("threat_detected") is True
            or bool(threat_output.get("threat_type"))
        )

        auth_disrupt = threat_output.get("authoritative_disruption") or {}
        if is_threat:
            disruption_type = (
                auth_disrupt.get("type")
                or threat_output.get("threat_type")
                or threat_output.get("disruption_type")
                or "Road disruption"
            )
            severity = auth_disrupt.get("severity") or threat_output.get("severity", "high")
            predicted_delay_hours = float(
                auth_disrupt.get("predicted_delay")
                or threat_output.get("predicted_delay_hours")
                or threat_output.get("predicted_disruption_delay")
                or 3.0
            )
            raw_loc = auth_disrupt.get("location") or threat_output.get("threat_location") or threat_output.get("location") or "En-route Corridor"
            if isinstance(raw_loc, dict):
                location = raw_loc.get("name", "En-route Corridor")
            else:
                location = str(raw_loc)
        else:
            disruption_type = auth_disrupt.get("type") or fleet_output.get("disruption_type") or "Vehicle Stoppage / Breakdown"
            severity = auth_disrupt.get("severity") or fleet_output.get("severity", "medium")
            stoppage_min = float(fleet_output.get("stoppage_duration_min", 45))
            predicted_delay_hours = float(auth_disrupt.get("predicted_delay") or round(stoppage_min / 60.0, 1))
            raw_loc = auth_disrupt.get("location") or fleet_output.get("location") or "Highway Segment"
            if isinstance(raw_loc, dict):
                location = raw_loc.get("name", "Highway Segment")
            else:
                location = str(raw_loc)

        # Authoritative Coordinates Extraction
        start_coords = None
        current_loc = fleet_output.get("location") or fleet_output.get("current_location")
        if isinstance(current_loc, dict) and "lat" in current_loc and "lng" in current_loc:
            start_coords = (float(current_loc["lng"]), float(current_loc["lat"]))
        elif dispatch_data.get("start_coords"):
            start_coords = dispatch_data.get("start_coords")

        end_coords = None
        dest_loc = fleet_output.get("destination_location")
        if isinstance(dest_loc, dict) and "lat" in dest_loc and "lng" in dest_loc:
            end_coords = (float(dest_loc["lng"]), float(dest_loc["lat"]))
        elif dispatch_data.get("end_coords"):
            end_coords = dispatch_data.get("end_coords")

        disruption_coords = None
        dis_loc = threat_output.get("location") or threat_output.get("disruption_location")
        if isinstance(dis_loc, dict) and "lat" in dis_loc and "lng" in dis_loc:
            disruption_coords = (float(dis_loc["lng"]), float(dis_loc["lat"]))

        # Phase 2A Part A: Baseline route calculation from start_coords to end_coords
        baseline_distance_km = 0.0
        baseline_duration_hours = 0.0
        if start_coords and end_coords:
            if dispatch_data.get("use_osrm", True):
                b_osrm = fetch_osrm_route(start_coords, end_coords)
                if b_osrm:
                    baseline_distance_km = float(b_osrm["distance_km"])
                    baseline_duration_hours = round(float(b_osrm["duration_min"]) / 60.0, 1)
            if baseline_distance_km <= 0.0:
                h_dist = haversine_distance_km(start_coords, end_coords)
                baseline_distance_km = h_dist
                baseline_duration_hours = round(h_dist / 60.0, 1)

        facilities = cls.load_facilities()

        return {
            "truck_id": truck_id,
            "shipment_id": shipment_id,
            "reason": reason,
            "is_threat": is_threat,
            "disruption_type": disruption_type,
            "severity": severity,
            "predicted_delay_hours": predicted_delay_hours,
            "location": location,
            "cargo_type": cargo_type,
            "quantity": quantity,
            "unit": unit,
            "cargo_value": cargo_value,
            "is_temp_sensitive": is_temp_sensitive,
            "is_hazmat": is_hazmat,
            "shelf_life_hours": shelf_life_hours,
            "deadline_hours": deadline_hours,
            "delivery_deadline": delivery_deadline_str,
            "scenario_timestamp": scenario_ts_str,
            "customer_priority": customer_priority,
            "priority": customer_priority,
            "start_coords": start_coords,
            "end_coords": end_coords,
            "disruption_coords": disruption_coords,
            "baseline_distance_km": baseline_distance_km,
            "baseline_duration_hours": baseline_duration_hours,
            "baseline_deadline_ok": (baseline_duration_hours <= deadline_hours),
            "baseline_shelf_life_ok": (baseline_duration_hours <= shelf_life_hours) if shelf_life_hours is not None else True,
            "fleet_output": fleet_output,
            "threat_output": threat_output,
            "facilities": facilities,
            "use_osrm": dispatch_data.get("use_osrm", True),
            "is_replan": dispatch_data.get("is_replan", False),
            "previous_rejection_reason": dispatch_data.get("previous_rejection_reason", ""),
        }


# ============================================================================
# 3. Candidate Evaluator Engine (Deterministic)
# ============================================================================

class CandidateEvaluator:
    """Evaluates multiple candidate actions deterministically before invoking Gemini."""

    @classmethod
    def evaluate_candidates(cls, context: Dict[str, Any]) -> List[CandidateOption]:
        """Generates and scores deterministic candidate options (Phase 2A candidate modeling)."""
        options: List[CandidateOption] = []
        is_threat = context["is_threat"]
        fleet_output = context["fleet_output"]
        threat_output = context["threat_output"]
        shelf_life = context["shelf_life_hours"]  # Optional[float]
        shelf_life_known = (shelf_life is not None)
        deadline = context["deadline_hours"]

        start_coords = context.get("start_coords")
        end_coords = context.get("end_coords")
        disruption_coords = context.get("disruption_coords")
        use_osrm = context.get("use_osrm", True)

        baseline_distance_km = float(context.get("baseline_distance_km", 0.0))
        baseline_duration_hours = float(context.get("baseline_duration_hours", 0.0))

        # ---------------------------------------------------------------------
        # Option 1: REROUTE (Alternate Corridor)
        # ---------------------------------------------------------------------
        reroute_dist_km = baseline_distance_km
        reroute_dur_h = baseline_duration_hours

        if use_osrm and start_coords and end_coords and disruption_coords:
            osrm_detour = fetch_osrm_detour_route(start_coords, end_coords, disruption_coords)
            if osrm_detour:
                reroute_dist_km = float(osrm_detour["distance_km"])
                reroute_dur_h = round(float(osrm_detour["duration_min"]) / 60.0, 1)

        if reroute_dist_km <= baseline_distance_km:
            reroute_dist_km = round(baseline_distance_km + 45.0, 1)
            reroute_dur_h = round(baseline_duration_hours + 1.5, 1)

        reroute_additional_delay_h = round(max(0.0, reroute_dur_h - baseline_duration_hours), 1)
        reroute_dur_min = round(reroute_dur_h * 60.0, 1)
        cost_reroute = calculate_route_cost_impact(reroute_dist_km, reroute_dur_min)

        deadline_margin_reroute = round(deadline - reroute_dur_h, 1)
        shelf_life_margin_reroute = round(shelf_life - reroute_dur_h, 1) if shelf_life_known else 999.0
        deadline_ok_reroute = (deadline_margin_reroute >= 0.0)
        shelf_life_ok_reroute = (shelf_life_margin_reroute >= 0.0) if shelf_life_known else True
        feasible_reroute = deadline_ok_reroute and shelf_life_ok_reroute

        options.append(
            CandidateOption(
                action="reroute",
                distance_km=reroute_dist_km,
                duration_min=reroute_dur_min,
                estimated_delay_hours=reroute_additional_delay_h,
                estimated_cost=cost_reroute,
                description=f"Reroute via alternate corridor ({reroute_dist_km} km, +{reroute_additional_delay_h}h delay).",
                shelf_life_ok=shelf_life_ok_reroute,
                deadline_ok=deadline_ok_reroute,
                score=cost_reroute + (reroute_additional_delay_h * 50) + (0 if feasible_reroute else 5000),
                baseline_duration_hours=baseline_duration_hours,
                candidate_duration_hours=reroute_dur_h,
                additional_delay_hours=reroute_additional_delay_h,
                candidate_distance_km=reroute_dist_km,
                deadline_margin_hours=deadline_margin_reroute,
                shelf_life_margin_hours=shelf_life_margin_reroute,
                feasible=feasible_reroute,
                feasibility_reasons=[] if feasible_reroute else (
                    (["Deadline exceeded"] if not deadline_ok_reroute else []) +
                    (["Shelf life exceeded"] if not shelf_life_ok_reroute else [])
                ),
            )
        )

        # ---------------------------------------------------------------------
        # Option 2: WAIT (At Disruption / Current Site)
        # ---------------------------------------------------------------------
        predicted_wait_h = context["predicted_delay_hours"]
        wait_dur_min = round(predicted_wait_h * 60.0, 1)
        penalty_per_h = float(fleet_output.get("delay_penalty_per_hour", DEFAULT_STOPPAGE_PENALTY_PER_HOUR))
        wait_cost = round((predicted_wait_h * penalty_per_h) + 150.0, 2)
        candidate_wait_dur_h = round(baseline_duration_hours + predicted_wait_h, 1)

        deadline_margin_wait = round(deadline - candidate_wait_dur_h, 1)
        shelf_life_margin_wait = round(shelf_life - candidate_wait_dur_h, 1) if shelf_life_known else 999.0
        deadline_ok_wait = (deadline_margin_wait >= 0.0)
        shelf_life_ok_wait = (shelf_life_margin_wait >= 0.0) if shelf_life_known else True
        feasible_wait = deadline_ok_wait and shelf_life_ok_wait

        options.append(
            CandidateOption(
                action="wait",
                distance_km=baseline_distance_km,
                duration_min=round(candidate_wait_dur_h * 60.0, 1),
                estimated_delay_hours=predicted_wait_h,
                estimated_cost=wait_cost,
                description=f"Wait out disruption at current site (~{predicted_wait_h}h).",
                shelf_life_ok=shelf_life_ok_wait,
                deadline_ok=deadline_ok_wait,
                score=wait_cost + (predicted_wait_h * 300) + 1500 + (0 if feasible_wait else 5000),
                baseline_duration_hours=baseline_duration_hours,
                candidate_duration_hours=candidate_wait_dur_h,
                additional_delay_hours=predicted_wait_h,
                candidate_distance_km=baseline_distance_km,
                deadline_margin_hours=deadline_margin_wait,
                shelf_life_margin_hours=shelf_life_margin_wait,
                feasible=feasible_wait,
                feasibility_reasons=[] if feasible_wait else (
                    (["Deadline exceeded"] if not deadline_ok_wait else []) +
                    (["Shelf life exceeded"] if not shelf_life_ok_wait else [])
                ),
            )
        )

        # ---------------------------------------------------------------------
        # Option 3: TRANSFER TO STORAGE (End-to-End Multi-Leg Modeling)
        # ---------------------------------------------------------------------
        facilities = context["facilities"]
        is_temp = context["is_temp_sensitive"]
        dis_coords = context.get("disruption_coords") or start_coords

        matching_facilities = [f for f in facilities if f.get("supports_perishable_cargo") == is_temp]

        target_fac = None
        if matching_facilities:
            if dis_coords:
                from agents.fleet_monitor import _sanitize_float
                def fac_dist(f):
                    f_lat = _sanitize_float(f.get("latitude"))
                    f_lng = _sanitize_float(f.get("longitude"))
                    return (f_lat - dis_coords[1])**2 + (f_lng - dis_coords[0])**2
                matching_facilities.sort(key=fac_dist)
                target_fac = matching_facilities[0]
            else:
                target_fac = matching_facilities[0]

        if target_fac:
            fac_name = target_fac.get("name", "Regional Logistics Hub")
            fac_coords = (float(target_fac.get("longitude", 75.78)), float(target_fac.get("latitude", 26.85)))

            # Leg 1: truck -> facility
            t2f_dist = 25.0
            t2f_dur_h = 0.5
            if use_osrm and start_coords:
                t2f_osrm = fetch_osrm_route(start_coords, fac_coords)
                if t2f_osrm:
                    t2f_dist = float(t2f_osrm["distance_km"])
                    t2f_dur_h = round(float(t2f_osrm["duration_min"]) / 60.0, 1)
                else:
                    t2f_dist = haversine_distance_km(start_coords, fac_coords)
                    t2f_dur_h = round(t2f_dist / 50.0, 1)

            # Leg 2: storage & handling
            storage_hours = max(2.0, predicted_wait_h)
            handling_hours = 1.0

            # Leg 3: facility -> destination
            f2d_dist = baseline_distance_km
            f2d_dur_h = baseline_duration_hours
            if use_osrm and end_coords:
                f2d_osrm = fetch_osrm_route(fac_coords, end_coords)
                if f2d_osrm:
                    f2d_dist = float(f2d_osrm["distance_km"])
                    f2d_dur_h = round(float(f2d_osrm["duration_min"]) / 60.0, 1)
                else:
                    f2d_dist = haversine_distance_km(fac_coords, end_coords)
                    f2d_dur_h = round(f2d_dist / 60.0, 1)

            total_candidate_dist_km = round(t2f_dist + f2d_dist, 1)
            total_candidate_dur_h = round(t2f_dur_h + handling_hours + storage_hours + f2d_dur_h, 1)
            add_storage_delay_h = round(max(0.0, total_candidate_dur_h - baseline_duration_hours), 1)

            fac_cost_per_h = float(target_fac.get("storage_cost_per_hour", DEFAULT_STORAGE_COST_PER_HOUR))
            fac_handling = float(target_fac.get("handling_cost", DEFAULT_HANDLING_COST))
            fac_total_cost = round(fac_handling + (storage_hours * fac_cost_per_h) + calculate_route_cost_impact(t2f_dist, t2f_dur_h * 60.0), 2)

            shelf_life_consumed = total_candidate_dur_h

            deadline_margin_fac = round(deadline - total_candidate_dur_h, 1)
            shelf_life_margin_fac = round(shelf_life - total_candidate_dur_h, 1) if shelf_life_known else 999.0

            deadline_ok_fac = (deadline_margin_fac >= 0.0)
            shelf_life_ok_fac = (shelf_life_margin_fac >= 0.0) if shelf_life_known else True
            feasible_fac = deadline_ok_fac and shelf_life_ok_fac

            options.append(
                CandidateOption(
                    action="transfer_to_storage",
                    distance_km=total_candidate_dist_km,
                    duration_min=round(total_candidate_dur_h * 60.0, 1),
                    estimated_delay_hours=add_storage_delay_h,
                    estimated_cost=fac_total_cost,
                    description=f"Divert cargo to storage at {fac_name} for preservation.",
                    shelf_life_ok=shelf_life_ok_fac,
                    deadline_ok=deadline_ok_fac,
                    score=fac_total_cost + (add_storage_delay_h * 150) + 800 + (0 if feasible_fac else 5000),
                    baseline_duration_hours=baseline_duration_hours,
                    candidate_duration_hours=total_candidate_dur_h,
                    additional_delay_hours=add_storage_delay_h,
                    candidate_distance_km=total_candidate_dist_km,
                    deadline_margin_hours=deadline_margin_fac,
                    shelf_life_margin_hours=shelf_life_margin_fac,
                    feasible=feasible_fac,
                    feasibility_reasons=[] if feasible_fac else (
                        (["Deadline exceeded"] if not deadline_ok_fac else []) +
                        (["Shelf life exceeded"] if not shelf_life_ok_fac else [])
                    ),
                )
            )
        else:
            options.append(
                CandidateOption(
                    action="transfer_to_storage",
                    distance_km=0.0,
                    duration_min=0.0,
                    estimated_delay_hours=999.0,
                    estimated_cost=99999.0,
                    description="No compatible storage facility available near location.",
                    shelf_life_ok=False,
                    deadline_ok=False,
                    score=999999.0,
                    feasible=False,
                    feasibility_reasons=["No compatible storage facility available"],
                )
            )

        # Sort candidate options by deterministic score ascending
        options.sort(key=lambda opt: opt.score)
        return options


# ============================================================================
# 4. PromptBuilder
# ============================================================================

class PromptBuilder:
    """Constructs strict system and user prompts for Gemini reasoning."""

    SYSTEM_PROMPT = (
        "You are the Senior National Logistics Operations Commander.\n"
        "Your responsibility is to analyze active shipment disruptions, evaluate candidate operational "
        "trade-offs, and recommend an optimal incident response plan.\n\n"
        "STRICT OPERATIONAL RULES:\n"
        "1. Compare candidate options based on cargo preservation, safety, contractual deadlines, and cost.\n"
        "2. Select the single best recommended_action strictly from candidate actions: 'reroute', 'wait', or 'transfer_to_storage'.\n"
        "3. 'transfer_to_another_vehicle' is NEVER a valid action and must NOT be selected.\n"
        "4. Do NOT calculate distances, delays, or costs yourself. Use the exact numeric values provided for your selected action.\n"
        "5. Provide professional, detailed operational reasoning explaining trade-offs.\n"
        "6. SHELF LIFE RULES:\n"
        "   - If remaining_shelf_life_hours is provided (known), evaluate whether candidate action delay exceeds remaining shelf life.\n"
        "   - If remaining_shelf_life_hours is null or shelf_life_status is 'unknown', explicitly acknowledge in your reasoning that remaining shelf-life information is unavailable and cannot be verified.\n"
        "   - NEVER invent, guess, or assume a numeric shelf life when remaining_shelf_life_hours is null/unknown.\n"
        "   - Do NOT claim that a plan is safe with respect to shelf life when shelf-life information is unavailable.\n"
        "7. CARGO & TEMPERATURE RULES:\n"
        "   - If temperature_requirement is null, unspecified, or the cargo is non-perishable (e.g. electronics, industrial machinery), you MUST NOT describe the cargo as 'temperature-sensitive', 'perishable', 'cold-chain', or 'requiring climate-controlled storage'.\n"
        "   - For non-perishable cargo diverted to storage, explain the action strictly as operational holding/warehousing during vehicle breakdown or road disruption recovery.\n"
        "8. CURRENCY RULES:\n"
        "   - All monetary values MUST be formatted using INR or ₹ (e.g., 'INR 2205' or '₹2205').\n"
        "   - NEVER use '$', 'USD', or dollar signs anywhere in reasoning or explanations.\n"
        "9. Output MUST be valid JSON matching Contract 4 schema ONLY. Do NOT wrap in markdown or add extra fields.\n\n"
        "REQUIRED JSON OUTPUT CONTRACT:\n"
        "{\n"
        '  "truck_id": "<str>",\n'
        '  "recommended_action": "<reroute|wait|transfer_to_storage>",\n'
        '  "reasoning": "<professional operational trade-off analysis string>",\n'
        '  "estimated_delay_hours": <number>,\n'
        '  "estimated_cost": <number>,\n'
        '  "alternative_route": {\n'
        '    "distance_km": <number>,\n'
        '    "duration_min": <number>\n'
        "  }\n"
        "}"
    )

    @classmethod
    def build_user_prompt(
        cls, context: Dict[str, Any], candidates: List[CandidateOption]
    ) -> str:
        """Formats structured context and candidates into the user prompt."""
        sl_hours = context["shelf_life_hours"]
        sl_known = (sl_hours is not None)

        candidate_summary = []
        for cand in candidates:
            candidate_summary.append({
                "action": cand.action,
                "baseline_duration_hours": cand.baseline_duration_hours,
                "candidate_duration_hours": cand.candidate_duration_hours,
                "additional_delay_hours": cand.additional_delay_hours,
                "candidate_distance_km": cand.candidate_distance_km,
                "estimated_cost": cand.estimated_cost,
                "deadline_margin_hours": cand.deadline_margin_hours,
                "shelf_life_margin_hours": cand.shelf_life_margin_hours if sl_known else None,
                "feasible": cand.feasible,
                "description": cand.description,
            })

        payload = {
            "truck_id": context["truck_id"],
            "disruption_event": {
                "type": context["disruption_type"],
                "severity": context["severity"],
                "location": context["location"],
                "predicted_delay_hours": context["predicted_delay_hours"],
            },
            "baseline_route": {
                "baseline_distance_km": context.get("baseline_distance_km"),
                "baseline_duration_hours": context.get("baseline_duration_hours"),
            },
            "shipment_constraints": {
                "cargo_type": context["cargo_type"],
                "is_temperature_sensitive": context["is_temp_sensitive"],
                "is_hazmat": context["is_hazmat"],
                "remaining_shelf_life_hours": sl_hours,
                "shelf_life_status": "known" if sl_known else "unknown",
                "deadline_hours_remaining": context["deadline_hours"],
                "customer_priority": context["customer_priority"],
            },
            "evaluated_candidate_actions": candidate_summary,
        }

        if context.get("is_replan"):
            payload["replan_notice"] = {
                "is_replan": True,
                "previous_rejection_reason": context.get("previous_rejection_reason"),
            }

        return (
            f"Analyze the following operational incident and select the best candidate action:\n"
            f"```json\n{json.dumps(payload, indent=2)}\n```\n"
            f"Return ONLY valid JSON matching Contract 4 schema."
        )


# ============================================================================
# 5. LLM Client & JSON Validator
# ============================================================================

class JSONValidator:
    """Validates raw LLM response dict against Contract 4 specification."""

    @staticmethod
    def validate_and_clean(data: Any, context: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Validates Contract 4 format and sanitizes numeric fields."""
        if not isinstance(data, dict):
            return False, None

        action = str(data.get("recommended_action") or data.get("selected_action") or "").lower()
        if action in ("transfer", "warehouse_storage", "warehouse storage"):
            action = "transfer_to_storage"

        if action not in VALID_RECOMMENDED_ACTIONS:
            return False, None

        reasoning = str(data.get("reasoning", ""))
        if len(reasoning) < 10:
            return False, None

        truck_id = str(data.get("truck_id") or context.get("truck_id", "UNKNOWN"))

        candidates = CandidateEvaluator.evaluate_candidates(context) if context else []
        feasible_cand_actions = {c.action for c in candidates if c.feasible}

        # Feasibility Enforcement Guard:
        # If no candidates are feasible, action MUST be "no_feasible_action"
        if not feasible_cand_actions:
            action = "no_feasible_action"
            b_dur = context.get("baseline_duration_hours", 0.0)
            dl_rem = context.get("deadline_hours", 0.0)
            sl_rem = context.get("shelf_life_hours")
            sl_str = f" and remaining shelf life of {sl_rem}h" if sl_rem is not None else ""
            reasoning = (
                f"No feasible operational action exists. Baseline remaining travel time ({b_dur}h) "
                f"already exceeds delivery deadline of {dl_rem}h{sl_str}. All evaluated candidate actions "
                f"(reroute, wait, transfer_to_storage) deterministically violate contractual deadline and/or cargo shelf-life constraints. "
                f"Escalation required."
            )
            delay_h = 0.0
            cost = 0.0
            dist_km = float(context.get("baseline_distance_km", 0.0))
            dur_min = float(b_dur * 60.0)
        else:
            # If feasible candidates exist, LLM must not pick an infeasible candidate action
            if action not in feasible_cand_actions and action != "no_feasible_action":
                return False, None

        matching_cand = next((c for c in candidates if c.action == action), None)

        alt_route = data.get("alternative_route")
        if not isinstance(alt_route, dict):
            if matching_cand:
                alt_route = {
                    "distance_km": matching_cand.distance_km,
                    "duration_min": matching_cand.duration_min
                }
            else:
                alt_route = {"distance_km": 0, "duration_min": 0}

        try:
            delay_h = float(data.get("estimated_delay_hours") or data.get("estimated_eta") or (matching_cand.estimated_delay_hours if matching_cand else 0.0))
            cost = float(data.get("estimated_cost") or (matching_cand.estimated_cost if matching_cand else 0.0))
            dist_km = float(alt_route.get("distance_km", 0.0))
            dur_min = float(alt_route.get("duration_min", 0.0))
        except (ValueError, TypeError):
            return False, None

        reasoning = reasoning.replace("$", "INR ").replace("USD", "INR")
        if not context.get("is_temp_sensitive"):
            for term in ["temperature-sensitive", "temperature controlled", "climate-controlled", "refrigerated"]:
                reasoning = re.sub(re.escape(term), "operational holding", reasoning, flags=re.IGNORECASE)

        cleaned = {
            "truck_id": truck_id,
            "recommended_action": action,
            "reasoning": reasoning,
            "estimated_delay_hours": delay_h if delay_h % 1 != 0 else int(delay_h),
            "estimated_cost": cost if cost % 1 != 0 else int(cost),
            "alternative_route": {
                "distance_km": int(dist_km) if dist_km.is_integer() else dist_km,
                "duration_min": int(dur_min) if dur_min.is_integer() else dur_min,
            },
        }
        return True, cleaned


class LLMClient:
    """Handles interaction with Gemini API using the shared Gemini client service."""

    @classmethod
    def call_gemini(cls, system_prompt: str, user_prompt: str, timeout: float = 5.0) -> Optional[str]:
        """
        Invokes Gemini API via shared services.gemini_client.
        Returns raw text response or None on failure/timeout.
        """
        from services.gemini_client import generate
        try:
            return generate(
                prompt=user_prompt,
                system_instruction=system_prompt,
                temperature=0.2
            )
        except Exception as e:
            logger.debug(f"Gemini API call failed via shared client: {e}")
            return None


# ============================================================================
# 6. Planning Service (Orchestrator & Fallback Engine)
# ============================================================================

class PlanningService:
    """High-level service orchestrating context prep, candidate evaluation, LLM execution & fallbacks."""

    @classmethod
    def generate_plan(cls, dispatch_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generates Contract 4 incident response plan with LLM reasoning and safe fallback."""
        context = ContextBuilder.build_context(dispatch_data)
        candidates = CandidateEvaluator.evaluate_candidates(context)

        # 1. Attempt Gemini LLM execution if API key is present
        system_prompt = PromptBuilder.SYSTEM_PROMPT
        user_prompt = PromptBuilder.build_user_prompt(context, candidates)

        raw_llm_response = LLMClient.call_gemini(system_prompt, user_prompt)
        if raw_llm_response:
            try:
                # Clean code blocks if returned
                cleaned_text = raw_llm_response.strip()
                if cleaned_text.startswith("```json"):
                    cleaned_text = cleaned_text[7:]
                if cleaned_text.startswith("```"):
                    cleaned_text = cleaned_text[3:]
                if cleaned_text.endswith("```"):
                    cleaned_text = cleaned_text[:-3]

                parsed_json = json.loads(cleaned_text.strip())
                is_valid, cleaned_plan = JSONValidator.validate_and_clean(parsed_json, context)
                if is_valid and cleaned_plan is not None:
                    return cleaned_plan
            except Exception as e:
                logger.debug(f"Failed to parse LLM JSON response: {e}")

            # Retry once with correction prompt if first attempt failed
            retry_prompt = f"{user_prompt}\n\nWARNING: Previous response was invalid JSON. Ensure response matches Contract 4 JSON schema exactly."
            raw_retry = LLMClient.call_gemini(system_prompt, retry_prompt)
            if raw_retry:
                try:
                    cleaned_retry = raw_retry.strip().strip("`").replace("json\n", "")
                    parsed_retry = json.loads(cleaned_retry)
                    is_valid_r, cleaned_plan_r = JSONValidator.validate_and_clean(parsed_retry, context)
                    if is_valid_r and cleaned_plan_r is not None:
                        return cleaned_plan_r
                except Exception:
                    pass

        # 2. Fallback Path (Deterministic trade-off reasoning)
        return cls._create_deterministic_fallback_plan(context, candidates)

    @classmethod
    def _create_deterministic_fallback_plan(
        cls, context: Dict[str, Any], candidates: List[CandidateOption]
    ) -> Dict[str, Any]:
        """Constructs high-quality deterministic fallback plan matching Contract 4 schema."""
        feasible_candidates = [c for c in candidates if c.feasible] if candidates else []

        if not feasible_candidates:
            b_dur = context.get("baseline_duration_hours", 0.0)
            dl_rem = context.get("deadline_hours", 0.0)
            sl_rem = context.get("shelf_life_hours")
            sl_str = f" and remaining shelf life of {sl_rem}h" if sl_rem is not None else ""
            reasoning = (
                f"No feasible operational action exists. Baseline remaining travel time ({b_dur}h) "
                f"already exceeds delivery deadline of {dl_rem}h{sl_str}. All evaluated candidate actions "
                f"(reroute, wait, transfer_to_storage) deterministically violate contractual deadline and/or cargo shelf-life constraints. "
                f"Escalation required."
            )
            return {
                "truck_id": context["truck_id"],
                "recommended_action": "no_feasible_action",
                "reasoning": reasoning,
                "estimated_delay_hours": 0.0,
                "estimated_cost": 0,
                "alternative_route": {
                    "distance_km": int(context.get("baseline_distance_km", 0)),
                    "duration_min": int(b_dur * 60.0),
                },
            }

        top_cand = feasible_candidates[0]

        truck_id = context["truck_id"]
        cargo_type = context["cargo_type"]
        disruption_type = context["disruption_type"]
        predicted_delay_h = context["predicted_delay_hours"]
        deadline_h = context["deadline_hours"]
        shelf_life_h = context["shelf_life_hours"]
        location = context["location"]
        action = top_cand.action
        is_temp = context["is_temp_sensitive"]

        shelf_life_clause = f"and shelf-life limit of {shelf_life_h}h." if shelf_life_h is not None else "(cargo shelf-life unspecified)."
        storage_shelf_clause = f"With {shelf_life_h}h safe transport remaining vs {predicted_delay_h}h delay" if shelf_life_h is not None else f"Due to {predicted_delay_h}h expected disruption delay"

        if action == "reroute":
            if context["is_threat"]:
                reasoning = (
                    f"{disruption_type} reported near {location} with ~{predicted_delay_h}h expected disruption. "
                    f"Rerouting via alternate highway adds {top_cand.estimated_delay_hours}h delay (costing INR {top_cand.estimated_cost:g}), "
                    f"staying comfortably within cargo deadline window of {deadline_h}h {shelf_life_clause}"
                )
            else:
                stoppage_min = int(context["fleet_output"].get("stoppage_duration_min", 45))
                reasoning = (
                    f"Unplanned stoppage ({stoppage_min} min) detected at {location} for {cargo_type}; "
                    f"rerouting via alternate highway adds total {top_cand.estimated_delay_hours}h delay (costing INR {top_cand.estimated_cost:g}), "
                    f"protecting the remaining cargo delivery deadline of {deadline_h}h."
                )
        elif action == "transfer_to_storage":
            if is_temp:
                reasoning = (
                    f"{disruption_type} near {location} threatens perishable {cargo_type}. "
                    f"{storage_shelf_clause}, transferring cargo to cold-storage hub ensures preservation (costing INR {top_cand.estimated_cost:g})."
                )
            else:
                reasoning = (
                    f"{disruption_type} near {location} affects transport of {cargo_type}. "
                    f"Diverting cargo to local logistics warehouse ensures operational holding and cargo security (costing INR {top_cand.estimated_cost:g})."
                )
        else:  # wait
            reasoning = (
                f"Disruption severity near {location} is low (~{predicted_delay_h}h). "
                f"Waiting out the stoppage incurs minimal delay ({top_cand.estimated_delay_hours}h, costing INR {top_cand.estimated_cost:g}), "
                f"preserving cargo safety within the remaining deadline of {deadline_h}h."
            )

        return {
            "truck_id": truck_id,
            "recommended_action": action,
            "reasoning": reasoning,
            "estimated_delay_hours": top_cand.estimated_delay_hours,
            "estimated_cost": top_cand.estimated_cost if top_cand.estimated_cost % 1 != 0 else int(top_cand.estimated_cost),
            "alternative_route": {
                "distance_km": int(top_cand.distance_km) if top_cand.distance_km.is_integer() else top_cand.distance_km,
                "duration_min": int(top_cand.duration_min) if top_cand.duration_min.is_integer() else top_cand.duration_min,
            },
        }


# ============================================================================
# 7. Main Entry Point (Preserves Public Contract Signature)
# ============================================================================

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
      "estimated_delay_hours": float/int,
      "estimated_cost": float/int,
      "alternative_route": {"distance_km": float/int, "duration_min": float/int}
    }
    """
    return PlanningService.generate_plan(dispatch_data)


