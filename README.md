# 🚛 LOGISTICS INCIDENT COMMANDER

**LOGISTICS INCIDENT COMMANDER** is an AI-powered logistics incident control tower that continuously monitors real-time fleet disruptions, evaluates incoming threats, generates operational response plans, critiques candidate actions against strict business and safety constraints, and presents decision recommendations through a command-center UI with human approval. Built as a multi-agent system, it bridges raw telemetry and actionable dispatch decisions, allowing logistics controllers to proactively navigate disruptions—such as floods, landslides, protests, and mechanical breakdowns—before shipments are compromised.

---

## 🎯 Problem

In freight and supply-chain logistics, disruptions occur while shipments are already moving:

- **Incomplete Telemetry**: Telemetry tells operators *where* a truck is stopped or moving, but not *why* or *what operational action* should be taken.
- **Complex Multi-Constraint Decisions**: Choosing whether to reroute, wait, or transfer cargo requires balancing route distance, ETA, cargo shelf life, contract delivery deadlines, disruption severity, facility locations, additional cost, and operational feasibility.
- **Manual Bottlenecks**: Human controllers are overwhelmed by raw alerts and lack automated tool support to evaluate candidate solutions holistically under tight deadline pressures.

LOGISTICS INCIDENT COMMANDER replaces slow, reactive manual intervention with automated multi-agent decision support, providing human operators with validated, cost-optimized incident response plans.

---

## 💡 Solution

The system processes incidents through an end-to-end multi-agent pipeline, moving seamlessly from disruption detection to human approval:

- **Fleet Monitor**: Analyzes truck telemetry for abnormal stoppages and delay anomalies.
- **Threat Intelligence**: Scans corridor data to verify disruption type, severity, location, and whether the threat is currently active or upcoming.
- **Dispatch Gate**: Acts as a deterministic gatekeeper, escalating only high-confidence disruptions that warrant incident planning while filtering out false positives.
- **Incident Planner**: Generates candidate operational actions (such as rerouting or warehouse transfer) and uses structured Google Gemini AI reasoning alongside OSRM routing data to propose an optimal response plan.
- **Risk Critic**: Performs an independent audit of the proposed plan against strict cargo shelf life, delivery deadlines, budget thresholds, and driver safety constraints, enforcing a re-planning loop if necessary.
- **Human Approval**: Serves as the final control boundary, presenting the validated plan to human dispatch controllers for final authorization before execution.

---

## 🏗️ Architecture

The application follows a clean modular architecture separating agent logic, external service integrations, deterministic constraint validation, and the Streamlit command center UI.

```text
               User / Control Tower UI (Streamlit)
                                ↓
                          Fleet Monitor
                                ↓
                       Threat Intelligence
                                ↓
                          Dispatch Gate
                                ↓
                        Incident Planner
                                ↓
                           Risk Critic
                                ↓
                          Human Approval
```

### Supporting System Components

- **Google Gemini API**: Powers structured multi-agent reasoning in Threat Intelligence, Incident Planner, and Risk Critic.
- **OSRM Routing Engine**: Provides real-world driving distance, duration, and detour route calculations without external billing dependencies.
- **Authoritative Mock Datasets**: Structured JSON datasets representing fleet telemetry (`mock_fleet.json`), active disruptions (`mock_disruptions.json`), and distribution hubs (`facilities.json`).
- **Streamlit & Folium**: Delivers a high-contrast dark ops command dashboard featuring interactive Leaflet route polylines and operational markers (`streamlit-folium`).

---

## 🤖 AI & Decision Engine

The core decision engine combines LLM-driven operational reasoning with deterministic fallback logic to ensure output safety and mathematical precision:

- **Structured LLM Reasoning**: Google Gemini evaluates candidate response actions using structured schemas for transparent chain-of-thought justification.
- **Explicit Operational Candidate Modeling**: Candidate options are pre-evaluated for distance, time, and cost before being presented to the model.
- **Complete Journey Feasibility Evaluation**: Every plan is tested against remaining delivery deadlines and cargo shelf life.
- **Deterministic Guardrails & Fallbacks**: Protective validation rules prevent invalid, hallucinated, or infeasible AI outputs from reaching dispatchers.
- **`no_feasible_action` State**: When no permitted operational action can satisfy both deadline and shelf-life constraints, the system explicitly reports `no_feasible_action` and escalates to human managers.
- **Forbidden Action Enforcement**: Operational actions are strictly constrained to permitted strategies; actions such as `transfer_to_another_vehicle` are explicitly **forbidden** and excluded from the action space.

### Permitted Operational Actions

| Action | Description |
|---|---|
| `reroute` | Navigates the shipment around the disruption corridor via an alternate OSRM waypoint. |
| `wait` | Holds the vehicle at a safe location when disruption duration is shorter than reroute overhead. |
| `transfer_to_storage` | Offloads perishable or critical cargo to a nearby cold-storage facility or logistics hub. |
| `no_feasible_action` | Triggered when all candidates deterministically violate delivery deadlines or shelf life. |

> **Design Principle**: Gemini does not act as an unconstrained sole authority. Deterministic operational constraints guard the system at every step.

---

## 🗺️ Live Control-Tower UI

The Streamlit control tower dashboard is structured for real-time situational awareness and rapid decision-making:

- **Fleet Status Overview**: Top-level summary metrics tracking total trucks, normal transit, at-risk corridors, active incidents, and high-priority cargo values.
- **Truck Selection Panel**: Filterable sidebar dropdown displaying real-time operational status badges (`🔴 INCIDENT`, `🟠 AT_RISK`, `🟢 NORMAL`).
- **Live Operational Control Map**: Dark-themed Folium Leaflet map rendering current truck position, disruption location, original route polyline, alternate reroute path, and nearby logistics facilities.
- **Agent Decision Trace**: Real-time narration stream displaying step-by-step reasoning, confidence scores, and telemetry checks from each agent in the pipeline.
- **Human Approval Gate**: Interactive tab allowing controllers to review candidate metrics (cost, ETA, shelf-life margin) and explicitly click `Approve & Dispatch` or `Reject Action Plan`.
- **Analyze Incident Workflow**: On-demand analysis trigger executing the multi-agent pipeline for selected vehicles.

---

## 🔄 Incident Decision Flow

A concrete incident walkthrough follows eight discrete steps from detection to action dispatch:

1. **Telemetry Anomaly Detection**: Fleet Monitor flags a truck exhibiting abnormal stoppage (e.g., speed = 0 for >30 minutes) or corridor delay.
2. **Threat Intelligence Verification**: Threat Intel queries disruption data to verify event type, severity, coordinates, and active stage (`current` vs `upcoming`).
3. **Escalation Gating**: Dispatch Gate evaluates combined telemetry and threat confidence, escalating only validated incidents to planning.
4. **Candidate Generation**: Incident Planner generates candidate actions (`reroute`, `wait`, `transfer_to_storage`, `no_feasible_action`) and fetches OSRM route metrics.
5. **Feasibility Evaluation**: Complete journey duration, additional delay overhead, fuel/driver cost, and deadline/shelf-life margins are calculated for each candidate.
6. **Gemini Structured Reasoning**: Gemini analyzes valid candidate options and selects the optimal operational recommendation with written rationale.
7. **Independent Risk Critique**: Risk Critic verifies candidate metrics against strict safety and business rules. If rejected, a 2nd re-planning cycle is executed automatically.
8. **Human Controller Approval**: The validated action plan is presented in the Human Approval tab for final authorization.

> **Control Boundary**: LOGISTICS INCIDENT COMMANDER is designed strictly as a human-in-the-loop decision-support system, not an autonomous vehicle controller.

---

## 📊 Operational Scenarios

The system evaluates real-world logistics challenges using authoritative test scenarios present in the repository:

| Vehicle ID | Disruption Type | Location / Corridor | Operational Outcome | Decision Status |
|---|---|---|---|---|
| **TRK-102** | Flood | NH-160 near Kalyan, MH | **`reroute`** around waterlogged corridor via alternate highway | `ACCEPT` |
| **TRK-104** | Protest | NH-48 near Kotputli, RJ | **`reroute`** proactively around upcoming protest location | `ACCEPT` |
| **TRK-105** | Vehicle Breakdown | NH-48 near Thane, MH | **`transfer_to_storage`** cargo diverted to nearby logistics hub | `ACCEPT` |
| **TRK-107** | Landslide | NH-48 near Jaipur, RJ | **`no_feasible_action`** (baseline travel time exceeds deadline) | `REJECT` / Escalated |
| **TRK-112** | Protest | NH-48 near Jaipur Entry, RJ | **`reroute`** via alternate entry route avoiding farmer rally | `ACCEPT` |

### Key Operational Behaviors

- **Proactive & Reactive Rerouting**: Reroutes vehicles around both active flooding (TRK-102) and upcoming protests (TRK-104, TRK-112).
- **Facility-Aware Offloading**: Diverts breakdown vehicles (TRK-105) carrying sensitive electronics to verified regional storage warehouses.
- **Deterministic Constraint Protection**: Correctly identifies when no operational action satisfies delivery deadlines (TRK-107) and rejects infeasible plans.

---

## 🧠 Engineering Highlights

- **Structured Agent Contracts**: Well-defined JSON inputs and outputs passed across all pipeline stages for predictable inter-agent communication.
- **Separation of AI Reasoning & Deterministic Guardrails**: LLMs perform contextual reasoning while Python rule engines enforce hard constraints.
- **Operational Candidate Modeling**: Explicit pre-computation of route distances, durations, and costs before AI decision evaluation.
- **Complete Journey Feasibility Evaluation**: Calculates total end-to-end journey feasibility rather than evaluating disruption segments in isolation.
- **OSRM Route Engine Integration**: Real-time road network routing and detour generation via OSRM HTTP API.
- **Facility-Aware Planning**: Spatial distance matching against regional distribution centers and cold-storage warehouses (`facilities.json`).
- **Authoritative Data Preservation**: Preserves original truck telemetry and cargo constraints across all agent transformations.
- **Deterministic Fallback Behavior**: Guaranteed system execution even during API rate limits or network offline states.
- **Strict Human Approval Boundary**: Action plan dispatch requires explicit user authorization in the UI workspace.
- **Forbidden Action Enforcement**: Hardcoded exclusion of unsafe operational actions (e.g. `transfer_to_another_vehicle`).
- **UI/Backend Separation**: Modular division between UI dashboard rendering (`ui/`) and core multi-agent execution pipeline (`agents/`).

---

## 🛠️ Tech Stack

| Layer | Technology | Usage in Project |
|---|---|---|
| **Core Language** | Python 3.10+ | Multi-agent orchestrator, constraint validation, and data pipeline |
| **User Interface** | Streamlit 1.61.1 | Command center layout, agent trace narration, and human approval UI |
| **AI / LLM API** | Google Gemini API (`google-genai`) | Multi-agent operational reasoning and risk auditing (`gemini-3-flash-preview`) |
| **Interactive Maps** | Folium 0.19.4 | Custom Leaflet map tiles, markers, route polylines, and popups |
| **Streamlit Map Bridge** | Streamlit-Folium 0.24.0 | Seamless rendering of Folium maps inside Streamlit components |
| **Routing Engine** | OSRM (Open Source Routing Machine) | Driving distance and duration calculations via public HTTP REST API |
| **Operational Data** | JSON Datasets | Mock telemetry (`mock_fleet.json`), disruptions (`mock_disruptions.json`), facilities (`facilities.json`) |

---

## 📁 Project Structure

```text
.
├── app.py                  # Main Streamlit application & multi-agent pipeline orchestrator
├── agents/                 # Autonomous agent implementation modules
│   ├── fleet_monitor.py    # Telemetry anomaly & stoppage detector (Agent 1)
│   ├── threat_intel.py     # Route threat verification agent (Agent 2)
│   ├── dispatch_gate.py    # Deterministic escalation gate (Agent 3)
│   ├── incident_planner.py # AI response plan generator (Agent 4)
│   └── risk_critic.py      # AI constraint auditor & risk critic (Agent 5)
├── services/               # Centralized external API integrations
│   └── gemini_client.py    # Google Gemini API client wrapper with fallback retries
├── ui/                     # Command Center UI components & layout
│   ├── dashboard.py        # 3-Column main command center layout assembly
│   ├── components.py       # Header, fleet summary cards & truck telemetry panels
│   ├── map_view.py         # Leaflet operational map component with OSRM polylines
│   └── agent_trace.py      # Agent decision workspace & human approval tabs
├── data/                   # Authoritative operational datasets
│   ├── mock_fleet.json     # Primary fleet telemetry dataset
│   ├── fleet_mock.json    # Fallback fleet telemetry dataset
│   ├── mock_disruptions.json # Active disruption intelligence dataset
│   └── facilities.json     # Logistics hubs & storage facilities catalog
├── requirements.txt        # Python package manifest
├── .env.example            # Environment configuration template
├── SETUP.md                # Local installation and developer setup guide
└── README.md               # System overview, architecture & engineering guide
```

---

## ⚙️ Quick Start

### 1. Clone & Setup Virtual Environment

```bash
git clone <repository-url>
cd Transcendents

python -m venv .venv
# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API Key

Copy `.env.example` to `.env` and set your Google Gemini API key:

```env
GEMINI_API_KEY=your_google_gemini_api_key_here
```

### 4. Launch Command Center

```bash
streamlit run app.py
```

Open your browser at `http://localhost:8501` to access the **LOGISTICS INCIDENT COMMANDER** Control Tower UI.

---

## 📄 License & Documentation

For detailed developer setup instructions, troubleshooting steps, and environment configuration, refer to [SETUP.md](file:///c:/Users/yugal%20redhu/Projects/Transcendents/SETUP.md).