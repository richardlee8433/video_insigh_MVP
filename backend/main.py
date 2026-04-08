import os
import uuid
import json
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from tasks import process_video, r

app = FastAPI(title="HALOS Video Insight Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "/tmp/uploads"


@app.post("/analyze")
async def analyze_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    ext = os.path.splitext(file.filename)[1] if file.filename else ".mp4"
    video_path = os.path.join(job_dir, f"video{ext}")

    contents = await file.read()
    with open(video_path, "wb") as f:
        f.write(contents)

    # Initialize job state
    r.hset(f"job:{job_id}", mapping={"status": "pending"})

    background_tasks.add_task(process_video, job_id, video_path)

    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    data = r.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Job not found")

    status = data.get(b"status", b"pending").decode()
    result_raw = data.get(b"result")
    result = json.loads(result_raw) if result_raw else None

    return {"status": status, "result": result}
