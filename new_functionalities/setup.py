from fastapi import FastAPI
from new_functionalities.video_downloader_api import router as downloader_router

def setup_new_functionalities(app: FastAPI):
    """
    Strictly isolates the registration of new modules.
    Only call this once from the main server.py
    """
    print("[Debug-Setup] Registering Video Downloader Router...")
    app.include_router(downloader_router)
    print("[Debug-Setup] Done.")
