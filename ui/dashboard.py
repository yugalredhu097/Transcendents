"""
Dashboard Page Assembly for LOGISTICS INCIDENT COMMANDER Command Center
Phase 3 Final Control Tower Layout:
- Top: Persistent Sticky Fleet Overview Status Bar (.lic-fleet-overview)
- Left Column (Fixed): Truck Selection & Selected Truck Details ONLY (.lic-dashboard-left)
- Center Column (Fixed): High-contrast Dark Ops Live Map with OSRM Route Polylines & Legend (.lic-dashboard-center)
- Right Column (Scrollable): Decision Workspace Tabs ([ AGENT TRACE ] | [ HUMAN APPROVAL ]) & [ ANALYZE INCIDENT ] trigger (.lic-dashboard-right)
"""

import streamlit as st
from typing import Dict, Any, List
from ui.components import (
    apply_dark_theme,
    render_header,
    render_fleet_summary,
    render_selected_truck_panel,
    get_truck_operational_status,
)
from ui.map_view import render_leaflet_map, load_facilities_data, load_disruptions_data
from ui.agent_trace import render_agent_decision_trace, render_human_approval_tab


def render_command_center_dashboard(
    fleet_data: List[Dict[str, Any]],
    pipeline_runner_fn=None,
    thought_stream_fn=None,
    human_approval_fn=None,
):
    """
    Assembles final locked LOGISTICS INCIDENT COMMANDER Control Tower Dashboard.
    """
    apply_dark_theme()
    render_header()

    disruptions_data = load_disruptions_data()
    facilities_data = load_facilities_data()

    # Session state initialization
    if "pipeline_results" not in st.session_state:
        st.session_state["pipeline_results"] = {}
    if "approval_states" not in st.session_state:
        st.session_state["approval_states"] = {}

    truck_by_id = {t.get("truck_id"): t for t in fleet_data if t.get("truck_id")}
    available_tids = list(truck_by_id.keys())

    if "selected_truck_id" not in st.session_state or st.session_state["selected_truck_id"] not in truck_by_id:
        st.session_state["selected_truck_id"] = "TRK-107" if "TRK-107" in truck_by_id else (available_tids[0] if available_tids else "UNKNOWN")

    # 1. TOP ROW: Persistent Sticky Fleet Overview (Wrapped in .lic-fleet-overview)
    st.markdown('<div class="lic-fleet-overview">', unsafe_allow_html=True)
    render_fleet_summary(fleet_data, disruptions_data)
    st.markdown('</div>', unsafe_allow_html=True)

    # 2. MAIN OPERATIONAL LAYOUT (3 Columns)
    col_left, col_center, col_right = st.columns([1.1, 1.8, 1.2])

    # ------------------------------------------------------------------------
    # LEFT COLUMN: STICKY TRUCK SELECTION & TELEMETRY PROFILE ONLY
    # ------------------------------------------------------------------------
    with col_left:
        st.markdown('<div class="lic-dashboard-left">', unsafe_allow_html=True)
        st.markdown("### 🎯 Fleet Vehicle Selection")

        # Dropdown options formatted with operational status
        truck_options = {}
        for truck in fleet_data:
            tid = truck.get("truck_id", "UNKNOWN")
            status = get_truck_operational_status(truck, disruptions_data)
            dis_type = disruptions_data.get(tid, {}).get("disruption_type", "")

            if status == "INCIDENT":
                label = f"🔴 {tid} — Incident ({dis_type})"
            elif status == "AT_RISK":
                label = f"🟠 {tid} — At Risk ({dis_type})"
            else:
                label = f"🟢 {tid} — Normal Transit"

            truck_options[tid] = label

        current_tid = st.session_state["selected_truck_id"]
        current_idx = available_tids.index(current_tid) if current_tid in available_tids else 0

        selected_tid = st.selectbox(
            "Select Truck for Investigation:",
            options=available_tids,
            format_func=lambda tid: truck_options.get(tid, tid),
            index=current_idx,
            key="truck_selector_dropdown",
        )

        if selected_tid != current_tid:
            st.session_state["selected_truck_id"] = selected_tid
            current_tid = selected_tid

        st.markdown("---")

        # Selected Truck Telemetry Details (NO Active Incidents list, NO analyze button)
        selected_truck = truck_by_id.get(current_tid, {})
        render_selected_truck_panel(selected_truck, disruptions_data)
        st.markdown('</div>', unsafe_allow_html=True)

    # Fetch current pipeline analysis result if previously executed
    current_result_or_status = st.session_state["pipeline_results"].get(current_tid)
    if isinstance(current_result_or_status, dict) and current_result_or_status.get("FAILED"):
        pipeline_result = None
        pipeline_failed = True
    else:
        pipeline_result = current_result_or_status
        pipeline_failed = False

    # ------------------------------------------------------------------------
    # CENTER COLUMN: STICKY LIVE OPERATIONAL MAP
    # ------------------------------------------------------------------------
    with col_center:
        st.markdown('<div class="lic-dashboard-center">', unsafe_allow_html=True)
        st.markdown("### 🗺️ Live Operational Control Map")
        render_leaflet_map(
            fleet_data=fleet_data,
            disruptions_data=disruptions_data,
            facilities_data=facilities_data,
            selected_truck_id=current_tid,
            pipeline_result=pipeline_result,
        )
        st.markdown('</div>', unsafe_allow_html=True)

    # ------------------------------------------------------------------------
    # RIGHT COLUMN: INDEPENDENTLY SCROLLABLE DECISION WORKSPACE
    # ------------------------------------------------------------------------
    with col_right:
        st.markdown('<div class="lic-dashboard-right">', unsafe_allow_html=True)
        if pipeline_failed:
            st.error("⚠️ **ANALYSIS FAILED**: The incident analysis could not be completed. Please retry.")

        tab_trace, tab_approval = st.tabs(["AGENT TRACE", "HUMAN APPROVAL"])

        with tab_trace:
            analyze_requested = render_agent_decision_trace(pipeline_result, selected_truck)

            # EXPLICIT TRIGGER FROM RIGHT WORKSPACE INSTRUCTION CARD
            if analyze_requested and pipeline_runner_fn:
                with st.status(f"ANALYZING INCIDENT for {current_tid}...", expanded=True) as status_box:
                    st.write("🔍 **Fleet Monitor** — Telemetry & Stoppage Evaluation...")
                    st.write("🌐 **Threat Intelligence** — Route Threat Verification...")
                    st.write("🛑 **Dispatch Gate** — Escalation Evaluation...")
                    st.write("🗺️ **Incident Planner** — AI Response Proposal...")
                    st.write("⚖️ **Risk Critic** — Constraint Critique...")
                    
                    try:
                        res = pipeline_runner_fn(selected_truck)
                        st.session_state["pipeline_results"][current_tid] = res
                        status_box.update(label=f"✓ Analysis Complete for {current_tid}", state="complete", expanded=False)
                    except Exception as ex:
                        st.session_state["pipeline_results"][current_tid] = {"FAILED": True, "error": str(ex)}
                        status_box.update(label=f"⚠️ Analysis Failed for {current_tid}", state="error", expanded=False)
                
                st.rerun()

        with tab_approval:
            render_human_approval_tab(pipeline_result, current_tid, st.session_state["approval_states"])

        st.markdown('</div>', unsafe_allow_html=True)
