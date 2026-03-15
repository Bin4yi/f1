import asyncio
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

async def test_live_connect():
    print("Testing Gemini Live API Connection...")
    client = genai.Client(
        vertexai=True,
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("VERTEX_AI_LOCATION", "us-central1")
    )
    model_id = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.0-flash-001")
    print(f"Project: {os.getenv('GOOGLE_CLOUD_PROJECT')}")
    print(f"Location: {os.getenv('VERTEX_AI_LOCATION')}")
    print(f"Model: {model_id}")
    
    try:
        config = types.LiveConnectConfig(response_modalities=["AUDIO"])
        async with client.aio.live.connect(model=model_id, config=config) as session:
            print("SUCCESS: Connected to Gemini Live API!")
    except Exception as e:
        print(f"FAILED: {repr(e)}")

if __name__ == "__main__":
    asyncio.run(test_live_connect())
