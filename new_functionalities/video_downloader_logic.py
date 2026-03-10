import os
import json
import yt_dlp
import logging
import time
import threading
import unicodedata
import re

# Configuration
BASE_DIR = os.getcwd()
DOWNLOADS_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "rocoto_videos")
DATA_DIR = os.path.join(BASE_DIR, "new_functionalities", "data")
STATE_FILE = os.path.join(DATA_DIR, "download_states.json")
DOWNLOADS_LOG = os.path.join(BASE_DIR, "downloads.log")

os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Setup Download Logger
download_logger = logging.getLogger("downloader")
download_logger.setLevel(logging.INFO)
if download_logger.hasHandlers():
    download_logger.handlers.clear()
dl_handler = logging.FileHandler(DOWNLOADS_LOG, encoding='utf-8')
dl_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
download_logger.addHandler(dl_handler)

# Memory store
download_queue = []
active_downloads = {} # url -> DownloadState object
queue_lock = threading.RLock() # USE REENTRANT LOCK TO PREVENT DEADLOCKS
download_semaphore = threading.Semaphore(1)

class DownloadState:
    def __init__(self, url, title="", status="queued", progress=0, error=None, timestamp=None, filename=None):
        self.url = url
        self.title = title
        self.status = status
        self.progress = progress
        self.error = error
        self.timestamp = timestamp or time.time()
        self.filename = filename

    def to_dict(self):
        return {
            "url": self.url,
            "title": self.title,
            "status": self.status,
            "progress": self.progress,
            "error": self.error,
            "timestamp": self.timestamp,
            "filename": self.filename
        }

def save_states():
    with queue_lock:
        try:
            data = {url: state.to_dict() for url, state in active_downloads.items()}
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            download_logger.error(f"Error saving states: {e}")

def load_states():
    global active_downloads
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                with queue_lock:
                    for url, d in data.items():
                        if d["status"] in ["downloading", "queued"]:
                            d["status"] = "failed"
                            d["error"] = "Servidor interrumpido."
                        active_downloads[url] = DownloadState(**d)
        except Exception as e:
            download_logger.error(f"Error loading states: {e}")

# Load initial states
load_states()

class YDLLogger:
    def debug(self, msg):
        if "retry" in msg.lower() or "retrying" in msg.lower():
            download_logger.warning(f"[INTENTO] {msg.strip()}")
    def warning(self, msg):
        download_logger.warning(f"[ADVERTENCIA] {msg.strip()}")
    def error(self, msg):
        download_logger.error(f"[ERROR] {msg.strip()}")

def get_video_info(url):
    # Added timeout to prevent hanging the whole system
    ydl_opts = {
        'quiet': True, 
        'no_warnings': True, 
        'noplaylist': True,
        'socket_timeout': 10,
        'retries': 2
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def sanitize_filename(text):
    """
    Sanitiza el nombre del archivo para que sea compatible con Linux:
    - Todo en minúsculas.
    - Sin caracteres especiales (acentos, ñ, comas, emojis, etc.).
    - Sin espacios (reemplazados por guiones bajos).
    - Sin puntos (removidos o reemplazados por guiones bajos).
    """
    if not text:
        return "video_descargado"
    
    # 1. Normalizar para eliminar acentos y caracteres especiales (como ñ -> n)
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    
    # 2. Convertir a minúsculas
    text = text.lower()
    
    # 3. Reemplazar cualquier cosa que no sea letra o número por guion bajo
    # Esto elimina comas, puntos, paréntesis, emojis, etc.
    text = re.sub(r'[^a-z0-9]+', '_', text)
    
    # 4. Limpiar guiones bajos al inicio y al final
    text = text.strip('_')
    
    # 5. Colapsar múltiples guiones bajos consecutivos
    text = re.sub(r'_+', '_', text)
    
    return text if text else "video_descargado"

def download_video_sync(url, state):
    try:
        with queue_lock:
            state.status = "downloading"
            state.progress = 0
            save_states()
            
        download_logger.info(f"Iniciando descarga: {url}")
        
        def progress_hook(d):
            if d['status'] == 'downloading':
                p = d.get('_percent_str', '0%').replace('%','')
                try:
                    state.progress = float(p)
                except: pass

        ffmpeg_bin = r"C:\Users\MELCHOR\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.WinGet.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
        
        # Sanitize title for Linux-friendly filename
        sanitized_title = sanitize_filename(state.title)
        
        ydl_opts = {
            'format': 'bestvideo[height<=1440]+bestaudio/best[height<=1440]/best',
            'merge_output_format': 'mp4',
            'outtmpl': os.path.join(DOWNLOADS_DIR, f'{sanitized_title}.%(ext)s'),
            'progress_hooks': [progress_hook],
            'overwrites': True,
            'ffmpeg_location': ffmpeg_bin if os.path.exists(ffmpeg_bin) else None,
            'retries': 5,
            'fragment_retries': 5,
            'socket_timeout': 10,
            'nocheckcertificate': True,
            'logger': YDLLogger(),
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            with queue_lock:
                state.title = info.get('title', state.title)
                state.filename = ydl.prepare_filename(info)
                state.status = "completed"
                state.progress = 100
                save_states()
            download_logger.info(f"Descarga COMPLETADA: {state.title} ({url})")
            
    except Exception as e:
        download_logger.error(f"Error en descarga {url}: {e}")
        with queue_lock:
            state.status = "failed"
            state.error = str(e)
            save_states()

def process_queue():
    while True:
        url_to_process = None
        state_to_process = None
        with queue_lock:
            if download_queue:
                url_to_process = download_queue.pop(0)
                state_to_process = active_downloads.get(url_to_process)
        
        if url_to_process:
            with download_semaphore:
                download_video_sync(url_to_process, state_to_process)
        else:
            time.sleep(2)

threading.Thread(target=process_queue, daemon=True).start()

def add_to_download_queue(url):
    # 1. Check if already exists (WITHOUT blocking for long)
    with queue_lock:
        if url in active_downloads:
            s = active_downloads[url]
            if s.status not in ["completed", "failed"]:
                return s

    # 2. Extract info (OUTSIDE the lock to prevent blocking the whole UI)
    try:
        info = get_video_info(url)
        title = info.get('title', 'YouTube Video')
    except Exception as e:
        download_logger.warning(f"Could not fetch title for {url}: {e}")
        title = "YouTube Video"
            
    # 3. Add to queue (RE-LOCK to modify state)
    with queue_lock:
        state = DownloadState(url, title)
        active_downloads[url] = state
        download_queue.append(url)
        save_states()
        download_logger.info(f"Añadido a la cola: {title} ({url})")
        return state

def get_all_downloads():
    with queue_lock:
        return [s.to_dict() for s in sorted(active_downloads.values(), key=lambda x: x.timestamp, reverse=True)]
