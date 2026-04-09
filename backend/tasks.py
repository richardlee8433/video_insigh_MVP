import json
import hashlib
import fakeredis
from pipeline import extract_audio, extract_frames, transcribe, analyze_v1, analyze_v2
from audit import log_analysis

r = fakeredis.FakeRedis()


def _set_status(job_id: str, status: str, result=None, stage: str = None):
    data = {"status": status}
    if result is not None:
        data["result"] = json.dumps(result)
    if stage is not None:
        data["stage"] = stage
    r.hset(f"job:{job_id}", mapping=data)


def process_video(job_id: str, video_path: str, filename: str = "video.mp4"):
    try:
        _set_status(job_id, "processing", stage="extracting")

        # Block 2: Hash verification
        with open(video_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        audio_path = extract_audio(video_path)

        transcript = transcribe(audio_path)
        segments = transcript["segments"]

        # Block 1: Extract frames for vision analysis
        frames = extract_frames(video_path, job_id)

        # Block 5: Run both analyses
        _set_status(job_id, "processing", stage="analyzing_v1")
        result_v1 = analyze_v1(segments)

        _set_status(job_id, "processing", stage="analyzing_v2")
        result_v2 = analyze_v2(segments, frames)

        # Block 3: Audit log
        audit = log_analysis(job_id, filename, file_hash, "gpt-4o")

        combined = {
            "v1": {
                "summary": result_v1["summary"],
                "events": result_v1["events"],
            },
            "v2": {
                "summary": result_v2["summary"],
                "events": result_v2["events"],
                "file_hash": file_hash,
                "filename": filename,
                "audit": audit,
            }
        }

        _set_status(job_id, "done", combined)
    except Exception as e:
        _set_status(job_id, "error", {"error": str(e)})
        raise
