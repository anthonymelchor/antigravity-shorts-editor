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

@app.get("/")
async def health_check():
    return {"status": "alive", "engine": "RocotoClip", "time": time.ctime()}

@app.middleware("http")
async def log_requests(request, call_next):
    print(f"[RAW-REQUEST] {request.method} {request.url}")
    response = await call_next(request)
    if response.status_code == 404:
        print(f"[404-DEBUG] Route not found: {request.url}")
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

import httpx

# Supabase Config for Server
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

@app.get("/api/discovery")
async def get_discovery_candidates(niche: Optional[str] = None, user_id: Optional[str] = None):
    print(f"[DEBUG] Reached /api/discovery endpoint. user_id: {user_id}, niche: {niche}")
    """
    Fetches discovery candidates from Supabase.
    Implements security by filtering results.
    """
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    # Base URL with limit and order
    url = f"{SUPABASE_URL}/rest/v1/discovery_results?select=*,accounts(niche)&status=eq.discovered&order=views.desc&limit=50"
    
    if user_id:
        url += f"&user_id=eq.{user_id}"
    
    if niche:
        # Note: Supabase filtering by joined table requires specific syntax
        # For simplicity, we filter in memory for now, or use a more precise query
        pass

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                raw_results = resp.json()
                results = []
                for c in raw_results:
                    # Filter by niche in memory if provided
                    current_niche = c.get('accounts', {}).get('niche', 'Unknown')
                    if niche and niche != current_niche:
                        continue
                        
                    results.append({
                        "id": c.get('id'),
                        "title": c.get('title'),
                        "original_url": c.get('original_url'),
                        "views": c.get('views'),
                        "niche": current_niche,
                        "status": c.get('status')
                    })
                return results
            else:
                print(f"[Supabase-Error] {resp.status_code}: {resp.text}")
                return []
        except Exception as e:
            print(f"[Supabase-Exception] {e}")
            return []

from discovery.youtube_discovery import ContentDiscoveryEngine

@app.post("/api/discovery/run")
async def run_discovery(limit: int = 5, user_id: Optional[str] = None, background_tasks: BackgroundTasks = None):
    """
    Triggers the content discovery engine with real-time status tracking.
    """
    discovery_id = f"discovery_{user_id or 'global'}"
    
    # Initialize state synchronously to avoid race conditions with frontend polling
    state = get_or_create_state(discovery_id, url="Discovery Engine", user_id=user_id)
    state.version = discovery_id 
    state.user_id = user_id 
    state.timestamp = time.time() 
    state.title = "Neural Trend Discovery"
    state.status = "queued" # Start in queue
    state.message = "Esperando turno para análisis neural..."
    state.progress = 0

    def task(l, uid, d_id):
        # State already retrieved and initialized above
        current_state = get_or_create_state(d_id, user_id=uid)
        
        print(f"[QUEUE] Discovery {d_id} waiting for semaphore...")
        try:
            with process_semaphore:
                print(f"[QUEUE] Discovery {d_id} is now ACTIVE")
                try:
                    current_state.status = "processing"
                    current_state.message = "Despertando Motor de Tendencias..."
                    current_state.progress = 5
                    
                    # Small delay to ensure UI picks up the 'processing' state
                    time.sleep(1)
                    
                    current_state.message = "Escaneando nichos de contenido..."
                    engine = ContentDiscoveryEngine()
                    # We wrap the engine call to provide basic progress feedback
                    engine.run_cycle(limit_per_niche=l, user_id=uid)
                    current_state.status = "completed"
                    current_state.message = "Digital trends analyzed. Dashboard updated."
                    current_state.progress = 100
                except Exception as e:
                    current_state.status = "failed"
                    current_state.message = f"Discovery failed: {str(e)}"
                    current_state.error = str(e)
                    print(f"[DISCOVERY] Engine crashed: {e}")
        finally:
            pass

    if background_tasks:
        background_tasks.add_task(task, limit, user_id, discovery_id)
        return {"status": "success", "version": discovery_id}
    return {"error": "Background tasks not available"}

@app.post("/api/discovery/approve/{candidate_id}")
async def approve_candidate(candidate_id: int):
    """
    Marks a discovery candidate as approved in Supabase.
    """
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    url = f"{SUPABASE_URL}/rest/v1/discovery_results?id=eq.{candidate_id}"
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.patch(url, json={"status": "approved"}, headers=headers)
            if resp.status_code in [200, 201, 204]:
                return {"status": "success", "message": f"Candidate {candidate_id} approved for processing"}
            else:
                raise HTTPException(status_code=resp.status_code, detail=f"Supabase error: {resp.text}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

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
process_semaphore = threading.Semaphore(1) # Only process 1 video at a time for efficiency

class ProcessRequest(BaseModel):
    url: str
    user_id: Optional[str] = None

class ProcessingState:
    def __init__(self, url="", title="", user_id=None):
        self.status = "queued" # queued, downloading, transcribing, analyzing, framing, completing, failed
        self.progress = 0
        self.message = "En cola de espera..."
        self.error = None
        self.url = url
        self.title = title
        self.version = None
        self.started_at = None
        self.user_id = user_id
        self.timestamp = time.time() # High-precision float for perfect ordering

    def to_dict(self):
        # Determine active status for UI
        is_active = self.status not in ["completed", "failed"]
        return {
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "error": self.error,
            "url": self.url,
            "title": self.title,
            "version": str(self.version),
            "timestamp": self.timestamp,
            "isActive": is_active
        }

def get_or_create_state(version_id, url="", user_id=None):
    with processes_lock:
        if version_id not in active_processes:
            active_processes[version_id] = ProcessingState(url=url, user_id=user_id)
        # Always ensure user_id is updated if we have a fresh one (resilience)
        if user_id:
            active_processes[version_id].user_id = user_id
        return active_processes[version_id]

class RenderRequest(BaseModel):
    version: str
    user_id: str
    indices: List[int]

class FramingUpdate(BaseModel):
    version: str
    user_id: str
    center: float = None
    layout: str = None
    framing_segments: list = None

def run_pipeline(url: str, version: int):
    # Use localized state for this process
    state = get_or_create_state(version, url)
    state.version = str(version)
    state.title = "Obteniendo información..."
    state.status = "queued"

    # Log Start for Observability (Standard 5)
    print(f"[START] Process {version} initiated for URL: {url}")

    try:
        # Fetch Title with timeout (Standard 1 - Resiliencia)
        ydl_opts = {'quiet': True, 'no_warnings': True, 'noplaylist': True, 'socket_timeout': 10}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # We use download=False to just get metadata
            info = ydl.extract_info(url, download=False)
            state.title = info.get('title', url)
    except Exception as e:
        print(f"[Pipeline] Title fetch error (probable timeout/network): {e}")
        state.title = url

    # Wait for turn (The Queue logic - Standard 4)
    print(f"[QUEUE] Process {version} waiting for semaphore...")
    try:
        with process_semaphore: 
            state.status = "processing"
            state.started_at = time.time()
            print(f"[QUEUE] Process {version} is now ACTIVE")
            
            log_filename = f"pipeline_{version}.log"
            try:
                cmd = [sys.executable, "-u", "backend_pipeline.py", "--url", url, "--version", str(version)]
                if state.user_id:
                    cmd.extend(["--user_id", str(state.user_id)])
                
                with open(log_filename, "w", encoding="utf-8") as log_file:
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        cwd=BASE_DIR
                    )
                    
                    for line in process.stdout:
                        line_stripped = line.strip()
                        if not line_stripped.startswith("[download]") and not any(p in line_stripped for p in ["%", "ETA", "at", "MiB/s"]):
                            log_file.write(line)
                            log_file.flush()
                        
                        # Track progress via logs (Standard 5 - Observability)
                        if "Downloading video" in line:
                            state.status = "downloading"
                            state.message = "Descargando video de YouTube..."
                            state.progress = 10
                        elif "Transcribing" in line:
                            state.status = "transcribing"
                            state.message = "Transcribiendo audio (IA Whisper)..."
                            state.progress = 30
                        elif "Analyzing transcript" in line:
                            state.status = "analyzing"
                            state.message = "Gemini AI seleccionando momentos..."
                            state.progress = 60
                        elif "Starting Local HIGH-PRECISION Framing" in line:
                            state.status = "framing"
                            state.message = "Local AI Tracking (Alta Precisión)..."
                            state.progress = 80
                        elif "Backend processing pipeline complete" in line:
                            state.status = "completed"
                            state.message = "Procesamiento completado!"
                            state.progress = 100
                    
                    process.wait()

                if process.returncode == 0:
                    print(f"[END] Process {version} completed successfully.")
                    state.status = "completed"
                    state.progress = 100
                    
                    # Syncing files
                    import glob
                    T_OUT = os.path.join(BASE_DIR, f"transcript_{version}.json")
                    if os.path.exists(T_OUT):
                        shutil.copy(T_OUT, os.path.join(PUBLIC_DIR, f"transcript_{version}.json"))
                        shutil.copy(T_OUT, os.path.join(PUBLIC_DIR, "transcript_data.json"))
                        shutil.copy(T_OUT, os.path.join(REMOTION_DIR, "src", "transcript_data.json"))
                    
                    for ftype in ["*.mp4", "*.wav"]:
                        for f in glob.glob(f"video_{version}{ftype}") + glob.glob(f"audio_{version}{ftype}"):
                            shutil.copy(f, os.path.join(PUBLIC_DIR, f))
                            shutil.copy(f, os.path.join(REMOTION_DIR, "public", f))
                else:
                    state.status = "failed"
                    state.message = "Error en el pipeline"
                    try:
                        with open(log_filename, "r", encoding="utf-8") as lf:
                            err_lines = lf.readlines()
                            state.error = err_lines[-1] if err_lines else "Unknown error"
                    except: pass

            except Exception as e:
                state.status = "failed"
                state.message = "Error Crítico"
                state.error = str(e)
                print(f"[ERROR] Process {version} crashed: {e}")
    finally:
        # Ensure semaphore is clear and state is finalized
        pass

@app.post("/api/update-framing")
async def update_framing(update: FramingUpdate):
    # Determine which file to update
    target_path = os.path.join(BASE_DIR, f"transcript_{update.version}.json")
    
    if not os.path.exists(target_path):
        # Fallback to legacy if no version (less secure, but avoids breaking current state)
        target_path = TRANSCRIPT_PATH 

    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Ownership Check
        if data.get("user_id") and data.get("user_id") != update.user_id:
            raise HTTPException(status_code=403, detail="Unauthorized to update this transcript")
            
        if update.center is not None: data["center"] = update.center
        if update.layout is not None: data["layout"] = update.layout
        if update.framing_segments is not None: data["framing_segments"] = update.framing_segments
        
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        # Syncing to Remotion/Public for preview/rendering (Semaphore protects this)
        # Note: We sync to 'transcript_data.json' because Remotion's Dev Server and Renderer 
        # usually expect this specific name in their static imports/build configs.
        shutil.copy(target_path, os.path.join(PUBLIC_DIR, "transcript_data.json"))
        shutil.copy(target_path, os.path.join(REMOTION_DIR, "src", "transcript_data.json"))
        return {"status": "success"}
    return {"error": "Transcript not found"}

@app.post("/api/process")
async def process_video(request: ProcessRequest, background_tasks: BackgroundTasks):
    with processes_lock:
        for v, s in active_processes.items():
            if s.url == request.url and s.status not in ["completed", "failed"]:
                return {"message": "Project already being processed", "version": v, "isDuplicate": True}

    version = int(time.time())
    state = get_or_create_state(version, request.url, user_id=request.user_id)
    state.version = version
    state.timestamp = version # Manual videos use version as timestamp
    background_tasks.add_task(run_pipeline, request.url, version)
    return {"message": "Processing started", "version": version}

@app.post("/api/reset")
async def reset_project(user_id: Optional[str] = None):
    """User-scoped reset."""
    if not user_id:
        return {"error": "user_id required for reset"}
        
    with processes_lock:
        # Remove this user's active processes
        to_delete = [v for v, s in active_processes.items() if s.user_id == user_id]
        for v in to_delete:
            del active_processes[v]

    import glob
    deleted_count = 0
    
    # Iterate over transcripts to find this user's versions
    for f_name in os.listdir(BASE_DIR):
        if f_name.startswith("transcript_") and f_name.endswith(".json"):
            if f_name == "transcript_data.json": continue
            version = f_name.replace("transcript_", "").replace(".json", "")
            
            try:
                with open(os.path.join(BASE_DIR, f_name), "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("user_id") == user_id:
                    # Found a version belonging to this user, delete all related files
                    patterns = [
                        f"transcript_{version}.json", 
                        f"video_{version}*", 
                        f"audio_{version}*", 
                        f"input_{version}.mp4",
                        f"output_{version}*", 
                        os.path.join(PUBLIC_DIR, f"transcript_{version}.json"),
                        os.path.join(PUBLIC_DIR, f"video_{version}*"), 
                        os.path.join(PUBLIC_DIR, f"audio_{version}*"),
                    ]
                    for p in patterns:
                        for f_path in glob.glob(p):
                            if os.path.isfile(f_path):
                                os.remove(f_path)
                                deleted_count += 1
            except: continue
            
    return {"message": "User projects wiped", "files_removed": deleted_count}

@app.get("/api/projects")
async def list_projects(user_id: Optional[str] = None):
    """Lists all projects with strict queue management and user isolation (Standard 3)."""
    projects = []
    
    # 1. Identify global queue state across ALL users
    with processes_lock:
        # All currently active items, sorted by system arrival time (timestamp)
        active_items = sorted(
            [(v, s) for v, s in active_processes.items() if s.status not in ["completed", "failed"]],
            key=lambda x: x[1].timestamp
        )
        all_active_versions = [str(v) for v, s in active_items]
        
        # 2. Add this user's active/failed tasks (but skip completed to avoid duplicates from disk)
        for v, state in active_processes.items():
            if state.status == "completed": continue
            if user_id and state.user_id != user_id:
                continue
                
            item = state.to_dict()
            # Global priority logic: only the oldest active in SYSTEM is "active"
            if all_active_versions and str(v) != all_active_versions[0]:
                if item["status"] == "queued": # Only set message if still in queue
                    item["message"] = "En cola de espera (Gubernamental)..."
            
            projects.append(item)

    # 3. Gather completed projects from disk with deep user-isolation check
    active_versions = set(p["version"] for p in projects)
    try:
        for f_name in os.listdir(BASE_DIR):
            if f_name.startswith("transcript_") and f_name.endswith(".json"):
                if f_name == "transcript_data.json": continue
                version = f_name.replace("transcript_", "").replace(".json", "")
                if version in active_versions: continue
                
                try:
                    with open(os.path.join(BASE_DIR, f_name), "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # Security Check: Only include if user matches
                    if user_id and data.get("user_id") != user_id:
                        continue
                        
                    projects.append({
                        "version": version,
                        "title": data.get("video_title") or data.get("clips", [{}])[0].get("title", f"Project {version}"),
                        "status": "completed", 
                        "timestamp": int(version) if version.isdigit() else 0,
                        "isActive": False
                    })
                except: continue
    except: pass
            
    # 4. Global Priority Sort: Active first (by newest timestamp), then completed (newest first)
    projects.sort(key=lambda x: (not x.get("isActive", False), -float(x.get("timestamp", 0))))
    return projects

@app.delete("/api/project/{version}")
async def delete_project(version: str, user_id: Optional[str] = None):
    """Deletes files with user-ownership validation."""
    # Verify ownership before deletion
    with processes_lock:
        if version in active_processes:
            if user_id and active_processes[version].user_id != user_id:
                raise HTTPException(status_code=403, detail="Unauthorized to delete this project")
    
    # Check physical file for ownership if not in memory
    t_path = os.path.join(BASE_DIR, f"transcript_{version}.json")
    if os.path.exists(t_path):
        try:
            with open(t_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if user_id and data.get("user_id") != user_id:
                    raise HTTPException(status_code=403, detail="Unauthorized to delete this project")
        except: pass
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
async def get_status(version: Optional[str] = None, user_id: Optional[str] = None):
    # Returns the status of a specific version, or the most recent active one
    with processes_lock:
        if version and version in active_processes:
            state = active_processes[version]
            if user_id and state.user_id != user_id:
                raise HTTPException(status_code=403, detail="Unauthorized")
            return state.to_dict()
        
        # Default to the most recent active process of THIS user
        if active_processes:
            user_actives = [s for v, s in active_processes.items() if (not user_id or s.user_id == user_id)]
            if user_actives:
                latest = max(user_actives, key=lambda s: float(s.timestamp) if s.timestamp else 0)
                return latest.to_dict()
            
    return {"status": "idle", "message": "No active tasks found."}

@app.get("/api/transcript/{version}")
async def get_transcript_version(version: str, user_id: Optional[str] = None):
    path = os.path.join(BASE_DIR, f"transcript_{version}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if user_id and data.get("user_id") != user_id:
                raise HTTPException(status_code=403, detail="Unauthorized")
            return data
    return {"error": "Transcript not found"}

@app.get("/api/transcript")
async def get_transcript():
    if os.path.exists(TRANSCRIPT_PATH):
        with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"error": "Transcript not found"}

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
    print(f"\n[SERVER] Recibida solicitud de renderizado para versión: {request.version} (User: {request.user_id})")
    
    # Ownership Check
    t_path = os.path.join(BASE_DIR, f"transcript_{request.version}.json")
    if os.path.exists(t_path):
        with open(t_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("user_id") and data.get("user_id") != request.user_id:
                raise HTTPException(status_code=403, detail="Unauthorized to render this project")

    background_tasks.add_task(do_render_queue, request.version, request.indices)
    return {"message": "Render started for selected clips"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
