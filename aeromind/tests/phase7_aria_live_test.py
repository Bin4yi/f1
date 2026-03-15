import pytest
from backend.aria.aria_live_agent import AriaLiveAgent, ARIA_SYSTEM_INSTRUCTION, ARIA_LIVE_TOOLS

# Test 1
def test_aria_agent_init():
    aria = AriaLiveAgent()
    assert aria.model is not None
    assert "gemini" in aria.model.lower()

# Test 2
def test_aria_system_instruction_no_drs():
    assert "DRS is ABOLISHED" in ARIA_SYSTEM_INSTRUCTION or \
           "Never say DRS" in ARIA_SYSTEM_INSTRUCTION or \
           "NEVER say DRS" in ARIA_SYSTEM_INSTRUCTION

# Test 3
def test_aria_has_live_tools():
    tool_names = [t.name for t in ARIA_LIVE_TOOLS]
    assert "get_live_race_state_summary" in tool_names
    assert "get_latest_decision" in tool_names
    assert "get_win_probability" in tool_names

# Test 4
@pytest.mark.asyncio
async def test_aria_tool_get_live_state():
    aria = AriaLiveAgent()
    aria.live_context = {
        "cars": [{"number": 16, "driver_name": "Leclerc", "team": "Ferrari",
                  "battery_soc": 0.67, "speed": 220, "y": 100}],
        "edges": [], "latest_decision": "Push now", "simulation": {}, "chronicle": ""
    }
    result = await aria._handle_tool_call("get_live_race_state_summary", {})
    assert "Leclerc" in result
    assert "67%" in result

# Test 5
@pytest.mark.asyncio
async def test_aria_tool_explain_overtake_mode_eligible():
    aria = AriaLiveAgent()
    aria.live_context = {
        "cars": [
            {"number": 16, "driver_name": "Leclerc", "battery_soc": 0.72, "y": 100},
            {"number": 1, "driver_name": "Verstappen", "battery_soc": 0.58, "y": 90}
        ], "edges": [], "latest_decision": "", "simulation": {}, "chronicle": ""
    }
    result = await aria._handle_tool_call("explain_overtake_mode",
                                          {"attacker_number": 16, "defender_number": 1})
    assert "72%" in result
    assert "IS" in result  # eligible
    assert "drs" not in result.lower()

# Test 6
@pytest.mark.asyncio
async def test_aria_tool_explain_overtake_mode_not_eligible():
    aria = AriaLiveAgent()
    aria.live_context = {
        "cars": [
            {"number": 16, "driver_name": "Leclerc", "battery_soc": 0.28, "y": 100},
            {"number": 1, "driver_name": "Verstappen", "battery_soc": 0.58, "y": 90}
        ], "edges": [], "latest_decision": "", "simulation": {}, "chronicle": ""
    }
    result = await aria._handle_tool_call("explain_overtake_mode",
                                          {"attacker_number": 16, "defender_number": 1})
    assert "is NOT" in result or "NOT" in result

# Test 7
def test_aria_update_context_stores_data():
    aria = AriaLiveAgent()
    fake_snap = {"cars": [{"number": 1}], "edges": []}
    aria.update_context(fake_snap, [{"message": "push"}], {"win_probability_bars": {}}, "lap 34")
    assert len(aria.live_context["cars"]) == 1
    assert "push" in aria.live_context["latest_decision"]
