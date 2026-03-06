import os
import json
import time
import logging
from dotenv import load_dotenv

# Re-import from the local file to test the actual implementation
from backend_pipeline import transcribe_audio, extract_audio

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

def test_transcription_system():
    # 1. Need a small input file
    input_video = "input.mp4"
    if not os.path.exists(input_video):
        print(f"ERROR: '{input_video}' not found in root. Cannot test.")
        return

    print("--- 🚀 STARTING HYBRID TRANSCRIPTION TEST ---")
    
    # Check API keys
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    print(f"Groq Key: {'Found' if groq_key else 'MISSING'}")
    print(f"Gemini Key: {'Found' if gemini_key else 'MISSING'}")
    
    start_time = time.time()
    try:
        # This will call the hybrid function (Groq -> Gemini -> Local)
        result = transcribe_audio(input_video, model_size="tiny") # Use tiny for local fallback speed
        
        duration = time.time() - start_time
        print(f"\n✅ SUCCESS (Total Time: {duration:.2f}s)")
        print(f"Detected Language: {result.get('language')}")
        print(f"Number of Segments: {len(result.get('segments', []))}")
        print(f"Number of Words: {len(result.get('words', []))}")
        
        # Validate internal structure
        if result.get('segments'):
            first_seg = result['segments'][0]
            print(f"\nFirst Segment: [{first_seg['start']}s - {first_seg['end']}s] {first_seg['text']}")
            if first_seg.get('words'):
                print(f"First Word in Segment: {first_seg['words'][0]}")
        
        # Save for manual inspection
        with open("test_transcription_result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print("\nFull result saved to 'test_transcription_result.json'")

    except Exception as e:
        print(f"\n❌ CRITICAL SYSTEM FAILURE: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_transcription_system()
