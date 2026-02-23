import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

try:
    print("Listing models...")
    for model in client.models.list():
        print(f"Model ID: {model.name}, Display Name: {model.display_name}")
except Exception as e:
    print(f"Failed to list models: {e}")
