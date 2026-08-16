"""
Agent Decision Trace & Human Approval Components for LOGISTICS INCIDENT COMMANDER
Exposes structured agent outputs, deterministic decision factors, risk audit details, and human-in-the-loop decision controls.
"""

import streamlit as st
from typing import Dict, Any, Optional


def render_agent_decision_trace(pipeline_result: Optional[Dict[str, Any]], selected_truck: Dict[str, Any]) -> bool:
    """
    Renders the AGENT DECISION TRACE workspace tab in the right column.
    - If pipeline_result is None: Displays instruction state and primary [ ANALYZE INCIDENT ] button.
    - If pipeline_result is present: Displays the 5-Agent Decision Trace cards, Re-Plan attempt details, and Final Recommendation card.
    Returns True if the operator clicked [ ANALYZE INCIDENT ].
    """
    st.markdown("### 🤖 Agent Decision Workspace")
    tid = selected_truck.get("truck_id", "UNKNOWN")

    # BEFORE ANALYSIS INSTRUCTION STATE
    if not pipeline_result:
        st.markdown(
            f"""
            <div style="background-color: #171923; border: 1px dashed #4A5568; border-radius: 8px; padding: 1.5rem; text-align: center; margin-bottom: 1.2rem;">
                <div style="font-size: 2.2rem; margin-bottom: 0.4rem;">ℹ️</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #E2E8F0; margin-bottom: 0.3rem;">
                    Select a truck and click ANALYZE INCIDENT to execute the multi-agent decision chain.
                </div>
                <div style="font-size: 0.8rem; color: #A0AEC0;">
                    Target Vehicle: <b style="color: #63B3ED;">{tid}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        analyze_clicked = st.button(
            f"🚨 ANALYZE INCIDENT ({tid})",
            key=f"btn_analyze_right_{tid}",
            type="primary",
            use_container_width=True,
        )
        return analyze_clicked

    # AFTER ANALYSIS: AGENT DECISION TRACE
    fleet = pipeline_result.get("fleet_output") or {}
    threat = pipeline_result.get("threat_output") or {}
    gate = pipeline_result.get("dispatch_output") or {}
    plan = pipeline_result.get("plan_data") or {}
    risk = pipeline_result.get("risk_output") or {}

    # Check raw shelf life for strict UNKNOWN rule enforcement
    raw_shelf_life = selected_truck.get("remaining_shelf_life_hours")
    shelf_life_is_unknown = raw_shelf_life is None

    # Agent 1: Fleet Monitor
    with st.expander("🔍 [Agent 1: Fleet Monitor] Telemetry & Stoppage Agent", expanded=True):
        st_status = str(fleet.get("status", "normal")).upper()
        delay_min = fleet.get("delay_minutes", 0)
        stopped_min = fleet.get("stopped_duration_minutes") or fleet.get("stop_duration_minutes") or 0
        loc = fleet.get("location")
        loc_name = loc.get("name") if isinstance(loc, dict) else fleet.get("location_name", "N/A")
        
        st.write(f"**Status:** `{st_status}`")
        st.write(f"**Delay:** `{delay_min} mins` | **Stopped:** `{stopped_min} mins`")
        st.write(f"**Threshold:** `30 mins`")
        st.write(f"**Location:** `{loc_name}`")

        if fleet.get("status") == "abnormal_stop":
            st.warning("⚠️ **Assessment:** Vehicle exceeded abnormal stoppage threshold (>30 min).")
        else:
            st.info("ℹ️ **Assessment:** Telemetry within normal operating parameters.")

    # Agent 2: Threat Intelligence
    with st.expander("🌐 [Agent 2: Threat Intelligence] AI Evidence Analyzer", expanded=True):
        dis_type = str(threat.get("disruption_type", "NONE")).upper()
        stage = str(threat.get("disruption_stage", "NONE")).upper()
        severity = str(threat.get("severity", "NONE")).upper()
        conf = threat.get("confidence", 0.0)
        conf_pct = f"{int(conf * 100)}%" if isinstance(conf, (float, int)) else "N/A"
        verified = threat.get("verified", False)
        pred_delay = threat.get("predicted_delay_hours", 0.0)
        source = threat.get("source", "N/A")

        col1, col2 = st.columns(2)
        col1.write(f"**Threat:** `{dis_type}`")
        col1.write(f"**Stage:** `{stage}`")
        col1.write(f"**Severity:** `{severity}`")
        
        col2.write(f"**Confidence:** `{conf_pct}`")
        col2.write(f"**Verified:** `{'✓ YES' if verified else '✕ NO'}`")
        col2.write(f"**Predicted Delay:** `{pred_delay} hours`")
        
        st.write(f"**Source:** `{source}`")
        st.caption(f"Description: {threat.get('description', 'N/A')}")

    # Agent 3: Dispatch Gate
    with st.expander("🛑 [Agent 3: Dispatch Gate] Deterministic Escalation Gate", expanded=True):
        escalate = gate.get("escalate", False)
        reason = gate.get("reason", "none")
        fleet_trig = "abnormal_stop" if fleet.get("status") == "abnormal_stop" else "none"
        threat_trig = f"{stage.lower()}" if verified else "none"

        st.write(f"**Fleet Trigger:** `{'YES (abnormal_stop)' if fleet_trig != 'none' else 'NO'}`")
        st.write(f"**Threat Trigger:** `{'YES (verified ' + threat_trig + ')' if verified else 'NO'}`")
        st.write(f"**Decision:** `{'ESCALATE' if escalate else 'NO ESCALATION'}`")
        st.write(f"**Reason Code:** `{reason}`")

        if escalate:
            st.error("🚨 Dispatch Gate ESCALATED incident to Planner & Risk Auditor.")
        else:
            st.success("✅ Shipment operating normally — no escalation required.")

    # Re-Plan Notification Card if re-planning occurred
    if pipeline_result.get("replan_attempted"):
        st.markdown(
            """
            <div style="background-color: #2C1A1D; border-left: 4px solid #E53E3E; padding: 0.75rem; border-radius: 6px; margin: 0.75rem 0;">
                <b style="color: #FEB2B2;">🔄 RE-PLAN TRIGGERED BY RISK CRITIC</b><br/>
                <span style="font-size: 0.82rem; color: #E2E8F0;">
                    Initial proposal (Attempt 1) was rejected. Incident Planner re-evaluated detour parameters.
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        init_plan = pipeline_result.get("initial_plan_data") or {}
        init_risk = pipeline_result.get("initial_risk_output") or {}
        with st.expander("❌ Attempt 1 Rejected Proposal Details", expanded=False):
            st.write(f"**Action:** `{init_plan.get('recommended_action')}`")
            st.write(f"**Rejection Reason:** {init_risk.get('reasoning')}")

    # Agent 4: Incident Planner (if escalated)
    if gate.get("escalate") and plan:
        with st.expander("🗺️ [Agent 4: Incident Planner] Response Proposal", expanded=True):
            action = str(plan.get("recommended_action", "WAIT")).upper()
            st.write(f"**Recommended Action:** `{action}`")
            st.write(f"**Reasoning:** {plan.get('reasoning', 'N/A')}")
            
            est_delay = plan.get("estimated_delay_hours", 0.0)
            est_cost = plan.get("estimated_cost", 0.0)
            delay_mins = int(est_delay * 60) if est_delay < 1 else round(est_delay, 1)
            delay_str = f"+{delay_mins} min" if est_delay < 1 else f"+{delay_mins} hours"

            st.write(f"**Expected Additional Delay:** `{delay_str}`")
            st.write(f"**Estimated Additional Cost:** `₹{est_cost:,.2f}`")

            alt = plan.get("alternative_route")
            if isinstance(alt, dict) and alt:
                st.write(f"**Detour Stats:** `{alt.get('distance_km', 'N/A')} km` | `{alt.get('duration_min', 'N/A')} mins`")

    # Agent 5: Risk Critic (if escalated)
    if gate.get("escalate") and risk:
        with st.expander("⚖️ [Agent 5: Risk Critic] Independent Risk Auditor", expanded=True):
            decision = str(risk.get("decision", "REJECT")).upper()
            factors = risk.get("risk_factors") or {}
            
            if decision == "ACCEPT":
                st.success(f"**Audit Decision:** `ACCEPT`")
            else:
                st.error(f"**Audit Decision:** `REJECT`")

            st.write("**Constraint Risk Factors:**")
            col_a, col_b, col_c, col_d = st.columns(4)

            # MANDATORY UNKNOWN SHELF LIFE RULE
            if shelf_life_is_unknown:
                col_a.markdown("**Shelf Life**\n\n⚠️ UNKNOWN")
            else:
                sl_ok = factors.get("shelf_life_ok", True)
                col_a.markdown(f"**Shelf Life**\n\n{'✓ PASS' if sl_ok else '❌ FAIL'}")

            cost_ok = factors.get("cost_ok", True)
            eta_ok = factors.get("eta_ok", True)
            safety_ok = factors.get("safety_ok", True)

            col_b.markdown(f"**Cost**\n\n{'✓ PASS' if cost_ok else '❌ FAIL'}")
            col_c.markdown(f"**ETA**\n\n{'✓ PASS' if eta_ok else '❌ FAIL'}")
            col_d.markdown(f"**Safety**\n\n{'✓ PASS' if safety_ok else '❌ FAIL'}")

            st.write(f"**Auditor Reasoning:** {risk.get('reasoning', 'N/A')}")

    # FINAL RECOMMENDATION CARD
    if gate.get("escalate") and plan and risk:
        st.markdown("---")
        rec_action = str(plan.get("recommended_action", "WAIT")).upper()
        crit_dec = str(risk.get("decision", "REJECT")).upper()
        est_delay = plan.get("estimated_delay_hours", 0.0)
        est_cost = plan.get("estimated_cost", 0.0)
        delay_mins = int(est_delay * 60) if est_delay < 1 else round(est_delay, 1)
        delay_str = f"+{delay_mins} min" if est_delay < 1 else f"+{delay_mins}h"
        conf_val = f"{int(threat.get('confidence', 0.85) * 100)}%"

        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, #1A202C 0%, #2D3748 100%); border: 1px solid #4A5568; border-radius: 8px; padding: 1.1rem; margin-top: 0.8rem; text-align: center;">
                <div style="font-size: 0.72rem; font-weight: 700; color: #A0AEC0; letter-spacing: 0.08em; text-transform: uppercase;">FINAL AI RECOMMENDATION</div>
                <div style="font-size: 1.7rem; font-weight: 800; color: #63B3ED; margin: 0.3rem 0;">{rec_action}</div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-size: 0.82rem; color: #E2E8F0; margin-top: 0.6rem; border-top: 1px solid #4A5568; padding-top: 0.6rem;">
                    <div><b>Exp. Delay:</b> {delay_str}</div>
                    <div><b>Est. Cost:</b> ₹{est_cost:,.0f}</div>
                    <div><b>Risk Audit:</b> <span style="color: {'#48BB78' if crit_dec == 'ACCEPT' else '#F56565'};">{'✓ ' + crit_dec}</span></div>
                    <div><b>Confidence:</b> {conf_val}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return False


def render_human_approval_tab(
    pipeline_result: Optional[Dict[str, Any]],
    selected_truck_id: str,
    approval_state_dict: Dict[str, str],
):
    """
    Renders the HUMAN APPROVAL workspace tab.
    Contains final operator decision interface ([ ✓ APPROVE PLAN ] / [ ✕ REJECT & REPLAN ]).
    """
    st.markdown("### 👤 Human Controller Approval Gate")

    if not pipeline_result:
        st.info("ℹ️ No analysis available for approval yet. Select a truck and click **ANALYZE INCIDENT** in the AGENT TRACE tab first.")
        return

    gate = pipeline_result.get("dispatch_output") or {}
    plan = pipeline_result.get("plan_data") or {}
    risk = pipeline_result.get("risk_output") or {}

    if not gate.get("escalate"):
        st.success("✅ **Normal Transit**: Shipment operating within normal parameters. No human approval required.")
        return

    rec_action = str(plan.get("recommended_action", "WAIT")).upper() if plan else "NONE"
    risk_dec = str(risk.get("decision", "REJECT")).upper() if risk else "REJECT"
    reasoning = plan.get("reasoning", "") if plan else ""
    est_delay = plan.get("estimated_delay_hours", 0.0) if plan else 0.0
    est_cost = plan.get("estimated_cost", 0.0) if plan else 0.0
    delay_mins = int(est_delay * 60) if est_delay < 1 else round(est_delay, 1)
    delay_str = f"+{delay_mins} min" if est_delay < 1 else f"+{delay_mins}h"

    st.markdown(
        f"""
        <div style="background-color: #171923; border: 1px solid #2D3748; border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
            <div style="font-size: 0.75rem; color: #A0AEC0; font-weight: 700; text-transform: uppercase;">Proposed AI Action Plan</div>
            <div style="font-size: 1.4rem; font-weight: 800; color: #63B3ED; margin: 0.3rem 0;">{rec_action}</div>
            <div style="font-size: 0.83rem; color: #CBD5E0; margin-bottom: 0.5rem;"><i>{reasoning}</i></div>
            <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: #A0AEC0; border-top: 1px solid #2D3748; padding-top: 0.4rem; margin-top: 0.4rem;">
                <span>Exp. Delay: <b style="color: #EDF2F7;">{delay_str}</b></span>
                <span>Est. Cost: <b style="color: #EDF2F7;">₹{est_cost:,.0f}</b></span>
                <span>Risk Audit: <b style="color: {'#48BB78' if risk_dec == 'ACCEPT' else '#F56565'};">{risk_dec}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info("🛡️ **Operator Authority**: The AI recommendation will not execute without explicit human authorization.")

    current_status = approval_state_dict.get(selected_truck_id, "PENDING")

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("✓ APPROVE PLAN", key=f"btn_approve_{selected_truck_id}", type="primary", use_container_width=True):
            approval_state_dict[selected_truck_id] = "APPROVED"
            st.rerun()

    with btn_col2:
        if st.button("✕ REJECT & REPLAN", key=f"btn_reject_{selected_truck_id}", use_container_width=True):
            approval_state_dict[selected_truck_id] = "REJECTED"
            st.rerun()

    st.markdown("<div style='margin-top: 0.8rem;'></div>", unsafe_allow_html=True)
    if current_status == "APPROVED":
        st.success(f"✓ **PLAN APPROVED**: Action plan dispatched to fleet controller for {selected_truck_id}.")
    elif current_status == "REJECTED":
        st.error(f"🛑 **PLAN REJECTED**: Action plan rejected by controller for {selected_truck_id}. Re-planning initiated.")
    else:
        st.warning(f"⏳ **Awaiting Controller Authorization for {selected_truck_id}**")
