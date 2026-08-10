"""
Risk Critic Agent (Agent 4)
Evaluates proposed incident response plans against risk factors:
cargo shelf-life, cost, ETA tolerance, and action safety constraints.
"""

# Named Threshold Constants for Live Demo Q&A
DEFAULT_SHELF_LIFE_MARGIN_HOURS = 6.0
DEFAULT_MAX_ALLOWED_COST = 5000.0
DEFAULT_MAX_ALLOWED_DELAY_HOURS = 8.0
SAFE_ACTIONS = {"reroute", "wait", "transfer_to_storage", "transfer_to_another_vehicle"}


def evaluate_risk(plan_data: dict) -> dict:
    """
    Evaluates risk factors for a proposed incident response plan.

    Input shape (Contract 4 - Incident Planner Output):
    {
      "truck_id": "TRK-104",
      "recommended_action": "reroute",
      "reasoning": "Protest expected in ~2 hours on current route; alternate adds 1.5h, still within deadline",
      "estimated_delay_hours": 1.5,
      "estimated_cost": 850,
      "alternative_route": {"distance_km": 62, "duration_min": 95}
    }

    Output shape (Contract 5 - Risk Critic Output):
    {
      "truck_id": "TRK-104",
      "decision": "ACCEPT",
      "reasoning": "Cargo shelf-life margin (6h) exceeds new ETA delay (1.5h); cost within threshold",
      "risk_factors": {
        "shelf_life_ok": true,
        "cost_ok": true,
        "eta_ok": true,
        "safety_ok": true
      }
    }
    """
    truck_id = str(plan_data.get("truck_id", ""))
    recommended_action = str(plan_data.get("recommended_action", "")).lower()
    estimated_delay_hours = float(plan_data.get("estimated_delay_hours", 0.0))
    estimated_cost = float(plan_data.get("estimated_cost", 0.0))

    # Evaluate risk factors against named constants
    shelf_life_ok = estimated_delay_hours <= DEFAULT_SHELF_LIFE_MARGIN_HOURS
    cost_ok = estimated_cost <= DEFAULT_MAX_ALLOWED_COST
    eta_ok = estimated_delay_hours <= DEFAULT_MAX_ALLOWED_DELAY_HOURS
    safety_ok = recommended_action in SAFE_ACTIONS

    # Overall decision logic
    all_passed = shelf_life_ok and cost_ok and eta_ok and safety_ok
    decision = "ACCEPT" if all_passed else "REJECT"

    # Construct reasoning string matching contract format
    if decision == "ACCEPT":
        shelf_life_str = (
            f"{int(DEFAULT_SHELF_LIFE_MARGIN_HOURS)}"
            if DEFAULT_SHELF_LIFE_MARGIN_HOURS.is_integer()
            else f"{DEFAULT_SHELF_LIFE_MARGIN_HOURS}"
        )
        delay_str = (
            f"{int(estimated_delay_hours)}"
            if estimated_delay_hours.is_integer()
            else f"{estimated_delay_hours}"
        )
        reasoning = (
            f"Cargo shelf-life margin ({shelf_life_str}h) exceeds new ETA delay ({delay_str}h); "
            f"cost within threshold"
        )
    else:
        failed_reasons = []
        if not shelf_life_ok:
            failed_reasons.append(
                f"ETA delay ({estimated_delay_hours}h) exceeds cargo shelf-life margin ({DEFAULT_SHELF_LIFE_MARGIN_HOURS}h)"
            )
        if not cost_ok:
            failed_reasons.append(
                f"Estimated cost (INR {estimated_cost}) exceeds budget threshold (INR {DEFAULT_MAX_ALLOWED_COST})"
            )
        if not eta_ok:
            failed_reasons.append(
                f"Estimated delay ({estimated_delay_hours}h) exceeds maximum allowed ETA delay ({DEFAULT_MAX_ALLOWED_DELAY_HOURS}h)"
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
        "risk_factors": {
            "shelf_life_ok": shelf_life_ok,
            "cost_ok": cost_ok,
            "eta_ok": eta_ok,
            "safety_ok": safety_ok
        }
    }
