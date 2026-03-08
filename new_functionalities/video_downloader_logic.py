import os
import yt_dlp
import logging
import time
import threading

# Configuration
DOWNLOADS_DIR = "videos"
DOWNLOADS_LOG = "downloads.log"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Setup Download Logger
download_logger = logging.getLogger("downloader")
download_logger.setLevel(logging.INFO)
# Clear existing handlers if any (useful for reloads)
if download_logger.hasHandlers():
    download_logger.handlers.clear()
dl_handler = logging.FileHandler(DOWNLOADS_LOG, encoding='utf-8')
dl_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
download_logger.addHandler(dl_handler)

# Queue management
download_queue = []
active_downloads = {} # url -> state
queue_lock = threading.Lock()
download_semaphore = threading.Semaphore(1) # One download at a time

class DownloadState:
    def __init__(self, url, title=""):
        self.url = url
        self.title = title
        self.status = "queued" # queued, downloading, completed, failed
        self.progress = 0
        self.error = None
        self.timestamp = time.time()
        self.filename = None

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

def get_video_info(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info

def download_video_sync(url, state):
    try:
        state.status = "downloading"
        state.progress = 0
        download_logger.info(f"Iniciando descarga: {url}")
        
        def progress_hook(d):
            if d['status'] == 'downloading':
                p = d.get('_percent_str', '0%').replace('%','')
                try:
                    state.progress = float(p)
                except:
                    pass

        # Windows-specific ffmpeg location (from existing code)
        ffmpeg_bin = r"C:\Users\MELCHOR\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
        
        ydl_opts = {
            'format': 'bestvideo[height<=1440]+bestaudio/best[height<=1440]/best',
            'merge_output_format': 'mp4',
            'outtmpl': os.path.join(DOWNLOADS_DIR, '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'overwrites': True,
            'ffmpeg_location': ffmpeg_bin if os.path.isdir(ffmpeg_bin) else None,
            # Fast failure settings
            'retries': 5,
            'fragment_retries': 5,
            'socket_timeout': 10,
            'nocheckcertificate': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            state.title = info.get('title', 'Unknown Title')
            state.filename = ydl.prepare_filename(info)
            state.status = "completed"
            state.progress = 100
            download_logger.info(f"Descarga COMPLETADA: {state.title} ({url}) -> {state.filename}")
            
    except Exception as e:
        download_logger.error(f"Error en descarga {url}: {e}")
        state.status = "failed"
        state.error = str(e)

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

# Start queue processor thread
threading.Thread(target=process_queue, daemon=True).start()

def add_to_download_queue(url):
    with queue_lock:
        if url in active_downloads and active_downloads[url].status not in ["completed", "failed"]:
            return active_downloads[url]
        
        # Try to get title first
        try:
            info = get_video_info(url)
            title = info.get('title', 'YouTube Video')
        except:
            title = "YouTube Video"
            
        state = DownloadState(url, title)
        download_logger.info(f"Añadido a la cola: {title} ({url})")
        active_downloads[url] = state
        download_queue.append(url)
        return state

def get_all_downloads():
    with queue_lock:
        # Return sorted by timestamp descending
        return [s.to_dict() for s in sorted(active_downloads.values(), key=lambda x: x.timestamp, reverse=True)]
