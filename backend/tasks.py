import os
import json
from celery import Celery
import redis as redis_client
from pipeline import extract_audio, transcribe, analyze

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)
r = redis_client.from_url(REDIS_URL)


def _set_status(job_id: str, status: str, result=None):
    data = {"status": status}
    if result is not None:
        data["result"] = json.dumps(result)
    r.hset(f"job:{job_id}", mapping=data)


@app.task(name="tasks.process_video")
def process_video(job_id: str, video_path: str):
    try:
        _set_status(job_id, "processing")

        audio_path = extract_audio(video_path)

        transcript = transcribe(audio_path)
        segments = transcript["segments"]

        result = analyze(segments)

        _set_status(job_id, "done", result)
    except Exception as e:
        _set_status(job_id, "error", {"error": str(e)})
        raise
