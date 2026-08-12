"""
Risk Critic Agent (Agent 4 - AI Risk Auditor)

Evaluates proposed incident response plans against comprehensive risk factors:
cargo shelf-life, driver safety, cost, ETA tolerance, customer priority, weather severity, 
cold-chain integrity, warehouse availability, and operational feasibility.

Acts as an independent Senior Logistics Risk Auditor powered by Google Gemini AI reasoning,
with deterministic pre-evaluation and graceful fallback mechanisms.
"""

import json
import os
import re
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, Callable

# Named Threshold Constants for Live Demo Q&A and Backward Compatibility
DEFAULT_MAX_ALLOWED_COST = 5000.0
DEFAULT_MAX_ALLOWED_DELAY_HOURS = 8.0
SAFE_ACTIONS = {"reroute", "wait", "transfer_to_storage", "transfer_to_another_vehicle"}


class DeterministicEvaluator:
    """Computes baseline deterministic risk factors and threshold checks."""

    @staticmethod
    def evaluate(plan_data: Dict[str, Any]) -> Dict[str, Any]:
        truck_id = str(plan_data.get("truck_id", ""))
        recommended_action = str(plan_data.get("recommended_action", "")).lower()
        estimated_delay_hours = float(plan_data.get("estimated_delay_hours", 0.0))
        estimated_cost = float(plan_data.get("estimated_cost", 0.0))

        raw_shelf_life = plan_data.get("shelf_life_hours")
        shelf_life_hours: Optional[float] = None
        if raw_shelf_life is not None:
            try:
                shelf_life_hours = float(raw_shelf_life)
            except (ValueError, TypeError):
                shelf_life_hours = None

        max_cost = float(plan_data.get("budget_limit", DEFAULT_MAX_ALLOWED_COST))
        max_delay = float(plan_data.get("max_allowed_delay", DEFAULT_MAX_ALLOWED_DELAY_HOURS))

        shelf_life_known = (shelf_life_hours is not None)
        if shelf_life_known:
            shelf_life_ok = estimated_delay_hours <= shelf_life_hours
            shelf_life_status = "pass" if shelf_life_ok else "fail"
        else:
            # True here must not be interpreted as verified shelf-life safety when shelf life is unknown.
            # Contract 5 requires a boolean field risk_factors.shelf_life_ok. We set True to avoid
            # false automatic rejection when shelf life is unknown, but record shelf_life_status = "unknown"
            # and explicitly state in reasoning that shelf-life safety could not be verified.
            shelf_life_ok = True
            shelf_life_status = "unknown"

        cost_ok = estimated_cost <= max_cost
        eta_ok = estimated_delay_hours <= max_delay
        safety_ok = recommended_action in SAFE_ACTIONS

        all_passed = shelf_life_ok and cost_ok and eta_ok and safety_ok
        decision = "ACCEPT" if all_passed else "REJECT"

        if decision == "ACCEPT":
            delay_str = (
                f"{int(estimated_delay_hours)}"
                if estimated_delay_hours.is_integer()
                else f"{estimated_delay_hours}"
            )
            if shelf_life_known:
                shelf_life_str = (
                    f"{int(shelf_life_hours)}"
                    if shelf_life_hours.is_integer()
                    else f"{shelf_life_hours}"
                )
                reasoning = (
                    f"Cargo shelf-life margin ({shelf_life_str}h) exceeds new ETA delay ({delay_str}h); "
                    f"cost within threshold."
                )
            else:
                reasoning = (
                    f"ETA delay ({delay_str}h) and cost within operational thresholds; "
                    f"shelf-life safety could not be verified because remaining shelf-life information is unavailable."
                )
        else:
            failed_reasons = []
            if shelf_life_known and not shelf_life_ok:
                failed_reasons.append(
                    f"ETA delay ({estimated_delay_hours}h) exceeds cargo shelf-life margin ({shelf_life_hours}h)"
                )
            if not cost_ok:
                failed_reasons.append(
                    f"Estimated cost (INR {estimated_cost}) exceeds budget threshold (INR {max_cost})"
                )
            if not eta_ok:
                failed_reasons.append(
                    f"Estimated delay ({estimated_delay_hours}h) exceeds maximum allowed ETA delay ({max_delay}h)"
                )
            if not safety_ok:
                failed_reasons.append(
                    f"Recommended action '{recommended_action}' failed safety check"
                )
            reasoning = "Risk evaluation rejected plan: " + "; ".join(failed_reasons)

        return {
            "truck_id": truck_id,
            "decision": decision,
            "reasoning": reasoning,
            "shelf_life_status": shelf_life_status,
            "risk_factors": {
                "shelf_life_ok": shelf_life_ok,
                "cost_ok": cost_ok,
                "eta_ok": eta_ok,
                "safety_ok": safety_ok
            }
        }


class PromptBuilder:
    """Builds structured system and user prompts for Gemini AI Risk Auditor."""

    @staticmethod
    def build_system_prompt() -> str:
        return (
            "You are a Senior Logistics Risk Auditor at an enterprise global supply chain company.\n"
            "Your role is to independently review proposed incident response plans for freight disruptions.\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. NEVER automatically agree with the planner. Actively search for hidden operational, safety, or financial risks.\n"
            "2. Thoroughly review driver safety, cargo preservation, customer priority, delivery deadline, remaining shelf life, "
            "estimated delay, weather severity, road conditions, fuel impact, business constraints, operational feasibility, "
            "cold-chain requirements, and warehouse availability.\n"
            "3. Reject plans that:\n"
            "   - Increase safety risks or endanger drivers.\n"
            "   - Threaten perishable cargo or breach cold-chain limits (e.g., delay exceeds remaining shelf life).\n"
            "   - Unnecessarily miss high-priority customer SLAs when better alternatives exist.\n"
            "   - Exceed cost budgets without critical justification.\n"
            "   - Rely on unsupported assumptions (e.g., waiting when disruption duration is long).\n"
            "4. Accept ONLY when the plan is operationally sound, risks are acceptable, and logic is internally consistent.\n"
            "5. If information is insufficient or contradictory, explicitly note the uncertainty in reasoning.\n"
            "6. UNKNOWN SHELF LIFE RULE: If remaining shelf life is UNKNOWN / Unspecified (null/missing), the shelf-life constraint cannot be independently verified. "
            "Do NOT assume or invent a numeric shelf life. Do NOT estimate shelf life from cargo type. Explicitly state in your reasoning that shelf-life safety could not be verified due to missing information. "
            "Evaluate remaining operational risk factors (safety, cost, ETA, disruption severity) to reach an ACCEPT or REJECT decision.\n\n"
            "OUTPUT FORMAT (STRICT JSON ONLY):\n"
            "You MUST respond with valid JSON matching Contract 5. Do NOT include markdown code fences or extra conversational text.\n"
            "{\n"
            '  "truck_id": "<string>",\n'
            '  "decision": "ACCEPT" | "REJECT",\n'
            '  "reasoning": "<detailed auditor critique explaining why the plan was accepted or rejected>",\n'
            '  "risk_factors": {\n'
            '    "shelf_life_ok": <boolean>,\n'
            '    "cost_ok": <boolean>,\n'
            '    "eta_ok": <boolean>,\n'
            '    "safety_ok": <boolean>\n'
            "  }\n"
            "}"
        )

    @staticmethod
    def build_user_prompt(plan_data: Dict[str, Any], det_eval: Dict[str, Any]) -> str:
        raw_sl = plan_data.get("shelf_life_hours")
        sl_display = f"{raw_sl} hours (Known)" if raw_sl is not None else "UNKNOWN / Unspecified (Cannot be verified)"
        return f"""Audit the following proposed logistics incident response plan:

### PROPOSED PLAN DETAILS (Contract 4)
- Truck ID: {plan_data.get('truck_id', 'UNKNOWN')}
- Recommended Action: {plan_data.get('recommended_action', 'N/A')}
- Planner Reasoning: {plan_data.get('reasoning', 'N/A')}
- Estimated Delay: {plan_data.get('estimated_delay_hours', 0.0)} hours
- Estimated Cost: INR {plan_data.get('estimated_cost', 0)}
- Alternative Route: {json.dumps(plan_data.get('alternative_route', {}))}

### CONTEXTUAL DISRUPTION & CARGO METRICS
- Cargo Type: {plan_data.get('cargo_type', 'General Freight')}
- Cold Chain Required: {plan_data.get('cold_chain', False)}
- Remaining Shelf Life: {sl_display}
- Shelf Life Status: {det_eval.get('shelf_life_status', 'unknown')}
- Customer Priority: {plan_data.get('customer_priority', 'Standard')}
- Disruption Type: {plan_data.get('disruption_type', 'Unspecified')}
- Weather Severity: {plan_data.get('weather_severity', 'Normal')}
- Road Conditions: {plan_data.get('road_conditions', 'Normal')}
- Warehouse Available: {plan_data.get('warehouse_available', 'N/A')}
- Fuel Impact: {plan_data.get('fuel_impact', 'Normal')}

### DETERMINISTIC PRE-AUDIT EVALUATION
- Baseline Checks Passed: {det_eval.get('decision') == 'ACCEPT'}
- Calculated Risk Factors: {json.dumps(det_eval.get('risk_factors', {}))}
- Baseline Reasoning: {det_eval.get('reasoning', '')}

Review all risk factors carefully. Perform deep trade-off reasoning and output the JSON response:"""


class JSONValidator:
    """Validates and parses Gemini output against Contract 5 specification."""

    @staticmethod
    def clean_json_string(raw_text: str) -> str:
        """Strips markdown code fences and extraneous text surrounding JSON."""
        text = raw_text.strip()
        # Remove ```json ... ``` code blocks if present
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Find first '{' and last '}'
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start:end+1].strip()
        return text

    @classmethod
    def validate(cls, raw_text: str, fallback_truck_id: str = "") -> Optional[Dict[str, Any]]:
        """
        Parses raw text into JSON and validates strict field contracts.
        Returns dict matching Contract 5 or None if validation fails.
        """
        cleaned = cls.clean_json_string(raw_text)
        try:
            data = json.loads(cleaned)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        truck_id = str(data.get("truck_id") or fallback_truck_id)
        decision = str(data.get("decision", "")).strip().upper()
        if decision not in ("ACCEPT", "REJECT"):
            return None

        reasoning = str(data.get("reasoning", "")).strip()
        if not reasoning:
            return None

        risk_factors = data.get("risk_factors")
        if not isinstance(risk_factors, dict):
            is_accept = (decision == "ACCEPT")
            risk_factors = {
                "shelf_life_ok": is_accept,
                "cost_ok": is_accept,
                "eta_ok": is_accept,
                "safety_ok": is_accept
            }
        else:
            for field in ("shelf_life_ok", "cost_ok", "eta_ok", "safety_ok"):
                if field not in risk_factors or not isinstance(risk_factors[field], bool):
                    risk_factors[field] = bool(risk_factors.get(field, decision == "ACCEPT"))

        return {
            "truck_id": truck_id,
            "decision": decision,
            "reasoning": reasoning,
            "risk_factors": {
                "shelf_life_ok": bool(risk_factors["shelf_life_ok"]),
                "cost_ok": bool(risk_factors["cost_ok"]),
                "eta_ok": bool(risk_factors["eta_ok"]),
                "safety_ok": bool(risk_factors["safety_ok"])
            }
        }


class LLMClient:
    """Wrapper for calling Google Gemini API or injected mock handler using shared gemini_client service."""

    def __init__(self, mock_handler: Optional[Callable[[str, str], str]] = None):
        self.mock_handler = mock_handler

    def generate(self, system_prompt: str, user_prompt: str, timeout_sec: float = 5.0) -> Optional[str]:
        if self.mock_handler is not None:
            return self.mock_handler(system_prompt, user_prompt)

        from services.gemini_client import generate
        try:
            return generate(
                prompt=user_prompt,
                system_instruction=system_prompt,
                temperature=0.2
            )
        except Exception:
            return None


class RiskCriticService:
    """Orchestrates deterministic pre-evaluation, Gemini AI audit, retry logic, and fallback."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def evaluate(self, plan_data: Dict[str, Any]) -> Dict[str, Any]:
        truck_id = str(plan_data.get("truck_id", ""))
        
        # Step 1: Baseline Deterministic Evaluation (retains internal shelf_life_status)
        det_eval = DeterministicEvaluator.evaluate(plan_data)

        # Step 2: Build Prompts
        system_prompt = PromptBuilder.build_system_prompt()
        user_prompt = PromptBuilder.build_user_prompt(plan_data, det_eval)

        # Step 3: LLM Invocation with Attempt 1
        raw_response = self.llm_client.generate(system_prompt, user_prompt)
        if raw_response:
            validated = JSONValidator.validate(raw_response, fallback_truck_id=truck_id)
            if validated:
                return validated

            # Step 4: Retry Strategy (Attempt 2 with explicit formatting warning)
            retry_prompt = (
                f"{user_prompt}\n\n"
                "WARNING: Your previous response was not valid JSON matching Contract 5. "
                "Output ONLY a raw, unformatted JSON object matching the contract strictly."
            )
            raw_retry = self.llm_client.generate(system_prompt, retry_prompt)
            if raw_retry:
                validated_retry = JSONValidator.validate(raw_retry, fallback_truck_id=truck_id)
                if validated_retry:
                    return validated_retry

        # Step 5: Safe Fallback to Deterministic Evaluator formatted strictly as Contract 5
        return self._format_contract_5_fallback(det_eval)

    @staticmethod
    def _format_contract_5_fallback(det_eval: Dict[str, Any]) -> Dict[str, Any]:
        """Formats deterministic evaluation into strict Contract 5 payload, stripping internal metadata."""
        rf = det_eval.get("risk_factors", {})
        return {
            "truck_id": str(det_eval.get("truck_id", "")),
            "decision": str(det_eval.get("decision", "REJECT")),
            "reasoning": str(det_eval.get("reasoning", "")),
            "risk_factors": {
                "shelf_life_ok": bool(rf.get("shelf_life_ok", True)),
                "cost_ok": bool(rf.get("cost_ok", True)),
                "eta_ok": bool(rf.get("eta_ok", True)),
                "safety_ok": bool(rf.get("safety_ok", True)),
            }
        }


def evaluate_risk(plan_data: dict) -> dict:
    """
    Public API endpoint matching Contract 4 input and Contract 5 output specification.
    Preserves exact function signature for backward compatibility across all modules.
    """
    service = RiskCriticService()
    return service.evaluate(plan_data)

