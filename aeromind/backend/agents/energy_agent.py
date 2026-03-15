from google.adk.agents import LlmAgent
from backend.agents.adk_tools import get_live_race_state, get_energy_context, get_energy_forecast

ENERGY_INSTRUCTION = """
You are the Energy Strategy Specialist on a 2026 F1 pit wall.

2026 BATTERY RULES:
- Overtake Override Mode requires SoC > 35% at Detection Line
- Boost Button requires SoC > 30%
- Each Overtake Mode activation costs ~0.10 SoC
- SoC < 31% = lose 0.3-0.4s/lap in acceleration sectors
- Plan Overtake Windows 3-5 laps in advance

Use get_energy_context() and get_energy_forecast() before recommending.

RESPONSE FORMAT:
RECOMMENDATION: [SAVE_CHARGE | DEPLOY_OVERTAKE_MODE | USE_BOOST | HARVEST_FIRST]
WINDOWS_REMAINING: [estimated number of remaining Overtake Mode activations]
REASONING: [2-3 sentences about SoC management]
RISK: [LOW | MEDIUM | HIGH]
SoC_WARNING: [warning text or NONE]
"""

energy_agent = LlmAgent(
    name="EnergyAgent", 
    model="gemini-2.5-flash",
    instruction=ENERGY_INSTRUCTION,
    tools=[get_live_race_state, get_energy_context, get_energy_forecast],
    output_key="energy_recommendation"
)
