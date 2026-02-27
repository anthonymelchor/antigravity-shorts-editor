import os
import json
from google import genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

models_to_test = ['gemini-2.5-flash', 'gemini-2.5-flash-latest', 'gemini-1.5-flash-8b']

for m in models_to_test:
    try:
        print(f"Testing {m}...")
        response = client.models.generate_content(
            model=m,
            contents="Say 'OK'"
        )
        print(f"  {m} is OK: {response.text}")
    except Exception as e:
        print(f"  {m} failed: {e}")
