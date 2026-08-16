# LOGISTICS INCIDENT COMMANDER — Setup

Complete step-by-step developer setup guide to configure, run, and evaluate the **LOGISTICS INCIDENT COMMANDER** Control Tower application in a clean local environment.

---

## Prerequisites

Before starting, ensure the following software is installed on your machine:

- **Python 3.10 or newer**: Required Python runtime.
- **Git**: Required for repository cloning and version control.
- **Internet Connection**: Required for live Google Gemini API calls and map routing queries.

---

## 1. Clone the Repository

Clone the project repository to your local system and navigate to the project directory:

```bash
git clone <repository-url>
cd Transcendents
```

---

## 2. Create a Virtual Environment

Isolate project dependencies by creating and activating a clean Python virtual environment.

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> **Note**: If PowerShell displays an execution policy restriction, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` before activating.

### Windows (Command Prompt)

```cmd
.\.venv\Scripts\activate
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## 3. Install Dependencies

Install all required third-party Python packages using the finalized `requirements.txt`:

```bash
pip install -r requirements.txt
```

### Final `requirements.txt` Package Manifest
- `streamlit==1.61.1`: Web dashboard framework.
- `google-genai==2.17.0`: Official Google Gemini API SDK.
- `python-dotenv==1.2.2`: Environment configuration manager.
- `folium==0.19.4`: Interactive leaflet map renderer.
- `streamlit-folium==0.24.0`: Streamlit folium map integration component.

---

## 4. Configure Gemini API Key

The application uses Google Gemini API for live multi-agent AI reasoning and risk auditing.

1. Copy the provided environment template `.env.example` to create your local `.env` file:

```bash
cp .env.example .env
```

2. Open `.env` and configure your valid Gemini API key:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

> **Security Note**: Never commit your local `.env` file or expose your `GEMINI_API_KEY` in source control. The `.env` file is excluded via `.gitignore`.

---

## 5. Run the Application

Launch the LOGISTICS INCIDENT COMMANDER interactive control tower UI:

```bash
streamlit run app.py
```

This starts the local Streamlit application server and automatically opens the Command Center UI in your web browser (typically at `http://localhost:8501`).

---

## 6. Project Structure

```text
Transcendents/
│
├── app.py                  # Main application entry point & multi-agent pipeline orchestrator
├── agents/                 # Autonomous agent implementation modules
│   ├── fleet_monitor.py    # Disruption & telemetry anomaly detector (Agent 1)
│   ├── threat_intel.py     # Route threat verification agent (Agent 2)
│   ├── dispatch_gate.py    # Deterministic escalation gate (Agent 3)
│   ├── incident_planner.py # AI response plan generator (Agent 4)
│   └── risk_critic.py      # AI constraint auditor (Agent 5)
├── services/               # Centralized external API integrations
│   └── gemini_client.py    # Shared Google Gemini API client wrapper
├── ui/                     # Control Tower Streamlit UI layout & components
│   ├── dashboard.py        # 3-Column main command center layout assembly
│   ├── components.py       # Header, fleet summary counters & telemetry cards
│   ├── map_view.py         # Leaflet operational control map component
│   └── agent_trace.py      # Agent decision workspace & human approval tabs
├── data/                   # Authoritative mock telemetry & disruption datasets
│   ├── mock_fleet.json     # Primary fleet telemetry dataset
│   ├── fleet_mock.json    # Fallback fleet telemetry dataset
│   ├── mock_disruptions.json # Disruption intelligence dataset
│   └── facilities.json     # Distribution hubs & facilities catalog
├── requirements.txt        # Python runtime package dependencies
├── .env.example            # Environment configuration template
├── SETUP.md                # Developer onboarding setup documentation
└── README.md               # System overview and architecture guide
```

---

## 7. Runtime Behavior

- **Authoritative Mock Telemetry**: Operational status for fleet vehicles is dynamically derived from `data/mock_disruptions.json` and `data/mock_fleet.json`.
- **AI Reasoning & Deterministic Fallback**: When `GEMINI_API_KEY` is configured, live Gemini LLM models generate candidate response plans and risk critiques. If API requests encounter network or rate-limit issues, built-in deterministic fallback engines guarantee continuous operational stability.

---

## 8. Troubleshooting

### `streamlit` Command Not Found
- **Cause**: Virtual environment is not activated or packages were installed globally.
- **Solution**: Activate `.venv` (`.\.venv\Scripts\Activate.ps1` or `.\.venv\Scripts\activate`) and re-run `pip install -r requirements.txt`. Alternatively, run `python -m streamlit run app.py`.

### Gemini Authentication / API Key Error
- **Cause**: `.env` file is missing or `GEMINI_API_KEY` is unconfigured/invalid.
- **Solution**: Ensure `.env` exists in the project root directory and contains `GEMINI_API_KEY=your_valid_key`.

### Dependency Installation Error
- **Cause**: Incompatible Python version or outdated virtual environment.
- **Solution**: Ensure Python 3.10 or newer is installed. Remove `.venv` and recreate it cleanly before re-running `pip install -r requirements.txt`.

---

## Security

- **Keep Secrets Local**: Never commit `.env` or hardcode API keys into codebase files.
- **Environment Template**: `.env.example` contains only non-sensitive placeholders.
- **Version Control**: `.env` and `.venv` are strictly ignored by `.gitignore`.
