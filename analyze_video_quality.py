import os
import json
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables (GEMINI_API_KEY)
load_dotenv()

def analyze_video_files(original_path, rendered_path):
    print("Initializing Deep Multimodal Analysis (Gemini 2.0 Flash)...")
    
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    files_to_upload = [
        {"path": original_path, "display_name": "Original Widescreen Video"},
        {"path": rendered_path, "display_name": "Rendered Vertical Video"}
    ]
    
    uploaded_files = []
    
    try:
        for item in files_to_upload:
            print(f"Uploading {item['display_name']} ({item['path']})...")
            uf = client.files.upload(file=item['path'])
            # Wait for file to be processed (standard for Gemini video analysis)
            while uf.state.name == "PROCESSING":
                print("  Processing on Gemini servers...")
                time.sleep(5)
                uf = client.files.get(name=uf.name)
            
            if uf.state.name == "FAILED":
                raise ValueError(f"File {item['display_name']} failed to process on Gemini.")
            
            uploaded_files.append(uf)
            print(f"  {item['display_name']} ready.")

        prompt = """
        You are a high-end cinematic editor and technical advisor for AI video automation.
        I have provided two videos:
        1. "Original Widescreen Video": The source material.
        2. "Rendered Vertical Video": The output of our AI-driven cropping and captioning system.
        
        CRITICAL ISSUES TO DIAGNOSE:
        
        1. THE LOGO BUG: Look at the first 40 seconds of the "Rendered Vertical Video". 
           The user reports that the "The School of Greatness" logo/banner is still being emphasized or visible in a way that blocks the subjects. 
           Identify the EXACT timestamps where this happens and WHY the AI might be failing to crop it out (is it horizontal center confusion?).
        
        2. THE 1:40 CUT: The user reports the video cuts or freezes at 1 minute or 1:40. 
           Evaluate the full duration of the "Rendered Vertical Video". Does it play correctly until the end? 
           Is there a mismatch between the content length and the metadata?
        
        3. LAYOUT CRITIQUE: We intended for a "split" layout (top/bottom) for interviews. 
           In the rendered video, did it actually use the split layout? If not, why? 
           Are the participants (speaker and host) properly framed or are they cut off?
        
        4. TECHNICAL ADVICE: Based on the visual evidence, what SPECIFIC adjustment should we make to the horizontal cropping logic or the Remotion layout settings to achieve a premium look?
        
        Output your analysis in a structured JSON:
        {
            "logo_issue": {
                "detected": true/false,
                "timestamps": ["..."],
                "explanation": "..."
            },
            "cut_issue": {
                "duration_observed": "...",
                "freezes_at": "...",
                "explanation": "..."
            },
            "layout_status": {
                "was_split": true/false,
                "framing_score_1_to_10": 5,
                "issues": "..."
            },
            "remediation_steps": [
                "Step 1...",
                "Step 2..."
            ]
        }
        """
        
        print("Starting video reasoning analysis...")
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=uploaded_files + [prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        
        analysis = json.loads(response.text)
        print("\n=== MULTIMODAL DIAGNOSTIC REPORT ===")
        print(json.dumps(analysis, indent=2))
        print("===================================\n")
        
        with open("deep_diagnostic_report.json", "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
            
        return analysis

    except Exception as e:
        print(f"Analysis failed: {e}")
        return None
    finally:
        # Clean up files from Gemini account
        for uf in uploaded_files:
            try:
                client.files.delete(name=uf.name)
                print(f"Deleted {uf.display_name} from Gemini.")
            except:
                pass

if __name__ == "__main__":
    original = "input_full.mp4"
    rendered = os.path.join("remotion-app", "out.mp4")
    
    if os.path.exists(original) and os.path.exists(rendered):
        analyze_video_files(original, rendered)
    else:
        print(f"Missing required video files: {original} or {rendered}")
