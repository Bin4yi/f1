import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

def list_models():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not found in .env")
        return

    client = genai.Client(api_key=api_key)
    print(f"Listing models for API Key: {api_key[:5]}...")
    
    try:
        for model in client.models.list():
            print(f"- {model.name}")
    except Exception as e:
        print(f"FAILED to list models: {repr(e)}")

if __name__ == "__main__":
    list_models()
