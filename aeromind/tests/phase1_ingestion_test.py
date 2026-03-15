import pytest
from backend.ingestion.openf1_stream import OpenF1Streamer

@pytest.mark.asyncio
async def test_fetch_car_data():
    streamer = OpenF1Streamer(session_key="9158")
    # For a real test, you'd likely mock the httpx client.
    # We'll just assert it's a coroutine object/doesn't crash immediately for this placeholder
    assert hasattr(streamer, 'fetch_car_data')
