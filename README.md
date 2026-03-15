# AeroMind — AI Race Intelligence Platform for F1 2026

Demo Link: https://aeromind-frontend-1018926496655.us-central1.run.app/

> **Six ADK agents. Real telemetry. Live voice. Graph intelligence.**
> The pit wall — reimagined.

---

## What is AeroMind?

AeroMind is a fully deployed, real-time AI race intelligence system built for Formula One 2026 regulations. It ingests live telemetry from the OpenF1 API, writes every car position and battle into a Memgraph knowledge graph, runs a six-agent Google ADK pit wall to analyse every overtake opportunity, and delivers spoken commentary through ARIA — an AI race commentator powered by Gemini Live.

This is not a simulation. This is not a prototype. It is running on Google Cloud Run right now.

---

## Architecture

```
OpenF1 Telemetry
      │
      ▼
Memgraph Live Graph ──► Race Loop (Edge Detector)
      │                        │
      │              ATTACKING / OVERTAKE_MODE_ELIGIBLE edges
      │                        │
      │                        ▼
      │            ┌─── PitWall SequentialAgent ───┐
      │            │                               │
      │            │   SpecialistTeam (Parallel)   │
      │            │   ┌──────┬──────┬──────┬────┐ │
      │            │   │ Aero │Energy│ Tyre │Anom│ │
      │            │   └──────┴──────┴──────┴────┘ │
      │            │            │                  │
      │            │       Strategist               │
      │            │     (+ Monte Carlo)            │
      │            │            │                  │
      │            │       Chronicler               │
      │            └───────────────────────────────┘
      │                        │
      ◄── Decision node written back to Memgraph
      │
      ▼
ARIA WebSocket Bridge
      │
      ├── Instant text commentary → all clients
      ├── Gemini TTS audio → audio-enabled clients
      └── Gemini Live API → bidirectional voice session
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent Framework | Google ADK — `ParallelAgent`, `SequentialAgent`, `LlmAgent` |
| AI Models | Gemini 2.5 Pro (strategy, chronicle), Gemini 2.5 Flash (specialists) |
| Voice | Gemini Live API — bidirectional, interruptible voice |
| TTS | Gemini TTS — PCM audio streamed over WebSocket |
| Graph Database | Memgraph — real-time knowledge graph via Bolt/Cypher |
| Telemetry | OpenF1 API — live F1 session data |
| Simulation | Monte Carlo — 1000 simulations per battle event |
| Backend | FastAPI + Uvicorn + WebSockets |
| Frontend | Three.js (background), D3.js (graph), GSAP (animations) |
| Cloud | Google Cloud Run, GCS, Firestore, Vertex AI |
| Infrastructure | Docker, Cloud Build |

---

## ADK Pit Wall Agents

### SpecialistTeam — ParallelAgent
All four specialists run simultaneously on every battle event.

| Agent | Model | Role | Output Key |
|---|---|---|---|
| **AeroAgent** | gemini-2.5-flash | Slipstream, active aero, Overtake Override eligibility | `aero_recommendation` |
| **EnergyAgent** | gemini-2.5-flash | State of Charge management, deployment windows | `energy_recommendation` |
| **TireAgent** | gemini-2.5-flash | Degradation, stint strategy, grip deltas | `tire_recommendation` |
| **AnomalyAgent** | gemini-2.5-flash | Mechanical anomaly detection, safety flags | `anomaly_report` |

### Strategist — LlmAgent (gemini-2.5-pro)
Synthesises all four specialist outputs. Calls `run_race_simulation()` (Monte Carlo) before every decision. Applies the **TRIPLE_ALIGN** and **ANOMALY_OVERRIDE** principles.

### Chronicler — LlmAgent (gemini-2.5-pro)
Writes the race narrative in the style of a live journalist. Output written back to Memgraph as a Decision node.

---

## ARIA — AI Race Commentator

ARIA is a live race commentator powered by Gemini. She operates on two channels:

**Commentary Feed (`/aria` WebSocket)**
- Proactive commentary fires on every race event detected in the graph
- Phase 1: instant template text — zero latency, no API call
- Phase 2: Gemini TTS audio — streamed as PCM to audio-enabled clients
- Fans can send text questions and receive Gemini-generated answers

**Live Voice (`/aria/voice` WebSocket)**
- Full Gemini Live API bidirectional voice session
- Browser mic → 16kHz PCM → Gemini Live → ARIA speaks back
- Fully interruptible — native Gemini Live feature
- Multimodal: ARIA can analyse a screenshot of the live circuit

---

## Memgraph Schema

```cypher
-- Car node (live telemetry, updated every 5s)
(:Car {driver_number, driver_name, team, battery_soc, speed, x, y, track_pos})

-- Decision node (written by ADK Chronicler after each analysis)
(:Decision {id, text, agent, attacker, defender, timestamp})

-- Battle edges (recomputed from scratch every tick)
(:Car)-[:ATTACKING]->(:Car)              -- gap < 20m
(:Car)-[:OVERTAKE_MODE_ELIGIBLE]->(:Car) -- gap < 12m AND SoC > 35%

-- AI decision edges
(:Decision)-[:DECIDED_ON]->(:Car)
```

---

## F1 2026 Regulations

AeroMind is built specifically for the 2026 technical regulations:

- **DRS abolished** — replaced by Overtake Override Mode
- **Overtake Override Mode** — activates at gap < 1s + SoC > 35%, awards +0.5MJ
- **Active Aero** — automatic Straight Mode / Corner Mode switching
- **Boost Button** — manual 350kW deployment
- **Battery SoC** — below 31% costs 0.3–0.4s/lap in acceleration sectors
- Cars are 200mm shorter, 100mm narrower, 30kg lighter

---

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker
- Memgraph running on `localhost:7687` (or Memgraph Cloud)
- Google Cloud project with Vertex AI enabled
- Gemini API key

### Local Setup

```bash
# Clone and enter project
cd aeromind

# Backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Copy and fill in your credentials
cp .env.example .env

# Start Memgraph (Docker)
docker run -d -p 7687:7687 -p 3000:3000 memgraph/memgraph-platform

# Run backend
uvicorn backend.server:app --reload --port 8080

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

### Environment Variables

```env
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=./credentials.json
VERTEX_AI_LOCATION=us-central1

GEMINI_AGENT_MODEL=gemini-2.5-flash
GEMINI_STRATEGIST_MODEL=gemini-2.5-pro
GEMINI_LIVE_MODEL=gemini-2.5-flash-native-audio

MEMGRAPH_HOST=localhost
MEMGRAPH_PORT=7687

GCS_BUCKET_NAME=aeromind-f1-data
OPENF1_SESSION_KEY=latest
MONTE_CARLO_SIMULATIONS=1000
```

---

## Deploy to Google Cloud Run

```bash
# Build and deploy
gcloud builds submit --config deploy/cloudbuild.yaml

gcloud run deploy aeromind \
  --image gcr.io/PROJECT_ID/aeromind:latest \
  --region us-central1 \
  --memory 2Gi \
  --cpu 2 \
  --set-env-vars MEMGRAPH_HOST=your-memgraph-host

# View live logs
gcloud run services logs tail aeromind --region us-central1
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | System status — Memgraph, OpenF1, models |
| GET | `/api/snapshot` | Live car positions + battle edges |
| GET | `/api/graph` | Full D3 graph — cars + decision nodes + edges |
| GET | `/api/chronicle` | Last 50 race events |
| GET | `/api/aria/situation` | Gemini race situation brief (cached 25s) |
| POST | `/api/aria/analyse-frame` | Multimodal circuit frame analysis |
| POST | `/api/session` | Hot-swap race session |
| POST | `/api/heartbeat` | Tab activity signal — gates Gemini spend |
| POST | `/api/demo/trigger` | Fire a manual test event |
| WS | `/aria` | ARIA commentary feed + text Q&A |
| WS | `/aria/voice` | Gemini Live bidirectional voice |

---

## Cost Management

AeroMind gates all Gemini API calls behind two conditions:
1. **Heartbeat** — frontend sends `POST /api/heartbeat` every 20s while a tab is open. No heartbeat for 90s = zero Gemini calls.
2. **Audio opt-in** — TTS audio only generated for clients who click ENABLE AUDIO. No listeners = no TTS spend.
3. **OpenF1 lock detection** — if the OpenF1 API returns 401 (live race in progress), ADK analysis and ARIA commentary are paused automatically.

---

## Project Structure

```
aeromind/
├── backend/
│   ├── agents/
│   │   ├── pit_wall.py          # SequentialAgent — entry point
│   │   ├── strategist.py        # Chief Strategist (gemini-2.5-pro)
│   │   ├── aero_agent.py        # Aerodynamics specialist
│   │   ├── energy_agent.py      # Energy/SoC specialist
│   │   ├── tire_agent.py        # Tyre degradation specialist
│   │   ├── anomaly_agent.py     # Anomaly detection
│   │   ├── chronicler_agent.py  # Race journalist
│   │   └── adk_tools.py         # Shared ADK tool functions
│   ├── aria/
│   │   ├── aria_live_agent.py   # ARIA core — TTS, vision, Q&A
│   │   └── aria_websocket.py    # WebSocket bridge
│   ├── graph/
│   │   ├── live_graph.py        # Memgraph real-time operations
│   │   ├── knowledge_graph.py   # Historical knowledge schema
│   │   └── graphrag.py          # Graph-augmented retrieval
│   ├── ingestion/
│   │   └── openf1_stream.py     # OpenF1 telemetry ingestion
│   ├── models/
│   │   ├── energy_model.py      # Battery SoC model
│   │   └── overtake_model.py    # ML overtake probability
│   ├── simulation/
│   │   └── monte_carlo.py       # 1000-run race simulator
│   └── server.py                # FastAPI app + race loop
├── frontend/
│   └── src/
│       ├── index.js             # Main orchestrator
│       ├── track/F1Track.js     # Live circuit visualisation
│       ├── panels/
│       │   ├── AskAria.js       # ARIA commentary panel
│       │   ├── TelemetryPanel.js
│       │   ├── GraphPanel.js    # D3 Memgraph visualisation
│       │   └── ChroniclePanel.js
│       └── index.css
├── deploy/
│   ├── Dockerfile
│   └── service.yaml
└── .env.example
```

---

## Built With

- [Google ADK](https://google.github.io/adk-docs/) — Agent Development Kit
- [Gemini API](https://ai.google.dev/) — Gemini 2.5 Pro / Flash / Live
- [Memgraph](https://memgraph.com/) — Real-time graph database
- [OpenF1](https://openf1.org/) — Free F1 telemetry API
- [FastAPI](https://fastapi.tiangolo.com/) — Backend framework
- [Three.js](https://threejs.org/) — 3D background renderer
- [D3.js](https://d3js.org/) — Graph visualisation

Built an AI Pit Wall for F1 2026  Live Agents | #GeminiLiveAgentChallenge

---

*Formula One changes in 2026. The pit wall changes today.*
