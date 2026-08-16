"""
Leaflet Map View Component using Folium and streamlit-folium
Phase 7 Overhaul: Precision Local Rerouting, Origin Marker & Map-Local Legend
- Filters map strictly to selected truck, dispatch origin, active disruption, and relevant destination facility.
- Renders 🔵 Original Scheduled Route (Neon Blue) from Dispatch Origin → Truck Location → Destination.
- Renders 🟢 AI Recommended Reroute (Neon Green Dashed) via precise local OSRM bypass anchored on original route polyline.
- Renders 🔴 Blocked Segment (Neon Red) directly on the original route polyline at the disruption point.
- Uses Leaflet dedicated Panes (z-index 420-700) for strict visual hierarchy.
- Caches OSRM route geometry via @st.cache_data to prevent unnecessary network requests during map interaction.
- Native Leaflet map-local control legend overlay positioned at top-right.
"""

import json
import math
import os
import urllib.request
import folium
import streamlit as st
from streamlit_folium import st_folium
from branca.element import MacroElement
from jinja2 import Template
from typing import Dict, Any, List, Optional, Tuple


FACILITIES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "facilities.json")
DISRUPTIONS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mock_disruptions.json")

# Authoritative Affected-Area Routing & Clearance Constants
AFFECTED_RADIUS_KM = 14.0
TARGET_BYPASS_ANCHOR_DIST_KM = 4.0  # 3-5 km target before and after incident
MIN_DEVIATION_KM = 0.50             # Minimum lateral deviation >= 500m
PEAK_DEVIATION_KM = 1.00            # Peak lateral deviation >= 1.0 km
MIN_DEVIATED_RATIO = 0.40           # At least 40% of points must deviate >= 500m
MIN_INCIDENT_CLEARANCE_KM = 0.40    # Clearance from exact disruption center >= 400m

# Backward compatibility aliases
REROUTE_CLEARANCE_KM = 1.0
MIN_CLEARANCE_KM = AFFECTED_RADIUS_KM + REROUTE_CLEARANCE_KM  # 15.0 km
MIN_REROUTE_SEPARATION_KM = 2.0
MIN_SEPARATION_RATIO = 0.80

# Authoritative City Coordinates Mapping for India Logistics Corridors
CITY_COORDINATES = {
    "jaipur": (26.9124, 75.7873),
    "delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "pune": (18.5204, 73.8567),
    "kalyan": (19.2403, 73.1305),
    "gurgaon": (28.4595, 77.0266),
    "gurugram": (28.4595, 77.0266),
    "sikar": (27.6094, 75.1398),
    "rewari": (28.3500, 76.9000),
    "vadodara": (22.3072, 73.1812),
    "surat": (21.1702, 72.8311),
    "ahmedabad": (23.0225, 72.5714),
    "nagpur": (21.1458, 79.0882),
    "bhopal": (23.2599, 77.4126),
}


class LeafletPaneManager(MacroElement):
    """
    Creates dedicated Leaflet custom panes with strict z-index ordering:
    - disruption_pane (z-index 420): Translucent affected area & radar circles
    - route_pane (z-index 500): Multi-layer glowing route polylines
    - hazard_marker_pane (z-index 600): Incident hazard triangle marker & facility building marker
    - truck_pane (z-index 700): Selected truck cyan halo rings & cyan truck icon marker (HIGHEST)
    """

    def __init__(self):
        super().__init__()
        self._name = "LeafletPaneManager"
        self._template = Template("""
            {% macro script(this, kwargs) %}
            var map = {{ this._parent.get_name() }};
            if (!map.getPane('disruption_pane')) {
                map.createPane('disruption_pane');
                map.getPane('disruption_pane').style.zIndex = 420;
            }
            if (!map.getPane('route_pane')) {
                map.createPane('route_pane');
                map.getPane('route_pane').style.zIndex = 500;
            }
            if (!map.getPane('hazard_marker_pane')) {
                map.createPane('hazard_marker_pane');
                map.getPane('hazard_marker_pane').style.zIndex = 600;
            }
            if (!map.getPane('truck_pane')) {
                map.createPane('truck_pane');
                map.getPane('truck_pane').style.zIndex = 700;
            }
            {% endmacro %}
        """)


class MapLegendControl(MacroElement):
    """
    Native Leaflet map-local legend control (L.control({position: 'topright'})).
    Disables click/scroll propagation to prevent map dragging when interacting with legend.
    """

    def __init__(self, html_content: str, position: str = "topright"):
        super().__init__()
        self._name = "MapLegendControl"
        self.html_content = html_content
        self.position = position
        self._template = Template("""
            {% macro script(this, kwargs) %}
            var legendControl = L.control({position: '{{ this.position }}'});
            legendControl.onAdd = function (map) {
                var div = L.DomUtil.create('div', 'lic-map-legend-control');
                div.innerHTML = {{ this.html_content|tojson }};
                L.DomEvent.disableClickPropagation(div);
                L.DomEvent.disableScrollPropagation(div);
                return div;
            };
            legendControl.addTo({{ this._parent.get_name() }});
            {% endmacro %}
        """)


def load_facilities_data() -> List[Dict[str, Any]]:
    """Loads facility data from data/facilities.json."""
    if os.path.exists(FACILITIES_PATH):
        try:
            with open(FACILITIES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def load_disruptions_data() -> Dict[str, Any]:
    """Loads disruption data from data/mock_disruptions.json."""
    if os.path.exists(DISRUPTIONS_PATH):
        try:
            with open(DISRUPTIONS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


@st.cache_data(show_spinner=False)
def fetch_osrm_route_geometry(
    start_coords: Tuple[float, float],
    end_coords: Tuple[float, float],
    timeout: float = 2.0,
) -> List[List[float]]:
    """
    Fetches real OSRM driving route polyline coordinates [[lat, lng], ...] from public OSRM server.
    Cached deterministically via @st.cache_data to prevent unnecessary OSRM network requests during map interaction.
    start_coords & end_coords format: (lat, lng)
    """
    start_lat, start_lng = round(float(start_coords[0]), 5), round(float(start_coords[1]), 5)
    end_lat, end_lng = round(float(end_coords[0]), 5), round(float(end_coords[1]), 5)
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lng},{start_lat};{end_lng},{end_lat}?overview=full&geometries=geojson"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LogisticsCommanderMap/7.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == "Ok" and data.get("routes"):
                    geojson_coords = data["routes"][0]["geometry"]["coordinates"]
                    return [[c[1], c[0]] for c in geojson_coords]
    except Exception:
        pass
    return [[start_lat, start_lng], [end_lat, end_lng]]


def add_glowing_polyline(
    m: folium.Map,
    coords: List[List[float]],
    color: str,
    tooltip_text: str,
    dash_array: Optional[str] = None,
    is_reroute: bool = False,
    pane: str = "route_pane",
):
    """
    Creates a multi-layer glowing polyline effect for command-center map visualization:
    Layer 1: Wide translucent underlay glow
    Layer 2: Medium colored glow core
    Layer 3: High-contrast bright core line
    All polylines rendered inside explicit Leaflet pane.
    """
    if not coords or len(coords) < 2:
        return

    # Layer 1: Wide Translucent Underlay Glow
    folium.PolyLine(
        coords,
        color=color,
        weight=14 if is_reroute else 12,
        opacity=0.30 if is_reroute else 0.25,
        dash_array=dash_array,
        tooltip=tooltip_text,
        pane=pane,
    ).add_to(m)

    # Layer 2: Medium Glow Core
    folium.PolyLine(
        coords,
        color=color,
        weight=7 if is_reroute else 6,
        opacity=0.75 if is_reroute else 0.65,
        dash_array=dash_array,
        tooltip=tooltip_text,
        pane=pane,
    ).add_to(m)

    # Layer 3: Bright Core Line
    core_color = "#E6FFFA" if is_reroute else ("#E0F7FA" if color == "#00BFFF" else "#FFE6EC")
    folium.PolyLine(
        coords,
        color=core_color,
        weight=3.0 if is_reroute else 2.5,
        opacity=0.95,
        dash_array=dash_array,
        tooltip=tooltip_text,
        pane=pane,
    ).add_to(m)


def resolve_origin_coordinates(truck: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """
    Resolves shipment dispatch origin coordinates.
    1. Checks if truck possesses explicit origin object {"lat": ..., "lng": ...}.
    2. Checks if origin is a string name matching CITY_COORDINATES or facilities.
    """
    origin = truck.get("origin")
    if isinstance(origin, dict):
        lat, lng = origin.get("lat"), origin.get("lng")
        if lat is not None and lng is not None:
            try:
                return (float(lat), float(lng))
            except (ValueError, TypeError):
                pass
    elif isinstance(origin, str):
        origin_lower = origin.lower()
        for city_key, coords in CITY_COORDINATES.items():
            if city_key in origin_lower:
                return coords
    return None


def resolve_destination_coordinates(
    destination_str: str,
    facilities_data: List[Dict[str, Any]],
) -> Optional[Tuple[float, float]]:
    """
    Resolves semantically correct destination coordinates for original route or mapping.
    1. Checks if destination_str matches facility name or location_name in facilities_data.
    2. Checks CITY_COORDINATES dictionary.
    Does NOT force fallback to arbitrary cold storage or default facilities.
    """
    dest_lower = str(destination_str).lower().strip()
    if not dest_lower:
        return None

    # Match by facility name or location
    for fac in facilities_data:
        name = str(fac.get("name", "")).lower()
        loc = str(fac.get("location_name", "")).lower()
        if dest_lower and (dest_lower in name or dest_lower in loc or name in dest_lower):
            lat, lng = fac.get("latitude"), fac.get("longitude")
            if lat is not None and lng is not None:
                return (float(lat), float(lng))

    # Match by city coordinates mapping
    for city_key, coords in CITY_COORDINATES.items():
        if city_key in dest_lower:
            return coords

    return None


def resolve_truck_destination_coordinates(
    truck: Dict[str, Any],
    facilities_data: List[Dict[str, Any]],
) -> Optional[Tuple[float, float]]:
    """
    Resolves final shipment destination coordinates.
    First checks truck's destination_location object (authoritative), then destination string, then facilities/cities.
    """
    dest_loc = truck.get("destination_location")
    if isinstance(dest_loc, dict):
        lat, lng = dest_loc.get("lat"), dest_loc.get("lng")
        if lat is not None and lng is not None:
            try:
                return (float(lat), float(lng))
            except (ValueError, TypeError):
                pass

    dest_str = str(truck.get("destination", ""))
    return resolve_destination_coordinates(dest_str, facilities_data)


def _find_closest_point_index(route: List[List[float]], target: Tuple[float, float]) -> int:
    """Finds the index of the coordinate in route polyline closest to target (lat, lng)."""
    if not route:
        return 0
    t_lat, t_lng = target
    min_dist_sq = float("inf")
    closest_idx = 0
    for i, pt in enumerate(route):
        dist_sq = (pt[0] - t_lat) ** 2 + (pt[1] - t_lng) ** 2
        if dist_sq < min_dist_sq:
            min_dist_sq = dist_sq
            closest_idx = i
    return closest_idx


def haversine_km(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Calculates haversine distance in kilometers between two (lat, lng) points."""
    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return 6371.0 * c


def find_geographic_bypass_anchors(
    full_orig_route: List[List[float]],
    dis_coords: Tuple[float, float],
    target_dist_km: float = TARGET_BYPASS_ANCHOR_DIST_KM,
    min_start_idx: int = 0,
) -> Tuple[int, int]:
    """
    Finds bypass start and end indices along full_orig_route such that
    bypass_start is ~target_dist_km (3-5 km) BEFORE the incident along route (bounded below by min_start_idx),
    and bypass_end is ~target_dist_km (3-5 km) AFTER the incident along route.
    Uses cumulative haversine distance along route polyline.
    """
    if not full_orig_route or len(full_orig_route) < 2:
        return 0, 0

    incident_idx = _find_closest_point_index(full_orig_route, dis_coords)

    # Walk backward from incident_idx accumulating distance (bounded by min_start_idx)
    start_idx = incident_idx
    cum_dist_back = 0.0
    while start_idx > min_start_idx:
        prev_pt = full_orig_route[start_idx]
        next_pt = full_orig_route[start_idx - 1]
        dist = haversine_km((prev_pt[0], prev_pt[1]), (next_pt[0], next_pt[1]))
        cum_dist_back += dist
        start_idx -= 1
        if cum_dist_back >= target_dist_km:
            break

    start_idx = max(start_idx, min_start_idx)

    # Walk forward from incident_idx accumulating distance
    end_idx = incident_idx
    cum_dist_fwd = 0.0
    n = len(full_orig_route)
    while end_idx < n - 1:
        prev_pt = full_orig_route[end_idx]
        next_pt = full_orig_route[end_idx + 1]
        dist = haversine_km((prev_pt[0], prev_pt[1]), (next_pt[0], next_pt[1]))
        cum_dist_fwd += dist
        end_idx += 1
        if cum_dist_fwd >= target_dist_km:
            break

    return start_idx, end_idx


def find_affected_area_bypass_anchors(
    full_orig_route: List[List[float]],
    dis_coords: Tuple[float, float],
    min_clearance_km: float = MIN_CLEARANCE_KM,
    min_start_idx: int = 0,
) -> Tuple[int, int]:
    """
    Finds bypass start and end indices along full_orig_route such that anchor points
    bypass_start and bypass_end are outside min_clearance_km (15.0 km) from dis_coords.
    start_idx is bounded below by min_start_idx.
    """
    if not full_orig_route:
        return 0, 0

    incident_idx = _find_closest_point_index(full_orig_route, dis_coords)

    # Walk backwards along route until point is at least min_clearance_km from dis_coords
    start_idx = incident_idx
    while start_idx > min_start_idx:
        pt = (full_orig_route[start_idx][0], full_orig_route[start_idx][1])
        if haversine_km(pt, dis_coords) >= min_clearance_km:
            break
        start_idx -= 1

    start_idx = max(start_idx, min_start_idx)

    # Walk forwards along route until point is at least min_clearance_km from dis_coords
    end_idx = incident_idx
    n = len(full_orig_route)
    while end_idx < n - 1:
        pt = (full_orig_route[end_idx][0], full_orig_route[end_idx][1])
        if haversine_km(pt, dis_coords) >= min_clearance_km:
            break
        end_idx += 1

    return start_idx, end_idx


def find_bypass_anchors(
    full_orig_route: List[List[float]],
    dis_coords: Tuple[float, float],
    target_dist_km: float = MIN_CLEARANCE_KM,
    min_start_idx: int = 0,
) -> Tuple[int, int]:
    """Alias for find_affected_area_bypass_anchors maintaining backward compatibility."""
    return find_affected_area_bypass_anchors(
        full_orig_route, dis_coords, min_clearance_km=target_dist_km, min_start_idx=min_start_idx
    )


def calculate_route_distance(route: List[List[float]]) -> float:
    """Calculates total driving distance in kilometers along a route polyline."""
    if not route or len(route) < 2:
        return 0.0
    total = 0.0
    for i in range(len(route) - 1):
        total += haversine_km((route[i][0], route[i][1]), (route[i + 1][0], route[i + 1][1]))
    return total


def validate_reroute_separation(
    candidate_route: List[List[float]],
    original_bypass_corridor: List[List[float]],
    dis_coords: Tuple[float, float],
    min_affected_radius_km: float = AFFECTED_RADIUS_KM,
    min_separation_km: float = MIN_REROUTE_SEPARATION_KM,
    min_separation_ratio: float = MIN_SEPARATION_RATIO,
) -> bool:
    """
    Validates candidate reroute geometry against:
    A. Affected-area clearance: EVERY candidate coordinate MUST satisfy
       haversine_km(pt, dis_coords) >= min_affected_radius_km (14.0 km).
    B. Original-route separation: Count candidate points whose minimum distance
       to any point in original_bypass_corridor is >= min_separation_km (2.0 km).
    """
    if not candidate_route or not original_bypass_corridor:
        return False

    for pt in candidate_route:
        if haversine_km((pt[0], pt[1]), dis_coords) < min_affected_radius_km:
            return False

    separated_points = 0
    total_points = len(candidate_route)

    for pt in candidate_route:
        cand_tuple = (pt[0], pt[1])
        min_dist_to_corridor = min(
            haversine_km(cand_tuple, (c[0], c[1])) for c in original_bypass_corridor
        )
        if min_dist_to_corridor >= min_separation_km:
            separated_points += 1

    separation_ratio = separated_points / float(total_points)
    return separation_ratio >= min_separation_ratio


def generate_local_bypass_candidates(
    bypass_start: List[float],
    bypass_end: List[float],
    dis_coords: Tuple[float, float],
) -> List[Tuple[float, float]]:
    """
    Generates local candidate waypoints offset perpendicularly to the route segment
    between bypass_start and bypass_end around dis_coords.
    Offsets range from +/- 0.015 deg to +/- 0.09 deg (~1.5 km to 9 km lateral offset).
    """
    d_lat = bypass_end[0] - bypass_start[0]
    d_lng = bypass_end[1] - bypass_start[1]
    seg_len = math.sqrt(d_lat**2 + d_lng**2)

    if seg_len > 1e-5:
        u_lat = d_lat / seg_len
        u_lng = d_lng / seg_len
        p_lat = -u_lng
        p_lng = u_lat
    else:
        p_lat, p_lng = 1.0, 0.0

    offsets = [
        0.015, -0.015,
        0.025, -0.025,
        0.035, -0.035,
        0.050, -0.050,
        0.070, -0.070,
        0.090, -0.090,
    ]

    candidates = []
    for off in offsets:
        wp_lat = dis_coords[0] + p_lat * off
        wp_lng = dis_coords[1] + p_lng * off
        candidates.append((wp_lat, wp_lng))

    return candidates


def validate_local_bypass_candidate(
    candidate_route: List[List[float]],
    original_blocked_corridor: List[List[float]],
    dis_coords: Tuple[float, float],
    min_deviation_km: float = MIN_DEVIATION_KM,
    peak_deviation_km: float = PEAK_DEVIATION_KM,
    min_deviated_ratio: float = MIN_DEVIATED_RATIO,
    min_incident_clearance_km: float = MIN_INCIDENT_CLEARANCE_KM,
) -> bool:
    """
    Validates a candidate OSRM bypass route:
    1. Incident clearance: Point near middle must not pass directly through disruption center (< 400m).
    2. Meaningful lateral deviation: Count candidate points whose minimum distance to original_blocked_corridor is >= min_deviation_km (0.5 km).
       Requires ratio of deviated points >= min_deviated_ratio (0.40) AND peak deviation >= peak_deviation_km (1.0 km).
    """
    if not candidate_route or len(candidate_route) < 3 or not original_blocked_corridor:
        return False

    # 1. Incident clearance check: Check minimum distance of interior candidate points to dis_coords
    interior_pts = candidate_route[1:-1] if len(candidate_route) > 2 else candidate_route
    min_dist_to_disruption = min(
        haversine_km((pt[0], pt[1]), dis_coords) for pt in interior_pts
    )
    if min_dist_to_disruption < min_incident_clearance_km:
        return False

    # 2. Check lateral deviation from original_blocked_corridor
    distances_to_corridor = []
    for pt in candidate_route:
        cand_tuple = (pt[0], pt[1])
        min_d = min(haversine_km(cand_tuple, (c[0], c[1])) for c in original_blocked_corridor)
        distances_to_corridor.append(min_d)

    max_deviation = max(distances_to_corridor)
    if max_deviation < peak_deviation_km:
        return False

    deviated_count = sum(1 for d in distances_to_corridor if d >= min_deviation_km)
    deviated_ratio = deviated_count / float(len(candidate_route))

    return deviated_ratio >= min_deviated_ratio


def find_best_valid_local_bypass(
    bypass_start: List[float],
    bypass_end: List[float],
    dis_coords: Tuple[float, float],
    original_blocked_corridor: List[List[float]],
) -> Optional[List[List[float]]]:
    """
    Evaluates all generated candidate waypoints, queries OSRM for driving routes,
    validates candidate geometry, and returns the shortest valid alternate driving route.
    Returns None if no candidate passes validation (fallback behavior: do NOT render fake line).
    """
    candidates = generate_local_bypass_candidates(bypass_start, bypass_end, dis_coords)

    valid_routes: List[Tuple[float, List[List[float]]]] = []

    for cand_wp in candidates:
        r1 = fetch_osrm_route_geometry(tuple(bypass_start), cand_wp)
        r2 = fetch_osrm_route_geometry(cand_wp, tuple(bypass_end))
        full_cand = r1 + r2

        if full_cand and len(full_cand) >= 4:
            if validate_local_bypass_candidate(
                candidate_route=full_cand,
                original_blocked_corridor=original_blocked_corridor,
                dis_coords=dis_coords,
            ):
                total_dist = calculate_route_distance(full_cand)
                valid_routes.append((total_dist, full_cand))

    if not valid_routes:
        return None

    # Pick the shortest valid driving route
    valid_routes.sort(key=lambda x: x[0])
    return valid_routes[0][1]


def generate_best_local_bypass(
    bypass_start: List[float],
    bypass_end: List[float],
    dis_coords: Tuple[float, float],
    blocked_geom: List[List[float]],
    min_clearance_km: float = MIN_CLEARANCE_KM,
    original_bypass_corridor: Optional[List[List[float]]] = None,
) -> Optional[List[List[float]]]:
    """Backward compatibility alias for find_best_valid_local_bypass."""
    corridor = original_bypass_corridor if original_bypass_corridor else blocked_geom
    return find_best_valid_local_bypass(
        bypass_start=bypass_start,
        bypass_end=bypass_end,
        dis_coords=dis_coords,
        original_blocked_corridor=corridor,
    )


def find_relevant_facility(
    selected_truck: Dict[str, Any],
    facilities_data: List[Dict[str, Any]],
    pipeline_result: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Finds ONLY the facility relevant to the selected truck's recommended plan:
    1. Reads recommended_action = plan.get("recommended_action")
    2. If recommended_action == "transfer_to_storage":
       - Inspects plan/pipeline_result for authoritative fields:
         selected_facility, facility, facility_id, target_facility, facility_name
       - Inspects plan reasoning text for facility_id or facility name
       - Matches closest compatible facility in facilities_data to truck location based on cargo perishable support
    3. Returns None for other actions (reroute, wait, no_feasible_action).
    """
    if not pipeline_result:
        return None

    plan = (pipeline_result.get("plan_data") if isinstance(pipeline_result, dict) else {}) or {}
    if not isinstance(plan, dict):
        plan = {}

    recommended_action = str(plan.get("recommended_action", "")).lower()

    if recommended_action != "transfer_to_storage":
        return None

    # Step 1: Inspect plan & pipeline_result for authoritative facility fields
    target_facility_val = (
        plan.get("selected_facility")
        or plan.get("facility")
        or plan.get("facility_id")
        or plan.get("target_facility")
        or plan.get("facility_name")
        or pipeline_result.get("selected_facility")
        or pipeline_result.get("facility_id")
        or pipeline_result.get("target_facility")
    )

    if isinstance(target_facility_val, dict):
        fac_id = str(target_facility_val.get("facility_id", "")).strip()
        fac_name = str(target_facility_val.get("name", "")).strip()
        for f in facilities_data:
            if fac_id and f.get("facility_id") == fac_id:
                return f
            if fac_name and fac_name.lower() in str(f.get("name", "")).lower():
                return f
        if "latitude" in target_facility_val and "longitude" in target_facility_val:
            return target_facility_val

    elif isinstance(target_facility_val, str) and target_facility_val.strip():
        val_str = target_facility_val.strip()
        for f in facilities_data:
            if f.get("facility_id") == val_str:
                return f
        for f in facilities_data:
            if val_str.lower() in str(f.get("name", "")).lower() or val_str.lower() in str(f.get("location_name", "")).lower():
                return f

    # Step 2: Check reasoning text for facility_id or facility name match
    reasoning = str(plan.get("reasoning", "")).lower()
    for f in facilities_data:
        fid = str(f.get("facility_id", "")).lower()
        fname = str(f.get("name", "")).lower()
        if fid and fid in reasoning:
            return f
        if fname and fname in reasoning:
            return f

    # Step 3: Match based on proximity to truck location & cargo perishability
    t_lat = selected_truck.get("lat")
    t_lng = selected_truck.get("lng")
    if t_lat is None or t_lng is None:
        loc = selected_truck.get("location")
        if isinstance(loc, dict):
            t_lat = loc.get("lat")
            t_lng = loc.get("lng")

    try:
        truck_coords = (float(t_lat), float(t_lng)) if t_lat is not None and t_lng is not None else None
    except (ValueError, TypeError):
        truck_coords = None

    cargo = str(selected_truck.get("cargo_type", "")).lower()
    is_temp = (
        "spoilage" in cargo
        or "pharma" in cargo
        or "produce" in cargo
        or "dairy" in cargo
        or "vaccine" in cargo
        or "perishable" in cargo
        or bool(selected_truck.get("is_temp_sensitive"))
    )

    matching_facilities = [f for f in facilities_data if f.get("supports_perishable_cargo") == is_temp]
    if not matching_facilities:
        matching_facilities = facilities_data

    if matching_facilities and truck_coords:
        def dist_to_truck(f):
            flat, flng = f.get("latitude"), f.get("longitude")
            if flat is not None and flng is not None:
                return (float(flat) - truck_coords[0]) ** 2 + (float(flng) - truck_coords[1]) ** 2
            return float("inf")

        matching_facilities.sort(key=dist_to_truck)
        return matching_facilities[0]

    return matching_facilities[0] if matching_facilities else None


def build_legend_html(is_post_analysis: bool = False) -> str:
    """
    Generates high-contrast dark operations-center map legend HTML content.
    Pre-analysis state shows Original Route. Post-analysis state shows Original, AI Reroute & Blocked Segment.
    Explicitly distinguishes Vehicles & Locations, Routes & Hazards.
    """
    reroute_row = (
        """
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.3rem;">
            <span style="display: inline-block; width: 24px; height: 0; border-top: 3px dashed #00FF66; box-shadow: 0 0 6px #00FF66;"></span>
            <span style="color: #F7FAFC;">AI Recommended Reroute</span>
        </div>
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.3rem;">
            <span style="display: inline-block; width: 24px; height: 4px; background: #FF0055; box-shadow: 0 0 6px #FF0055; border-radius: 2px;"></span>
            <span style="color: #F7FAFC;">Blocked Route Segment</span>
        </div>
        """
        if is_post_analysis
        else """
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.3rem; opacity: 0.5;">
            <span style="display: inline-block; width: 24px; height: 0; border-top: 2px dashed #A0AEC0;"></span>
            <span style="color: #A0AEC0;">AI Reroute (Pending Analysis)</span>
        </div>
        """
    )

    return f"""
    <div style="
        background: rgba(14, 17, 23, 0.94);
        border: 1px solid #4A5568;
        border-radius: 8px;
        padding: 0.75rem 0.95rem;
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
        font-size: 11px;
        color: #E2E8F0;
        box-shadow: 0 8px 20px rgba(0,0,0,0.7);
        width: 235px;
        pointer-events: auto;
    ">
        <div style="font-weight: 800; color: #00FFFF; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.4rem; display: flex; align-items: center; justify-content: space-between;">
            <span>MAP LEGEND</span>
            <span style="font-size: 9px; font-weight: 600; padding: 2px 6px; border-radius: 4px; background: {'#22543D; color: #68D391;' if is_post_analysis else '#2A4365; color: #63B3ED;'};">
                {'POST-ANALYSIS' if is_post_analysis else 'LIVE TRACK'}
            </span>
        </div>
        <hr style="border: 0; border-top: 1px solid #2D3748; margin: 0.4rem 0;"/>
        
        <div style="font-weight: 700; color: #CBD5E0; font-size: 10px; text-transform: uppercase; margin-bottom: 0.3rem; letter-spacing: 0.05em;">VEHICLES & LOCATIONS</div>
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.3rem;">
            <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #00FFFF; border: 2px solid #FFFFFF; box-shadow: 0 0 8px #00FFFF;"></span>
            <span style="font-weight: 600; color: #FFFFFF;">Selected Target Vehicle (🚚)</span>
        </div>
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.3rem;">
            <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #3182CE; border: 2px solid #FFFFFF; box-shadow: 0 0 6px #3182CE;"></span>
            <span style="color: #E2E8F0;">Dispatch Origin (📍)</span>
        </div>
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.3rem;">
            <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #805AD5; border: 2px solid #FFFFFF; box-shadow: 0 0 6px #805AD5;"></span>
            <span style="color: #E2E8F0;">Shipment Destination (🏁)</span>
        </div>
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.5rem;">
            <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #B794F4; box-shadow: 0 0 6px #B794F4;"></span>
            <span>Relevant Logistics Facility (🏭)</span>
        </div>

        <div style="font-weight: 700; color: #CBD5E0; font-size: 10px; text-transform: uppercase; margin-bottom: 0.3rem; letter-spacing: 0.05em;">ROUTES & HAZARDS</div>
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.3rem;">
            <span style="display: inline-block; width: 24px; height: 4px; background: #00BFFF; box-shadow: 0 0 6px #00BFFF; border-radius: 2px;"></span>
            <span>Original Scheduled Route</span>
        </div>
        {reroute_row}
        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.3rem;">
            <span style="color: #FF0055; font-weight: bold; font-size: 13px; line-height: 1;">🔺</span>
            <span>Active Incident Hazard</span>
        </div>
        <div style="display: flex; align-items: center; gap: 0.6rem;">
            <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; border: 1.5px dashed #FF0055; background: rgba(255,0,85,0.2);"></span>
            <span>Affected Area Radius (⭕)</span>
        </div>
    </div>
    """


def render_leaflet_map(
    fleet_data: List[Dict[str, Any]],
    disruptions_data: Dict[str, Any],
    facilities_data: List[Dict[str, Any]],
    selected_truck_id: Optional[str] = None,
    pipeline_result: Optional[Dict[str, Any]] = None,
):
    """
    Renders the SELECTED TRUCK OPERATIONAL MAP using Folium.
    Phase 7 Requirements:
    - Filters map strictly to selected_truck_id, its dispatch origin, its disruption, and its destination.
    - Pre-Analysis: Renders 🔵 Original Scheduled Route (Neon Blue) from Dispatch Origin → Truck Location → Destination.
    - Post-Analysis: Renders 🟢 AI Recommended Reroute (Neon Green Dashed) via precise local OSRM bypass anchored on original route polyline.
    - Renders 🔴 Blocked Segment (Neon Red) directly on original route polyline.
    - Leaflet Pane z-index hierarchy guarantees Selected Truck is visible on top of all overlays.
    - Native Leaflet map-local control legend overlay positioned at top-right corner.
    """
    # 1. SCOPE FILTERING — Find Selected Truck ONLY
    truck_by_id = {t.get("truck_id"): t for t in fleet_data if t.get("truck_id")}
    if not selected_truck_id or selected_truck_id not in truck_by_id:
        selected_truck_id = list(truck_by_id.keys())[0] if truck_by_id else "UNKNOWN"

    selected_truck = truck_by_id.get(selected_truck_id, {})

    # Extract selected truck current location coordinates
    selected_lat = selected_truck.get("lat")
    selected_lng = selected_truck.get("lng")
    if selected_lat is None or selected_lng is None:
        loc = selected_truck.get("location")
        if isinstance(loc, dict):
            selected_lat = loc.get("lat")
            selected_lng = loc.get("lng")

    try:
        selected_coords = (float(selected_lat), float(selected_lng)) if selected_lat is not None and selected_lng is not None else None
    except (ValueError, TypeError):
        selected_coords = None

    # Resolve Shipment Origin coordinates
    origin_coords = resolve_origin_coordinates(selected_truck)

    center_lat, center_lng = selected_coords if selected_coords else (origin_coords if origin_coords else (22.5937, 78.9629))

    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=7,
        tiles="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
        name="Selected Truck Operational Map",
    )

    # Add Dedicated Leaflet Custom Panes with strict Z-Index Hierarchy
    LeafletPaneManager().add_to(m)

    bounds_points: List[Tuple[float, float]] = []
    if selected_coords:
        bounds_points.append(selected_coords)

    # 2. RENDER SHIPMENT DISPATCH ORIGIN MARKER
    if origin_coords:
        bounds_points.append(origin_coords)
        origin_raw = selected_truck.get("origin")
        origin_name = origin_raw.get("name") if isinstance(origin_raw, dict) else str(origin_raw or "Dispatch Origin")

        origin_group = folium.FeatureGroup(name="Shipment Dispatch Origin")

        # Blue Outer Glow Ring (hazard_marker_pane: z-index 600)
        folium.CircleMarker(
            location=origin_coords,
            radius=10,
            color="#3182CE",
            weight=2,
            fill=True,
            fill_color="#63B3ED",
            fill_opacity=0.4,
            tooltip=f"📍 DISPATCH ORIGIN: {origin_name}",
            pane="hazard_marker_pane",
        ).add_to(origin_group)

        # Dispatch Origin Icon Marker
        popup_html = f"""
        <div style="font-family: sans-serif; font-size: 12px; width: 200px; color: #1A202C;">
            <b style="color: #2B6CB0; font-size: 13px;">📍 DISPATCH ORIGIN</b><br/>
            <b>Location:</b> {origin_name}<br/>
            <b>Shipment Target:</b> {selected_truck_id}
        </div>
        """
        folium.Marker(
            location=origin_coords,
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=f"📍 ORIGIN — {origin_name}",
            icon=folium.Icon(color="blue", icon="play", prefix="fa"),
            pane="hazard_marker_pane",
        ).add_to(origin_group)

        origin_group.add_to(m)

    # 2b. RENDER DISTINCT SHIPMENT DESTINATION MARKER
    dest_coords = resolve_truck_destination_coordinates(selected_truck, facilities_data)
    if dest_coords:
        bounds_points.append(dest_coords)
        dest_loc_obj = selected_truck.get("destination_location")
        if isinstance(dest_loc_obj, dict) and dest_loc_obj.get("name"):
            dest_name = dest_loc_obj.get("name")
        else:
            dest_name = str(selected_truck.get("destination", "Shipment Destination"))

        shipment_id = selected_truck.get("shipment_id", "N/A")

        dest_group = folium.FeatureGroup(name="Shipment Destination")

        # Purple Outer Glow Ring (hazard_marker_pane: z-index 600)
        folium.CircleMarker(
            location=dest_coords,
            radius=10,
            color="#805AD5",
            weight=2,
            fill=True,
            fill_color="#B794F4",
            fill_opacity=0.4,
            tooltip=f"🏁 DESTINATION: {dest_name}",
            pane="hazard_marker_pane",
        ).add_to(dest_group)

        # Flag-checkered Icon Marker
        popup_html = f"""
        <div style="font-family: sans-serif; font-size: 12px; width: 200px; color: #1A202C;">
            <b style="color: #6B46C1; font-size: 13px;">🏁 DESTINATION</b><br/>
            <b>Name:</b> {dest_name}<br/>
            <b>Shipment ID:</b> {shipment_id}<br/>
            <b>Truck ID:</b> {selected_truck_id}
        </div>
        """

        folium.Marker(
            location=dest_coords,
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=f"🏁 DESTINATION: {dest_name}",
            icon=folium.Icon(color="purple", icon="flag-checkered", prefix="fa"),
            pane="hazard_marker_pane",
        ).add_to(dest_group)

        dest_group.add_to(m)

    # 3. RENDER SELECTED TRUCK MARKER ONLY (No other fleet trucks)
    # Rendered inside 'truck_pane' (z-index 700) to sit above all disruption circles and polylines
    if selected_coords:
        sid = selected_truck.get("shipment_id", "N/A")
        cargo = selected_truck.get("cargo_type", "General")
        dest = selected_truck.get("destination", "N/A")
        speed = selected_truck.get("speed_kmh", 0)
        delay = selected_truck.get("delay_minutes", 0)
        status = str(selected_truck.get("status", "")).lower()

        if selected_truck_id in disruptions_data:
            status_label = "🔴 Incident"
        elif status == "abnormal_stop" or selected_truck.get("stopped_duration_minutes", 0) > 30 or delay > 30:
            status_label = "🟠 At Risk"
        else:
            status_label = "🟢 Normal"

        popup_html = f"""
        <div style="font-family: sans-serif; font-size: 12px; width: 220px; color: #1A202C;">
            <b style="font-size: 13px; color: #00B5D8;">🩵 {selected_truck_id}</b> ({sid})<br/>
            <b>Status:</b> {status_label}<br/>
            <b>Cargo:</b> {cargo}<br/>
            <b>Destination:</b> {dest}<br/>
            <b>Speed:</b> {speed} km/h | <b>Delay:</b> {delay} mins
        </div>
        """

        fleet_group = folium.FeatureGroup(name="Selected Vehicle Target")

        # Outer Cyan Halo Ring (truck_pane: z-index 700)
        folium.CircleMarker(
            location=selected_coords,
            radius=22,
            color="#00FFFF",
            weight=3,
            fill=True,
            fill_color="#00FFFF",
            fill_opacity=0.25,
            tooltip=f"🩵 SELECTED VEHICLE TARGET — {selected_truck_id}",
            pane="truck_pane",
        ).add_to(fleet_group)

        # Inner Cyan Core Ring (truck_pane: z-index 700)
        folium.CircleMarker(
            location=selected_coords,
            radius=14,
            color="#00FFFF",
            weight=2,
            fill=True,
            fill_color="#00E5FF",
            fill_opacity=0.45,
            pane="truck_pane",
        ).add_to(fleet_group)

        # Highly Visible Truck Icon Marker (truck_pane: z-index 700)
        folium.Marker(
            location=selected_coords,
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"🩵 {selected_truck_id} — SELECTED TARGET ({status_label})",
            icon=folium.Icon(color="cadetblue", icon="truck", prefix="fa"),
            pane="truck_pane",
        ).add_to(fleet_group)

        fleet_group.add_to(m)

    # 4. RENDER SELECTED TRUCK'S DISRUPTION ONLY
    selected_disruption = disruptions_data.get(selected_truck_id)
    dis_coords: Optional[Tuple[float, float]] = None

    if selected_disruption:
        dis_loc = selected_disruption.get("location")
        if isinstance(dis_loc, dict):
            dlat, dlng = dis_loc.get("lat"), dis_loc.get("lng")
            if dlat is not None and dlng is not None:
                try:
                    dis_coords = (float(dlat), float(dlng))
                except (ValueError, TypeError):
                    pass

        if dis_coords is None and selected_coords:
            dis_coords = selected_coords

        if dis_coords:
            bounds_points.append(dis_coords)
            dis_type = str(selected_disruption.get("disruption_type", "Disruption")).upper()
            severity = str(selected_disruption.get("severity", "HIGH")).upper()
            desc = selected_disruption.get("description", "Road disruption reported")
            delay_h = selected_disruption.get("predicted_delay_hours", 0)
            corridor = selected_disruption.get("affected_corridor", "En-route Corridor")

            popup_html = f"""
            <div style="font-family: sans-serif; font-size: 12px; width: 220px; color: #1A202C;">
                <b style="color: #C53030; font-size: 13px;">🚨 INCIDENT HAZARD: {selected_truck_id}</b><br/>
                <b>Type:</b> {dis_type} ({severity})<br/>
                <b>Description:</b> {desc}<br/>
                <b>Predicted Delay:</b> {delay_h} hours<br/>
                <b>Corridor:</b> {corridor}
            </div>
            """

            disruption_group = folium.FeatureGroup(name="Active Incident Hazard")

            # Pulsing Red Hazard Radar Ring (disruption_pane: z-index 420)
            folium.CircleMarker(
                location=dis_coords,
                radius=18,
                color="#FF0055",
                weight=3,
                fill=False,
                opacity=0.8,
                tooltip=f"🚨 Hazard Radar: {dis_type}",
                pane="disruption_pane",
            ).add_to(disruption_group)

            # Translucent Red Affected Area Radius (disruption_pane: z-index 420)
            folium.Circle(
                location=dis_coords,
                radius=int(AFFECTED_RADIUS_KM * 1000),
                color="#FF0055",
                weight=2,
                fill=True,
                fill_color="#FF0055",
                fill_opacity=0.18,
                dash_array="5, 5",
                tooltip=f"🔴 Affected Area ({dis_type})",
                pane="disruption_pane",
            ).add_to(disruption_group)

            # Distinct Hazard Exclamation Triangle Marker (hazard_marker_pane: z-index 600)
            folium.Marker(
                location=dis_coords,
                popup=folium.Popup(popup_html, max_width=250),
                tooltip=f"🚨 INCIDENT HAZARD: {dis_type}",
                icon=folium.Icon(color="darkred", icon="exclamation-triangle", prefix="fa"),
                pane="hazard_marker_pane",
            ).add_to(disruption_group)

            disruption_group.add_to(m)

    # 5. RENDER RELEVANT FACILITY ONLY (IF PRESENT & SEPARATE)
    rel_fac = find_relevant_facility(selected_truck, facilities_data, pipeline_result)
    if rel_fac:
        flat, flng = rel_fac.get("latitude"), rel_fac.get("longitude")
        if flat is not None and flng is not None:
            fac_coords = (float(flat), float(flng))
            bounds_points.append(fac_coords)
            fac_id = rel_fac.get("facility_id", "FAC")
            name = rel_fac.get("name", "Warehouse Facility")
            fac_type = rel_fac.get("type", "warehouse").replace("_", " ").title()
            loc_name = rel_fac.get("location_name", "N/A")
            avail_cap = rel_fac.get("available_capacity_percent", 0)
            is_cold = rel_fac.get("supports_perishable_cargo", False)

            popup_html = f"""
            <div style="font-family: sans-serif; font-size: 12px; width: 210px; color: #1A202C;">
                <b style="color: #6B46C1; font-size: 13px;">🏭 {name}</b><br/>
                <b>Facility ID:</b> {fac_id}<br/>
                <b>Type:</b> {fac_type} {'(Cold Storage)' if is_cold else ''}<br/>
                <b>Location:</b> {loc_name}<br/>
                <b>Available Capacity:</b> {avail_cap}%
            </div>
            """

            facility_group = folium.FeatureGroup(name="Relevant Logistics Facility")

            # Purple Glowing Ring (disruption_pane: z-index 420)
            folium.CircleMarker(
                location=fac_coords,
                radius=12,
                color="#B794F4",
                weight=2,
                fill=True,
                fill_color="#9F7AEA",
                fill_opacity=0.3,
                tooltip=f"🏭 Relevant Hub: {name}",
                pane="disruption_pane",
            ).add_to(facility_group)

            # Facility Marker (hazard_marker_pane: z-index 600)
            folium.Marker(
                location=fac_coords,
                popup=folium.Popup(popup_html, max_width=250),
                tooltip=f"🏭 {name} ({fac_id})",
                icon=folium.Icon(color="purple", icon="building", prefix="fa"),
                pane="hazard_marker_pane",
            ).add_to(facility_group)

            facility_group.add_to(m)

    # 6. STATE 1: PRE-ANALYSIS ORIGINAL ROUTE (Neon Blue) — RENDERS IMMEDIATELY UPON SELECTION
    plan = (pipeline_result.get("plan_data") if pipeline_result else {}) or {}

    start_point = origin_coords if origin_coords else selected_coords

    full_orig_route: List[List[float]] = []

    if start_point:
        # Calculate Original Scheduled Route from Dispatch Origin → Current Truck Pos → Incident → Destination
        if origin_coords and selected_coords and (origin_coords != selected_coords):
            leg1 = fetch_osrm_route_geometry(origin_coords, selected_coords)
            if dis_coords and dest_coords:
                leg2 = fetch_osrm_route_geometry(selected_coords, dis_coords)
                leg3 = fetch_osrm_route_geometry(dis_coords, dest_coords)
                full_orig_route = leg1 + leg2 + leg3
            elif dest_coords:
                leg2 = fetch_osrm_route_geometry(selected_coords, dest_coords)
                full_orig_route = leg1 + leg2
            else:
                full_orig_route = leg1
        else:
            if dis_coords and dest_coords:
                leg1 = fetch_osrm_route_geometry(selected_coords, dis_coords)
                leg2 = fetch_osrm_route_geometry(dis_coords, dest_coords)
                full_orig_route = leg1 + leg2
            elif dest_coords:
                full_orig_route = fetch_osrm_route_geometry(selected_coords, dest_coords)
            elif dis_coords:
                full_orig_route = fetch_osrm_route_geometry(selected_coords, dis_coords)
            else:
                full_orig_route = []

        if full_orig_route:
            add_glowing_polyline(
                m,
                full_orig_route,
                color="#00BFFF",
                tooltip_text="🔵 ORIGINAL / SCHEDULED ROUTE",
                is_reroute=False,
                pane="route_pane",
            )

    # 7. STATE 2: POST-ANALYSIS REROUTE & STORAGE VISUALIZATION
    is_post_analysis = False
    if pipeline_result and selected_coords and selected_truck_id:
        gate = pipeline_result.get("dispatch_output") or {}
        plan = (pipeline_result.get("plan_data") if pipeline_result else {}) or {}
        recommended_action = str(plan.get("recommended_action", "")).lower()

        if gate.get("escalate") and plan:
            is_post_analysis = True

            truck_idx = _find_closest_point_index(full_orig_route, selected_coords) if full_orig_route else 0

            # 1. Render BLOCKED ROUTE SEGMENT on original route at disruption
            if dis_coords and full_orig_route:
                in_circle_indices = [
                    i for i, pt in enumerate(full_orig_route)
                    if haversine_km((pt[0], pt[1]), dis_coords) <= AFFECTED_RADIUS_KM
                ]

                if in_circle_indices:
                    b_start = max(0, in_circle_indices[0] - 1)
                    b_end = min(len(full_orig_route) - 1, in_circle_indices[-1] + 1)
                    blocked_geom = full_orig_route[b_start : b_end + 1]
                else:
                    closest_idx = _find_closest_point_index(full_orig_route, dis_coords)
                    b_start = max(0, closest_idx - 1)
                    b_end = min(len(full_orig_route) - 1, closest_idx + 1)
                    blocked_geom = full_orig_route[b_start : b_end + 1]

                if len(blocked_geom) >= 2:
                    folium.PolyLine(
                        blocked_geom,
                        color="#FF0055",
                        weight=14,
                        opacity=0.35,
                        tooltip="🔴 BLOCKED / AFFECTED CORRIDOR",
                        pane="route_pane",
                    ).add_to(m)
                    folium.PolyLine(
                        blocked_geom,
                        color="#FF0055",
                        weight=6,
                        opacity=0.90,
                        tooltip="🔴 BLOCKED / AFFECTED CORRIDOR",
                        pane="route_pane",
                    ).add_to(m)

            # 2. ACTION-SPECIFIC GEOMETRY VISUALIZATION
            # Only show green AI Recommended Reroute when recommended_action == "reroute"
            if recommended_action == "reroute" and dis_coords and full_orig_route:
                # Upstream anchor MUST NOT be located on dispatch-origin -> current-truck portion
                bypass_start_idx, bypass_end_idx = find_geographic_bypass_anchors(
                    full_orig_route, dis_coords, target_dist_km=TARGET_BYPASS_ANCHOR_DIST_KM, min_start_idx=truck_idx
                )

                start_i = max(truck_idx, min(bypass_start_idx, bypass_end_idx))
                end_i = max(start_i, max(bypass_start_idx, bypass_end_idx))

                bypass_start = full_orig_route[start_i]
                bypass_end = full_orig_route[end_i]
                original_blocked_corridor = full_orig_route[start_i : end_i + 1]

                local_bypass = find_best_valid_local_bypass(
                    bypass_start=bypass_start,
                    bypass_end=bypass_end,
                    dis_coords=dis_coords,
                    original_blocked_corridor=original_blocked_corridor,
                )

                if local_bypass:
                    # Operational reroute MUST start at current truck and end at final destination
                    truck_to_bypass = full_orig_route[truck_idx : start_i]
                    bypass_to_dest = full_orig_route[end_i + 1 :]

                    full_reroute: List[List[float]] = []
                    for pt in truck_to_bypass:
                        full_reroute.append([pt[0], pt[1]])
                    for pt in local_bypass:
                        if not full_reroute or haversine_km((full_reroute[-1][0], full_reroute[-1][1]), (pt[0], pt[1])) > 0.001:
                            full_reroute.append([pt[0], pt[1]])
                    for pt in bypass_to_dest:
                        if not full_reroute or haversine_km((full_reroute[-1][0], full_reroute[-1][1]), (pt[0], pt[1])) > 0.001:
                            full_reroute.append([pt[0], pt[1]])

                    if full_reroute:
                        # Ensure first coordinate is at current truck position
                        full_reroute[0] = [selected_coords[0], selected_coords[1]]
                        # Ensure last coordinate is at destination position if available
                        if dest_coords:
                            full_reroute[-1] = [dest_coords[0], dest_coords[1]]

                        for pt in full_reroute:
                            bounds_points.append((pt[0], pt[1]))

                        add_glowing_polyline(
                            m,
                            full_reroute,
                            color="#00FF66",
                            tooltip_text="🟢 AI RECOMMENDED REROUTE",
                            dash_array="8, 8",
                            is_reroute=True,
                            pane="route_pane",
                        )

            elif recommended_action == "transfer_to_storage" and rel_fac:
                flat, flng = rel_fac.get("latitude"), rel_fac.get("longitude")
                if flat is not None and flng is not None:
                    fac_coords = (float(flat), float(flng))
                    fac_name = rel_fac.get("name", "Storage Facility")

                    # Leg 1: Current Truck → Selected Facility
                    leg1 = fetch_osrm_route_geometry(selected_coords, fac_coords)
                    if leg1 and len(leg1) >= 2:
                        for pt in leg1:
                            bounds_points.append((pt[0], pt[1]))
                        add_glowing_polyline(
                            m,
                            leg1,
                            color="#9F7AEA",
                            tooltip_text=f"🟣 STORAGE DIVERSION LEG 1: Current Truck → {fac_name}",
                            dash_array="6, 6",
                            is_reroute=True,
                            pane="route_pane",
                        )

                    # Leg 2: Selected Facility → Final Destination
                    if dest_coords:
                        leg2 = fetch_osrm_route_geometry(fac_coords, dest_coords)
                        if leg2 and len(leg2) >= 2:
                            for pt in leg2:
                                bounds_points.append((pt[0], pt[1]))
                            add_glowing_polyline(
                                m,
                                leg2,
                                color="#B794F4",
                                tooltip_text=f"🏁 STORAGE DIVERSION LEG 2: {fac_name} → Final Destination",
                                dash_array="6, 6",
                                is_reroute=True,
                                pane="route_pane",
                            )

    # 8. DYNAMIC AUTO-FRAMING BOUNDS (Strictly scoped to selected truck context)
    if bounds_points and len(bounds_points) >= 2:
        lats = [p[0] for p in bounds_points if p[0] is not None]
        lngs = [p[1] for p in bounds_points if p[1] is not None]
        if lats and lngs:
            min_lat, max_lat = min(lats), max(lats)
            min_lng, max_lng = min(lngs), max(lngs)
            lat_margin = max((max_lat - min_lat) * 0.25, 0.15)
            lng_margin = max((max_lng - min_lng) * 0.25, 0.15)
            m.fit_bounds([
                [min_lat - lat_margin, min_lng - lng_margin],
                [max_lat + lat_margin, max_lng + lng_margin]
            ])

    # 9. NATIVE LEAFLET MAP-LOCAL CONTROL LEGEND OVERLAY (Top-Right)
    legend_html = build_legend_html(is_post_analysis=is_post_analysis)
    MapLegendControl(legend_html, position="topright").add_to(m)

    # Render Folium Map in Streamlit with returned_objects=[] to eliminate unnecessary rerun data sync
    st_folium(m, returned_objects=[], use_container_width=True, height=540, key=f"map_{selected_truck_id}")