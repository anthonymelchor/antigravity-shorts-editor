import os
import subprocess
import threading
import json
import time
import sys
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
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

# StaticFiles removed — media now served via authenticated /api/media endpoint

BASE_DIR = os.getcwd()
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)

import unicodedata
import re as _re

def slugify(text, max_length=60):
    """Convert text to a clean folder name: lowercase, underscores, no special chars.
    Example: '¿Cómo Ganar Dinero en 2026?' -> 'como_ganar_dinero_en_2026'
    """
    if not text:
        return "untitled"
    # Normalize unicode (é -> e, ñ -> n, etc.)
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    # Lowercase
    text = text.lower()
    # Replace any non-alphanumeric with underscore
    text = _re.sub(r'[^a-z0-9]+', '_', text)
    # Remove leading/trailing underscores
    text = text.strip('_')
    # Collapse multiple underscores
    text = _re.sub(r'_+', '_', text)
    # Truncate to max length (at word boundary)
    if len(text) > max_length:
        text = text[:max_length].rsplit('_', 1)[0]
    return text or "untitled"

def find_project_dir(version):
    """Find the project directory for a version. Handles both old (version-only) and new (slug_version) naming."""
    version_str = str(version)
    if not os.path.isdir(PROJECTS_DIR):
        return None
    # Direct match (old style: just version number)
    direct = os.path.join(PROJECTS_DIR, version_str)
    if os.path.isdir(direct):
        return direct
    # Search for folder ending with _{version}
    for name in os.listdir(PROJECTS_DIR):
        if name.endswith(f"_{version_str}") and os.path.isdir(os.path.join(PROJECTS_DIR, name)):
            return os.path.join(PROJECTS_DIR, name)
    return None


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
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import httpx

# Supabase Config for Server
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


# ============================================================
# AUTH: Supabase JWT Token Validation (Cached for Performance)
# ============================================================
_auth_cache = {}  # token_hash -> (user_id, expiry_timestamp)
AUTH_CACHE_TTL = 300  # 5 minutes

async def get_current_user(request: Request) -> str:
    """Validate Supabase JWT and extract user_id. Results are cached."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required. Send Bearer token.")
    
    token = auth_header[7:]  # Remove 'Bearer ' prefix
    token_key = hash(token)  # Use hash for cache key (don't store raw tokens)
    
    # Check cache first (fast path)
    if token_key in _auth_cache:
        user_id, expiry = _auth_cache[token_key]
        if time.time() < expiry:
            return user_id
        else:
            del _auth_cache[token_key]
    
    # Verify token with Supabase Auth API
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {token}"
            }
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        user_data = resp.json()
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user data in token")
    
    # Cache the result
    _auth_cache[token_key] = (user_id, time.time() + AUTH_CACHE_TTL)
    
    # Periodic cleanup of stale entries
    if len(_auth_cache) > 1000:
        now = time.time()
        stale = [k for k, (_, exp) in _auth_cache.items() if exp <= now]
        for k in stale:
            del _auth_cache[k]
    
    return user_id

def _validate_file_ownership(file_path: str, user_id: str) -> bool:
    """Check if a transcript file belongs to the given user."""
    if not os.path.exists(file_path):
        return False
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("user_id") == user_id
    except (json.JSONDecodeError, IOError):
        return False


@app.get("/api/discovery")
async def get_discovery_candidates(request: Request, niche: Optional[str] = None):
    user_id = await get_current_user(request)
    print(f"[DEBUG] Reached /api/discovery endpoint. user_id: {user_id}, niche: {niche}")
    """
    Fetches discovery candidates from Supabase. Always filtered by authenticated user.
    """
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    # Base URL — ALWAYS filter by authenticated user_id
    url = f"{SUPABASE_URL}/rest/v1/discovery_results?select=*,accounts(niche)&status=eq.discovered&order=views.desc&limit=50"
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
async def run_discovery(request: Request, limit: int = 5, background_tasks: BackgroundTasks = None):
    """
    Triggers the content discovery engine with real-time status tracking.
    """
    user_id = await get_current_user(request)
    discovery_id = f"discovery_{user_id}"
    
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
async def approve_candidate(candidate_id: int, request: Request):
    """
    Marks a discovery candidate as approved. Validates ownership.
    """
    user_id = await get_current_user(request)
    
    sb_headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    
    # Verify candidate belongs to this user
    verify_url = f"{SUPABASE_URL}/rest/v1/discovery_results?id=eq.{candidate_id}&select=user_id"
    async with httpx.AsyncClient() as client:
        verify_resp = await client.get(verify_url, headers=sb_headers)
        if verify_resp.status_code != 200 or not verify_resp.json():
            raise HTTPException(status_code=404, detail="Candidate not found")
        candidate_data = verify_resp.json()[0]
        if candidate_data.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="You don't own this candidate")
    
    # Now approve
    approve_url = f"{SUPABASE_URL}/rest/v1/discovery_results?id=eq.{candidate_id}"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.patch(approve_url, json={"status": "approved"}, headers={**sb_headers, "Prefer": "return=minimal"})
            if resp.status_code in [200, 201, 204]:
                return {"status": "success", "message": f"Candidate {candidate_id} approved for processing"}
            else:
                raise HTTPException(status_code=resp.status_code, detail=f"Supabase error: {resp.text}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

# Configuration
TRANSCRIPT_PATH = os.path.join(BASE_DIR, "transcript_data.json")
VIDEO_OUTPUT_PATH = os.path.join(BASE_DIR, "output_vertical_clip.mp4")
PUBLIC_DIR = os.path.join(BASE_DIR, "frontend", "public")
REMOTION_DIR = os.path.join(BASE_DIR, "remotion-app")

# SECURITY: Removed unsafe StaticFiles mount that exposed .env and all source code.
# Media files are served via Next.js from frontend/public/ directory.

ALLOWED_MEDIA_EXTENSIONS = {".mp4", ".wav", ".webm", ".jpg", ".png"}

@app.get("/api/media/{filename}")
async def serve_media(filename: str, request: Request):
    """Serve media files with ownership validation."""
    user_id = await get_current_user(request)
    
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_MEDIA_EXTENSIONS:
        raise HTTPException(status_code=403, detail="File type not allowed")
    
    safe_name = os.path.basename(filename)
    file_path = os.path.join(BASE_DIR, safe_name)
    
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    parts = safe_name.split("_")
    if len(parts) >= 2:
        version = parts[1]
        t_path = os.path.join(BASE_DIR, f"transcript_{version}.json")
        if os.path.exists(t_path) and not _validate_file_ownership(t_path, user_id):
            raise HTTPException(status_code=403, detail="You don't own this file")
    
    return FileResponse(file_path, media_type="application/octet-stream")

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
                if state.title and state.title != url:
                    cmd.extend(["--title", state.title])
                
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
                    
                    # Syncing files from projects/{version}/ to public dirs
                    import glob
                    proj_dir = find_project_dir(version) or os.path.join(PROJECTS_DIR, str(version))
                    clips_dir = os.path.join(proj_dir, "clips")
                    
                    T_OUT = os.path.join(proj_dir, "transcript.json")
                    if os.path.exists(T_OUT):
                        shutil.copy(T_OUT, os.path.join(PUBLIC_DIR, f"transcript_{version}.json"))
                    
                    # Sync clips from projects/{version}/clips/ to public dirs
                    if os.path.isdir(clips_dir):
                        for f in os.listdir(clips_dir):
                            src = os.path.join(clips_dir, f)
                            if os.path.isfile(src):
                                shutil.copy(src, os.path.join(PUBLIC_DIR, f))
                                shutil.copy(src, os.path.join(REMOTION_DIR, "public", f))
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
async def update_framing(update: FramingUpdate, request: Request):
    # Determine which file to update
    # Look in projects dir first, then fallback to root
    _proj_dir = find_project_dir(update.version)
    target_path = os.path.join(_proj_dir, "transcript.json") if _proj_dir else None
    if not target_path or not os.path.exists(target_path):
        target_path = os.path.join(BASE_DIR, f"transcript_{update.version}.json")
    
    if not os.path.exists(target_path):
        return {"error": "Transcript not found for this version"}

    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Ownership Check — use validated auth token
        auth_user_id = await get_current_user(request)
        if data.get("user_id") and data.get("user_id") != auth_user_id:
            raise HTTPException(status_code=403, detail="Unauthorized to update this transcript")
            
        if update.center is not None: data["center"] = update.center
        if update.layout is not None: data["layout"] = update.layout
        if update.framing_segments is not None: data["framing_segments"] = update.framing_segments
        
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        # Sync to public for frontend access
        shutil.copy(target_path, os.path.join(PUBLIC_DIR, f"transcript_{update.version}.json"))
        # Also sync to remotion for rendering
        shutil.copy(target_path, os.path.join(REMOTION_DIR, "src", "transcript_data.json"))
        return {"status": "success"}
    return {"error": "Transcript not found"}

@app.post("/api/process")
async def process_video(process_req: ProcessRequest, request: Request, background_tasks: BackgroundTasks):
    user_id = await get_current_user(request)
    
    with processes_lock:
        for v, s in active_processes.items():
            if s.url == process_req.url and s.status not in ["completed", "failed"]:
                return {"message": "Project already being processed", "version": v, "isDuplicate": True}

    version = int(time.time())
    state = get_or_create_state(version, process_req.url, user_id=user_id)
    state.version = version
    state.user_id = user_id
    state.timestamp = version
    background_tasks.add_task(run_pipeline, process_req.url, version)
    return {"message": "Processing started", "version": version}

@app.post("/api/reset")
async def reset_project(request: Request):
    """User-scoped reset. User determined from auth token."""
    user_id = await get_current_user(request)
        
    with processes_lock:
        # Remove this user's active processes
        to_delete = [v for v, s in active_processes.items() if s.user_id == user_id]
        for v in to_delete:
            del active_processes[v]

    import glob
    deleted_count = 0
    
    # Iterate over project directories to find this user's projects
    if os.path.isdir(PROJECTS_DIR):
        for folder_name in os.listdir(PROJECTS_DIR):
            proj_dir = os.path.join(PROJECTS_DIR, folder_name)
            t_path = os.path.join(proj_dir, "transcript.json")
            if not os.path.exists(t_path): continue
            
            try:
                with open(t_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("user_id") == user_id:
                    # Delete project directory
                    for root, dirs, files in os.walk(proj_dir):
                        deleted_count += len(files)
                    shutil.rmtree(proj_dir, ignore_errors=True)
                    
                    # Clean public copies
                    for pattern in [os.path.join(PUBLIC_DIR, f"*{version}*"),
                                    os.path.join(REMOTION_DIR, "public", f"*{version}*")]:
                        for f_path in glob.glob(pattern):
                            if os.path.isfile(f_path):
                                os.remove(f_path)
                                deleted_count += 1
            except: continue
            
    return {"message": "User projects wiped", "files_removed": deleted_count}

@app.get("/api/projects")
async def list_projects(request: Request):
    """Lists all projects with strict user isolation."""
    user_id = await get_current_user(request)
    projects = []
    
    # 1. Identify global queue state across ALL users
    with processes_lock:
        # All currently active items, sorted by system arrival time (timestamp)
        active_items = sorted(
            [(v, s) for v, s in active_processes.items() if s.status not in ["completed", "failed"]],
            key=lambda x: x[1].timestamp
        )
        all_active_versions = [str(v) for v, s in active_items]
        
        # 2. Add ONLY this user's active/failed tasks
        for v, state in active_processes.items():
            if state.status == "completed": continue
            if state.user_id != user_id:
                continue
                
            item = state.to_dict()
            # Global priority logic: only the oldest active in SYSTEM is "active"
            if all_active_versions and str(v) != all_active_versions[0]:
                if item["status"] == "queued": # Only set message if still in queue
                    item["message"] = "En cola de espera (Gubernamental)..."
            
            projects.append(item)

    # 3. Gather completed projects from projects/ directory
    active_versions = set(p["version"] for p in projects)
    try:
        if os.path.isdir(PROJECTS_DIR):
            for folder_name in os.listdir(PROJECTS_DIR):
                # Extract version from folder name (could be "slug_version" or just "version")
                parts = folder_name.rsplit("_", 1)
                version = parts[-1] if parts[-1].isdigit() else folder_name
                if version in active_versions: continue
                t_path = os.path.join(PROJECTS_DIR, folder_name, "transcript.json")
                if not os.path.exists(t_path): continue
                
                try:
                    with open(t_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # Security Check: ALWAYS filter by authenticated user
                    if data.get("user_id") != user_id:
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
async def delete_project(version: str, request: Request):
    """Deletes files with strict user-ownership validation."""
    user_id = await get_current_user(request)
    
    # Verify ownership in memory
    with processes_lock:
        if version in active_processes:
            if active_processes[version].user_id != user_id:
                raise HTTPException(status_code=403, detail="Unauthorized to delete this project")
    
    # Verify ownership in physical file
    proj_dir = find_project_dir(version) or os.path.join(PROJECTS_DIR, version)
    t_path = os.path.join(proj_dir, "transcript.json")
    if os.path.exists(t_path):
        try:
            with open(t_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("user_id") and data.get("user_id") != user_id:
                    raise HTTPException(status_code=403, detail="Unauthorized to delete this project")
        except HTTPException:
            raise
        except (json.JSONDecodeError, IOError):
            pass
    
    # Remove from active processes
    with processes_lock:
        if version in active_processes:
            del active_processes[version]
        try:
            v_int = int(version)
            if v_int in active_processes:
                del active_processes[v_int]
        except: pass

    deleted_count = 0
    
    # Delete project directory (all files at once)
    if os.path.isdir(proj_dir):
        import glob
        for root, dirs, files in os.walk(proj_dir):
            deleted_count += len(files)
        shutil.rmtree(proj_dir, ignore_errors=True)
    
    # Also clean public dirs of any synced copies
    import glob
    for pattern in [
        os.path.join(PUBLIC_DIR, f"*{version}*"),
        os.path.join(REMOTION_DIR, "public", f"*{version}*"),
    ]:
        for f in glob.glob(pattern):
            if os.path.isfile(f):
                try: 
                    os.remove(f)
                    deleted_count += 1
                except: pass
            
    return {"message": f"Project {version} deleted", "files_removed": deleted_count}

@app.get("/api/status")
async def get_status(request: Request, version: Optional[str] = None):
    user_id = await get_current_user(request)
    
    # Returns the status of a specific version, or the most recent active one
    with processes_lock:
        if version and version in active_processes:
            state = active_processes[version]
            if state.user_id and state.user_id != user_id:
                raise HTTPException(status_code=403, detail="Unauthorized")
            return state.to_dict()
        
        # Default to the most recent active process of THIS user ONLY
        if active_processes:
            user_actives = [s for v, s in active_processes.items() if s.user_id == user_id]
            if user_actives:
                latest = max(user_actives, key=lambda s: float(s.timestamp) if s.timestamp else 0)
                return latest.to_dict()
            
    return {"status": "idle", "message": "No active tasks found."}

@app.get("/api/transcript/{version}")
async def get_transcript_version(version: str, request: Request):
    user_id = await get_current_user(request)
    
    path = os.path.join(BASE_DIR, f"transcript_{version}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("user_id") and data.get("user_id") != user_id:
                raise HTTPException(status_code=403, detail="Unauthorized: this project belongs to another user")
            return data
    return {"error": "Transcript not found"}

# REMOVED: Global /api/transcript endpoint (security risk)
# All transcript access now requires version + auth

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
                        # Save to public for serving
                        shutil.copy(final_out, os.path.join(PUBLIC_DIR, dest_file))
                        # Also save to project renders dir
                        _r_proj = find_project_dir(version_id)
                        renders_dir = os.path.join(_r_proj, "renders") if _r_proj else os.path.join(PROJECTS_DIR, str(version_id), "renders")
                        os.makedirs(renders_dir, exist_ok=True)
                        shutil.copy(final_out, os.path.join(renders_dir, f"out_clip_{idx+1}.mp4"))
                        log_file.write(f"[RENDER] Saved to {dest_file} + projects/{version_id}/renders/\n")
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
async def render_clips(render_req: RenderRequest, request: Request, background_tasks: BackgroundTasks):
    user_id = await get_current_user(request)
    print(f"\n[SERVER] Recibida solicitud de renderizado para versión: {render_req.version} (User: {user_id})")
    
    # Ownership Check with validated token
    _render_proj = find_project_dir(render_req.version)
    t_path = os.path.join(_render_proj, "transcript.json") if _render_proj else os.path.join(BASE_DIR, f"transcript_{render_req.version}.json")
    if os.path.exists(t_path):
        with open(t_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("user_id") and data.get("user_id") != user_id:
                raise HTTPException(status_code=403, detail="Unauthorized to render this project")

    background_tasks.add_task(do_render_queue, render_req.version, render_req.indices)
    return {"message": "Render started for selected clips"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
