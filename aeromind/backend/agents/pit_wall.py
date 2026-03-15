from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from backend.agents.aero_agent import aero_agent
from backend.agents.energy_agent import energy_agent
from backend.agents.tire_agent import tire_agent
from backend.agents.anomaly_agent import anomaly_agent
from backend.agents.strategist import strategist
from backend.agents.chronicler_agent import chronicler_agent
import os
import google.genai
from dotenv import load_dotenv

# Load environment variables early
load_dotenv()

# Patch to Vertex AI when GOOGLE_CLOUD_PROJECT is set (preferred over free-tier API key)
if os.getenv("GOOGLE_CLOUD_PROJECT"):
    _original_client_init = google.genai.Client.__init__
    def _patched_client_init(self, *args, **kwargs):
        if not kwargs.get("api_key"):
            kwargs['vertexai'] = True
            if 'location' not in kwargs:
                kwargs['location'] = os.getenv('VERTEX_AI_LOCATION', 'us-central1')
            if 'project' not in kwargs:
                kwargs['project'] = os.getenv('GOOGLE_CLOUD_PROJECT')
        return _original_client_init(self, *args, **kwargs)
    google.genai.Client.__init__ = _patched_client_init

# Step 1: Run all 4 specialists in parallel simultaneously
specialist_team = ParallelAgent(
    name="SpecialistTeam",
    description="Runs aerodynamics, energy, tire, and anomaly analysis in parallel",
    sub_agents=[aero_agent, energy_agent, tire_agent, anomaly_agent]
)
# Note: ADK ParallelAgent writes each agent's output_key to shared session state
# So strategist can read {aero_recommendation}, {energy_recommendation}, etc.

# Step 2: Strategist synthesizes all 4 outputs + Monte Carlo
# Step 3: Chronicler writes the race narrative

pit_wall = SequentialAgent(
    name="PitWall",
    description="F1 autonomous AI broadcast team — 2026 regulations",
    sub_agents=[specialist_team, strategist, chronicler_agent]
)

# This is the entry point for each race event
async def analyze_battle(context: dict) -> dict:
    """
    Run the full pit wall analysis for a detected battle event.
    context: {attacker_number, defender_number, gap_meters, ...}
    Returns the final session state with all agent outputs.
    """
    from google.adk.sessions.in_memory_session_service import InMemorySessionService
    from google.adk.runners import Runner
    from google.genai import types

    session_service = InMemorySessionService()
    runner = Runner(
        agent=pit_wall,
        app_name="aeromind",
        session_service=session_service,
        auto_create_session=True
    )

    # Format the message for ADK/Gemini
    message_text = (
        f"Analyze battle: Car {context.get('attacker_number')} vs "
        f"Car {context.get('defender_number')}, gap {context.get('gap_meters', 10):.1f}m. "
        f"Attacker SoC: {context.get('attacker_soc', 0):.2f}. "
        f"Overtake mode eligible: {context.get('overtake_mode_eligible', False)}."
    )
    
    new_message = types.Content(
        role="user",
        parts=[types.Part(text=message_text)]
    )

    session_id = f"battle_{context.get('attacker_number')}_vs_{context.get('defender_number')}"
    
    # Run the agent team via Runner to ensure state management and tool execution
    try:
        async for _ in runner.run_async(
            user_id="race_system",
            session_id=session_id,
            new_message=new_message
        ):
            pass  # We could log events here if needed

        # Retrieve the final state from the session service
        final_session = await session_service.get_session(
            app_name="aeromind",
            user_id="race_system",
            session_id=session_id
        )
        return final_session.state if final_session else {}
    except Exception as e:
        print(f"ADK Runner Error: {e}")
        # Log the full exception for debugging
        import traceback
        traceback.print_exc()
        return {"error": str(e), "status": "failed"}
