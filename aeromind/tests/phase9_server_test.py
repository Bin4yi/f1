import sys
from unittest.mock import MagicMock

class MockGoogleChild:
    pass

class MockGoogleCloud:
    logging = MockGoogleChild()
    logging.Client = MagicMock()

sys.modules['google'] = MagicMock()
sys.modules['google.cloud'] = MockGoogleCloud()
sys.modules['google.cloud.logging'] = sys.modules['google.cloud'].logging
sys.modules['vertexai'] = MagicMock()
sys.modules['vertexai.preview'] = MagicMock()
sys.modules['vertexai.preview.vision_models'] = MagicMock()
sys.modules['backend.cloud.gcs_client'] = MagicMock()
sys.modules['backend.cloud.firestore_client'] = MagicMock()
sys.modules['backend.graph.live_graph'] = MagicMock()
sys.modules['backend.graph.knowledge_graph'] = MagicMock()
sys.modules['backend.graph.graphrag'] = MagicMock()
sys.modules['backend.models.monte_carlo'] = MagicMock()
sys.modules['backend.models.overtake_model'] = MagicMock()
sys.modules['backend.models.energy_model'] = MagicMock()
sys.modules['backend.imaging.race_visualizer'] = MagicMock()
sys.modules['backend.aria.aria_live_agent'] = MagicMock()

import asyncio
from unittest.mock import AsyncMock
mock_stream = MagicMock()
mock_stream.OpenF1Streamer.return_value.run = AsyncMock()
sys.modules['backend.ingestion.openf1_stream'] = mock_stream

import pytest
from httpx import AsyncClient, ASGITransport

# Mock the background race loop before importing app
import backend.server
backend.server.race_loop = AsyncMock()

from backend.server import app

import asyncio
from asgi_lifespan import LifespanManager

@pytest.mark.asyncio
async def test_health_check_returns_200():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/health")
        assert response.status_code == 200
        assert response.json()["regulations"] == "2026"
        assert response.json()["deployment"] == "cloud_run"

@pytest.mark.asyncio
async def test_get_drivers_endpoint():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/drivers")
        assert response.status_code == 200
        assert "drivers" in response.json()
