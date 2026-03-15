import sys
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Mock Infinite Loops/External Ingestion to prevent hanging
# We keep these mocks because they start infinite loops that would block tests.
mock_stream = MagicMock()
mock_stream.OpenF1Streamer.return_value.run = AsyncMock()
sys.modules['backend.ingestion.openf1_stream'] = mock_stream

from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager
from fastapi.testclient import TestClient

# 2. Mock race_loop before importing app
import backend.server
backend.server.race_loop = AsyncMock()

from backend.server import app

@pytest.mark.asyncio
async def test_health_endpoint_returns_200():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
            assert response.status_code == 200

@pytest.mark.asyncio
async def test_health_shows_google_deployment():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
            data = response.json()
            assert data["regulations"] == "2026"
            assert "google" in data.get("deployment","").lower() or \
                   "cloud_run" in data.get("deployment","")

@pytest.mark.asyncio
async def test_health_shows_gcs_status():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
            data = response.json()
            assert "gcs_connected" in data

def test_websocket_welcome_has_live_api_feature():
    # Use TestClient for reliable WS testing in FastAPI/Starlette
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "connected"
            features = msg.get("features", [])
            assert any("aria" in f.lower() or "live" in f.lower() for f in features)

@pytest.mark.asyncio
async def test_ask_aria_rest_endpoint():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/ask-aria", json={"question":"What is Overtake Mode?"})
            assert response.status_code == 200
            assert "drs" not in response.json()["answer"].lower()

@pytest.mark.asyncio
async def test_chronicle_endpoint():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/chronicle")
            data = response.json()
            assert "entries" in data

@pytest.mark.asyncio
async def test_aria_websocket_endpoint_exists():
    # Verify /aria endpoint exists (not just /ws)
    # Check it's registered in app routes
    routes = [r.path for r in app.routes if hasattr(r, 'path')]
    assert "/aria" in routes
