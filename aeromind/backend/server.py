import os
import asyncio
import logging
import traceback
import sys

# Explicitly read and apply .env values — overrides stale Docker container env vars.
# docker restart does NOT re-read env_file; this ensures .env always wins.
try:
    from dotenv import dotenv_values as _dv
    for _k, _v in _dv("/app/.env").items():
        if _v is not None:
            os.environ[_k] = _v
except Exception:
    pass

from fastapi import FastAPI, WebSocket
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from backend.cloud.gcs_client import GCSClient
from backend.cloud.firestore_client import FirestoreClient
from backend.graph.live_graph import LiveGraph
from backend.graph.knowledge_graph import KnowledgeGraph
from backend.graph.graphrag import GraphRAG
from backend.simulation.monte_carlo import MonteCarloSimulator
from backend.models.overtake_model import OvertakeModel
from backend.models.energy_model import EnergyModel
from backend.imaging.race_visualizer import RaceVisualizer
from backend.aria.aria_live_agent import AriaLiveAgent
from backend.aria.aria_websocket import ARIAWebSocketBridge
from backend.ingestion.openf1_stream import OpenF1Streamer

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

import time as _time

# ---------------------------------------------------------------------------
# Active-user tracking — gates ALL Gemini API calls
# Frontend sends POST /api/heartbeat every 20s while a tab is open.
# If no heartbeat for 90s AND no WebSocket clients → skip all Gemini calls.
# ---------------------------------------------------------------------------
_last_heartbeat: float = 0.0
_HEARTBEAT_TTL  = 90.0   # seconds before we consider "no users"

def _has_active_users() -> bool:
    """Return True only if a browser tab sent a heartbeat within the last 90 seconds.
    WebSocket connections are NOT counted — the ARIA panel connects its WS on render
    before the user clicks LAUNCH, which would falsely indicate an active user."""
    return (_time.time() - _last_heartbeat) < _HEARTBEAT_TTL


# ---------------------------------------------------------------------------
# Background task: Race Loop
# ---------------------------------------------------------------------------

async def _run_adk_analysis(attacker_number: int, defender_number: int,
                             gap_meters: float, attacker_soc: float):
    """
    Run ADK pit-wall agent team (4 specialists → strategist → chronicler).
    Decision is written BACK into Memgraph as a Decision node so that:
      - The frontend graph panel shows the full AI reasoning chain
      - ARIA commentary references the actual graph decision
      - All intelligence flows through Memgraph (single source of truth)
    """
    try:
        from backend.agents.pit_wall import analyze_battle
        context = {
            "attacker_number": attacker_number,
            "defender_number": defender_number,
            "gap_meters":      gap_meters,
            "attacker_soc":    attacker_soc,
            "overtake_mode_eligible": True,
        }
        logger.info(f"ADK: analyzing Car {attacker_number} vs Car {defender_number}")
        result   = await analyze_battle(context)
        decision = result.get("final_decision", "") or result.get("chronicle_entry", "")

        if decision:
            # Write ADK decision BACK into Memgraph — this is what the graph panel shows
            if hasattr(app.state, "live_graph"):
                app.state.live_graph.write_decision_node(
                    attacker_number=attacker_number,
                    defender_number=defender_number,
                    decision_text=decision,
                    agent="ADK-PitWall",
                )

            # Also update ARIA context
            if hasattr(app.state, "aria_agent"):
                app.state.aria_agent.live_context["latest_decision"] = decision[:300]

            logger.info(f"ADK → Memgraph decision: {decision[:120]}")
        else:
            logger.warning("ADK returned no decision")

    except Exception as e:
        logger.warning(f"ADK analysis skipped: {repr(e)}")


async def race_loop():
    """
    Detect battle edges and push ARIA commentary.
    Re-fires commentary when edges disappear and reappear (cars separate then close again).
    Rate-limited to 1 ARIA broadcast per 15s to avoid quota burn.
    """
    logger.info("Race loop started — waiting for streamer to initialise graph")
    await asyncio.sleep(2)   # give streamer time to clear stale nodes and seed fresh data
    logger.info("Race loop active")
    active_edges: set[str] = set()   # edges currently in the graph
    event_counter = 1
    last_broadcast_time = 0.0
    last_state_commentary = 0.0
    last_adk_time = 0.0              # rate-limit ADK: at most 1 analysis per 90s
    try:
        while True:
            if hasattr(app.state, "live_graph"):
                snapshot = app.state.live_graph.get_full_snapshot()

                # Check if OpenF1 API is locked (live race in progress — don't burn Gemini quota)
                streamer_ref = getattr(app.state, "streamer", None)
                api_locked   = getattr(streamer_ref, "_401_logged", False)

                # Keep ARIA context current
                if hasattr(app.state, "aria_agent"):
                    latest = (app.state.chronicle_entries[-1]["text"]
                              if app.state.chronicle_entries else "")
                    app.state.aria_agent.update_context(snapshot, [], {}, latest)

                current_edges = {
                    f"{e['from']}-{e['to']}-{e['type']}"
                    for e in snapshot.get("edges", [])
                }

                # NEW edges (just appeared)
                new_edges = current_edges - active_edges
                for edge_id in new_edges:
                    parts = edge_id.split("-")
                    from_drv, to_drv, e_type = parts[0], parts[1], parts[2]

                    # Look up driver names from snapshot cars
                    cars_by_num = {str(c.get("driver_number")): c for c in snapshot.get("cars", [])}
                    attacker = cars_by_num.get(from_drv, {})
                    defender = cars_by_num.get(to_drv, {})
                    a_name = attacker.get("driver_name", f"Car {from_drv}")
                    d_name = defender.get("driver_name", f"Car {to_drv}")
                    a_soc  = round(attacker.get("battery_soc", 0) * 100)

                    if e_type == "ATTACKING":
                        msg = (f"{a_name} (Car {from_drv}) has closed within ATTACKING distance "
                               f"of {d_name} (Car {to_drv})! Gap is under 20 metres.")
                    elif e_type == "OVERTAKE_MODE_ELIGIBLE":
                        msg = (f"CRITICAL: {a_name} (Car {from_drv}) is in Overtake Override Mode range "
                               f"of {d_name} (Car {to_drv})! SoC {a_soc}% — energy deployment is live.")
                        # ADK analysis: skip when API locked (saves Gemini quota)
                        # rate-limited to 1 per 90s, only when clients connected
                        if not api_locked and _has_active_users():
                            now_adk = asyncio.get_event_loop().time()
                            if (now_adk - last_adk_time) > 90:
                                last_adk_time = now_adk
                                asyncio.create_task(_run_adk_analysis(
                                    attacker_number=int(from_drv),
                                    defender_number=int(to_drv),
                                    gap_meters=abs(attacker.get("y", 0) - defender.get("y", 100)),
                                    attacker_soc=attacker.get("battery_soc", 0.5),
                                ))
                    else:
                        msg = f"{a_name} → {d_name}: {e_type}"

                    entry = {"id": event_counter, "text": msg,
                             "timestamp": asyncio.get_event_loop().time(), "imageUrl": ""}
                    app.state.chronicle_entries.append(entry)
                    logger.info(f"Chronicle #{event_counter}: {msg}")
                    event_counter += 1

                    # Broadcast ARIA commentary (rate-limited: 1 per 15s, skip if API locked or no users)
                    now = asyncio.get_event_loop().time()
                    if not api_locked and _has_active_users() and hasattr(app.state, "aria_bridge") and (now - last_broadcast_time) > 15:
                        last_broadcast_time = now
                        asyncio.create_task(app.state.aria_bridge.broadcast_event(msg))

                # CLEARED edges (cars separated) — remove so they can re-fire later
                cleared = active_edges - current_edges
                if cleared:
                    logger.info(f"Edges cleared (cars separated): {cleared}")

                active_edges = current_edges

                # Periodic state commentary every 30s (skip if API locked or no active users)
                now2 = asyncio.get_event_loop().time()
                if not api_locked and _has_active_users() and hasattr(app.state, "aria_bridge") and (now2 - last_state_commentary) > 30:
                    last_state_commentary = now2
                    cars = snapshot.get("cars", [])
                    edges = snapshot.get("edges", [])
                    if cars:
                        def _pos(c): return float(c.get("track_pos") or c.get("y") or 0)
                        sorted_cars = sorted(cars, key=lambda c: -_pos(c))
                        leader = sorted_cars[0]
                        p2     = sorted_cars[1] if len(sorted_cars) > 1 else None
                        gap_m  = round(_pos(leader) - (_pos(p2) if p2 else 0), 1)
                        soc_l  = round(leader.get("battery_soc", 0) * 100)
                        soc_p2 = round(p2.get("battery_soc", 0) * 100) if p2 else 0
                        if edges:
                            state_msg = (
                                f"LIVE: {leader.get('driver_name','P1')} leads by {gap_m}m "
                                f"(SoC {soc_l}%) — {len(edges)} active battle edge(s) in the graph. "
                                f"P2 {p2.get('driver_name','P2') if p2 else ''} SoC {soc_p2}%."
                            )
                        else:
                            state_msg = (
                                f"SITUATION: {leader.get('driver_name','P1')} leads "
                                f"(SoC {soc_l}%, {leader.get('speed',0):.0f} km/h). "
                                f"Gap to P2 is {gap_m} metres — no battles active."
                            )
                        asyncio.create_task(app.state.aria_bridge.broadcast_event(state_msg))

                if len(app.state.chronicle_entries) > 50:
                    app.state.chronicle_entries = app.state.chronicle_entries[-50:]

            await asyncio.sleep(5)

    except asyncio.CancelledError:
        logger.info("Race loop stopped")
    except Exception as e:
        logger.error(f"Race loop error: {repr(e)}")
        traceback.print_exc()


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    sys.stderr.write("!!! DEBUG: AeroMind lifespan starting !!!\n")
    sys.stderr.flush()
    logger.info("Initializing AeroMind V5 Backend...")

    stream_task = None
    loop_task = None
    try:
        app.state.gcs = GCSClient(bucket_name=os.getenv("GCS_BUCKET_NAME", "aeromind-f1-data"))
        app.state.firestore = FirestoreClient()

        app.state.live_graph = LiveGraph()
        app.state.knowledge_graph = KnowledgeGraph()
        app.state.knowledge_graph.setup_schema()

        app.state.graphrag = GraphRAG(
            live_graph=app.state.live_graph,
            knowledge_graph=app.state.knowledge_graph,
        )

        app.state.aria_agent = AriaLiveAgent()
        app.state.aria_agent.set_graph(app.state.live_graph)  # Cypher graph queries for context
        app.state.aria_bridge = ARIAWebSocketBridge(app.state.aria_agent)

        mc_sims = int(os.getenv("MONTE_CARLO_SIMULATIONS", "1000"))
        app.state.monte_carlo = MonteCarloSimulator(n_simulations=mc_sims)
        app.state.overtake_model = OvertakeModel()
        app.state.energy_model = EnergyModel()
        app.state.race_visualizer = RaceVisualizer()

        session_key = os.getenv("OPENF1_SESSION_KEY", "latest")
        app.state.streamer = OpenF1Streamer(
            session_key=session_key,
            live_graph=app.state.live_graph,
        )
        app.state.chronicle_entries = []

        stream_task = asyncio.create_task(app.state.streamer.run())
        loop_task = asyncio.create_task(race_loop())

        logger.info(
            f"Models — Agent: {os.getenv('GEMINI_AGENT_MODEL')} | "
            f"Live: {os.getenv('GEMINI_LIVE_MODEL')}"
        )
        logger.info("Backend services initialized successfully.")
        yield

    finally:
        logger.info("Shutting down backend services...")
        if stream_task:
            stream_task.cancel()
        if loop_task:
            loop_task.cancel()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="AeroMind 2026 Live", version="5.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    mg_ok = False
    if hasattr(app.state, "live_graph"):
        mg_ok = app.state.live_graph.health_check()
    streamer = getattr(app.state, "streamer", None)
    openf1_locked = getattr(streamer, "_401_logged", False) if streamer else False
    return {
        "status": "ok",
        "regulations": "2026",
        "memgraph_connected": mg_ok,
        "openf1_locked": openf1_locked,
        "openf1_lock_msg": (
            "Live F1 session in progress — OpenF1 API locked for free users. "
            "Running 2026 AUS GP simulation. Real data returns when the session ends."
        ) if openf1_locked else "",
        "gcs_connected": hasattr(app.state, "gcs"),
        "firestore_connected": hasattr(app.state, "firestore"),
        "models_loaded": hasattr(app.state, "monte_carlo"),
        "monte_carlo_n": app.state.monte_carlo.n_simulations if hasattr(app.state, "monte_carlo") else 0,
        "google_project": os.getenv("GOOGLE_CLOUD_PROJECT", "UNKNOWN"),
    }


@app.get("/api/snapshot")
async def get_snapshot():
    snap = app.state.live_graph.get_full_snapshot()
    streamer = getattr(app.state, "streamer", None)
    # is_2026_regs: True = SoC/Overtake Override (2026+), False = DRS system (pre-2026)
    # demo always uses 2026 regs; real sessions detected from session year
    snap["is_2026_regs"] = getattr(streamer, "is_2026_regs", True)
    return snap


@app.get("/api/session-info")
async def get_session_info():
    """Returns what session the system is currently monitoring."""
    sk = os.getenv("OPENF1_SESSION_KEY", "latest")
    streamer = getattr(app.state, "streamer", None)
    resolved = getattr(streamer, "_resolved_key", sk) if streamer else sk
    demo     = getattr(streamer, "demo_mode", sk == "demo") if streamer else (sk == "demo")
    cars     = app.state.live_graph.get_all_cars() if hasattr(app.state, "live_graph") else []
    return {
        "config_key":   sk,
        "resolved_key": resolved,
        "demo_mode":    demo,
        "car_count":    len(cars),
        "instructions": (
            "Set OPENF1_SESSION_KEY=latest in .env to auto-follow any live race. "
            "Set to a specific session number (e.g. 9693) to replay a past race. "
            "Set to 'demo' for the built-in 10-car 2026 simulation."
        ),
    }


@app.get("/api/drivers")
async def get_drivers():
    cars = app.state.live_graph.get_all_cars()
    return {"drivers": [c.get("driver_name", str(c.get("driver_number"))) for c in cars]}


@app.get("/api/chronicle")
async def get_chronicle():
    return {
        "entries": app.state.chronicle_entries,
        "count": len(app.state.chronicle_entries),
    }


@app.get("/api/graph")
async def get_graph():
    """
    Return full Memgraph graph for D3 visualization:
      - Car nodes (live telemetry)
      - Decision nodes (ADK pit-wall results written back to Memgraph)
      - ATTACKING / OVERTAKE_MODE_ELIGIBLE / DECIDED_ON edges
    This makes Memgraph the single source of truth for all AI decisions.
    """
    return app.state.live_graph.get_full_graph()


@app.get("/api/simulation")
async def get_simulation():
    return {"simulation": {}}


class SessionChange(BaseModel):
    session_key: str  # numeric session id (e.g. "9693") or "demo" or "latest"

@app.post("/api/session")
async def change_session(payload: SessionChange):
    """
    Hot-swap the session without restarting the container.
    Frontend session picker calls this when the user types a session key.
    """
    key = payload.session_key.strip()
    if not key:
        return {"status": "error", "detail": "empty session key"}

    streamer = getattr(app.state, "streamer", None)
    if not streamer:
        return {"status": "error", "detail": "streamer not ready"}

    # Reset streamer state for the new session
    streamer.session_key    = key
    streamer.demo_mode      = key.lower() == "demo"
    streamer._resolved_key  = key
    streamer._demo_seeded   = False
    streamer._driver_cache  = {}
    streamer._session_start = None
    streamer._replay_cursor = None
    # is_2026_regs re-detected from session year on next fetch; demo always 2026
    streamer.is_2026_regs   = True if key.lower() == "demo" else True  # will update on fetch

    # Clear chronicle so the UI starts fresh
    app.state.chronicle_entries = []

    if streamer.demo_mode:
        # For demo: clear stale nodes then seed fresh demo cars immediately
        try:
            app.state.live_graph._run("MATCH (c:Car) DETACH DELETE c")
        except Exception:
            pass
        streamer._seed_demo_cars()
        return {"status": "ok", "session_key": key, "mode": "demo"}

    # For real sessions: do NOT clear the graph yet — keep existing nodes visible
    # until OpenF1 returns real data (streamer poll loop will overwrite them).
    # This prevents a blank screen when OpenF1 is slow or temporarily down.
    return {"status": "ok", "session_key": key, "mode": "live",
            "note": "Switching session — existing data visible until OpenF1 responds"}


@app.post("/api/heartbeat")
async def heartbeat():
    """
    Frontend pings this every 20s while a tab is open and visible.
    Backend uses this to gate ALL Gemini API calls — zero users = zero spend.
    """
    global _last_heartbeat
    _last_heartbeat = _time.time()
    return {"ok": True, "active": True}


# Cache for situation brief — avoids hammering Gemini when multiple tabs are open
_situation_cache: dict = {"text": "", "ts": 0.0}
_SITUATION_TTL = 25.0  # seconds between real Gemini calls

@app.get("/api/aria/situation")
async def get_race_situation():
    """
    Gemini-generated 3-line race situation brief.
    Only calls Gemini when: active user present + cache expired + API not locked.
    Returns cached or template response otherwise — costs nothing.
    """
    global _situation_cache
    streamer_ref = getattr(app.state, "streamer", None)
    api_locked   = getattr(streamer_ref, "_401_logged", False)

    if not hasattr(app.state, "aria_agent"):
        return {"situation": "RACE IN PROGRESS", "lines": ["RACE IN PROGRESS", "", ""]}

    # No active users → return template (free)
    if not _has_active_users():
        text = app.state.aria_agent._situation_fallback()
        return {"situation": text, "lines": text.split("\n")}

    # API locked → template (free)
    if api_locked:
        text = app.state.aria_agent._situation_fallback()
        return {"situation": text, "lines": text.split("\n")}

    # Cache still fresh → return without a Gemini call
    if _time.time() - _situation_cache["ts"] < _SITUATION_TTL and _situation_cache["text"]:
        text = _situation_cache["text"]
        return {"situation": text, "lines": text.split("\n")}

    # Active user + cache stale → call Gemini
    text = await app.state.aria_agent.generate_race_image_prompt()
    _situation_cache = {"text": text, "ts": _time.time()}
    return {"situation": text, "lines": text.split("\n")}


class FrameAnalysisRequest(BaseModel):
    image: str  # base64 PNG of the circuit SVG screenshot

@app.post("/api/aria/analyse-frame")
async def analyse_frame(body: FrameAnalysisRequest):
    """
    Multimodal: receive a base64 PNG of the live circuit SVG,
    send it to Gemini Vision for ARIA visual commentary + TTS audio.
    Demonstrates image → Gemini → spoken ARIA for hackathon judges.
    """
    if not hasattr(app.state, "aria_agent"):
        return {"commentary": "ARIA not initialised", "audio_b64": "", "mime_type": ""}
    text, audio_b64, mime_type = await app.state.aria_agent.analyse_frame(body.image)
    return {"commentary": text, "audio_b64": audio_b64, "mime_type": mime_type}


@app.post("/api/demo")
async def start_demo(payload: dict = None):
    return {"status": "demo running", "session_key": os.getenv("OPENF1_SESSION_KEY")}


class DemoTrigger(BaseModel):
    event: str = "CRITICAL: Leclerc (Car 16) has activated Overtake Override Mode on Verstappen (Car 1). Gap 9.4m — SoC 72%."

@app.post("/api/demo/trigger")
async def trigger_demo_event(payload: DemoTrigger = None):
    """Manually fire a test race event → ARIA generates commentary immediately."""
    msg = payload.event if payload else "CRITICAL: Leclerc (Car 16) has activated Overtake Override Mode on Verstappen (Car 1). Gap 9.4m — SoC 72%."
    entry = {
        "id": len(app.state.chronicle_entries) + 1,
        "text": msg,
        "timestamp": asyncio.get_event_loop().time(),
        "imageUrl": "",
    }
    app.state.chronicle_entries.append(entry)
    asyncio.create_task(app.state.aria_bridge.broadcast_event(msg))
    return {"status": "triggered", "event": msg}


# ---------------------------------------------------------------------------
# WebSocket endpoints
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_broadcaster(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({
        "type": "connected",
        "features": ["live_telemetry", "aria_text_chat"],
    })
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"echo: {data}")
    except Exception:
        pass


@app.websocket("/aria")
async def aria_endpoint(websocket: WebSocket):
    """
    ARIA commentary feed.
    - Proactive TTS voice commentary pushed when race events detected
    - Fan can also send text questions: {"type":"question","text":"..."}
    """
    await app.state.aria_bridge.handle_fan_connection(websocket)


@app.websocket("/aria/voice")
async def aria_voice_endpoint(websocket: WebSocket):
    """
    Gemini Live API bidirectional voice session.
    Fan sends binary PCM audio (16kHz, 16-bit, mono) → ARIA responds in voice.
    Fully interruptible — Gemini Live API native feature.
    """
    await app.state.aria_bridge.handle_voice_session(websocket)


# ---------------------------------------------------------------------------
# Global error handler
# ---------------------------------------------------------------------------

from fastapi.responses import JSONResponse


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
    )
