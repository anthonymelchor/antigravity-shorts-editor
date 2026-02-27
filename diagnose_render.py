import os
import json
import subprocess
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables (GEMINI_API_KEY)
load_dotenv()

def extract_frame(video_path, time_s, output_name):
    # Precise absolute path to ffmpeg.exe
    ffmpeg_exe = r"C:\Users\MELCHOR\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"

    command = [
        ffmpeg_exe, "-y",
        "-ss", str(time_s),
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        output_name
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def analyze_failure(original_video, rendered_video, start_time):
    print(f"Starting diagnostic analysis...")
    
    # Extract frames for comparison
    original_frame = "diag_original.jpg"
    rendered_frame = "diag_rendered.jpg"
    
    # We take a frame 2 seconds into the clip
    extract_frame(original_video, start_time + 2, original_frame)
    extract_frame(rendered_video, 2, rendered_frame)
    
    if not os.path.exists(original_frame) or not os.path.exists(rendered_frame):
        print("Error: Could not extract frames for diagnosis.")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    print("Uploading frames to Gemini for expert critique...")
    uploaded = []
    try:
        uploaded.append(client.files.upload(file=original_frame))
        uploaded.append(client.files.upload(file=rendered_frame))
        
        prompt = """
        You are an expert video editor and AI diagnostic engineer.
        Image 1: The original widescreen video frame.
        Image 2: Our AI-automated vertical (9:16) render result.
        
        THE USER SAYS THE RESULT IS WRONG (subject cut off, layout failed, etc.).
        
        TASK:
        1. Compare both images.
        2. Identify specifically WHAT went wrong in Image 2.
        3. Determine if this scene SHOULD have been a "single" or "split" layout.
        4. Provide the EXACT optimal horizontal center coordinates (0.0 to 1.0) for the subject(s).
        5. Explain WHY the automated system might have failed (e.g., logo confusion, multiple people detected incorrectly, etc.).
        
        Output your analysis in a concise JSON format:
        {
            "diagnosis": "...",
            "recommended_layout": "single" | "split",
            "optimal_centers": {
                "single": 0.5,
                "split_top": 0.5,
                "split_bottom": 0.5
            },
            "root_cause_of_failure": "..."
        }
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=uploaded + [prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        
        result = json.loads(response.text)
        print("\n=== DIAGNOSTIC REPORT ===")
        print(json.dumps(result, indent=2))
        print("=========================\n")
        
        with open("diagnostic_report.json", "w") as f:
            json.dump(result, f, indent=2)
            
        return result

    finally:
        for f in [original_frame, rendered_frame]:
            if os.path.exists(f): 
                os.remove(f)
        for uf in uploaded:
            client.files.delete(name=uf.name)

if __name__ == "__main__":
    # Attempt to pull clip start time from transcript data
    try:
        with open("transcript_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            # The words list usually contains the timing
            start_time = data["words"][0]["start"]
    except:
        start_time = 0 # Fallback
        
    original = "input_full.mp4"
    rendered = os.path.join("remotion-app", "out.mp4")
    
    if os.path.exists(original) and os.path.exists(rendered):
        analyze_failure(original, rendered, start_time)
    else:
        print(f"Missing files for diagnosis: {original} or {rendered}")
