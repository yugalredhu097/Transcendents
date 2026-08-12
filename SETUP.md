# AI Logistics Incident Commander - Setup Guide

This document contains complete, step-by-step setup instructions required to clone, configure, run, and test the **AI Logistics Incident Commander** project locally from scratch.

---

## 1. Prerequisites

Before installing the application, ensure the following tools are installed on your system:

- **Python 3.10 or newer**: Required runtime environment for the application backend and Streamlit framework.
- **Git**: Required for version control and cloning the repository.
- **Internet Connection**: Required for live API interactions (e.g., Google Gemini API calls and OSRM route queries).
- **Windows PowerShell / Terminal**: Windows PowerShell command examples are provided throughout this guide (Linux/macOS commands are also included where applicable).

---

## 2. Clone the Repository

Clone the project repository to your local machine and navigate into the workspace directory:

```bash
git clone <repository-url>
cd Transcendents
```

---

## 3. Create a Virtual Environment

A virtual environment isolates project dependencies, preventing conflicts with global Python packages or system libraries.

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> **Note**: If PowerShell displays a script execution policy error, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` before activating.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

> **Note**: The `.venv` directory is intentionally ignored by Git to avoid committing binary executable files.

---

## 4. Install Project Dependencies

Install all third-party Python libraries specified in `requirements.txt`:

```bash
pip install -r requirements.txt
```

---

## 5. Configure Environment Variables

The application requires environment variables for external AI services. Create a local `.env` file in the root directory:

```env
GEMINI_API_KEY=your_api_key_here
```

### Important Security Rules

- **Never commit `.env` to Git**: The `.env` file contains sensitive credentials and is listed in `.gitignore`.
- Always verify `.env` remains untracked before staging commits.

---

## 6. Verify the Environment

Confirm that Python and pip are executing from inside the activated `.venv` virtual environment rather than a global Python installation:

```bash
python --version
pip --version
```

Verify that the path returned by `pip --version` points to the project's local `.venv` directory.

---

## 7. Run the Application

Launch the Streamlit interactive dashboard:

```bash
streamlit run app.py
```

This starts a local web server and opens the application UI in your default browser (typically at `http://localhost:8501`).

---

## 8. Run the Tests

Execute each test suite to verify that agent modules, data contracts, and integration flows are functioning correctly:

```bash
python test_fleet_monitor.py
python test_threat_intel.py
python test_dispatch_gate.py
python test_incident_planner.py
python test_risk_critic.py
```

All test suites should execute cleanly with a 100% pass rate before pushing code or creating a Pull Request.

---

## 9. Troubleshooting

### Virtual Environment Not Activated
- **Symptom**: Packages installed globally or `pip` installs fail due to permissions.
- **Solution**: Ensure your shell prompt displays `(.venv)`. Re-run activation: `.\.venv\Scripts\Activate.ps1` (Windows) or `source .venv/bin/activate` (Linux/macOS).

### Permission Issues Activating Virtual Environment (Windows)
- **Symptom**: `File ... cannot be loaded because running scripts is disabled on this system.`
- **Solution**: Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` in PowerShell, then activate again.

### `ModuleNotFoundError`
- **Symptom**: `ModuleNotFoundError: No module named 'streamlit'` (or another package name).
- **Solution**: Confirm `.venv` is active, then re-run `pip install -r requirements.txt`.

### `"streamlit"` Command Not Found
- **Symptom**: `streamlit : The term 'streamlit' is not recognized...`
- **Solution**: Run `python -m streamlit run app.py` or reactivate `.venv` where Streamlit is installed.

### Missing `GEMINI_API_KEY`
- **Symptom**: LLM API calls fail or return authentication errors.
- **Solution**: Ensure `.env` exists in the root directory with a valid key: `GEMINI_API_KEY=your_api_key_here`.

### Missing Dependencies in `requirements.txt`
- **Symptom**: Importing a library fails despite running `pip install -r requirements.txt`.
- **Solution**: Run `pip install <package_name>` inside `.venv` and append the requirement to `requirements.txt`.

---

## 10. Project Structure

```text
Transcendents/
│
├── agents/
│   ├── fleet_monitor.py
│   ├── threat_intel.py
│   ├── dispatch_gate.py
│   ├── incident_planner.py
│   └── risk_critic.py
├── data/
│   ├── mock_fleet.json
│   ├── mock_disruptions.json
│   └── facilities.json
├── app.py
├── README.md
├── SETUP.md
├── requirements.txt
├── .env.example
├── .gitignore
└── test_*.py
```

---

## 11. Notes

- **`.venv`**: Intentionally ignored by Git. Do not commit virtual environment files.
- **`.env`**: Intentionally ignored by Git. Never expose secret keys in source control.
- **`requirements.txt`**: Must be kept up-to-date and committed whenever dependencies change.
- **`SETUP.md`**: Should be maintained and updated whenever the project setup or configuration requirements change.
- All new developers, contributors, and evaluators should follow this guide step-by-step for a seamless local onboarding experience.
