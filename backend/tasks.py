import json
import hashlib
import numpy as np
import fakeredis
import db
from openai import OpenAI
from PIL import Image, ImageFilter
from pipeline import extract_audio, extract_frames, transcribe, analyze_v1, analyze_v2, analyze_v3
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

        audio_path = extract_audio(video_path, job_id)

        transcript = transcribe(audio_path)
        segments = transcript["segments"]
        
        # Store segments for streaming analysis
        r.hset(f"job:{job_id}", "segments", json.dumps(segments))

        # Block 1: Extract frames for vision analysis
        frames = extract_frames(video_path, job_id)

        # Detect body cam footage: low avg sharpness + high motion variance
        analysis_mode = "standard_v2"
        if frames:
            sharpness_scores = []
            for path in frames:
                try:
                    img = Image.open(path).convert("L")
                    sharpness_scores.append(np.array(img.filter(ImageFilter.FIND_EDGES)).var())
                except Exception:
                    continue
            if sharpness_scores:
                avg_sharpness = sum(sharpness_scores) / len(sharpness_scores)
                motion_variance = float(np.var(sharpness_scores))
                if avg_sharpness < 80 and motion_variance > 500:
                    analysis_mode = "bodycam_v3"
                    print(f"[process_video] bodycam detected (avg_sharpness={avg_sharpness:.1f}, motion_variance={motion_variance:.1f}) — using analyze_v3")

        # Block 5: Run both analyses
        _set_status(job_id, "processing", stage="analyzing_v1")
        result_v1 = analyze_v1(segments)

        _set_status(job_id, "processing", stage="analyzing_v2")
        if analysis_mode == "bodycam_v3":
            result_v2 = analyze_v3(segments, frames)
        else:
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
                "analysis_mode": analysis_mode,
            }
        }

        _set_status(job_id, "done", combined)

        # Persist to SQLite
        db.save_job(job_id, filename)
        event_ids = db.save_events(job_id, result_v2["events"])

        # Generate embeddings for each event
        client = OpenAI()
        for i, event in enumerate(result_v2["events"]):
            text = f"{event['label']}: {event['description']}"
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            db.save_embedding(event_ids[i], response.data[0].embedding)
    except Exception as e:
        _set_status(job_id, "error", {"error": str(e)})
        raise
