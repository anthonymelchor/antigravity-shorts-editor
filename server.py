import os
import subprocess
import threading
import json
import time
import sys
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil

app = FastAPI()

@app.middleware("http")
async def log_requests(request, call_next):
    print(f"Incoming request: {request.method} {request.url}")
    response = await call_next(request)
    return response

from fastapi.staticfiles import StaticFiles

BASE_DIR = os.getcwd()

# Logging for client errors
APP_ERRORS_LOG = os.path.join(BASE_DIR, "app_errors.log")

@app.post("/api/log-error")
async def log_client_error(error_data: dict):
    timestamp = time.ctime()
    try:
        with open(APP_ERRORS_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[{timestamp}] CLIENT ERROR:\n")
            f.write(json.dumps(error_data, indent=2))
            f.write("\n" + "="*50 + "\n")
        print(f"Captured client error in {APP_ERRORS_LOG}")
        return {"status": "success"}
    except Exception as e:
        print(f"Failed to log client error: {e}")
        return {"status": "error", "message": str(e)}

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
TRANSCRIPT_PATH = os.path.join(BASE_DIR, "transcript_data.json")
VIDEO_OUTPUT_PATH = os.path.join(BASE_DIR, "output_vertical_clip.mp4")
PUBLIC_DIR = os.path.join(BASE_DIR, "frontend", "public")
REMOTION_DIR = os.path.join(BASE_DIR, "remotion-app")

app.mount("/media", StaticFiles(directory=BASE_DIR), name="media")

# State management
class ProcessingState:
    def __init__(self):
        self.status = "idle"  # idle, downloading, transcribing, analyzing, rendering, completed, failed
        self.progress = 0
        self.message = "Ready"
        self.error = None

state = ProcessingState()

class ProcessRequest(BaseModel):
    url: str

class FramingUpdate(BaseModel):
    center: float = None
    layout: str = None
    framing_segments: list = None

def run_pipeline(url: str, version: int):
    global state
    try:
        state.status = "processing"
        state.message = "Starting pipeline..."
        state.progress = 10
        
        # Call backend_pipeline.py with version
        process = subprocess.Popen(
            [sys.executable, "-u", "backend_pipeline.py", url, str(version)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=BASE_DIR
        )
        
        for line in process.stdout:
            # SILENT PROGRESS TRACKING
            if "Downloading video" in line:
                state.status = "downloading"
                state.message = "Downloading video from YouTube..."
                state.progress = 10
            elif "Transcribing" in line:
                state.status = "transcribing"
                state.message = "Transcribing audio (Whisper AI)..."
                state.progress = 30
            elif "Analyzing transcript" in line:
                state.status = "analyzing"
                state.message = "Brainstorming hooks (Gemini Script AI)..."
                state.progress = 50
            elif "Using local OpenCV" in line or "Starting Scene-Based" in line:
                state.status = "framing"
                state.message = "Visual Tracking (MediaPipe AI)..."
                state.progress = 75
            elif "Processing video with FFmpeg" in line:
                state.status = "rendering"
                state.message = "Extracting clip slices..."
                state.progress = 90

        process.wait()
        
        if process.returncode == 0:
            print(f"[Pipeline] Process version {version} completed successfully.")
            state.status = "completed"
            state.message = "Video processed successfully!"
            state.progress = 100
            
            # Use the versioned names created by backend_pipeline
            v_name = f"video_{version}.mp4" # Wait, backend calls it output_{version}.mp4
            # Actually backend_pipeline calls them:
            # INPUT_FILE = f"input_{version}.mp4"
            # OUTPUT_FILE = f"output_{version}.mp4"
            # TRANSCRIPT_FILE = f"transcript_{version}.json"
            
            V_OUT = os.path.join(BASE_DIR, f"video_{version}.mp4")
            A_OUT = os.path.join(BASE_DIR, f"audio_{version}.wav")
            T_OUT = os.path.join(BASE_DIR, f"transcript_{version}.json")

            print(f"[Sync] Checking for files: {V_OUT}, {A_OUT}, {T_OUT}")

            # Sync Transcript
            if os.path.exists(T_OUT):
                print(f"[Sync] Copying transcript...")
                shutil.copy(T_OUT, os.path.join(PUBLIC_DIR, f"transcript_{version}.json"))
                shutil.copy(T_OUT, os.path.join(PUBLIC_DIR, "transcript_data.json"))
                shutil.copy(T_OUT, os.path.join(REMOTION_DIR, "src", "transcript_data.json"))
            else:
                print(f"[Sync] ERROR: Transcript file NOT FOUND at {T_OUT}")

            # Sync Video
            if os.path.exists(V_OUT):
                print(f"[Sync] Copying video...")
                shutil.copy(V_OUT, os.path.join(PUBLIC_DIR, f"video_{version}.mp4"))
                shutil.copy(V_OUT, os.path.join(REMOTION_DIR, "public", f"video_{version}.mp4"))
            else:
                print(f"[Sync] ERROR: Video file NOT FOUND at {V_OUT}")

            # Sync Audio
            if os.path.exists(A_OUT):
                print(f"[Sync] Copying audio...")
                shutil.copy(A_OUT, os.path.join(PUBLIC_DIR, f"audio_{version}.wav"))
                shutil.copy(A_OUT, os.path.join(REMOTION_DIR, "public", f"audio_{version}.wav"))
            else:
                print(f"[Sync] ERROR: Audio file NOT FOUND at {A_OUT}")
                
            print(f"Version {version} sync attempt complete.")
        else:
            state.status = "failed"
            state.message = "Pipeline failed."
            state.error = "Check pipeline.log for crash details."
            
    except Exception as e:
        state.status = "failed"
        state.message = "Error occurred"
        state.error = str(e)

@app.post("/api/update-framing")
async def update_framing(update: FramingUpdate):
    if os.path.exists(TRANSCRIPT_PATH):
        with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if update.center is not None: data["center"] = update.center
        if update.layout is not None: data["layout"] = update.layout
        if update.framing_segments is not None: data["framing_segments"] = update.framing_segments
        
        with open(TRANSCRIPT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        # Update public files for frontend sync
        shutil.copy(TRANSCRIPT_PATH, os.path.join(PUBLIC_DIR, "transcript_data.json"))
        # Also update remotion-app source for build sync
        shutil.copy(TRANSCRIPT_PATH, os.path.join(REMOTION_DIR, "src", "transcript_data.json"))
        
        return {"status": "success"}
    return {"error": "Transcript not found"}

@app.post("/api/process")
async def process_video(request: ProcessRequest, background_tasks: BackgroundTasks):
    global state
    # Define filenames with timestamp at the end
    version = int(time.time())

    # 1. TEMPORARILY DISABLED CLEANUP as per user request to investigate files
    """
    patterns = [
        "transcript_*.json", "video_*.mp4", "audio_*.wav", "output_*.mp4", "output_*.wav",
        os.path.join(PUBLIC_DIR, "transcript_*.json"),
        os.path.join(PUBLIC_DIR, "video_*.mp4"), 
        os.path.join(PUBLIC_DIR, "audio_*.wav"),
        os.path.join(REMOTION_DIR, "public", "video_*.mp4"),
        os.path.join(REMOTION_DIR, "public", "audio_*.wav")
    ]
    
    import glob
    for p in patterns:
        for f in glob.glob(p):
            try: os.remove(f)
            except: pass
    """

    state = ProcessingState()
    background_tasks.add_task(run_pipeline, request.url, version)
    return {"message": "Processing started", "version": version}

@app.post("/api/reset")
async def reset_project():
    global state
    state = ProcessingState()
    
    # HARD WIPEOUT using * patterns
    import glob
    patterns = [
        "transcript_*.json", "video_*.mp4", "audio_*.wav", "output_*.mp4", "output_*.wav",
        os.path.join(PUBLIC_DIR, "*"),
        os.path.join(REMOTION_DIR, "public", "*"),
        os.path.join(REMOTION_DIR, "src", "transcript_data.json")
    ]
    for p in patterns:
        for f in glob.glob(p):
            if os.path.isfile(f):
                try: os.remove(f)
                except: pass
            
    return {"message": "Project fully WIPED"}

@app.get("/api/status")
async def get_status():
    return {
        "status": state.status,
        "progress": state.progress,
        "message": state.message,
        "error": state.error
    }

@app.get("/api/transcript")
async def get_transcript():
    if os.path.exists(TRANSCRIPT_PATH):
        with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"error": "Transcript not found"}

@app.post("/api/render")
async def render_video(background_tasks: BackgroundTasks):
    global state
    if state.status == "rendering":
        return {"message": "Already rendering"}
        
    def do_render():
        global state
        try:
            state.status = "rendering"
            state.message = "Preparing files for render..."
            state.progress = 5
            
            # SYNC FILES BEFORE RENDER
            with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            v_name = data.get("video_url", "output_vertical_clip.mp4")
            a_name = data.get("audio_url", "output_vertical_clip.wav")

            # 1. Transcript to Remotion src
            shutil.copy(TRANSCRIPT_PATH, os.path.join(REMOTION_DIR, "src", "transcript_data.json"))
            
            # 2. Media to Remotion public
            remotion_public = os.path.join(REMOTION_DIR, "public")
            if not os.path.exists(remotion_public):
                os.makedirs(remotion_public)
                
            v_path = os.path.join(BASE_DIR, v_name)
            a_path = os.path.join(BASE_DIR, a_name)
            
            if os.path.exists(v_path):
                shutil.copy(v_path, os.path.join(remotion_public, v_name))
            
            if os.path.exists(a_path):
                shutil.copy(a_path, os.path.join(remotion_public, a_name))
            
            state.message = "Running Remotion Build..."
            state.progress = 20
            
            with open("pipeline.log", "a") as logf:
                print(f"[Remotion] Starting Remotion Build for version {v_name}...")
                process = subprocess.Popen(
                    ["npm", "run", "build"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=REMOTION_DIR,
                    shell=True
                )
                
                for line in process.stdout:
                    if "Rendering" in line:
                        state.progress = 50
                        state.message = "Rendering frames..."
                
                process.wait()
                logf.write(f"[{time.ctime()}] REMOTION RENDER FINISHED (Code: {process.returncode})\n")
                print(f"[Remotion] Render process finished.")
            
            if process.returncode == 0:
                state.status = "completed"
                state.message = "Render successful!"
                state.progress = 100
                
                # Copy out.mp4 to frontend public
                final_out = os.path.join(REMOTION_DIR, "out.mp4")
                if os.path.exists(final_out):
                    shutil.copy(final_out, os.path.join(PUBLIC_DIR, "out.mp4"))
                    print(f"Final video copied to {os.path.join(PUBLIC_DIR, 'out.mp4')}")
            else:
                state.status = "failed"
                state.message = "Remotion render failed."
                state.error = "Check console for detail."
                
        except Exception as e:
            state.status = "failed"
            state.message = f"Error: {str(e)}"
            state.error = str(e)

    background_tasks.add_task(do_render)
    return {"message": "Render started"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
