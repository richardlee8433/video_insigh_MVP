import os
import uuid
import json
import hashlib
import base64
import db
import numpy as np
from datetime import datetime
from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from tasks import process_video, r
from openai import OpenAI
from pipeline import analyze_v2_stream, analyze_live_frame
from audit import append_live_alert

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield

app = FastAPI(title="HALOS Video Insight Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "/tmp/uploads"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/live-url")
async def get_live_url():
    return {
        "url": "https://ITSStreamingBR2.dotd.la.gov/public/shr-cam-002.streams/playlist.m3u8",
        "source": "Live CCTV Stream - Louisiana DOT"
    }


@app.post("/analyze")
async def analyze_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    original_filename = file.filename or "video.mp4"
    ext = os.path.splitext(original_filename)[1] if original_filename else ".mp4"
    video_path = os.path.join(job_dir, f"video{ext}")

    contents = await file.read()
    with open(video_path, "wb") as f:
        f.write(contents)

    # Initialize job state
    r.hset(f"job:{job_id}", mapping={"status": "pending"})

    background_tasks.add_task(process_video, job_id, video_path, original_filename)

    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    data = r.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Job not found")

    status = data.get(b"status", b"pending").decode()
    stage = data.get(b"stage", b"").decode() or None
    result_raw = data.get(b"result")
    result = json.loads(result_raw) if result_raw else None

    return {"status": status, "stage": stage, "result": result}


@app.get("/audit/{job_id}")
async def get_audit(job_id: str):
    audit_path = os.path.join(UPLOAD_DIR, job_id, "audit_log.json")
    if not os.path.exists(audit_path):
        raise HTTPException(status_code=404, detail=f"Audit log not found for job {job_id}")
    try:
        with open(audit_path) as f:
            data = json.load(f)
        return data
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to read audit log: {e}")


@app.post("/analyze-stream/{job_id}")
async def analyze_stream(job_id: str):
    data = r.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Job not found")

    segments_raw = data.get(b"segments")
    if not segments_raw:
        raise HTTPException(status_code=400, detail="Transcription not yet complete")

    segments = json.loads(segments_raw)

    job_dir = os.path.join(UPLOAD_DIR, job_id)
    frames_dir = os.path.join(job_dir, "frames")
    if not os.path.exists(frames_dir):
        raise HTTPException(status_code=400, detail="Frames not yet extracted")

    frames = sorted([
        os.path.join(frames_dir, f)
        for f in os.listdir(frames_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    ])

    async def event_generator():
        for chunk in analyze_v2_stream(segments, frames):
            # SSE format: data: {token}\n\n
            yield f"data: {chunk}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class LiveFrameRequest(BaseModel):
    frame: str  # base64_string
    hash: str   # sha256_string
    job_id: str = None


@app.post("/analyze-live-frame")
async def analyze_live(request: LiveFrameRequest):
    # Verifies hash matches received frame
    try:
        frame_bytes = base64.b64decode(request.frame)
        computed_hash = hashlib.sha256(frame_bytes).hexdigest()
        if computed_hash != request.hash:
            raise HTTPException(status_code=400, detail="Hash mismatch")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid frame data: {e}")

    # Calls analyze_live_frame()
    try:
        analysis = analyze_live_frame(request.frame)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

    label = analysis.get("label", "[NORMAL]")
    description = analysis.get("description", "No description provided.")
    confidence = analysis.get("confidence", 0.0)
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    # Use provided job_id or generate one for the session (handled by frontend usually,
    # but let's use timestamp if not provided as per requirements)
    job_id = request.job_id or f"live_{timestamp.replace(':', '-')}"

    # Logs to live_interventions in audit_log.json
    append_live_alert(job_id, label, description, request.hash, timestamp)

    return {
        "label": label,
        "description": description,
        "confidence": confidence,
        "hash": request.hash,
        "timestamp": timestamp,
        "job_id": job_id
    }


class SearchRequest(BaseModel):
    query: str
    job_ids: list[str] = []


@app.post("/search")
async def search_events(request: SearchRequest):
    # 1. Embed query
    client = OpenAI()
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=request.query
    )
    query_embedding = response.data[0].embedding

    # 2. Fetch all events with embeddings
    all_events = db.get_all_events_with_embeddings()

    # 3. Filter by job_ids if provided
    if request.job_ids:
        all_events = [e for e in all_events if e["job_id"] in request.job_ids]

    # 4. Compute cosine similarity
    def cosine_similarity(a, b):
        a, b = np.array(a), np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    results = []
    for event in all_events:
        score = cosine_similarity(query_embedding, event["embedding"])
        # 5. Filter out results with score <= 0.4
        if score > 0.4:
            # 7. Add filename
            filename = db.get_filename_for_job(event["job_id"])
            results.append({
                "job_id": event["job_id"],
                "filename": filename,
                "timestamp": event["timestamp"],
                "seconds": event["seconds"],
                "label": event["label"],
                "description": event["description"],
                "score": score
            })

    # 6. Sort by score descending and return top 10
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:10]


@app.post("/analyze-batch")
async def analyze_batch(background_tasks: BackgroundTasks, files: list[UploadFile] = File(...)):
    batch_id = str(uuid.uuid4())
    job_ids = []

    for file in files:
        job_id = str(uuid.uuid4())
        job_ids.append(job_id)

        job_dir = os.path.join(UPLOAD_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)

        original_filename = file.filename or "video.mp4"
        ext = os.path.splitext(original_filename)[1] if original_filename else ".mp4"
        video_path = os.path.join(job_dir, f"video{ext}")

        contents = await file.read()
        with open(video_path, "wb") as f:
            f.write(contents)

        # Initialize job state
        r.hset(f"job:{job_id}", mapping={"status": "pending"})

        # Save to batch table
        db.save_batch(batch_id, job_id, original_filename)

        background_tasks.add_task(process_video, job_id, video_path, original_filename)

    return {"batch_id": batch_id, "job_ids": job_ids}


@app.get("/batch-status/{batch_id}")
async def get_batch_status(batch_id: str):
    jobs_in_batch = db.get_jobs_in_batch(batch_id)
    if not jobs_in_batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    jobs_status = []
    all_done = True

    for job in jobs_in_batch:
        job_id = job["job_id"]
        data = r.hgetall(f"job:{job_id}")
        status = data.get(b"status", b"pending").decode()

        jobs_status.append({
            "job_id": job_id,
            "filename": job["filename"],
            "status": status
        })

        if status not in ["done", "error"]:
            all_done = False

    return {
        "batch_id": batch_id,
        "jobs": jobs_status,
        "all_done": all_done
    }
