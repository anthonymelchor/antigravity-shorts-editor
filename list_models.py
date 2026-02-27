
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

def list_models():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found.")
        return

    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
    print("Available models:")
    try:
        for m in client.models.list():
            print(f"- {m.name}")
    except Exception as e:
        print(f"Error listing models: {e}")

if __name__ == "__main__":
    list_models()
