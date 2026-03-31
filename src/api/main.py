from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from typing import List
import uuid
import os
import shutil
import tempfile
from contextlib import redirect_stdout
import asyncio
import json

from .models import JobResponse
from .sse import SSELogger, job_streams, job_results
from src.pipeline.orchestrator import run_pipeline

app = FastAPI(
    title="Flick AI Extraction Service", 
    version="1.0.0",
    description="Asynchronous batch ALPR and visual intelligence pipeline."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def process_job(job_id: str, target_dir: str, loop: asyncio.AbstractEventLoop):
    logger = SSELogger(job_id, loop=loop)
    with redirect_stdout(logger):
        try:
            print(f"[{job_id}] Initializing Flick AI for directory: {target_dir}")
            results = run_pipeline(target_dir=target_dir, job_id=job_id)
            job_results[job_id] = results
            print(f"[{job_id}] Pipeline completed successfully.")
        except Exception as e:
            print(f"[{job_id}] Pipeline failed: {str(e)}")
            job_results[job_id] = {"status": "failed", "error": str(e)}
        finally:
            logger.write("[__EOF__]")

@app.post("/api/v1/jobs/process", status_code=202)
async def create_job(background_tasks: BackgroundTasks, files: list[UploadFile]):
    job_id = str(uuid.uuid4())
    
    job_dir = os.path.join(tempfile.gettempdir(), f"flick_ingress_{job_id}")
    os.makedirs(job_dir, exist_ok=True)
    
    for f in files:
        fname = f.filename or f"{uuid.uuid4()}.mp4"
        file_path = os.path.join(job_dir, fname)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(f.file, buffer)
            
    loop = asyncio.get_running_loop()
    background_tasks.add_task(process_job, job_id, job_dir, loop)
    return {"job_id": job_id, "status": "processing", "message": f"Processing {len(files)} files."}

@app.get("/api/v1/jobs/{job_id}/stream")
async def stream_job(request: Request, job_id: str):
    q = asyncio.Queue()
    if job_id not in job_streams:
        job_streams[job_id] = []
    job_streams[job_id].append(q)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                line = await q.get()
                if line == "[__EOF__]":
                    yield {"event": "end", "data": "Pipeline completed."}
                    break
                
                clean_line = line.replace('\n', '')
                if clean_line:
                    yield {"event": "log", "data": clean_line}
        finally:
            if q in job_streams.get(job_id, []):
                job_streams[job_id].remove(q)

    return EventSourceResponse(event_generator())



@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
def get_job_results(job_id: str):
    if job_id not in job_results:
        if job_id in job_streams:
            return JobResponse(id=job_id, status="processing")
        raise HTTPException(status_code=404, detail="Job not found")
        
    res = job_results[job_id]
    if res.get("status") == "failed":
        return JobResponse(id=job_id, status="failed")
    
    return JobResponse(
        id=job_id,
        status="completed",
        stats=res.get("stats"),
        results=res.get("results")
    )
