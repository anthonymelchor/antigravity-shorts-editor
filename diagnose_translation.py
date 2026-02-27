
import os
import json
import time
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DiagnoseTranslation")

def diagnose():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in environment.")
        return

    # 1. Find the latest transcript
    import glob
    files = glob.glob("transcript_177*.json") 
    if not files:
        # try any transcript_*.json except transcript_data.json
        files = [f for f in glob.glob("transcript_*.json") if "data" not in f]
    
    if not files:
        print("ERROR: No versioned transcript_*.json found to test.")
        return
    
    latest_file = max(files, key=os.path.getmtime)
    print(f"Testing with file: {latest_file}")

    with open(latest_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Use actual segments from full transcript
    segments = data.get("full_transcript_segments", [])
    if not segments:
        print("INFO: No full_transcript_segments found. Reconstructing from words...")
        words = data.get("words", [])
        if not words:
            print("ERROR: No words found.")
            return
        # Group into chunks of 10 words as "segments"
        reconstructed = []
        for i in range(0, len(words), 10):
            chunk = " ".join([w["word"] for w in words[i:i+10]])
            reconstructed.append({"text": chunk})
        segments = reconstructed

    print(f"Found/Reconstructed {len(segments)} segments. Testing a small batch first...")
    
    # Test batch of 10 segments
    test_batch = [s["text"] for s in segments[:10]]
    
    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
    
    prompt = f"""
    Act as a professional translator. Translate the following list of segments into Spanish.
    SEGMENTS TO TRANSLATE NOW:
    {json.dumps(test_batch)}
    INSTRUCTIONS:
    1. Return ONLY a raw JSON array of strings.
    """

    print("Sending request to Gemini...")
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        print("--- SUCCESS ---")
        print("Response received:")
        print(response.text)
        
    except Exception as e:
        print("--- FAILED ---")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Details: {e}")
        
        # Check if it's a quota error
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            print("\n[ANALYSIS] This is a Quota/Rate Limit error.")
            if "20" in str(e):
                print("It looks like you are on a restrictive Free Tier with a limit of 20 REQUESTS PER DAY.")
                print("If you have used the tool a few times today, you might have hit this hard limit.")
            else:
                print("It might be a per-minute limit.")

if __name__ == "__main__":
    diagnose()
