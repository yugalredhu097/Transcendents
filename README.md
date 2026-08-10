# AI Logistics Incident Commander

**Track:** Advanced Autonomous AI Agents — Ascendant Agents (D'Code, NSUT)

> An autonomous multi-agent system that decides *what to do* when a shipment is disrupted — and can act before the truck even gets stuck, not just after.

<!-- TODO: add a 15–30s demo GIF or screenshot here once the UI is working -->

---

## Overview

### The problem

Indian logistics companies routinely lose money when trucks are disrupted by flooding, road closures, protests, or accidents. GPS tracking tells a company *where* a truck is, but not *what it should do* — and that decision depends on cargo type, delivery deadline, storage cost, rerouting cost, and risk, changing in real time. Today this is a manual, slow, reactive process.

### The solution

AI Logistics Incident Commander runs two independent detection agents on every truck at once: one watching the truck itself for abnormal stoppages, and one scanning the route ahead for disruptions the truck hasn't reached yet. Either one finding a real problem triggers the same downstream response: a planning agent proposes an action, a critic agent checks it against cargo and cost constraints and can reject it and force a re-plan, and a human approves the final call.

This means the system handles two genuinely different situations with one pipeline:
- **Reactive:** a truck has already stopped — investigate why, and respond.
- **Proactive:** a truck is moving normally, but a threat (e.g. a protest) is found further down its route — reroute before the disruption ever happens.

---

## Features

- **Two independent detection agents running in parallel** on the same truck data — not a single fixed trigger.
- **Proactive disruption detection** — the system can recommend a reroute before a truck is ever affected, using real-world disruption search.
- **A Dispatch Gate that only escalates on real evidence** — if neither agent finds a genuine problem, the pipeline stays quiet and just updates the dashboard, rather than crying wolf.
- **Multi-option incident planning** — reroute, wait, transfer to storage, or transfer to another vehicle — scored against cargo shelf-life, deadline, and cost.
- **Self-critique and re-planning loop** — a dedicated Risk Critic agent can reject the Planner's first proposal and force a genuine alternative, rather than accepting the first plan blindly.
- **Human-in-the-loop approval** before any action is treated as final.
- **Transparent agent reasoning stream** — every agent's decision and justification is shown live, not hidden in a black box.

---

## Technical Workflow

```
                    [Mock Fleet/Truck Data]
              Location + Cargo + Destination + Deadline
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
   ┌─────────────────────┐      ┌─────────────────────┐
   │  Agent 1: Fleet      │      │  Agent 2: Threat     │
   │  Monitor             │      │  Intelligence         │
   │  Detects abnormal    │      │  Scans for current OR │
   │  stoppage             │      │  upcoming disruptions,│
   │                       │      │  independent of Agent │
   │                       │      │  1's status            │
   └──────────┬───────────┘      └──────────┬───────────┘
              └──────────────┬───────────────┘
                             ▼
                ┌─────────────────────────┐
                │  Dispatch Gate           │
                │  Escalates if EITHER     │
                │  agent found a real      │
                │  problem                 │
                └─────────────┬───────────┘
                     ┌────────┴────────┐
                     ▼                 ▼
              No escalation       Escalation
              (dashboard only)         │
                                        ▼
                             ┌─────────────────────┐
                             │ Agent 3: Incident     │
                             │ Planner — proposes:   │
                             │ Reroute/Wait/Storage/ │
                             │ Transfer               │
                             └──────────┬───────────┘
                                        ▼
                             ┌─────────────────────┐
                             │ Agent 4: Risk Critic  │
                             │ shelf-life/cost/ETA/  │
                             │ safety check          │
                             └──────┬───────────┬───┘
                                   ▼           ▼
                               ACCEPT       REJECT
                                   │           │
                                   ▼           └──► back to Agent 3
                            ┌─────────────┐
                            │ Action Plan │
                            └──────┬──────┘
                                   ▼
                            ┌─────────────┐
                            │   Human      │
                            │   Approval   │
                            └─────────────┘
```

**Why this counts as agentic, not just data analysis:** the system doesn't wait for one fixed condition to act — two independent agents each carry the authority to trigger a response, a dedicated Dispatch Gate makes a real accept/reject-style decision about whether to escalate at all, and the Risk Critic can genuinely reject the Planner's output and force a second, different proposal. Nothing here is a single-shot Q&A.

---

## Tech Stack

| Layer | Tool | Notes |
|---|---|---|
| UI / Dashboard | Streamlit | Live agent reasoning stream + incident dashboard |
| Data processing | Python + Pandas | Fleet, cargo, and warehouse mock data |
| Agent reasoning | LLM API (Gemini / OpenAI) | Powers Threat Intel, Planner, and Critic agents |
| Disruption detection | Web Search API | Verifies real-world current and upcoming disruption events |
| Routing | OSRM (primary), Google Maps (optional upgrade) | OSRM used for the prototype to avoid an external billing/key dependency on a tight timeline |
| Fleet/cargo/warehouse data | CSV / JSON | Mock dataset, not a live GPS feed |
| Constraint checks | Python rule engine | Shelf-life, cost, and safety validation logic |

> **Scoping note:** Live GPS is simulated via mock data for this prototype, and routing uses OSRM rather than Google Maps to remove a billing/key dependency from the critical path. If the Web Search API integration proves unreliable, disruption events fall back to a small pre-authored dataset of realistic (non-live) incident reports, clearly labeled as such in the code. Every claim in the demo is honestly backed by what's actually running.

---

## Setup Instructions

<!-- TODO: fill in exact commands once app.py / requirements.txt are finalized -->

```bash
# 1. Clone the repo
git clone <repo-url>
cd ai-logistics-incident-commander

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add API keys
cp .env.example .env
# Fill in your LLM API key and Web Search API key in .env

# 5. Run the app
streamlit run app.py
```

---

## Team

<!-- TODO: names + roles -->
-
-
-
-

## Roadmap (post–Round 1)

- Migrate agent orchestration from a sequential Python pipeline to CrewAI for genuine autonomous multi-agent coordination.
- Optional Google Maps integration for production-grade routing.
- Live GPS feed integration in place of mock fleet data.