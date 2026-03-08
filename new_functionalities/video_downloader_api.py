from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import time
from new_functionalities.video_downloader_logic import add_to_download_queue, get_all_downloads

router = APIRouter(prefix="/api/downloads", tags=["downloads"])

class DownloadRequest(BaseModel):
    url: str

@router.post("")
async def start_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    try:
        state = add_to_download_queue(req.url)
        return {"status": "success", "data": state.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("")
async def list_downloads():
    try:
        downloads = get_all_downloads()
        return downloads
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_downloads_status():
    """Returns the same data as list_downloads, for polling."""
    try:
        downloads = get_all_downloads()
        return downloads
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
