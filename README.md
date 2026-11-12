# TravelMind — 30-day MVP starter

A runnable starter for a small multi-agent travel-planning prototype:
- React + Vite frontend
- FastAPI backend
- Orchestrator coordinating Destination, Itinerary, and Validation agents
- Local curated destination data; no API keys required for the first run
- Deterministic budget validation; estimates are explicitly labeled

## Requirements
- Python 3.11+
- Node.js 20+ (includes npm)
- VS Code

## 1. Start the backend (PowerShell)
Open a terminal in this folder:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

If PowerShell blocks activation, run this once in that terminal:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Backend API: http://127.0.0.1:8000  
Interactive API docs: http://127.0.0.1:8000/docs

## 2. Start the frontend (a second terminal)
```powershell
cd frontend
npm install
npm run dev
```
Open the URL printed by Vite (normally http://localhost:5173).

## What works now
- Submit departure city, budget, duration, interests, and optional destination
- Select a destination from a small local dataset if none is specified
- Build a sample day-by-day itinerary
- Calculate estimated costs and flag a budget overrun
- Show agent activity and validation results

## Important scope limits
This is a first runnable vertical slice, not a production travel service. Destination/transport costs are illustrative estimates from local sample data, not live quotes. It does not book travel. Map links are search links. Social-media insights, live weather, and live train prices are not enabled yet.

## 30-day build plan
- Days 1–3: run starter, define API contracts, add tests
- Days 4–8: improve destination ranking and curated place dataset
- Days 9–13: map integration and route/time estimates
- Days 14–18: weather integration and adaptive replanning
- Days 19–23: social-data ingestion using permitted sources; clear provenance
- Days 24–27: evaluation against a baseline planner
- Days 28–30: bug fixing, demo, report and presentation

## Team split
1. Backend/agent workflow: orchestrator, agent roles, validation and tests
2. Frontend/UX: form, itinerary cards, responsive layout
3. Data/integrations/evaluation: destination dataset, maps/weather research, evaluation cases

## Next development rule
Keep a working main branch. Each person works on a separate branch and opens a pull request. Agree on request/response schemas before parallel work.


## Sasha: Destination, Context and provider components

The existing Chengdu API/planner remains available. Richer attraction candidates, weather context, guarded OpenRouter intent extraction and provider adapters are documented in [Sasha integration guide](docs/SASHA_INTEGRATION.md). Run `python -B -m scripts.test_offline` from the repository root for all current team tests and Sasha's offline regressions. Use `DestinationAgent.run_candidates(...)` for the richer contract or `TravelMindOrchestrator.collect_agent_results(trip)` for additive offline collection. No live calls occur by default. The richer path is not yet wired into the existing HTTP itinerary endpoint.
