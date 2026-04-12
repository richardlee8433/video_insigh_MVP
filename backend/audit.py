import json
import os
from datetime import datetime


def log_analysis(job_id: str, filename: str, file_hash: str, model: str):
    log = {
        "job_id": job_id,
        "filename": filename,
        "file_hash": file_hash,
        "model_used": model,
        "analyzed_at": datetime.utcnow().isoformat() + "Z",
        "software": "HALOS Video Insight Assistant v2.0"
    }
    path = f"/tmp/uploads/{job_id}/audit_log.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(log, f, indent=2)
    return log


def append_live_alert(job_id: str, label: str, description: str, frame_hash: str, timestamp: str):
    """Appends to live_interventions array in audit_log.json."""
    path = f"/tmp/uploads/{job_id}/audit_log.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if os.path.exists(path):
        with open(path, 'r') as f:
            try:
                log = json.load(f)
            except json.JSONDecodeError:
                log = {}
    else:
        log = {}

    if "live_interventions" not in log:
        log["live_interventions"] = []

    log["live_interventions"].append({
        "label": label,
        "description": description,
        "hash": frame_hash,
        "timestamp": timestamp
    })

    with open(path, 'w') as f:
        json.dump(log, f, indent=2)
    return log
