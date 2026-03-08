import os
import subprocess
import threading
import json
import time
import sys
import logging
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil
import yt_dlp
from typing import Optional, List
from dotenv import load_dotenv
# from backend_pipeline_mid import translate_with_gemini_text # DELETED: Module no longer exists
from dotenv import load_dotenv

# Cargar .env
load_dotenv()

# Configuración de Logging para Renders
RENDER_LOG = "render.log"
render_logger = logging.getLogger("render_logger")
render_logger.setLevel(logging.INFO)
render_handler = logging.FileHandler(RENDER_LOG, encoding='utf-8')
render_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
render_logger.addHandler(render_handler)

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
    try:
        print(f"[RAW-REQUEST] {request.method} {request.url}") # Re-enabled for debugging
        response = await call_next(request)
        if response.status_code == 404:
            print(f"[404-DEBUG] Route not found: {request.url}")
        return response
    except Exception as e:
        import traceback
        error_msg = f"\n[CRITICAL-500] {time.ctime()} EXCEPTION AT {request.url}:\n{traceback.format_exc()}\n"
        print(error_msg)
        with open(APP_ERRORS_LOG, "a", encoding="utf-8") as f:
            f.write(error_msg)
        raise e # Let FastAPI handle the actual response

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
# ============================================================
# ACCOUNTS: Centralized Branding Data (Temporary Mock)
# ============================================================
HARDCODED_ACCOUNTS = [
    {"id": 1, "name": "dominatusmetas_", "niche": "Mentalidad y Éxito Masculino"},
    {"id": 2, "name": "reinventatemujer_", "niche": "Empoderamiento y Amor Propio Femenino"},
    {"id": 3, "name": "melchor_ia", "niche": "IA y Futuro"},
    {"id": 4, "name": "reglas.del.amor", "niche": "Relaciones y Psicología Masc."},
    {"id": 5, "name": "the_manifest_path", "niche": "Manifestación y Espiritualidad"},
    {"id": 6, "name": "juanlondono.marketing", "niche": "marketing digital"},
    {"id": 7, "name": "Ninguno", "niche": "sin etiqueta"}
]

def get_account_by_id(account_id):
    if account_id is None: return None
    try:
        acc_id = int(account_id)
        return next((a for a in HARDCODED_ACCOUNTS if a["id"] == acc_id), None)
    except: return None

async def get_current_user(request: Request) -> str:
    """Validate Supabase JWT and extract user_id. Results are cached."""
    auth_header = request.headers.get("authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.query_params.get("token", "")
        
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required. Send Bearer token or ?token= param.")
    
    token_key = hash(token)  # Use hash for cache key (don't store raw tokens)
    
    # Check cache first (fast path)
    if token_key in _auth_cache:
        user_id, expiry = _auth_cache[token_key]
        if time.time() < expiry:
            return user_id
        else:
            del _auth_cache[token_key]
    
    # Verify token with Supabase Auth API
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {token}"
                }
            )
            if resp.status_code != 200:
                print(f"[AUTH] Failed to verify token: {resp.status_code} - {resp.text}")
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            
            user_data = resp.json()
            user_id = user_data.get("id")
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid user data in token")
    except httpx.ConnectError as ce:
        print(f"[AUTH-CRITICAL] Cannot connect to Supabase: {ce}. Check your internet/DNS.")
        raise HTTPException(status_code=500, detail="Supabase connection failed")
    except Exception as e:
        print(f"[AUTH-ERROR] Unexpected: {e}")
        raise e
    
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
    Returns enriched data with scoring from the High-Intensity Discovery Engine.
    """
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    # Base URL — ALWAYS filter by authenticated user_id, sort by discovery_score (video_score) desc
    url = f"{SUPABASE_URL}/rest/v1/discovery_results?select=*,accounts(niche)&status=eq.discovered&order=discovery_score.desc&limit=50"
    url += f"&user_id=eq.{user_id}"
    
    if niche:
        pass  # Filter in memory below

    async with httpx.AsyncClient(timeout=30) as client:
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
                    
                    # Extract enriched scoring from metadata_json
                    meta = c.get('metadata_json', {}) or {}
                    
                    results.append({
                        "id": c.get('id'),
                        "title": c.get('title'),
                        "original_url": c.get('original_url'),
                        "views": c.get('views'),
                        "duration": c.get('duration'),
                        "niche": current_niche,
                        "status": c.get('status'),
                        # Enriched scoring data
                        "video_score": meta.get('video_score', c.get('discovery_score', 0)),
                        "tension_score": meta.get('tension_score', 0),
                        "comment_score": meta.get('comment_score', 0),
                        "description_score": meta.get('description_score', 0),
                        "classification": meta.get('classification', []),
                        "comment_count": meta.get('comment_count', 0),
                        "comment_ratio": meta.get('comment_ratio', 0),
                        "strategic_reasoning": meta.get('strategic_reasoning', ''),
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

# Consolidated Media Serving moved to the bottom for clarity and hierarchy.


# Multi-process Registry
active_processes = {} # version_id -> ProcessingState
active_render_procs = {} # key -> subprocess.Popen object
render_batch_canceled = set() # version_id -> True
processes_lock = threading.Lock()
process_semaphore = threading.Semaphore(1) # Only process 1 video at a time for efficiency

def format_duration(seconds):
    """Formats seconds into 'X min Y seg' or 'X seg'."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} seg"
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins} min {secs} seg"

class ProcessRequest(BaseModel):
    url: str
    user_id: Optional[str] = None
    niche: Optional[str] = None
    enable_bg_music: Optional[bool] = True

class ProcessingState:
    def __init__(self, url="", title="", user_id=None, niche=None):
        self.status = "queued" # queued, downloading, transcribing, analyzing, framing, completing, failed
        self.progress = 0
        self.message = "En cola de espera..."
        self.error = None
        self.url = url
        self.title = title
        self.version = None
        self.started_at = None
        self.user_id = user_id
        self.niche = niche
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
            "isActive": is_active,
            "niche": self.niche
        }

def get_or_create_state(version_id, url="", user_id=None, niche=None):
    with processes_lock:
        if version_id not in active_processes:
            active_processes[version_id] = ProcessingState(url=url, user_id=user_id, niche=niche)
            active_processes[version_id].version = version_id
        # Always ensure user_id is updated if we have a fresh one (resilience)
        if user_id:
            active_processes[version_id].user_id = user_id
        if niche:
            active_processes[version_id].niche = niche
        return active_processes[version_id]

class RenderRequest(BaseModel):
    version: str
    user_id: str
    indices: List[int]
    preferredLanguage: Optional[str] = 'es'

class FramingUpdate(BaseModel):
    version: str
    user_id: str
    center: float = None
    layout: str = None
    framing_segments: list = None
    clip_index: Optional[int] = None
    start: Optional[float] = None
    end: Optional[float] = None

class MetadataUpdate(BaseModel):
    version: str
    user_id: str
    account_id: Optional[int] = None
    is_podcast: Optional[bool] = None

class PublishedToggle(BaseModel):
    version: str
    clip_index: int
    published: bool

def run_pipeline(url: str, version: int, niche: Optional[str] = None, enable_bg_music: bool = True):
    # Use localized state for this process
    state = get_or_create_state(version, url, niche=niche)
    state.version = str(version)
    state.title = "Obteniendo información..."
    state.status = "queued"

    # Log Start for Observability (Standard 5)
    print(f"[START] Process {version} initiated for URL: {url}")

    # --- MODO TEST: Si la URL es la palabra 'test', evitamos llamar a yt-dlp ---
    if url and url.lower().strip() == "test":
        state.title = "Local Test Project"
        print(f"🧪 [MODO TEST] Saltando metadatos para input.mp4 local")
    else:
        try:
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
                if niche:
                    cmd.extend(["--niche", niche])
                cmd.extend(["--enable_bg_music", "true" if enable_bg_music else "false"])
                
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
                        
                        # Track progress via logs (Standard 5 - Observability & Smooth Progress Bar)
                        if "Downloading video" in line:
                            state.status = "downloading"
                            state.message = "Descargando video de YouTube..."
                            state.progress = 5
                        elif "[PHASE 1] Download completed" in line or "Video downloaded to" in line:
                            state.progress = 20
                        elif "Extracting audio" in line:
                            state.progress = 25
                        elif "Loading Whisper model" in line:
                            state.status = "transcribing"
                            state.message = "Cargando Motor IA Acústico..."
                            state.progress = 30
                        elif "Transcribing" in line or "Processing audio with duration" in line:
                            state.status = "transcribing"
                            state.message = "Transcribiendo audio inteligentemente..."
                            state.progress = 40
                        elif "[PHASE 2] Full Transcription" in line:
                            state.progress = 50
                        elif "Pidiendo a Gemini que analice el texto" in line:
                            state.status = "analyzing"
                            state.message = "Gemini seleccionando momentos virales..."
                            state.progress = 60
                        elif "[PHASE 3] Gemini Viral Text Analysis" in line:
                            state.progress = 75
                        elif "Processing Clip #" in line:
                            state.status = "framing"
                            state.message = "Rastreo y Edición Automática de Clips..."
                            state.progress = min(98, state.progress + 3) # Incremental smoothly up to 98%
                        elif "Starting Local HIGH-PRECISION Framing" in line:
                            state.status = "framing"
                            state.progress = 80
                        elif "Backend processing pipeline complete" in line or "PIPELINE FINISHED SUCCESSFULY" in line:
                            state.status = "completed"
                            state.message = "Procesamiento completado!"
                            state.progress = 100
                    
                    process.wait()

                    if process.returncode == 0:
                        end_time = time.time()
                        total_duration = end_time - state.started_at
                        duration_str = format_duration(total_duration)
                        
                        finish_msg = f"[END] Process {version} completed successfully in {duration_str}."
                        print(finish_msg)
                        log_file.write(f"\n{finish_msg}\n")
                        log_file.flush()
                        
                        state.status = "completed"
                        state.progress = 100
                        
                        # Syncing files from projects/{version}/ to public dirs
                        proj_dir = find_project_dir(version)
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
            
        if update.clip_index is not None:
            clips = data.get("clips", [])
            if 0 <= update.clip_index < len(clips):
                clip = clips[update.clip_index]
                if update.center is not None: clip["center"] = update.center
                if update.layout is not None: clip["layout"] = update.layout
                if update.framing_segments is not None: clip["framing_segments"] = update.framing_segments
                if update.start is not None: clip["start"] = max(0.0, update.start)
                if update.end is not None:
                    clip["end"] = update.end
                    clip["duration"] = max(0.1, update.end - clip.get("start", 0))
        else:
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

@app.get("/api/accounts")
async def list_accounts(request: Request):
    """Fetch available social media accounts from Supabase."""
    # user_id = await get_current_user(request) # Keep for future filtering
    return HARDCODED_ACCOUNTS
    
    '''
    # ... (Rest of Supabase code)
    '''


@app.post("/api/update-published")
async def update_published(update: PublishedToggle, request: Request):
    """Update published status for a specific clip."""
    user_id = await get_current_user(request)
    
    _proj_dir = find_project_dir(update.version)
    target_path = os.path.join(_proj_dir, "transcript.json") if _proj_dir else None
    if not target_path or not os.path.exists(target_path):
        target_path = os.path.join(BASE_DIR, f"transcript_{update.version}.json")
        
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Project not found")
        
    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if data.get("user_id") and data.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    clips = data.get("clips", [])
    if update.clip_index < 0 or update.clip_index >= len(clips):
        raise HTTPException(status_code=400, detail="Invalid clip index")
        
    clips[update.clip_index]["published"] = update.published
    data["clips"] = clips
    
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    # Sync to all consumers for consistency
    shutil.copy(target_path, os.path.join(REMOTION_DIR, "src", "transcript_data.json"))
    shutil.copy(target_path, os.path.join(BASE_DIR, "frontend", "src", "remotion", "transcript_data.json"))
    shutil.copy(target_path, os.path.join(PUBLIC_DIR, f"transcript_{update.version}.json"))
    
    return {"status": "success", "published": update.published}

@app.post("/api/update-metadata")
async def update_metadata(update: MetadataUpdate, request: Request):
    """Update project-wide metadata like account_id or is_podcast."""
    user_id = await get_current_user(request)
    
    _proj_dir = find_project_dir(update.version)
    target_path = os.path.join(_proj_dir, "transcript.json") if _proj_dir else None
    if not target_path or not os.path.exists(target_path):
        target_path = os.path.join(BASE_DIR, f"transcript_{update.version}.json")
        
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Project not found")
        
    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if data.get("user_id") and data.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    if update.account_id is not None:
        data["account_id"] = update.account_id
    if update.is_podcast is not None:
        data["is_podcast"] = update.is_podcast
        
    if update.account_id is not None:
        acc = get_account_by_id(update.account_id)
        if acc:
            data["instagram_handle"] = acc.get("name")
            data["niche_name"] = acc.get("niche")
        
        '''
        # (Supabase code commented out)
        '''

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Sync to all consumers
    # 1. Rendering Engine
    shutil.copy(target_path, os.path.join(REMOTION_DIR, "src", "transcript_data.json"))
    # 2. Frontend Live Preview (Neural Preview Engine)
    shutil.copy(target_path, os.path.join(BASE_DIR, "frontend", "src", "remotion", "transcript_data.json"))
    # 3. Public Download Asset
    shutil.copy(target_path, os.path.join(PUBLIC_DIR, f"transcript_{update.version}.json"))
    
    return {
        "status": "success", 
        "data": {
            "account_id": data.get("account_id"), 
            "is_podcast": data.get("is_podcast"),
            "instagram_handle": data.get("instagram_handle"),
            "niche_name": data.get("niche_name")
        }
    }

@app.post("/api/process")
async def process_video(process_req: ProcessRequest, request: Request, background_tasks: BackgroundTasks):
    user_id = await get_current_user(request)
    
    with processes_lock:
        for v, s in active_processes.items():
            if s.url == process_req.url and s.status not in ["completed", "failed"]:
                return {"message": "Project already being processed", "version": v, "isDuplicate": True}

    version = int(time.time())
    state = get_or_create_state(version, process_req.url, user_id=user_id, niche=process_req.niche)
    state.version = version
    state.user_id = user_id
    state.timestamp = version
    background_tasks.add_task(run_pipeline, process_req.url, version, process_req.niche, process_req.enable_bg_music if process_req.enable_bg_music is not None else True)
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


@app.get("/api/media/{version}/{filename}")
async def serve_media(version: str, filename: str, request: Request):
    """Secure Unified Media Serving with User Isolation."""
    user_id = await get_current_user(request)
    
    proj_dir = find_project_dir(version)
    if not proj_dir:
        # Fallback to root directory if no project folder found (Legacy support)
        file_path = os.path.join(BASE_DIR, os.path.basename(filename))
        if os.path.exists(file_path):
            # Check ownership on root transcripts if available
            t_root = os.path.join(BASE_DIR, f"transcript_{version}.json")
            if os.path.exists(t_root) and not _validate_file_ownership(t_root, str(user_id)):
                raise HTTPException(status_code=403, detail="Access denied")
            return FileResponse(file_path)
        raise HTTPException(status_code=404, detail="Project or file not found")
        
    # Verify ownership via transcript.json inside the project
    t_path = os.path.join(proj_dir, "transcript.json")
    if os.path.exists(t_path):
        try:
            with open(t_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Cast to str to ensure match with Supabase UUID strings
                if data.get("user_id") and str(data.get("user_id")) != str(user_id):
                    print(f"[SECURITY] Blocking user {user_id} access to {filename} in {version}")
                    raise HTTPException(status_code=403, detail="Unauthorized access to this media")
        except HTTPException: raise
        except: pass
    
    # Locate the file (Root -> Clips -> Renders)
    search_dirs = [proj_dir, os.path.join(proj_dir, "clips"), os.path.join(proj_dir, "renders")]
    for d in search_dirs:
        file_path = os.path.join(d, filename)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            # Pro tip: FileResponse handles 'Range' internally for zero-lag seeking
            return FileResponse(file_path)
            
    print(f"[MEDIA] File {filename} NOT found in project {version}")
    raise HTTPException(status_code=404, detail=f"File {filename} not found")

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
            
            # Skip sub-tasks (renders) as they are handled within the parent project card logic below
            if str(v).startswith("render_"):
                continue
                
            item = state.to_dict()
            # Global priority logic: only the oldest active in SYSTEM is "active"
            if all_active_versions and str(v) != all_active_versions[0]:
                if item["status"] == "queued": # Only set message if still in queue
                    item["message"] = "En cola de espera (Gubernamental)..."
            
            item["canOpen"] = False # New projects cannot be opened until transcript exists
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
                        
                    # Proactive Niche Recovery
                    niche = data.get("niche_name") or data.get("niche")
                    if not niche or niche == "General":
                        # Try to find it in meta or handle-based logic if we wanted, 
                        # but for now we look for 'niche_name' or 'niche'.
                        niche = data.get("niche_name") or data.get("niche") or "General"

                    clips = data.get("clips", [])
                    total_clips = len(clips)
                    published_clips = sum(1 for c in clips if c.get("published"))

                    # Check if project has active renders
                    render_keys = [k for k, s in active_processes.items() if str(k).startswith(f"render_{version}_") and s.status in ["queued", "rendering"]]
                    
                    is_rendering = bool(render_keys)
                    render_progress = 0
                    render_status = "completed"
                    render_msg = "Completed"
                    
                    if is_rendering:
                        active_renders = [active_processes[k] for k in render_keys]
                        # Only report as rendering if at least one is actually rendering. Else queued.
                        if any(r.status == "rendering" for r in active_renders):
                            render_status = "rendering"
                            # Average progress of rendering clips, min 5 to show bar
                            render_progress = max(5, int(sum(r.progress for r in active_renders) / len(active_renders)))
                            render_msg = "Renderizando clips..."
                        else:
                            render_status = "queued"
                            render_progress = 0
                            render_msg = "En cola de renderizado..."

                    projects.append({
                        "version": version,
                        "title": data.get("video_title") or (clips[0].get("title") if clips else f"Project {version}"),
                        "status": "rendering" if is_rendering else "completed", # Always 'rendering' on dashboard
                        "realStatus": render_status if is_rendering else "completed", # Detailed status for internal use
                        "message": "Renderizando..." if is_rendering else "Ready",
                        "progress": render_progress,
                        "timestamp": int(version) if version.isdigit() else 0,
                        "isActive": is_rendering,
                        "niche": niche,
                        "published_count": published_clips,
                        "total_clips": total_clips,
                        "canOpen": True # Existing projects can always be opened
                    })
                except: continue
    except: pass
            
    # 4. Global Priority Sort: Completed projects (newest first). Active processes do not jump to top.
    projects.sort(key=lambda x: -float(x.get("timestamp", 0)))
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
        if version:
            v_norm = str(version)
            # Check for batch render tasks
            project_renders = []
            for k, s in active_processes.items():
                k_str = str(k)
                if k_str.startswith(f"render_{v_norm}_"):
                    project_renders.append(s.to_dict())
            
            if project_renders:
                # If there are renders (active or completed), return them.
                active_sum = [r for r in project_renders if r["status"] in ["queued", "rendering"]]
                
                # Determine overall status: rendering > queued > completed
                overall_status = "completed"
                if any(r["status"] == "rendering" for r in project_renders):
                    overall_status = "rendering"
                elif any(r["status"] == "queued" for r in project_renders):
                    overall_status = "queued"
                
                avg_progress = 100
                if active_sum:
                    avg_progress = int(sum(r["progress"] for r in active_sum) / len(active_sum))
                
                return {
                    "status": overall_status,
                    "progress": avg_progress,
                    "message": "Renderizando clips..." if overall_status == "rendering" else ("En cola..." if overall_status == "queued" else "Renderizado completado"),
                    "active_clips": project_renders,
                    "version": version
                }

            if version in active_processes:
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
    
    _proj_dir = find_project_dir(version)
    target_path = os.path.join(_proj_dir, "transcript.json") if _proj_dir else None
    if not target_path or not os.path.exists(target_path):
        target_path = os.path.join(BASE_DIR, f"transcript_{version}.json")
        
    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if data.get("user_id") and data.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")
            
        # Enrich with account handle and niche name if account_id exists
        account_id = data.get("account_id")
        if account_id:
            acc = get_account_by_id(account_id)
            if acc:
                data["instagram_handle"] = acc.get("name")
                data["niche_name"] = acc.get("niche")
                
                # PERSIST back to disk so Remotion sees it next time
                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    
                # Sync to all consumers for immediate consistency
                shutil.copy(target_path, os.path.join(REMOTION_DIR, "src", "transcript_data.json"))
                shutil.copy(target_path, os.path.join(BASE_DIR, "frontend", "src", "remotion", "transcript_data.json"))
            
            '''
            # ... (Supabase code commented out)
            '''

        return data
    raise HTTPException(status_code=404, detail="Transcript not found")

# REMOVED: Global /api/transcript endpoint (security risk)
# All transcript access now requires version + auth

def do_render_queue(version_id, clip_indices, preferredLanguage='es', proj_title=None):
    log_file_path = os.path.join(BASE_DIR, f"pipeline_{version_id}.log")
    
    # Requirement: HIGH-PRECISION Style HEADER (MATCHING PIPELINE.LOG)
    if not proj_title:
        proj_title = f"{version_id}"
        
    try:
        with open(RENDER_LOG, "a", encoding="utf-8") as f:
            f.write("\n")
            f.write("╔══════════════════════════════════════════════════════════════════════════╗\n")
            f.write(f"║                    🎬 [START BATCH RENDER] {time.strftime('%H:%M:%S')}              ║\n")
            f.write("╚══════════════════════════════════════════════════════════════════════════╝\n")
            f.write(f"   🎥 PROYECTO: {proj_title}\n")
            f.write(f"   🎞️ CLIPS   : {clip_indices}\n")
            f.write(f"   🌐 IDIOMA  : {preferredLanguage.upper()}\n")
            f.write("   ──────────────────────────────────────────────────────────────────────────\n\n")
    except:
        pass
    
    with open(log_file_path, "a", encoding="utf-8") as log_file:
        log_file.write(f"\n\n[RENDER] Starting Batch Render for version {version_id}. Indices: {clip_indices}\n")
        log_file.flush()
        
        # Wait for turn in the UNIFIED queue (Semaphore 1)
        # This fulfills Requirement #3: All processes (YT download + Render) share one queue.
        log_file.write(f"[QUEUE] Render batch waiting for semaphore...\n")
        with process_semaphore:
            log_file.write(f"[QUEUE] Render batch is now ACTIVE\n")
            log_file.flush()
            
            batch_start_time = time.time()
            
            for idx in clip_indices:
                # BREAK loop if batch was canceled
                if str(version_id) in render_batch_canceled:
                    render_logger.warning(f"RENDER BATCH ABORTED for version {version_id} (User Stop)")
                    break

                clip_key = f"render_{version_id}_{idx}"
                render_state = get_or_create_state(clip_key)
                if render_state.status == "rendering":
                    log_file.write(f"[RENDER] Skip Clip #{idx+1} - Busy\n")
                    continue
                    
                try:
                    clip_start_time = time.time()
                    render_state.status = "rendering"
                    render_state.message = f"Starting Clip #{idx+1}..."
                    render_state.progress = 5
                    
                    header = "="*50 + f"\n[RENDER] PROYECTO: {proj_title} | CLIP: #{idx+1}\n" + "="*50 + "\n"
                    log_file.write(header)
                    log_file.flush()
                    render_logger.info(f"Clip {idx+1}/{len(clip_indices)} start for project '{proj_title}'...")
                        
                    # Use version-specific transcript from projects dir
                    proj_dir = find_project_dir(version_id)
                    if not proj_dir:
                        msg = f"Project directory for {version_id} not found."
                        render_state.status = "failed"
                        render_state.error = msg
                        log_file.write(f"[RENDER] ERROR: {msg}\n")
                        continue
                        
                    t_path = os.path.join(proj_dir, "transcript.json")
                    if not os.path.exists(t_path):
                        msg = f"Original transcript {t_path} not found."
                        render_state.status = "failed"
                        render_state.error = msg
                        log_file.write(f"[RENDER] ERROR: {msg}\n")
                        continue
    
                    with open(t_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f) # Renamed 'data' to 'manifest' for clarity
                    
                    # Prepare clip_data for Remotion
                    clip_data = {
                        "words": [],
                        "words_es": [],
                        "video_url": None,
                        "audio_url": None,
                        "edit_events": {},
                        "duration": 30,
                        "layout": "single",
                        "center": 0.5,
                        "center_top": 0.5,
                        "center_bottom": 0.5,
                        "framing_segments": [],
                        "preferredLanguage": preferredLanguage
                    }
    
                    # If clip_index is provided, override root fields for Remotion parity
                    if "clips" in manifest and idx < len(manifest["clips"]):
                        clip = manifest["clips"][idx]
                        clip_data.update({
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
                            "framing_segments": clip.get("framing_segments", []),
                        })
                        log_file.write(f"[RENDER] Clip fields updated from index {idx}\n")
                    
                    # Enrich clip_data with real branding handle and niche if account_id is present
                    account_id = manifest.get("account_id")
                    if account_id:
                        acc = get_account_by_id(account_id)
                        if acc:
                            clip_data["instagram_handle"] = acc.get("name")
                            clip_data["niche_name"] = acc.get("niche")
                        
                        '''
                        # ... (Supabase code commented out)
                        '''
    
                    # 1. Save Isolated Transcript for this specific render instance
                    props_filename = f"props_{version_id}_{idx}.json"
                    props_path = os.path.join(REMOTION_DIR, props_filename)
                    with open(props_path, "w", encoding="utf-8") as f:
                        json.dump({"transcript": clip_data, "preferredLanguage": preferredLanguage}, f, ensure_ascii=False, indent=2)
                    
                    # Also keep the shared file updated for backward compatibility/legacy Studio watchers
                    # though 'props' will take priority in modern Root.tsx
                    with open(os.path.join(REMOTION_DIR, "src", "transcript_data.json"), "w", encoding="utf-8") as f:
                        json.dump(clip_data, f, ensure_ascii=False, indent=2)

                    v_name = clip_data.get("video_url")
                    a_name = clip_data.get("audio_url")
    
                    v_path = os.path.join(proj_dir, "clips", v_name) if v_name and v_name.startswith("video") else os.path.join(proj_dir, v_name)
                    if not v_name or not os.path.exists(v_path):
                        msg = f"Video file {v_name} not found."
                        render_state.status = "failed"
                        render_state.error = msg
                        log_file.write(f"[RENDER] ERROR: {msg}\n")
                        if os.path.exists(props_path): os.remove(props_path)
                        continue
    
                    # 2. Media to Remotion public
                    remotion_public = os.path.join(REMOTION_DIR, "public")
                    shutil.copy(v_path, os.path.join(remotion_public, v_name))
                    a_path = os.path.join(proj_dir, "clips", a_name) if a_name and a_name.startswith("audio") else os.path.join(proj_dir, a_name)
                    if a_name and os.path.exists(a_path):
                        shutil.copy(a_path, os.path.join(remotion_public, a_name))
                    
                    # IMPORTANT: Delete previous render output to avoid stale copies if build fails
                    final_out = os.path.join(REMOTION_DIR, "out.mp4")
                    if os.path.exists(final_out):
                        try: os.remove(final_out)
                        except: pass
    
                    render_state.message = f"Building Clip #{idx+1}..."
                    render_state.progress = 20
                    log_file.write(f"[RENDER] Running Remotion build for Clip #{idx+1} (Using isolated props: {props_filename})...\n")
                    log_file.flush()
                    
                    # Using isolated props file to prevent race conditions (Totalmente Diferente BUG)
                    render_cmd = ["npx", "remotion", "render", "src/index.ts", "ShortVideo", "out.mp4",
                                  f"--props={props_filename}", "--concurrency=4", "--force"]

                    # shell=True required on Windows for npx to resolve correctly
                    # shell=False on Linux/Ubuntu for proper process tree and SIGTERM support
                    _use_shell = sys.platform == "win32"
                    
                    # NOTE: We use text=True but specify universal newlines to catch '\r' natively without byte-by-byte overhead
                    import io
                    process = subprocess.Popen(
                        render_cmd,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=False,
                        cwd=REMOTION_DIR, shell=_use_shell
                    )
                    
                    # Wrap stdout in an TextIOWrapper that translates \r into \n dynamically
                    # This prevents Python from stalling on Remotion's progress lines but is 1000x faster than reading byte-by-byte
                    stdout_wrapper = io.TextIOWrapper(process.stdout, encoding='utf-8', errors='ignore', newline='')
                    
                    # Track for cancellation
                    with processes_lock:
                        active_render_procs[clip_key] = process
                    
                    import re
                    has_started_rendering = False
                    
                    # Read chunked blocks of characters directly
                    buf = ""
                    while True:
                        chunk = stdout_wrapper.read(128) # small efficient chunks
                        if not chunk:
                            break
                        
                        buf += chunk
                        # Remotion progress outputs \r to overwrite carriage. We split by it or \n.
                        if '\r' in buf or '\n' in buf:
                            # Use regex or simple replace to normalize splits, then process lines
                            lines = buf.replace('\r', '\n').split('\n')
                            # Keep the last segment in the buffer since it might be incomplete
                            buf = lines.pop()
                            
                            for line in lines:
                                line = line.strip()
                                if not line:
                                    continue
                                    
                                if "Rendering video" in line and not has_started_rendering:
                                    render_state.progress = 50
                                    render_state.message = f"Rendering Clip #{idx+1}..."
                                    log_file.write(f"[RENDER] Final rendering phase started for Clip #{idx+1}...\n")
                                    log_file.flush()
                                    has_started_rendering = True
                                    
                                if has_started_rendering:
                                    # Standard remotion output has forms like: "16x 1354/1354 (100%)"
                                    m = re.search(r"\((\d+)%\)", line)
                                    if m:
                                        p = int(m.group(1))
                                        render_state.progress = 50 + int(p / 2)
                                
                                # Only print true lines to terminal, avoids spamming same line over and over
                                if "x" not in line and "%" not in line: 
                                    print(f"[Remotion-Internal] {line}")
                                    
                    process.wait()
                    
                    # ALWAYS cleanup temporary props file
                    if os.path.exists(props_path):
                        try: os.remove(props_path)
                        except: pass
                    
                    # Remove from tracking
                    with processes_lock:
                        if clip_key in active_render_procs:
                            del active_render_procs[clip_key]

                    if process.returncode == 0:
                        clip_end_time = time.time()
                        clip_duration = clip_end_time - clip_start_time
                        duration_str = format_duration(clip_duration)
                        
                        render_state.status = "completed"
                        render_state.message = f"Clip #{idx+1} Ready!"
                        render_state.progress = 100
                        log_file.write(f"[RENDER] SUCCESS: Clip #{idx+1} completed in {duration_str}.\n\n")
                        render_logger.info(f"Clip {idx+1} SUCCESS for version {version_id} in {duration_str}")
                        
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
                        render_logger.error(f"Clip {idx+1} FAILED for version {version_id}")
                        
                except Exception as e:
                    render_state.status = "failed"
                    render_state.message = f"Error: {str(e)}"
                    log_file.write(f"[RENDER] EXCEPTION: {str(e)}\n")
                    render_logger.exception(f"Clip {idx+1} EXCEPTION for version {version_id}: {str(e)}")
                log_file.flush()
        
        batch_total_time = time.time() - batch_start_time
        total_str = format_duration(batch_total_time)
        
        # High-visibility Footer in RENDER.LOG (PIPELINE Style)
        try:
            with open(RENDER_LOG, "a", encoding="utf-8") as f:
                f.write("\n")
                f.write(f"   🏁 [FINISH BATCH RENDER] {time.strftime('%H:%M:%S')}\n")
                f.write(f"   ⏱️ TIEMPO TOTAL: {total_str}\n")
                f.write(f"   🎥 PROYECTO    : {proj_title}\n")
                f.write("   ──────────────────────────────────────────────────────────────────────────\n\n")
        except: pass

        log_file.write(f"\n" + "-"*50 + f"\n[BATCH END] Renderizado de tanda completado en {total_str}\n" + "-"*50 + "\n")
        log_file.flush()

    # Clean up cancellation flag if set
    with processes_lock:
        if str(version_id) in render_batch_canceled:
            render_batch_canceled.remove(str(version_id))

    render_logger.info(f"END BATCH RENDER: Version {version_id} in {total_str}")

@app.post("/api/render")
async def render_clips(render_req: RenderRequest, request: Request, background_tasks: BackgroundTasks):
    user_id = await get_current_user(request)
    print(f"\n[SERVER] Recibida solicitud de renderizado para versión: {render_req.version} (User: {user_id})")
    
    # Ownership Check with validated token
    _render_proj = find_project_dir(render_req.version)
    t_path = os.path.join(_render_proj, "transcript.json") if _render_proj else os.path.join(BASE_DIR, f"transcript_{render_req.version}.json")
    p_title = None
    if os.path.exists(t_path):
        with open(t_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("user_id") and data.get("user_id") != user_id:
                raise HTTPException(status_code=403, detail="Unauthorized to render this project")
            p_title = data.get("title")

    # Initialize queued state for visual feedback
    for idx in render_req.indices:
        state = get_or_create_state(f"render_{render_req.version}_{idx}", None, user_id=user_id)
        if state.status not in ["rendering"]:
            state.status = "queued"
            state.progress = 0
            state.message = "Esperando turno..."
            state.timestamp = time.time()  # Important for global sorting priority
            
    background_tasks.add_task(do_render_queue, render_req.version, render_req.indices, render_req.preferredLanguage, p_title)
    return {"message": "Render started for selected clips"}

@app.post("/api/cancel-render")
async def cancel_render(request: Request):
    """Emergency kill for all active render processes."""
    user_id = await get_current_user(request)
    render_logger.info(f"CANCEL RENDER REQUESTED by user: {user_id}")
    
    killed_count = 0
    canceled_names = set()
    with processes_lock:
        # We kill EVERY active render process currently tracked
        for key, proc in list(active_render_procs.items()):
            try:
                # Add version to cancellation set to stop do_render_queue loop
                v_id = None
                try:
                    v_id = key.split("_")[1]
                    render_batch_canceled.add(str(v_id))
                except: pass

                # Determine PROJECT NAME for logging
                try:
                    p_name = f"{v_id}"
                    _pd = find_project_dir(v_id)
                    _tp = os.path.join(_pd, "transcript.json") if _pd else os.path.join(BASE_DIR, f"transcript_{v_id}.json")
                    if os.path.exists(_tp):
                        with open(_tp, "r", encoding="utf-8") as tf:
                            p_name = json.load(tf).get("title") or v_id
                    canceled_names.add(p_name)
                except: pass

                # On Windows, taskkill is often safer for shell=True processes
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], check=False)
                else:
                    proc.terminate()
                
                # Mark state as failed/cancelled
                if key in active_processes:
                    state = active_processes[key]
                    state.status = "failed"
                    state.message = "Render Cancelado por el Usuario"
                    state.error = "Proceso terminado manualmente."
                
                del active_render_procs[key]
                killed_count += 1
            except Exception as e:
                render_logger.error(f"Error killing process {key}: {e}")

    # Log to render.log (Fancy Cancel Banner)
    projs_str = ", ".join(canceled_names) if canceled_names else "Desconocido"
    try:
        with open(RENDER_LOG, "a", encoding="utf-8") as f:
            f.write("\n")
            f.write("   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")
            f.write(f"   🛑 [CANCEL BATCH RENDER] {time.strftime('%H:%M:%S')}\n")
            f.write(f"   🎥 PROYECTO: {projs_str}\n")
            f.write(f"   ℹ️ DETALLE : {killed_count} procesos terminados por el usuario.\n")
            f.write("   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\n")
    except:
        render_logger.warning(f"Failed to write cancel log via file - using logger as fallback.")

    return {"status": "success", "message": f"Se detuvieron {killed_count} procesos de renderizado."}

class PreviewRemotionRequest(BaseModel):
    version: str
    clip_index: int
    preferredLanguage: str = "es"

remotion_studio_proc = None

@app.post("/api/preview-remotion")
async def start_remotion_preview(req: PreviewRemotionRequest, request: Request):
    user_id = await get_current_user(request)
    
    _proj_dir = find_project_dir(req.version)
    target_path = os.path.join(_proj_dir, "transcript.json") if _proj_dir else os.path.join(BASE_DIR, f"transcript_{req.version}.json")
    
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Transcript not found")
        
    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if data.get("user_id") and data.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    clips = data.get("clips", [])
    if req.clip_index >= len(clips):
        raise HTTPException(status_code=404, detail="Clip index out of range")
        
    clip_data = clips[req.clip_index].copy()
    for k, v in data.items():
        if k != "clips" and k not in clip_data:
            clip_data[k] = v
            
    clip_data["preferredLanguage"] = req.preferredLanguage

    account_id = data.get("account_id")
    if account_id:
        acc = get_account_by_id(account_id)
        if acc:
            clip_data["instagram_handle"] = acc.get("name")
            clip_data["niche_name"] = acc.get("niche")

    remotion_src_tr = os.path.join(REMOTION_DIR, "src", "transcript_data.json")
    with open(remotion_src_tr, "w", encoding="utf-8") as f:
        json.dump(clip_data, f, ensure_ascii=False, indent=2)

    v_name = clip_data.get("video_url")
    a_name = clip_data.get("audio_url")
    remotion_public = os.path.join(REMOTION_DIR, "public")
    
    if v_name:
        v_path = os.path.join(_proj_dir, "clips", v_name) if _proj_dir and v_name.startswith("video") else (os.path.join(_proj_dir, v_name) if _proj_dir else os.path.join(BASE_DIR, v_name))
        if os.path.exists(v_path):
            shutil.copy(v_path, os.path.join(remotion_public, v_name))
            
    if a_name:
        a_path = os.path.join(_proj_dir, "clips", a_name) if _proj_dir and a_name.startswith("audio") else (os.path.join(_proj_dir, a_name) if _proj_dir else os.path.join(BASE_DIR, a_name))
        if os.path.exists(a_path):
            shutil.copy(a_path, os.path.join(remotion_public, a_name))

    global remotion_studio_proc
    if not remotion_studio_proc or remotion_studio_proc.poll() is not None:
        try:
            cmd = "cmd /c npm start -- --port=3001" if sys.platform == "win32" else "npm start -- --port=3001"
            remotion_studio_proc = subprocess.Popen(
                cmd,
                cwd=REMOTION_DIR,
                shell=True
            )
            time.sleep(1.5) # Give it time to bind the port
        except Exception as e:
            print(f"Error starting Remotion Studio: {e}")

    return {"status": "success", "url": "http://localhost:3001"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
