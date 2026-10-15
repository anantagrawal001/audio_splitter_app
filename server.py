import os
import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from starlette.background import BackgroundTask
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import audio_processor

app = FastAPI(title="Audio Splitter & Batch Renamer")

# Mount UI static directory
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Processing state
processing_state = {
    "is_processing": False,
    "current_file": "",
    "processed_count": 0,
    "total_chunks": 0,
    "logs": [],
    "completed": False,
    "error": None
}

import traceback

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    print("SERVER ERROR OCCURRED:")
    traceback.print_exc()
    return JSONResponse(
        status_code=400,
        content={"detail": f"Error processing folder: {str(exc)}"}
    )




class ScanRequest(BaseModel):
    folder_path: str

class ProcessRequest(BaseModel):
    folder_path: str
    output_folder: Optional[str] = None

@app.get("/")
def get_index():
    index_path = static_dir / "index.html"
    if not index_path.exists():
        return JSONResponse({"error": "UI index.html not found"}, status_code=404)
    return FileResponse(str(index_path))

@app.post("/api/scan")
def scan_directory(req: ScanRequest):
    path_str = req.folder_path.strip().strip('"').strip("'")
    if not path_str:
        raise HTTPException(status_code=400, detail="Folder path cannot be empty.")
    
    try:
        results = audio_processor.scan_folder(path_str)
        
        total_audios = len(results)
        total_chunks = sum(item["total_parts"] for item in results)
        audios_over_30m = sum(1 for item in results if item["needs_split"])
        
        return {
            "folder_path": path_str,
            "total_audios": total_audios,
            "total_chunks": total_chunks,
            "audios_over_30m": audios_over_30m,
            "files": results
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def run_batch_job(folder_path: str, output_folder: str):
    global processing_state
    processing_state["is_processing"] = True
    processing_state["processed_count"] = 0
    processing_state["logs"] = []
    processing_state["completed"] = False
    processing_state["error"] = None

    try:
        items = audio_processor.scan_folder(folder_path)
        total_chunks = sum(item["total_parts"] for item in items)
        processing_state["total_chunks"] = total_chunks
        
        processing_state["logs"].append(f"Started batch processing: {len(items)} audio files into {total_chunks} chunk parts.")
        
        for idx, item in enumerate(items, 1):
            processing_state["current_file"] = item["original_filename"]
            msg = f"[{idx}/{len(items)}] Analyzing {item['original_filename']} ({item['duration_formatted']})..."
            if item['needs_split']:
                msg += f" Splitting into {item['total_parts']} parts (29-min intervals)."
            else:
                msg += " Preserving single chunk (under 30 mins)."
            processing_state["logs"].append(msg)
            
            def on_progress(chunk_name):
                processing_state["processed_count"] += 1
                processing_state["logs"].append(f"  --> Saved part: {chunk_name}")

            audio_processor.process_audio_file(item, output_folder, progress_callback=on_progress)
            
        processing_state["logs"].append(f"SUCCESS: All {total_chunks} files created in output directory: {output_folder}")
        processing_state["completed"] = True
    except Exception as e:
        processing_state["error"] = str(e)
        processing_state["logs"].append(f"ERROR: {str(e)}")
    finally:
        processing_state["is_processing"] = False

@app.post("/api/process")
def start_processing(req: ProcessRequest):
    global processing_state
    if processing_state["is_processing"]:
        raise HTTPException(status_code=400, detail="A processing job is already running.")
    
    in_path = req.folder_path.strip().strip('"').strip("'")
    out_path = req.output_folder.strip().strip('"').strip("'") if req.output_folder else ""
    
    if not out_path:
        out_path = str(Path(in_path) / "Processed_Audios")
        
    import threading
    threading.Thread(target=run_batch_job, args=(in_path, out_path), daemon=True).start()
    return {"message": "Batch processing started", "output_folder": out_path}


@app.get("/api/status")
def get_status():
    return processing_state

if __name__ == "__main__":
    import socket
    import webbrowser
    import uvicorn

    def find_free_port(start_port=8000, max_attempts=50):
        for port in range(start_port, start_port + max_attempts):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('127.0.0.1', port)) != 0:
                    return port
        return start_port

    port = find_free_port(8000)
    url = f"http://127.0.0.1:{port}"
    print(f"\n==================================================")
    print(f" Audio Slicer App running on: {url}")
    print(f"==================================================\n")
    
    # Automatically open web app in user's default browser after 1.5 seconds
    def open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open(url)

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(app, host="127.0.0.1", port=port)

