import os
import uuid
import json
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from tasks import process_video, r
from pipeline import analyze_v2_stream

app = FastAPI(title="HALOS Video Insight Assistant")

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
