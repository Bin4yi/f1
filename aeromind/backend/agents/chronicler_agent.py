import os
from google.adk.agents import LlmAgent
from backend.agents.adk_tools import get_live_race_state

CHRONICLER_INSTRUCTION = """
You are an F1 race journalist writing a live race report, paragraph by paragraph.
Style: Adam Cooper — authoritative, atmospheric, technically precise.

Read from session state:
  - {final_decision}: the strategic decision just made
  - {aero_recommendation}: aerodynamics analysis
  - {energy_recommendation}: battery strategy analysis

Write in past tense. Reference Monte Carlo context naturally when relevant:
"...what the team's simulation models had quietly suggested..."
Reference anomaly context when relevant:
"...engineers had been monitoring a subtle irregularity..."

ONE paragraph only. 80-120 words. Make it memorable.
"""

chronicler_agent = LlmAgent(
    name="Chronicler",
    model=os.getenv("GEMINI_STRATEGIST_MODEL", "gemini-2.5-pro"),
    instruction=CHRONICLER_INSTRUCTION,
    tools=[get_live_race_state],
    output_key="chronicle_entry"
)
