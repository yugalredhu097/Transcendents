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
    "transfer_to_another_vehicle",
}

FACILITIES_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "facilities.json"
)


# ============================================================================
# 1. Deterministic Helpers (Public API preservation)
# ============================================================================

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

        # Cargo & SLA constraints
        cargo_type = fleet_output.get("cargo_type") or dispatch_data.get("cargo_type") or "Standard Freight"
        # Cargo & SLA constraints
        cargo_type = fleet_output.get("cargo_type") or dispatch_data.get("cargo_type") or "Standard Freight"
        cargo_lower = cargo_type.lower()
        is_temp_sensitive = any(w in cargo_lower for w in ["vaccine", "pharmaceutical", "pharma", "seafood", "frozen", "produce", "perishable"])
        is_hazmat = any(w in cargo_lower for w in ["hazard", "chemical", "hazmat", "explosive", "fuel"])

        deadline_hours = float(fleet_output.get("deadline_hours_remaining") or dispatch_data.get("deadline_hours_remaining") or 4.0)
        customer_priority = str(fleet_output.get("customer_priority") or dispatch_data.get("customer_priority") or "medium").lower()

        # Explicit remaining shelf life (do NOT fabricate values if missing)
        raw_shelf_life = fleet_output.get("shelf_life_hours")
        if raw_shelf_life is None:
            raw_shelf_life = dispatch_data.get("shelf_life_hours")

        shelf_life_hours: Optional[float] = None
        if raw_shelf_life is not None:
            try:
                shelf_life_hours = float(raw_shelf_life)
            except (ValueError, TypeError):
                shelf_life_hours = None

        # Disruption details
        is_threat = (
            "threat" in reason
            or threat_output.get("threat_detected") is True
            or bool(threat_output.get("threat_type"))
        )

        if is_threat:
            disruption_type = threat_output.get("threat_type") or threat_output.get("disruption_type") or "Road disruption"
            severity = threat_output.get("severity", "high")
            predicted_delay_hours = float(threat_output.get("predicted_delay_hours") or threat_output.get("estimated_arrival_hours") or 3.0)
            location = threat_output.get("threat_location") or "En-route Corridor"
        else:
            disruption_type = fleet_output.get("disruption_type") or "Vehicle Stoppage / Breakdown"
            severity = fleet_output.get("severity", "medium")
            stoppage_min = float(fleet_output.get("stoppage_duration_min", 45))
            predicted_delay_hours = round(stoppage_min / 60.0, 1)
            location = fleet_output.get("location") or "Highway Segment"
            if isinstance(location, dict):
                location = location.get("name", "Highway Segment")

        # Coordinates
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

        facilities = cls.load_facilities()

        return {
            "truck_id": truck_id,
            "reason": reason,
            "is_threat": is_threat,
            "disruption_type": disruption_type,
            "severity": severity,
            "predicted_delay_hours": predicted_delay_hours,
            "location": location,
            "cargo_type": cargo_type,
            "is_temp_sensitive": is_temp_sensitive,
            "is_hazmat": is_hazmat,
            "shelf_life_hours": shelf_life_hours,
            "deadline_hours": deadline_hours,
            "customer_priority": customer_priority,
            "start_coords": start_coords,
            "end_coords": end_coords,
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
        """Generates and scores deterministic candidate options."""
        options: List[CandidateOption] = []
        is_threat = context["is_threat"]
        fleet_output = context["fleet_output"]
        threat_output = context["threat_output"]
        shelf_life = context["shelf_life_hours"]  # Optional[float]
        shelf_life_known = (shelf_life is not None)
        deadline = context["deadline_hours"]

        # Attempt OSRM route for reroute option
        osrm_data = None
        if context["use_osrm"]:
            osrm_data = fetch_osrm_route(context["start_coords"], context["end_coords"])

        # ---------------------------------------------------------------------
        # Option 1: REROUTE
        # ---------------------------------------------------------------------
        if is_threat:
            if osrm_data:
                dist_km = float(osrm_data["distance_km"])
                dur_min = float(osrm_data["duration_min"])
            else:
                dist_km = float(threat_output.get("suggested_detour_km", 62))
                dur_min = float(threat_output.get("suggested_detour_min", 95))
            base_rate = float(threat_output.get("base_cost_per_km", DEFAULT_BASE_COST_PER_KM))
            cost_reroute = calculate_route_cost_impact(dist_km, dur_min, base_cost_per_km=base_rate)
            delay_reroute = round(dur_min / 60.0, 1)
        else:
            stoppage_min = float(fleet_output.get("stoppage_duration_min", 45))
            if osrm_data:
                dist_km = float(osrm_data["distance_km"])
                dur_min = float(osrm_data["duration_min"])
            else:
                dist_km = float(fleet_output.get("detour_distance_km", 45))
                dur_min = float(fleet_output.get("detour_duration_min", 75))
            delay_reroute = round((stoppage_min + dur_min) / 60.0, 1)
            base_cost = calculate_route_cost_impact(dist_km, dur_min)
            penalty_rate = float(fleet_output.get("delay_penalty_per_hour", DEFAULT_STOPPAGE_PENALTY_PER_HOUR))
            stoppage_penalty = penalty_rate * (stoppage_min / 60.0)
            cost_reroute = round(base_cost + stoppage_penalty, 2)

        shelf_life_ok_reroute = (delay_reroute <= shelf_life) if shelf_life_known else True

        options.append(
            CandidateOption(
                action="reroute",
                distance_km=dist_km,
                duration_min=dur_min,
                estimated_delay_hours=delay_reroute,
                estimated_cost=cost_reroute,
                description=f"Reroute via alternate corridor ({dist_km} km, {dur_min} min).",
                # True here must not be interpreted as verified shelf-life safety when shelf life is unknown.
                shelf_life_ok=shelf_life_ok_reroute,
                deadline_ok=delay_reroute <= deadline,
                score=cost_reroute + (delay_reroute * 50),
            )
        )

        # ---------------------------------------------------------------------
        # Option 2: WAIT
        # ---------------------------------------------------------------------
        predicted_wait_h = context["predicted_delay_hours"]
        wait_dur_min = round(predicted_wait_h * 60.0, 1)
        penalty_per_h = float(fleet_output.get("delay_penalty_per_hour", DEFAULT_STOPPAGE_PENALTY_PER_HOUR))
        wait_cost = round((predicted_wait_h * penalty_per_h) + 150.0, 2)
        shelf_life_ok_wait = (predicted_wait_h <= shelf_life) if shelf_life_known else True

        options.append(
            CandidateOption(
                action="wait",
                distance_km=0.0,
                duration_min=wait_dur_min,
                estimated_delay_hours=predicted_wait_h,
                estimated_cost=wait_cost,
                description=f"Wait out disruption at current site (~{predicted_wait_h}h).",
                # True here must not be interpreted as verified shelf-life safety when shelf life is unknown.
                shelf_life_ok=shelf_life_ok_wait,
                deadline_ok=predicted_wait_h <= deadline,
                score=wait_cost + (predicted_wait_h * 300) + 1500 + (0 if shelf_life_ok_wait else 5000),
            )
        )

        # ---------------------------------------------------------------------
        # Option 3: TRANSFER TO STORAGE (Warehouse / Cold Storage)
        # ---------------------------------------------------------------------
        facilities = context["facilities"]
        is_temp = context["is_temp_sensitive"]
        matching_facilities = [f for f in facilities if f.get("supports_perishable_cargo") == is_temp]
        target_fac = matching_facilities[0] if matching_facilities else (facilities[0] if facilities else {})

        fac_name = target_fac.get("name", "Regional Logistics Hub")
        fac_cost_per_h = float(target_fac.get("storage_cost_per_hour", DEFAULT_STORAGE_COST_PER_HOUR))
        fac_handling = float(target_fac.get("handling_cost", DEFAULT_HANDLING_COST))
        storage_hours = max(2.0, predicted_wait_h)
        fac_total_cost = round(fac_handling + (storage_hours * fac_cost_per_h) + 300.0, 2)
        fac_delay_h = round(storage_hours + 1.0, 1)

        options.append(
            CandidateOption(
                action="transfer_to_storage",
                distance_km=15.0,
                duration_min=round(fac_delay_h * 60.0, 1),
                estimated_delay_hours=fac_delay_h,
                estimated_cost=fac_total_cost,
                description=f"Divert cargo to storage at {fac_name} for preservation.",
                shelf_life_ok=True,
                deadline_ok=fac_delay_h <= deadline,
                score=fac_total_cost + (fac_delay_h * 150) + 800,
            )
        )

        # ---------------------------------------------------------------------
        # Option 4: TRANSFER TO ANOTHER VEHICLE (Cross-dock / Emergency Swap)
        # ---------------------------------------------------------------------
        dispatch_fee = 1200.0
        handling_fee = 800.0
        xfer_cost = round(dispatch_fee + handling_fee + 250.0, 2)
        xfer_delay_h = 2.0
        shelf_life_ok_xfer = (xfer_delay_h <= shelf_life) if shelf_life_known else True

        options.append(
            CandidateOption(
                action="transfer_to_another_vehicle",
                distance_km=0.0,
                duration_min=120.0,
                estimated_delay_hours=xfer_delay_h,
                estimated_cost=xfer_cost,
                description="Cross-dock cargo onto secondary relief vehicle at current location.",
                # True here must not be interpreted as verified shelf-life safety when shelf life is unknown.
                shelf_life_ok=shelf_life_ok_xfer,
                deadline_ok=xfer_delay_h <= deadline,
                score=xfer_cost + (xfer_delay_h * 200) + 1000,
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
        "2. Select the single best recommended_action from candidate actions: 'reroute', 'wait', 'transfer_to_storage', or 'transfer_to_another_vehicle'.\n"
        "3. Do NOT calculate distances, delays, or costs yourself. Use the exact numeric values provided for your selected action.\n"
        "4. Provide professional, detailed operational reasoning explaining trade-offs.\n"
        "5. SHELF LIFE RULES:\n"
        "   - If remaining_shelf_life_hours is provided (known), evaluate whether candidate action delay exceeds remaining shelf life.\n"
        "   - If remaining_shelf_life_hours is null or shelf_life_status is 'unknown', explicitly acknowledge in your reasoning that remaining shelf-life information is unavailable and cannot be verified.\n"
        "   - NEVER invent, guess, or assume a numeric shelf life when remaining_shelf_life_hours is null/unknown.\n"
        "   - Do NOT claim that a plan is safe with respect to shelf life when shelf-life information is unavailable.\n"
        "6. Output MUST be valid JSON matching Contract 4 schema ONLY. Do NOT wrap in markdown or add extra fields.\n\n"
        "REQUIRED JSON OUTPUT CONTRACT:\n"
        "{\n"
        '  "truck_id": "<str>",\n'
        '  "recommended_action": "<reroute|wait|transfer_to_storage|transfer_to_another_vehicle>",\n'
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
                "distance_km": cand.distance_km,
                "duration_min": cand.duration_min,
                "estimated_delay_hours": cand.estimated_delay_hours,
                "estimated_cost": cand.estimated_cost,
                "description": cand.description,
                "shelf_life_ok": cand.shelf_life_ok if sl_known else None,
                "shelf_life_status": "known" if sl_known else "unknown",
                "deadline_ok": cand.deadline_ok,
            })

        payload = {
            "truck_id": context["truck_id"],
            "disruption_event": {
                "type": context["disruption_type"],
                "severity": context["severity"],
                "location": context["location"],
                "predicted_delay_hours": context["predicted_delay_hours"],
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
        top_cand = candidates[0] if candidates else CandidateOption(
            action="reroute",
            distance_km=62.0,
            duration_min=95.0,
            estimated_delay_hours=1.5,
            estimated_cost=850.0,
            description="Default detour",
            shelf_life_ok=True,
            deadline_ok=True,
            score=0.0,
        )

        truck_id = context["truck_id"]
        cargo_type = context["cargo_type"]
        disruption_type = context["disruption_type"]
        predicted_delay_h = context["predicted_delay_hours"]
        deadline_h = context["deadline_hours"]
        shelf_life_h = context["shelf_life_hours"]
        location = context["location"]
        action = top_cand.action

        shelf_life_clause = f"and shelf-life limit of {shelf_life_h}h." if shelf_life_h is not None else "(cargo shelf-life unspecified)."
        storage_shelf_clause = f"With {shelf_life_h}h safe transport remaining vs {predicted_delay_h}h delay" if shelf_life_h is not None else f"Due to {predicted_delay_h}h expected disruption delay"

        if action == "reroute":
            if context["is_threat"]:
                reasoning = (
                    f"{disruption_type} reported near {location} with ~{predicted_delay_h}h expected disruption. "
                    f"Rerouting via alternate highway adds {top_cand.estimated_delay_hours}h delay (costing ${top_cand.estimated_cost:g}), "
                    f"staying comfortably within cargo deadline window of {deadline_h}h {shelf_life_clause}"
                )
            else:
                stoppage_min = int(context["fleet_output"].get("stoppage_duration_min", 45))
                reasoning = (
                    f"Unplanned stoppage ({stoppage_min} min) detected at {location} for {cargo_type}; "
                    f"rerouting via alternate highway adds total {top_cand.estimated_delay_hours}h delay (costing ${top_cand.estimated_cost:g}), "
                    f"protecting the remaining cargo delivery deadline of {deadline_h}h."
                )
        elif action == "transfer_to_storage":
            reasoning = (
                f"{disruption_type} near {location} threatens temperature-sensitive {cargo_type}. "
                f"{storage_shelf_clause}, transferring cargo to climate-controlled storage hub ensures preservation (costing ${top_cand.estimated_cost:g})."
            )
        elif action == "transfer_to_another_vehicle":
            reasoning = (
                f"Severe vehicle stoppage at {location} prevents standard transit. "
                f"Cross-docking {cargo_type} onto a secondary relief vehicle resolves disruption within {top_cand.estimated_delay_hours}h "
                f"(costing ${top_cand.estimated_cost:g}), meeting delivery commitment of {deadline_h}h."
            )
        else:  # wait
            reasoning = (
                f"Disruption severity near {location} is low (~{predicted_delay_h}h). "
                f"Waiting out the stoppage incurs minimal delay ({top_cand.estimated_delay_hours}h, costing ${top_cand.estimated_cost:g}), "
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


