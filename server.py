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
import yt_dlp
from typing import Optional, List
from dotenv import load_dotenv

# Cargar .env
load_dotenv()

# Debug: Verificar clave de Gemini en el servidor
gemini_key = os.environ.get("GEMINI_API_KEY", "")
if gemini_key:
    print(f"[Debug-Server] Gemini API Key detectada (termina en: ...{gemini_key[-4:]})")
else:
    print("[Debug-Server] ADVERTENCIA: GEMINI_API_KEY no detectada.")

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
# Multi-process Registry
active_processes = {} # version_id -> ProcessingState
processes_lock = threading.Lock()

class ProcessingState:
    def __init__(self, url="", title=""):
        self.status = "idle" # downloading, transcribing, analyzing, framing, completing, failed
        self.progress = 0
        self.message = "Initializing..."
        self.error = None
        self.url = url
        self.title = title
        self.version = None

    def to_dict(self):
        return {
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "error": self.error,
            "url": self.url,
            "title": self.title,
            "version": self.version
        }

def get_or_create_state(version_id, url=""):
    with processes_lock:
        if version_id not in active_processes:
            active_processes[version_id] = ProcessingState(url)
        return active_processes[version_id]

class ProcessRequest(BaseModel):
    url: str

class FramingUpdate(BaseModel):
    center: float = None
    layout: str = None
    framing_segments: list = None

def run_pipeline(url: str, version: int):
    # Use localized state for this process
    state = get_or_create_state(version, url)
    state.version = version
    state.title = "Obteniendo información..." # Placeholder visible instantly
    try:
        # Fetch Title using the library - much more robust and faster
        try:
            ydl_opts = {'quiet': True, 'no_warnings': True, 'noplaylist': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                state.title = info.get('title', url)
        except Exception as e:
            print(f"[Pipeline] Title fetch error: {e}")
            state.title = url

        state.status = "processing"
        state.message = f"Starting pipeline for: {state.title[:40]}..."
        state.progress = 10
        
        # Call backend_pipeline.py with version and log output (versioned log)
        log_filename = f"pipeline_{version}.log"
        with open(log_filename, "w", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                [sys.executable, "-u", "backend_pipeline.py", url, str(version)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=BASE_DIR
            )
            
            for line in process.stdout:
                line_stripped = line.strip()
                # Filtrar el ruido de la descarga de YouTube para mantener el log limpio
                if not line_stripped.startswith("[download]") and not any(p in line_stripped for p in ["%", "ETA", "of", "at", "MiB/s"]):
                    log_file.write(line)
                    log_file.flush()
                
                # SILENT PROGRESS TRACKING - Moved INSIDE the loop
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
                    state.message = "AI is selecting viral moments..."
                    state.progress = 60
                elif "Starting Local HIGH-PRECISION Framing" in line:
                    state.status = "framing"
                    state.message = "Visual Tracking (High-Precision Local AI)..."
                    state.progress = 80
                elif "Backend processing pipeline complete" in line:
                    state.status = "completed"
                    state.message = "Process complete!"
                    state.progress = 100

        process.wait()
        
        if process.returncode == 0:
            print(f"[Pipeline] Process version {version} completed successfully.")
            state.status = "completed"
            state.message = "Video processed successfully!"
            state.progress = 100
            
            # Use the versioned names created by backend_pipeline
            V_OUT = os.path.join(BASE_DIR, f"video_{version}.mp4")
            A_OUT = os.path.join(BASE_DIR, f"audio_{version}.wav")
            T_OUT = os.path.join(BASE_DIR, f"transcript_{version}.json")

            print(f"[Sync] Checking for files: {V_OUT}, {A_OUT}, {T_OUT}")

            import glob
            # Sync Transcript
            if os.path.exists(T_OUT):
                print(f"[Sync] Copying transcript...")
                shutil.copy(T_OUT, os.path.join(PUBLIC_DIR, f"transcript_{version}.json"))
                shutil.copy(T_OUT, os.path.join(PUBLIC_DIR, "transcript_data.json"))
                shutil.copy(T_OUT, os.path.join(REMOTION_DIR, "src", "transcript_data.json"))
            else:
                print(f"[Sync] ERROR: Transcript file NOT FOUND at {T_OUT}")

            # Sync All Generated Video Clips
            video_files = glob.glob(f"video_{version}*.mp4")
            for v_file in video_files:
                print(f"[Sync] Copying {v_file}...")
                shutil.copy(v_file, os.path.join(PUBLIC_DIR, v_file))
                shutil.copy(v_file, os.path.join(REMOTION_DIR, "public", v_file))
            
            # Sync All Generated Audio Clips
            audio_files = glob.glob(f"audio_{version}*.wav")
            for a_file in audio_files:
                print(f"[Sync] Copying {a_file}...")
                shutil.copy(a_file, os.path.join(PUBLIC_DIR, a_file))
                shutil.copy(a_file, os.path.join(REMOTION_DIR, "public", a_file))
                
            print(f"Version {version} sync attempt complete. ({len(video_files)} clips synced)")
        else:
            state.status = "failed"
            state.message = "Pipeline failed."
            # Try to read the last error from versioned log
            try:
                if os.path.exists(log_filename):
                    with open(log_filename, "r", encoding="utf-8") as lf:
                        lines = lf.readlines()
                        last_error = "Check logs."
                        for line in reversed(lines):
                            if "ERROR" in line:
                                last_error = line.strip()
                                break
                        state.error = last_error
            except:
                state.error = "Unknown pipeline crash."
            
    except Exception as e:
        state.status = "failed"
        state.message = "Critical Error"
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
    # PREVENT REDUNDANT DOWNLOADS
    with processes_lock:
        for v, s in active_processes.items():
            if s.url == request.url and s.status not in ["completed", "failed"]:
                print(f"[Process] BLOCKED Redundant process for same URL: {request.url}")
                return {"message": "Project already being processed", "version": v, "isDuplicate": True}

    # Use versioned state
    version = int(time.time())
    get_or_create_state(version, request.url).version = version
    
    background_tasks.add_task(run_pipeline, request.url, version)
    return {"message": "Processing started", "version": version}

@app.post("/api/reset")
async def reset_project():
    with processes_lock:
        active_processes.clear()
    
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

@app.get("/api/projects")
async def list_projects():
    """Lists all projects by scanning for transcript_*.json files and including active ones."""
    import glob
    projects = []
    
    # Active processes
    with processes_lock:
        for version_id, state in active_processes.items():
            if state.status not in ["idle", "completed"]:
                projects.append({
                    "version": str(version_id),
                    "title": state.title or "Procesando nuevo video...",
                    "status": state.status,
                    "progress": state.progress,
                    "message": state.message,
                    "error": state.error,
                    "timestamp": int(version_id),
                    "isActive": state.status not in ["failed", "completed", "idle"],
                    "url": state.url
                })

    # Pattern to match transcript_{version}.json but NOT transcript_data.json
    pattern = os.path.join(BASE_DIR, "transcript_[0-9]*.json")
    for f in glob.glob(pattern):
        try:
            with open(f, "r", encoding="utf-8") as tf:
                data = json.load(tf)
                version = os.path.basename(f).replace("transcript_", "").replace(".json", "")
                
                # Avoid duplicates (if it's in active_processes as completed)
                if any(p["version"] == version for p in projects):
                    continue

                projects.append({
                    "version": version,
                    "title": data.get("clips", [{}])[0].get("title", f"Project {version}"),
                    "status": "completed", 
                    "timestamp": int(version)
                })
        except: pass

    # Sort by timestamp desc
    projects.sort(key=lambda x: x["timestamp"], reverse=True)
    return projects

@app.delete("/api/project/{version}")
async def delete_project(version: str):
    """Deletes all files associated with a specific project version."""
    import glob
    patterns = [
        f"transcript_{version}.json", 
        f"video_{version}*.mp4", 
        f"audio_{version}*.wav", 
        f"input_{version}.mp4",
        f"output_{version}*.mp4", 
        f"output_{version}*.wav",
        os.path.join(PUBLIC_DIR, f"transcript_{version}.json"),
        os.path.join(PUBLIC_DIR, f"video_{version}*.mp4"), 
        os.path.join(PUBLIC_DIR, f"audio_{version}*.wav"),
        os.path.join(REMOTION_DIR, "public", f"video_{version}*.mp4"),
        os.path.join(REMOTION_DIR, "public", f"audio_{version}*.wav")
    ]
    
    # Remove from active processes if present
    with processes_lock:
        if version in active_processes:
            del active_processes[version]
        try:
            v_int = int(version)
            if v_int in active_processes:
                del active_processes[v_int]
        except: pass

    deleted_count = 0
    for p in patterns:
        files = glob.glob(p) if "*" in p else [p] # Handle both pattern and direct files
        for f in files:
            if os.path.isfile(f):
                try: 
                    os.remove(f)
                    deleted_count += 1
                except: pass
            
    return {"message": f"Project {version} deleted", "files_removed": deleted_count}

@app.get("/api/status")
async def get_status(version: Optional[str] = None):
    # Returns the status of a specific version, or the most recent active one
    with processes_lock:
        if version and version in active_processes:
            return active_processes[version].to_dict()
        
        # Default to the most recent active process if no version provided
        if active_processes:
            latest_version = max(active_processes.keys())
            return active_processes[latest_version].to_dict()
            
    return {"status": "idle", "message": "No active tasks found."}

@app.get("/api/transcript/{version}")
async def get_transcript_version(version: str):
    path = os.path.join(BASE_DIR, f"transcript_{version}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"error": "Transcript not found"}

@app.get("/api/transcript")
async def get_transcript():
    if os.path.exists(TRANSCRIPT_PATH):
        with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"error": "Transcript not found"}


class RenderRequest(BaseModel):
    version: str
    indices: List[int]

def do_render_queue(version_id, clip_indices):
    log_file_path = os.path.join(BASE_DIR, f"pipeline_{version_id}.log")
    
    with open(log_file_path, "a", encoding="utf-8") as log_file:
        log_file.write(f"\n\n[RENDER] Starting Batch Render for version {version_id}. Indices: {clip_indices}\n")
        log_file.flush()
        
        for idx in clip_indices:
            render_state = get_or_create_state(f"render_{version_id}_{idx}")
            if render_state.status == "rendering":
                log_file.write(f"[RENDER] Skip Clip #{idx+1} - Busy\n")
                continue
                
            try:
                render_state.status = "rendering"
                render_state.message = f"Starting Clip #{idx+1}..."
                render_state.progress = 5
                
                log_file.write(f"[RENDER] --- Processing Clip #{idx+1} ---\n")
                log_file.flush()
                
                # Use version-specific transcript
                t_path = os.path.join(BASE_DIR, f"transcript_{version_id}.json")
                if not os.path.exists(t_path):
                    msg = f"Original transcript {t_path} not found."
                    render_state.status = "failed"
                    render_state.error = msg
                    log_file.write(f"[RENDER] ERROR: {msg}\n")
                    continue

                with open(t_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # If clip_index is provided, override root fields for Remotion parity
                if "clips" in data and idx < len(data["clips"]):
                    clip = data["clips"][idx]
                    data.update({
                        "words": clip.get("words", []),
                        "words_es": clip.get("words_es", []),
                        "video_url": clip.get("video_url"),
                        "audio_url": clip.get("audio_url"),
                        "edit_events": clip.get("edit_events", {}),
                        "duration": clip.get("duration", 30),
                        "layout": clip.get("layout", "single"),
                        "center": clip.get("center", 0.5),
                        "center_top": clip.get("center_top", 0.5),
                        "center_bottom": clip.get("center_bottom", 0.5),
                        "framing_segments": clip.get("framing_segments", [])
                    })
                    log_file.write(f"[RENDER] Clip fields updated from index {idx}\n")
                
                v_name = data.get("video_url")
                a_name = data.get("audio_url")

                if not v_name or not os.path.exists(os.path.join(BASE_DIR, v_name)):
                    msg = f"Video file {v_name} not found."
                    render_state.status = "failed"
                    render_state.error = msg
                    log_file.write(f"[RENDER] ERROR: {msg}\n")
                    continue

                # 1. Save modified Transcript to Remotion src
                with open(os.path.join(REMOTION_DIR, "src", "transcript_data.json"), "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                # 2. Media to Remotion public
                remotion_public = os.path.join(REMOTION_DIR, "public")
                shutil.copy(os.path.join(BASE_DIR, v_name), os.path.join(remotion_public, v_name))
                if a_name and os.path.exists(os.path.join(BASE_DIR, a_name)):
                    shutil.copy(os.path.join(BASE_DIR, a_name), os.path.join(remotion_public, a_name))
                
                render_state.message = f"Building Clip #{idx+1}..."
                render_state.progress = 20
                log_file.write(f"[RENDER] Running Remotion build for Clip #{idx+1}...\n")
                log_file.flush()
                
                process = subprocess.Popen(
                    ["npm", "run", "build"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    cwd=REMOTION_DIR, shell=True
                )
                
                has_started_rendering = False
                for line in process.stdout:
                    if "Rendering" in line and not has_started_rendering:
                        render_state.progress = 50
                        render_state.message = f"Rendering Clip #{idx+1}..."
                        log_file.write(f"[RENDER] Final rendering phase started for Clip #{idx+1}...\n")
                        log_file.flush()
                        has_started_rendering = True
                    
                    # Still print to console for server visibility, but NOT to log_file
                    print(f"[Remotion-Internal] {line.strip()}")
                
                process.wait()
                if process.returncode == 0:
                    render_state.status = "completed"
                    render_state.message = f"Clip #{idx+1} Ready!"
                    render_state.progress = 100
                    log_file.write(f"[RENDER] SUCCESS: Clip #{idx+1} completed.\n")
                    
                    final_out = os.path.join(REMOTION_DIR, "out.mp4")
                    if os.path.exists(final_out):
                        dest_file = f"out_{version_id}_clip_{idx+1}.mp4"
                        shutil.copy(final_out, os.path.join(PUBLIC_DIR, dest_file))
                        log_file.write(f"[RENDER] Saved to {dest_file}\n")
                else:
                    render_state.status = "failed"
                    render_state.message = f"Failed Clip #{idx+1}"
                    log_file.write(f"[RENDER] ERROR: Remotion build failed (Exit Code {process.returncode})\n")
                    
            except Exception as e:
                render_state.status = "failed"
                render_state.message = f"Error: {str(e)}"
                log_file.write(f"[RENDER] EXCEPTION: {str(e)}\n")
            log_file.flush()

@app.post("/api/render")
async def render_clips(request: RenderRequest, background_tasks: BackgroundTasks):
    print(f"\n[SERVER] Recibida solicitud de renderizado para versión: {request.version}")
    print(f"[SERVER] Clips a procesar: {request.indices}")
    background_tasks.add_task(do_render_queue, request.version, request.indices)
    return {"message": "Render started for selected clips"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
