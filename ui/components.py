"""
UI Components for Logistics Incident Commander Command Center
"""

import os
import json
import streamlit as st
from typing import Dict, Any, List, Tuple, Optional


def apply_dark_theme():
    """Injects custom CSS for a professional dark logistics control tower aesthetic."""
    st.markdown(
        """
        <style>
        /* Base Dark Theme Overrides */
        .stApp {
            background-color: #0E1117;
            color: #E2E8F0;
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
        }
        
        /* Sticky Top Fleet Summary Banner */
        .lic-fleet-overview {
            position: sticky;
            top: 0;
            z-index: 999;
            background-color: #0E1117;
            padding-top: 0.25rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid #2D3748;
            margin-bottom: 0.75rem;
        }

        /* Command Center Header */
        .header-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: linear-gradient(90deg, #1A202C 0%, #171923 100%);
            padding: 0.8rem 1.25rem;
            border-radius: 8px;
            border: 1px solid #2D3748;
            margin-bottom: 0.75rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        }
        .header-title {
            font-size: 1.5rem;
            font-weight: 800;
            color: #F7FAFC;
            letter-spacing: 0.05em;
            margin: 0;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .header-status {
            background-color: #1A365D;
            color: #63B3ED;
            border: 1px solid #2B6CB0;
            padding: 0.35rem 0.75rem;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
            letter-spacing: 0.03em;
            display: flex;
            align-items: center;
            gap: 0.4rem;
        }
        .status-dot {
            height: 9px;
            width: 9px;
            background-color: #38A169;
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 8px #38A169;
        }

        /* Fleet Metric Cards */
        .summary-card {
            background-color: #171923;
            border: 1px solid #2D3748;
            border-radius: 8px;
            padding: 0.75rem;
            text-align: center;
        }
        .summary-label {
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.2rem;
        }
        .summary-count {
            font-size: 1.7rem;
            font-weight: 800;
            margin: 0;
        }
        .card-normal { border-left: 4px solid #38A169; }
        .card-normal .summary-label { color: #48BB78; }
        .card-normal .summary-count { color: #68D391; }

        .card-atrisk { border-left: 4px solid #DD6B20; }
        .card-atrisk .summary-label { color: #ED8936; }
        .card-atrisk .summary-count { color: #F6AD55; }

        .card-incident { border-left: 4px solid #E53E3E; }
        .card-incident .summary-label { color: #F56565; }
        .card-incident .summary-count { color: #FEB2B2; }

        /* Detail Panel Styling */
        .detail-panel {
            background-color: #171923;
            border: 1px solid #2D3748;
            border-radius: 8px;
            padding: 0.9rem;
            margin-top: 0.5rem;
        }
        .detail-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 0.6rem;
            margin-top: 0.4rem;
        }
        .detail-item {
            background-color: #2D3748;
            padding: 0.45rem 0.65rem;
            border-radius: 6px;
        }
        .detail-label {
            font-size: 0.68rem;
            color: #A0AEC0;
            text-transform: uppercase;
            font-weight: 600;
        }
        .detail-value {
            font-size: 0.85rem;
            font-weight: 700;
            color: #EDF2F7;
        }

        /* Scoped Primary Dashboard Column Wrappers (Prevents nested column contamination) */
        div[data-testid="column"]:has(.lic-dashboard-left),
        div[data-testid="stColumn"]:has(.lic-dashboard-left) {
            position: sticky;
            top: 130px;
            align-self: flex-start;
        }
        div[data-testid="column"]:has(.lic-dashboard-center),
        div[data-testid="stColumn"]:has(.lic-dashboard-center) {
            position: sticky;
            top: 130px;
            align-self: flex-start;
        }
        div[data-testid="column"]:has(.lic-dashboard-right),
        div[data-testid="stColumn"]:has(.lic-dashboard-right) {
            max-height: calc(100vh - 140px);
            overflow-y: auto;
            overflow-x: hidden;
            padding-right: 0.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header():
    """Renders the dark command center header banner with system operational status."""
    st.markdown(
        """
        <div class="header-container">
            <div class="header-title">
                🚚 LOGISTICS INCIDENT COMMANDER
            </div>
            <div class="header-status">
                <span class="status-dot"></span> SYSTEM OPERATIONAL
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def classify_fleet_status(fleet_data: List[Dict[str, Any]], disruptions: Dict[str, Any]) -> Tuple[int, int, int]:
    """
    Calculates operational fleet counts dynamically:
    - INCIDENT (Red): Associated with verified active disruption in mock_disruptions.json
    - AT RISK (Orange): Abnormal stoppage duration (>30 min) or active threat without full blockade
    - NORMAL (Green): Actively moving along route within limits
    """
    normal_count = 0
    at_risk_count = 0
    incident_count = 0

    for truck in fleet_data:
        tid = str(truck.get("truck_id", ""))
        status = str(truck.get("status", "")).lower()
        stopped_min = float(truck.get("stopped_duration_minutes") or truck.get("stop_duration_minutes") or 0)
        delay_min = float(truck.get("delay_minutes", 0))

        if tid in disruptions:
            incident_count += 1
        elif status == "abnormal_stop" or stopped_min > 30 or delay_min > 30:
            at_risk_count += 1
        else:
            normal_count += 1

    return normal_count, at_risk_count, incident_count


def render_fleet_summary(fleet_data: List[Dict[str, Any]], disruptions: Dict[str, Any]):
    """Renders dynamic horizontal status cards for Normal, At Risk, and Incident truck counts."""
    normal_count, at_risk_count, incident_count = classify_fleet_status(fleet_data, disruptions)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            f"""
            <div class="summary-card card-normal">
                <div class="summary-label">🟢 Normal</div>
                <div class="summary-count">{normal_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div class="summary-card card-atrisk">
                <div class="summary-label">🟠 At Risk</div>
                <div class="summary-count">{at_risk_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f"""
            <div class="summary-card card-incident">
                <div class="summary-label">🔴 Incident</div>
                <div class="summary-count">{incident_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_selected_truck_panel(truck: Dict[str, Any], disruptions: Dict[str, Any] = None):
    """
    Renders detailed telemetry profile for a selected truck in the left column.
    CRITICAL RULE: If remaining_shelf_life_hours is null/None, display UNKNOWN.
    """
    st.markdown("### 🚚 Selected Truck Operations")

    if not truck:
        st.info("Select a truck from the dropdown to view operational telemetry.")
        return

    tid = truck.get("truck_id", "UNKNOWN")
    sid = truck.get("shipment_id", "N/A")
    cargo = truck.get("cargo_type", "General Freight")
    qty = truck.get("quantity", "N/A")
    unit = truck.get("unit", "")
    priority = truck.get("priority", "STANDARD")
    dest = truck.get("destination", "N/A")

    loc = truck.get("location")
    loc_name = loc.get("name") if isinstance(loc, dict) else truck.get("location_name", "En-Route Segment")

    speed = truck.get("speed_kmh", 0)
    delay = truck.get("delay_minutes", 0)
    stopped_min = truck.get("stopped_duration_minutes") or truck.get("stop_duration_minutes") or 0
    deadline = truck.get("delivery_deadline") or truck.get("deadline") or "N/A"

    # Incident information if truck is involved in an active disruption
    incident_info = disruptions.get(tid) if disruptions else None
    dis_type = incident_info.get("disruption_type", "N/A").upper() if incident_info else None
    dis_severity = incident_info.get("severity", "N/A").upper() if incident_info else None
    dis_pred = f"{incident_info.get('predicted_delay_hours')} hours" if incident_info else None

    # STRICT SHELF LIFE RULE: null/None -> UNKNOWN
    raw_shelf_life = truck.get("remaining_shelf_life_hours")
    if raw_shelf_life is not None:
        try:
            shelf_life_val = float(raw_shelf_life)
            shelf_life_display = f"{shelf_life_val:g} hours"
        except (ValueError, TypeError):
            shelf_life_display = "⚠ UNKNOWN"
    else:
        shelf_life_display = "⚠ UNKNOWN"

    # Incident header banner if active incident
    if incident_info:
        st.markdown(
            f"""
            <div style="background-color: #2C1A1D; border-left: 4px solid #E53E3E; border-radius: 6px; padding: 0.65rem 0.85rem; margin-bottom: 0.6rem;">
                <div style="font-weight: 800; color: #FEB2B2; font-size: 0.9rem;">🔴 INCIDENT DETECTED — {tid}</div>
                <div style="font-size: 0.8rem; color: #E2E8F0; margin-top: 0.2rem;">
                    <b>Type:</b> {dis_type} | <b>Severity:</b> {dis_severity}<br/>
                    <b>Predicted Disruption:</b> {dis_pred}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="detail-panel">
            <div style="font-weight: 800; font-size: 1rem; color: #F7FAFC; margin-bottom: 0.4rem;">
                Telemetry Profile: <span style="color: #63B3ED;">{tid}</span> ({sid})
            </div>
            <div class="detail-grid">
                <div class="detail-item">
                    <div class="detail-label">Cargo Type</div>
                    <div class="detail-value">{cargo}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Quantity</div>
                    <div class="detail-value">{qty} {unit}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Priority</div>
                    <div class="detail-value">{priority}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Destination</div>
                    <div class="detail-value">{dest}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Current Location</div>
                    <div class="detail-value" style="font-size: 0.78rem;">{loc_name}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Speed / Delay</div>
                    <div class="detail-value">{speed} km/h (+{delay}m)</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Stopped Duration</div>
                    <div class="detail-value">{stopped_min} mins</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Delivery Deadline</div>
                    <div class="detail-value" style="font-size: 0.78rem;">{deadline}</div>
                </div>
                <div class="detail-item" style="border: 1px solid {'#E53E3E' if 'UNKNOWN' in shelf_life_display else '#2B6CB0'};">
                    <div class="detail-label">Remaining Shelf Life</div>
                    <div class="detail-value" style="color: {'#FEB2B2' if 'UNKNOWN' in shelf_life_display else '#9DECF9'};">
                        {shelf_life_display}
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
