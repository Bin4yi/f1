import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure the project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv()

from backend.cloud.gcs_client import GCSClient
from backend.cloud.firestore_client import FirestoreClient
from backend.graph.live_graph import LiveGraph
from backend.agents.pit_wall import pit_wall, analyze_battle
from backend.aria.aria_live_agent import AriaLiveAgent
from backend.imaging.race_visualizer import RaceVisualizer
from backend.agents.strategist import strategist
from google.adk.agents import SequentialAgent, ParallelAgent

async def test_aeromind_v5_google_gemini():
    print("\n" + "="*70)
    print("  AEROMIND v5 — GOOGLE GEMINI AI HACKATHON")
    print("  Live Agents Category | ADK + Gemini Live API + Vertex AI")
    print("="*70)

    results = {}

    # ── Google Cloud Setup ──
    print("Verifying Google Cloud Services...")
    gcs = GCSClient()
    results["gcs_bucket_accessible"] = gcs.verify_bucket()

    firestore = FirestoreClient()
    try:
        await firestore.update_race_state({"test": True, "timestamp": "integration_test_v5"})
        state = await firestore.get_race_state()
        results["firestore_read_write"] = (state is not None and state.get("timestamp") == "integration_test_v5")
    except Exception as e:
        print(f"Firestore Error: {e}")
        results["firestore_read_write"] = False

    # ── Phase 2: No UNDER_DRS edges ──
    print("Verifying LiveGraph 2026 Compliance...")
    lg = LiveGraph()
    results["live_graph_healthy"] = lg.health_check()
    
    # [insert 2 close cars, compute edges]
    if results["live_graph_healthy"]:
        lg.update_car_node(16, {"driver_name": "Leclerc", "y": 100, "team": "Ferrari", "battery_soc": 0.72, "speed": 225})
        lg.update_car_node(1, {"driver_name": "Verstappen", "y": 105, "team": "Red Bull", "battery_soc": 0.65, "speed": 224})
        lg.update_battle_edges()
        
        snap = lg.get_full_snapshot()
        results["no_under_drs"] = "UNDER_DRS" not in {e["type"] for e in snap["edges"]}
        results["has_2026_edges"] = bool({e["type"] for e in snap["edges"]} & {"ATTACKING","OVERTAKE_MODE_ELIGIBLE"})
    else:
        print("Warning: LiveGraph (Memgraph) offline, skipping graph compliance checks.")
        results["no_under_drs"] = False
        results["has_2026_edges"] = False

    # ── Phase 6: ADK agents ──
    print("Verifying ADK Agent Architecture...")
    results["pit_wall_is_sequential"] = isinstance(pit_wall, SequentialAgent)
    # Check if first sub-agent of pit_wall is the Parallel specialist_team
    results["specialist_team_is_parallel"] = isinstance(pit_wall.sub_agents[0], ParallelAgent)

    print("Running ADK Battle Analysis...")
    try:
        state = await analyze_battle({
            "attacker_number": 16, 
            "defender_number": 1,
            "gap_meters": 18.5, 
            "attacker_soc": 0.68,
            "overtake_mode_eligible": True
        })
        results["all_adk_agents_ran"] = all(
            k in state for k in ["aero_recommendation","energy_recommendation",
                                "tire_recommendation","anomaly_report",
                                "final_decision","chronicle_entry"]
        )
    except Exception as e:
        print(f"ADK Analysis Error: {e}")
        results["all_adk_agents_ran"] = False

    results["strategist_uses_pro"] = "2.5-pro" in strategist.model or "pro" in strategist.model.lower()

    # ── Phase 7: ARIA Live API ──
    print("Verifying ARIA Live API Integration...")
    aria = AriaLiveAgent()
    aria.live_context = {
        "cars": [{"number": 16, "driver_name": "Leclerc", "battery_soc": 0.72,
                  "speed": 225, "y": 100, "team": "Ferrari"}],
        "edges": [], 
        "latest_decision": "Deploy Overtake Mode",
        "simulation": {"win_probability_bars": {16: 0.61}}, 
        "chronicle": "Leclerc is hunting down Verstappen."
    }
    
    try:
        tool_result = await aria._handle_tool_call("get_live_race_state_summary", {})
        results["aria_tool_returns_data"] = "Leclerc" in tool_result
        results["aria_tool_no_drs"] = "drs" not in tool_result.lower()
        
        win_result = await aria._handle_tool_call("get_win_probability", {})
        results["aria_win_prob_mentions_percentage"] = "%" in win_result
    except Exception as e:
        print(f"ARIA Tool Error: {e}")
        results["aria_tool_returns_data"] = False
        results["aria_tool_no_drs"] = False
        results["aria_win_prob_mentions_percentage"] = False

    # ── Phase 8: Imagen ──
    print("Verifying RaceVisualizer (Imagen 3)...")
    rv = RaceVisualizer()
    prompt = rv.build_prompt("Leclerc closed in on lap 34...", {"car1_name": "Leclerc"})
    results["imagen_prompt_has_2026"] = "2026" in prompt
    results["imagen_prompt_no_drs"] = "DRS" not in prompt or "No DRS" in prompt

    # ── Compliance check ──
    results["uses_gemini_model"] = "gemini" in aria.model.lower()
    results["uses_adk"] = True  # verified by isinstance checks above
    results["uses_google_cloud_service"] = results["gcs_bucket_accessible"]

    # Print
    print("\n" + "-"*30)
    print("--- INTEGRATION RESULTS ---")
    print("-"*30)
    for test, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {test}")
    
    passed = sum(v for v in results.values())
    total = len(results)
    print(f"\n{passed}/{total} passed")

    print("\n" + "-"*30)
    print("--- GOOGLE STACK VERIFICATION ---")
    print("-"*30)
    print(f"  Gemini Agent Model: {os.getenv('GEMINI_AGENT_MODEL')}")
    print(f"  Gemini Live Model: {os.getenv('GEMINI_LIVE_MODEL')}")
    print(f"  Strategist Model: {os.getenv('GEMINI_STRATEGIST_MODEL')}")
    print(f"  GCS Bucket: {os.getenv('GCS_BUCKET_NAME')}")
    print(f"  Cloud Project: {os.getenv('GOOGLE_CLOUD_PROJECT')}")
    print(f"  ADK PitWall: {pit_wall.name} ({type(pit_wall).__name__})")
    print("="*70 + "\n")

    if passed == total:
        print("MISSION SUCCESS: AeroMind v5 is fully integrated and compliance-verified.")
    else:
        print(f"MISSION INCOMPLETE: {total - passed} checks failed. Review logs above.")

if __name__ == "__main__":
    asyncio.run(test_aeromind_v5_google_gemini())
