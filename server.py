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

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
BASE_DIR = os.getcwd()
TRANSCRIPT_PATH = os.path.join(BASE_DIR, "transcript_data.json")
VIDEO_OUTPUT_PATH = os.path.join(BASE_DIR, "output_vertical_clip.mp4")
PUBLIC_DIR = os.path.join(BASE_DIR, "frontend", "public")
REMOTION_DIR = os.path.join(BASE_DIR, "frontend")

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

def run_pipeline(url: str):
    global state
    try:
        state.status = "processing"
        state.message = "Starting pipeline..."
        state.progress = 10
        
        # Call backend_pipeline.py (Unbuffered to prevent log starving)
        process = subprocess.Popen(
            [sys.executable, "-u", "backend_pipeline.py", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=BASE_DIR
        )
        
        for line in process.stdout:
            out = line.strip()
            if out: print(f"[Pipeline] {out}")
            # Update state based on keywords in output
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
            elif "Using local OpenCV" in line:
                state.status = "framing"
                state.message = "Visual Tracking (MediaPipe AI)..."
                state.progress = 75
            elif "Processing video with FFmpeg" in line:
                state.status = "rendering"
                state.message = "Extracting clip slices..."
                state.progress = 90

        process.wait()
        
        if process.returncode == 0:
            state.status = "completed"
            state.message = "Video processed successfully!"
            state.progress = 100
            
            # Internal copy for persistence and engine sync
            if os.path.exists(TRANSCRIPT_PATH):
                shutil.copy(TRANSCRIPT_PATH, os.path.join(PUBLIC_DIR, "transcript_data.json"))
                # SYNC TO ENGINE SOURCE
                shutil.copy(TRANSCRIPT_PATH, os.path.join(REMOTION_DIR, "src", "transcript_data.json"))
            if os.path.exists(VIDEO_OUTPUT_PATH):
                shutil.copy(VIDEO_OUTPUT_PATH, os.path.join(PUBLIC_DIR, "output_vertical_clip.mp4"))
                # SYNC TO ENGINE SOURCE (public/static)
                target_video = os.path.join(REMOTION_DIR, "public", "output_vertical_clip.mp4")
                shutil.copy(VIDEO_OUTPUT_PATH, target_video)

            wav_path = VIDEO_OUTPUT_PATH.replace(".mp4", ".wav")
            if os.path.exists(wav_path):
                shutil.copy(wav_path, os.path.join(PUBLIC_DIR, "output_vertical_clip.wav"))
                shutil.copy(wav_path, os.path.join(REMOTION_DIR, "public", "output_vertical_clip.wav"))
        else:
            state.status = "failed"
            state.message = "Pipeline failed."
            state.error = "Error in backend_pipeline.py"
            
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
    if state.status not in ["idle", "completed", "failed"]:
        raise HTTPException(status_code=400, detail="A process is already running")
    
    state = ProcessingState()
    background_tasks.add_task(run_pipeline, request.url)
    return {"message": "Processing started"}

@app.post("/api/reset")
async def reset_project():
    global state
    state = ProcessingState()
    
    # Optional: Delete files
    files_to_delete = [TRANSCRIPT_PATH, VIDEO_OUTPUT_PATH, 
                       os.path.join(PUBLIC_DIR, "transcript_data.json"),
                       os.path.join(PUBLIC_DIR, "output_vertical_clip.mp4"),
                       os.path.join(PUBLIC_DIR, "out.mp4")]
    for f in files_to_delete:
        if os.path.exists(f):
            try: os.remove(f)
            except: pass
            
    return {"message": "Project reset"}

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
            # 1. Transcript to Remotion src
            shutil.copy(TRANSCRIPT_PATH, os.path.join(REMOTION_DIR, "src", "transcript_data.json"))
            # 2. Video to Remotion public (Static Files folder)
            remotion_public = os.path.join(REMOTION_DIR, "public")
            if not os.path.exists(remotion_public):
                os.makedirs(remotion_public)
            shutil.copy(VIDEO_OUTPUT_PATH, os.path.join(remotion_public, "output_vertical_clip.mp4"))
            
            state.message = "Running Remotion Build..."
            state.progress = 20
            
            # Run npm run build
            # Using shell=True for Windows compatibility with npm
            process = subprocess.Popen(
                ["npm", "run", "build"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=REMOTION_DIR,
                shell=True
            )
            
            for line in process.stdout:
                out = line.strip()
                if out: print(f"[Remotion] {out}")
                if "Rendering" in line:
                    state.progress = 50
                    state.message = "Rendering frames..."
            
            process.wait()
            
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
