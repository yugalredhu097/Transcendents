# AI Logistics Incident Commander

**Track:** Advanced Autonomous AI Agents — Ascendant Agents (D'Code, NSUT)

> An autonomous multi-agent system that decides *what to do* when a truck shipment is disrupted — not just where the truck is.

<!-- TODO: add a 15–30s demo GIF or screenshot here once the UI is working -->
<!-- ![demo](assets/demo.gif) -->

---

## Overview

### The problem

Indian logistics companies routinely lose money when trucks are disrupted by flooding, road closures, protests, or accidents. GPS tracking tells a company *where* a truck is, but not *what it should do* about a disruption — and that decision depends on cargo type, delivery deadline, storage cost, rerouting cost, and risk, all changing in real time. Today this decision is made manually and slowly, by a human piecing together GPS data, phone calls, and news, under time pressure.

### The solution

AI Logistics Incident Commander is an autonomous agent pipeline that:
1. Continuously monitors mock fleet data for abnormal delays or stoppages.
2. Independently investigates *why* — searching for and verifying real-world disruption events (flooding, closures, protests) near the truck's location.
3. Plans a response (reroute / wait / transfer to storage / transfer to another vehicle) based on cargo shelf-life, delivery deadline, and cost.
4. Critiques its own plan against risk, cost, and safety constraints — and re-plans autonomously if the first plan doesn't hold up.
5. Surfaces a final, justified action plan for human approval before execution.

This is deliberately not a chatbot that answers a question once. It's a pipeline that **investigates, proposes, critiques, and revises its own decision** — the same propose → critique → accept/reject → replan loop used in serious autonomous agent design, applied to a real logistics decision.

---

## Features

- **Autonomous disruption detection** from mock live fleet/GPS data (no manual trigger needed).
- **Real-world disruption verification** via web search — the agent doesn't just guess a truck is delayed by "traffic," it looks for and cites what's actually happening near that location.
- **Multi-option incident planning** — reroute, wait, transfer to storage, or transfer to another vehicle — scored against cargo-specific constraints (shelf-life, deadline, cost).
- **Self-critique and re-planning loop** — a dedicated Risk Critic agent can *reject* the Planner's first proposal, sending it back to generate an alternative, rather than accepting the first plan blindly.
- **Human-in-the-loop approval** — the system proposes; a human makes the final call before any action is "executed," reflecting how this would need to work in a real logistics operation.
- **Transparent agent reasoning stream** — each agent's decision and justification is shown live, not hidden inside a black box.

---

## Technical Workflow

```
                  [Mock Fleet Data]
        Location + Cargo + Destination + Deadline
                          │
                          ▼
              ┌─────────────────────────┐
              │  Agent 1: Fleet Monitor  │
              │  Detects delay/abnormal  │
              │  stoppage                │
              └───────────┬─────────────┘
                          ▼
              ┌─────────────────────────┐
              │ Agent 2: Threat Intel    │
              │ Web Search API — finds & │
              │ verifies the disruption  │
              └───────────┬─────────────┘
                          ▼
              ┌─────────────────────────┐
              │ Agent 3: Incident        │
              │ Planner — proposes:      │
              │ Reroute / Wait / Storage │
              │ / Transfer               │
              └───────────┬─────────────┘
                          ▼
              ┌─────────────────────────┐
              │ Agent 4: Risk Critic     │
              │ Checks shelf-life, cost, │
              │ ETA, safety              │
              └──────┬───────────┬──────┘
                     ▼           ▼
                 ACCEPT       REJECT
                     │           │
                     ▼           └──► back to Agent 3 (re-plan)
              ┌─────────────┐
              │ Action Plan │
              └──────┬──────┘
                     ▼
              ┌─────────────┐
              │   Human      │
              │   Approval   │
              └─────────────┘
```

**Why this counts as agentic, not just data analysis:** each agent has a distinct responsibility, produces evidence the next agent consumes, and — critically — the Risk Critic can *reject* the Planner's output and force a genuine re-planning cycle. The system doesn't just present one computed answer; it can disagree with itself and revise before a human ever sees the final recommendation.

---

## Tech Stack

| Layer | Tool | Notes |
|---|---|---|
| UI / Dashboard | Streamlit | Live agent reasoning stream + incident dashboard |
| Data processing | Python + Pandas | Fleet, cargo, and warehouse mock data |
| Agent reasoning | LLM API (Gemini / OpenAI) | Powers Threat Intel, Planner, and Critic agents |
| Disruption detection | Web Search API | Verifies real-world disruption events |
| Routing | OSRM (primary), Google Maps (optional upgrade) | OSRM used for MVP to avoid API-key/billing setup risk before the deadline |
| Fleet/cargo/warehouse data | CSV / JSON | Mock dataset, not a live GPS feed |
| Constraint checks | Python rule engine | Shelf-life, cost, and safety validation logic |

> **Scoping note (stated up front, not discovered by a reviewer):** For the Round 1 prototype, live GPS is simulated via mock data, and routing uses OSRM rather than Google Maps to remove an external billing/key dependency from the critical path. If the Web Search API integration proves unreliable within the build window, disruption events fall back to a small pre-authored dataset of realistic (non-live) incident reports, clearly labeled as such in the code. This keeps every claim in the demo honestly backed by what's actually running.

---

## Setup Instructions

<!-- TODO: fill in once app.py / requirements.txt exist -->

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

## Roadmap (post–Round 1)

- Migrate agent orchestration from a sequential Python pipeline to CrewAI for genuine autonomous multi-agent coordination.
- Optional Google Maps integration for production-grade routing.
- Live GPS feed integration in place of mock fleet data.