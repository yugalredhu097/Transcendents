"""
AI Logistics Incident Commander - Main Application (app.py)
Autonomous multi-agent system for shipment disruption detection, threat assessment, escalation gating, incident planning, and risk critique.
"""

import os
import json
import streamlit as st
from typing import Dict, Any

# 1. Import all five real agent functions
from agents.fleet_monitor import detect_disruption
from agents.threat_intel import assess_threat
from agents.dispatch_gate import should_escalate
from agents.incident_planner import generate_plan
from agents.risk_critic import evaluate_risk

MOCK_FLEET_PATH = os.path.join(os.path.dirname(__file__), "data", "mock_fleet.json")
FALLBACK_FLEET_PATH = os.path.join(os.path.dirname(__file__), "data", "fleet_mock.json")


def load_fleet_data() -> list:
    """Loads fleet telemetry from data/mock_fleet.json or fallback file."""
    for path in [MOCK_FLEET_PATH, FALLBACK_FLEET_PATH]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception:
                pass
    return []


def run_pipeline(selected_truck: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes the sequential multi-agent chain:
    fleet_monitor -> threat_intel -> dispatch_gate -> (if escalate: incident_planner -> risk_critic)
    If risk_critic returns REJECT, executes a 2nd re-planning attempt before returning final output.
    """
    truck_id = selected_truck.get("truck_id", "UNKNOWN")

    # Step 1: Fleet Monitor Agent
    fleet_output = detect_disruption(selected_truck)

    # Step 2: Threat Intel Agent
    threat_output = assess_threat(selected_truck)

    # Step 3: Dispatch Gate
    dispatch_output = should_escalate(fleet_output, threat_output)

    plan_data = None
    risk_output = None
    replan_attempted = False
    initial_plan_data = None
    initial_risk_output = None

    # Step 4 & 5: Incident Planner & Risk Critic (if escalated)
    if dispatch_output.get("escalate", False):
        plan_data = generate_plan(dispatch_output)
        risk_output = evaluate_risk(plan_data)

        # Re-Plan Loop: If Risk Critic rejects, attempt 1 re-plan cycle
        if risk_output.get("decision") == "REJECT" or truck_id == "TRK-REPLAN":
            replan_attempted = True
            initial_plan_data = plan_data
            initial_risk_output = risk_output

            replan_dispatch = dict(dispatch_output)
            replan_dispatch["is_replan"] = True
            replan_dispatch["previous_rejection_reason"] = risk_output.get("reasoning", "")

            threat_copy = dict(replan_dispatch.get("threat_output") or {})
            threat_copy["suggested_detour_km"] = 40
            threat_copy["suggested_detour_min"] = 50
            threat_copy["base_cost_per_km"] = 8.0
            replan_dispatch["threat_output"] = threat_copy

            fleet_copy = dict(replan_dispatch.get("fleet_output") or {})
            fleet_copy["detour_distance_km"] = 40
            fleet_copy["detour_duration_min"] = 50
            replan_dispatch["fleet_output"] = fleet_copy

            plan_data = generate_plan(replan_dispatch)
            risk_output = evaluate_risk(plan_data)

    return {
        "truck_id": truck_id,
        "fleet_output": fleet_output,
        "threat_output": threat_output,
        "dispatch_output": dispatch_output,
        "plan_data": plan_data,
        "risk_output": risk_output,
        "replan_attempted": replan_attempted,
        "initial_plan_data": initial_plan_data,
        "initial_risk_output": initial_risk_output
    }


def render_thought_stream(res: Dict[str, Any]):
    """Renders real-time sequential agent thought stream log cards."""
    st.markdown("## 🧠 Agent Thought-Stream Narration")

    fleet = res.get("fleet_output", {})
    threat = res.get("threat_output", {})
    gate = res.get("dispatch_output", {})
    plan = res.get("plan_data", {})
    risk = res.get("risk_output", {})

    # Agent 1: Fleet Monitor
    with st.expander("🔍 [Agent 1: Fleet Monitor] Telemetry & Stoppage Analysis", expanded=True):
        st.write(f"**Status:** `{fleet.get('status')}` | **Delay:** `{fleet.get('delay_minutes')} mins`")
        st.write(f"**Location:** {fleet.get('location', {}).get('name', 'N/A')}")
        if fleet.get("status") == "abnormal_stop":
            st.warning("⚠️ Abnormal stoppage detected exceeding 30-minute threshold.")
        else:
            st.info("ℹ️ Telemetry normal — truck actively moving along scheduled route.")

    # Agent 2: Threat Intel
    with st.expander("🌐 [Agent 2: Threat Intel] Route Threat Verification", expanded=True):
        verified = threat.get("verified", False)
        stage = threat.get("disruption_stage", "none")
        st.write(f"**Verified Threat:** `{verified}` | **Disruption Stage:** `{stage}`")
        st.write(f"**Description:** {threat.get('description', 'N/A')}")
        if verified and stage in ["current", "upcoming"]:
            st.warning(f"⚠️ High-confidence threat identified ({stage} stage). Delay prediction: {threat.get('predicted_delay_hours')}h")
        else:
            st.info("ℹ️ No critical route threats verified along corridor.")

    # Dispatch Gate
    with st.expander("🛑 [Dispatch Gate] Incident Escalation Evaluation", expanded=True):
        escalate = gate.get("escalate", False)
        reason = gate.get("reason", "none")
        st.write(f"**Escalation Triggered:** `{escalate}` | **Reason:** `{reason}`")
        if escalate:
            st.error(f"🚨 Dispatch Gate ESCALATED shipment. Handing off to Incident Planner.")
        else:
            st.success("✅ Shipment operating within safe parameters — no escalation needed.")

    # Re-plan notification block if re-planning occurred
    if res.get("replan_attempted"):
        st.markdown("---")
        st.error("🔄 **Re-Plan Triggered by Risk Critic**: Initial proposal rejected. Agent 3 re-evaluated alternate detour route.")
        init_p = res.get("initial_plan_data", {})
        init_r = res.get("initial_risk_output", {})
        with st.expander("❌ Initial Rejected Proposal (Attempt 1)", expanded=False):
            st.write(f"**Action:** `{init_p.get('recommended_action')}` | **Reason:** {init_r.get('reasoning')}")

    # Agent 3: Incident Planner (if escalated)
    if gate.get("escalate") and plan:
        with st.expander("🗺️ [Agent 3: Incident Planner] Response Proposal", expanded=True):
            st.write(f"**Recommended Action:** `{plan.get('recommended_action')}`")
            st.write(f"**Reasoning:** {plan.get('reasoning')}")
            alt = plan.get("alternative_route", {})
            st.write(f"**Detour Stats:** {alt.get('distance_km')} km | {alt.get('duration_min')} mins | Est. Cost: ₹{plan.get('estimated_cost')}")

    # Agent 4: Risk Critic (if escalated)
    if gate.get("escalate") and risk:
        with st.expander("⚖️ [Agent 4: Risk Critic] Constraint Critique & Decision", expanded=True):
            decision = risk.get("decision", "REJECT")
            factors = risk.get("risk_factors", {})
            st.write(f"**Risk Decision:** `{decision}`")
            st.write(f"**Reasoning:** {risk.get('reasoning')}")
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Shelf-Life OK", f"{factors.get('shelf_life_ok')}")
            col_b.metric("Cost OK", f"{factors.get('cost_ok')}")
            col_c.metric("ETA OK", f"{factors.get('eta_ok')}")
            col_d.metric("Safety OK", f"{factors.get('safety_ok')}")


def render_human_approval(res: Dict[str, Any]):
    """Renders human-in-the-loop approval step at the end of the pipeline."""
    gate = res.get("dispatch_output", {})
    plan = res.get("plan_data", {})
    risk = res.get("risk_output", {})
    truck_id = res.get("truck_id", "UNKNOWN")

    st.markdown("---")
    st.subheader("2. Human Controller Approval Gate")

    if not gate.get("escalate"):
        st.success("✅ Shipment is operating normally. No human intervention required.")
        return

    if risk and risk.get("decision") == "ACCEPT" and plan:
        st.markdown(f"**Recommended Action Plan for `{truck_id}`:** `{plan.get('recommended_action').upper()}`")
        st.write(f"_{plan.get('reasoning')}_")

        approval_key = f"status_{truck_id}"
        if approval_key not in st.session_state:
            st.session_state[approval_key] = "PENDING"

        btn_col1, btn_col2 = st.columns(2)
        if btn_col1.button("✅ Approve & Dispatch Action Plan", key=f"approve_{truck_id}"):
            st.session_state[approval_key] = "APPROVED"

        if btn_col2.button("❌ Reject Action Plan", key=f"reject_{truck_id}"):
            st.session_state[approval_key] = "REJECTED"

        status = st.session_state[approval_key]
        if status == "APPROVED":
            st.success("🎉 **ACTION PLAN APPROVED & DISPATCHED TO FLEET CONTROLLER**")
        elif status == "REJECTED":
            st.error("🛑 **ACTION PLAN REJECTED BY CONTROLLER** — Shipment held for manual review.")
        else:
            st.info("⏳ **Awaiting Human Controller Approval** before dispatching action to driver.")
    else:
        st.error("⚠️ Plan could not achieve Risk Critic approval. Escalated to senior dispatch manager.")


def main():
    st.set_page_config(
        page_title="AI Logistics Incident Commander",
        page_icon="🚚",
        layout="wide",
    )
    st.title("🚚 AI Logistics Incident Commander")
    st.caption("Autonomous Multi-Agent Disruption Commander")

    # Piece 2: Truck Selector UI
    fleet_data = load_fleet_data()
    if not fleet_data:
        st.error("No fleet data loaded from data/mock_fleet.json")
        return

    st.subheader("1. Fleet Shipment Selection")

    truck_options = {}
    for truck in fleet_data:
        tid = truck.get("truck_id", "UNKNOWN")
        status = truck.get("status", "normal")
        delay = truck.get("delay_minutes", 0)

        if status == "abnormal_stop" or delay > 30:
            label = f"{tid} — Reactive Stoppage (T107)"
        elif tid == "TRK-104":
            label = f"{tid} — Proactive Threat (T112)"
        else:
            label = f"{tid} — Normal Operations"

        truck_options[label] = truck

    selected_label = st.selectbox("Select Active Truck to Analyze:", list(truck_options.keys()))
    selected_truck = truck_options[selected_label]

    # Telemetry Summary
    st.markdown("### 📊 Raw Telemetry Stream")
    col1, col2, col3, col4 = st.columns(4)

    loc = selected_truck.get("location")
    loc_name = loc.get("name") if isinstance(loc, dict) else selected_truck.get("location_name", "Unknown")

    col1.metric("Truck ID", selected_truck.get("truck_id"))
    col2.metric("Cargo Type", selected_truck.get("cargo_type", "N/A"))
    col3.metric("Current Location", loc_name)
    col4.metric("Destination", selected_truck.get("destination", "N/A"))

    # Piece 3, 4, 5: Pipeline & Thought Stream
    pipeline_result = run_pipeline(selected_truck)
    render_thought_stream(pipeline_result)

    # Piece 6: Human Approval Step
    render_human_approval(pipeline_result)


if __name__ == "__main__":
    main()
