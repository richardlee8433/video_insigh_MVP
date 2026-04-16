import os
import json
import base64
import ffmpeg
import openai
import numpy as np
import hashlib
from datetime import datetime
from prompts import SYSTEM_PROMPT, USER_TEMPLATE

LIVE_SYSTEM_PROMPT = """
You are a professional Video Forensics AI for retail and law enforcement environments.
Analyze this security camera frame and return ONLY valid JSON.

Detection Rules:

1. Violence & Physical Threat
   - Flag ALERT if: physical fighting, weapons visible, aggressive physical contact,
     pushing, shoving, grabbing, or pulling between individuals
   - Flag CAUTION if: aggressive posturing, confrontational stance,
     individuals in close aggressive proximity

2. Crowd Density (count ALL visible people including background figures)
   - Count everyone visible, including partially visible and background figures
   - When in doubt, round UP your estimate
   - NORMAL: fewer than 20 people, moving freely
   - CAUTION: 20-50 people OR visible crowding/blocking near entrance
   - ALERT: more than 50 people OR visible pushing/blocking in crowd

   Note: Temple Bar and busy street scenes with free-flowing pedestrians
   are NORMAL even with many people. Only flag if movement is restricted
   or crowd is stationary and densely packed.

3. Vehicle Intrusion
   - Flag ALERT if: any vehicle (car, van, motorcycle, bicycle) visible
     on a pedestrian-only area, footpath, or inside a building/venue entrance
   - Flag CAUTION if: vehicle stopped or moving slowly in area where
     pedestrians are present and at risk
   - NORMAL if: vehicle is clearly on a designated road with no pedestrian conflict

4. Unauthorized Access
   - Flag ALERT if: person climbing, jumping barriers, entering restricted zones
   - Flag CAUTION if: tailgating through access points, loitering near
     restricted areas, person in staff-only area

5. Suspect Objects
   - Flag ALERT if: visible weapons, large concealed objects, abandoned bags
   - Flag CAUTION if: person wearing full face covering in non-medical context

6. Time-Based Sensitivity
   Current time will be provided. Adjust thresholds:
   - 11pm-5am: lower crowd threshold (6+ people = CAUTION, 12+ = ALERT)
   - 5am-11pm: standard thresholds apply

Return ONLY this JSON:
{
  "label": "[NORMAL]" | "[CAUTION]" | "[ALERT]",
  "description": "one sentence, specific and factual, mention what triggered the flag",
  "confidence": 0.0-1.0,
  "people_count": estimated total number of visible people,
  "primary_trigger": "violence" | "crowd_density" | "vehicle_intrusion" | "unauthorized_access" | "suspect_object" | "none"
}
"""


def extract_audio(video_path: str) -> str:
    job_dir = os.path.dirname(video_path)
    audio_path = os.path.join(job_dir, "audio.mp3")
    (
        ffmpeg
        .input(video_path)
        .output(audio_path, ac=1, ar="16000", acodec="libmp3lame", q=4)
        .overwrite_output()
        .run(quiet=True)
    )
    return audio_path


def extract_frames(video_path: str, job_id: str) -> list:
    """Extract one frame every 30 seconds from the video."""
    job_dir = os.path.dirname(video_path)
    frames_dir = os.path.join(job_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    output_pattern = os.path.join(frames_dir, "frame_%02d.jpg")
    (
        ffmpeg
        .input(video_path)
        .filter("fps", fps="1/30")
        .output(output_pattern, vframes=999)
        .overwrite_output()
        .run(quiet=True)
    )
    frames = sorted([
        os.path.join(frames_dir, f)
        for f in os.listdir(frames_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    ])
    return frames


def transcribe(audio_path: str) -> dict:
    client = openai.OpenAI()
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
        )
    segments = []
    for seg in response.segments:
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        })
    return {"segments": segments}


def _format_timestamp(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def analyze_v1(segments: list) -> dict:
    """Text-only analysis (v1.0)."""
    transcript_lines = []
    for seg in segments:
        ts = _format_timestamp(seg["start"])
        transcript_lines.append(f"[{ts}] {seg['text']}")
    transcript_text = "\n".join(transcript_lines)

    client = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(transcript_text=transcript_text)},
        ],
        temperature=0.2,
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def analyze_v2(segments: list, frames: list) -> dict:
    """Vision analysis (v2.0) — uses frames + transcript."""
    transcript_lines = []
    for seg in segments:
        ts = _format_timestamp(seg["start"])
        transcript_lines.append(f"[{ts}] {seg['text']}")
    transcript_text = "\n".join(transcript_lines)

    n = len(frames)
    vision_intro = (
        f"You have access to {n} frames extracted from the video every 30 seconds. "
        "Use both the visual frames AND the transcript to identify key events. "
        "For each event, note if it was detected visually, from audio, or both."
    )

    # Build image content blocks (cap at 10 frames to stay within token limits)
    image_blocks = []
    for frame_path in frames[:10]:
        with open(frame_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        image_blocks.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"},
        })

    user_content = [
        {"type": "text", "text": vision_intro},
        *image_blocks,
        {"type": "text", "text": USER_TEMPLATE.format(transcript_text=transcript_text)},
    ]

    client = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def analyze_v2_stream(segments: list, frames: list):
    """Vision analysis (v2.0) streaming — uses frames + transcript."""
    transcript_lines = []
    for seg in segments:
        ts = _format_timestamp(seg["start"])
        transcript_lines.append(f"[{ts}] {seg['text']}")
    transcript_text = "\n".join(transcript_lines)

    n = len(frames)
    vision_intro = (
        f"You have access to {n} frames extracted from the video every 30 seconds. "
        "Use both the visual frames AND the transcript to identify key events. "
        "For each event, note if it was detected visually, from audio, or both."
    )

    # Build image content blocks (cap at 10 frames)
    image_blocks = []
    for frame_path in frames[:10]:
        with open(frame_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        image_blocks.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"},
        })

    user_content = [
        {"type": "text", "text": vision_intro},
        *image_blocks,
        {"type": "text", "text": USER_TEMPLATE.format(transcript_text=transcript_text)},
    ]

    client = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        stream=True
    )

    started = False
    for chunk in response:
        delta = chunk.choices[0].delta.content
        if not delta:
            continue
        
        # Strip potential markdown prefix
        if not started:
            if "```" in delta:
                delta = delta.split("```")[-1]
                if delta.startswith("json"):
                    delta = delta[4:]
            started = True
        
        # Strip potential markdown suffix
        if "```" in delta:
            delta = delta.split("```")[0]
        
        if delta:
            yield delta


def analyze_live_frame(base64_frame: str) -> dict:
    """Analyze a single live frame using GPT-4o Vision."""
    current_time = datetime.utcnow().strftime("%H:%M UTC")

    client = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": LIVE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Current time: {current_time}. Analyze this security camera frame."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_frame}"
                        }
                    }
                ],
            },
        ],
        max_tokens=300
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


# Backward-compatible alias
analyze = analyze_v1

TACTICAL_PROMPT = """
You are a Video Forensics AI performing multi-camera target tracking.
Target description: {target_description}

Analyze this frame from {camera_label} and return ONLY valid JSON:
{{
  "target_visible": true | false,
  "target_timestamp": "MM:SS" | null,
  "target_seconds": 0.0 | null,
  "visual_description": "detailed description of target if visible: color, size, direction of movement",
  "confidence": 0.0-1.0,
  "sha256": "{frame_hash}"
}}

If the target matching the description is visible, set target_visible to true.
Be specific about visual features: vehicle color, make if identifiable, 
direction of travel, any distinctive features.
"""

NARRATIVE_PROMPT = """
You are a forensic investigator writing an official incident report.
Based on multi-camera footage analysis, generate a concise investigation narrative.

Camera detections:
{camera_detections}

Camera topology (adjacency):
{topology}

Write a 3-5 sentence narrative describing the target's movement path,
timestamps, and any significant observations. Be factual and precise.
Format: "Target [description] was first observed at [Camera X] at [timestamp]..."
"""

def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def process_tactical(job_id: str, video_paths: list, target_description: str):
    from tasks import r
    def set_status(status: str, stage: str = None, result=None):
        data = {"status": status}
        if stage: data["stage"] = stage
        if result: data["result"] = json.dumps(result)
        r.hset(f"tactical:{job_id}", mapping=data)

    try:
        set_status("processing", stage="extracting_frames")
        
        all_camera_data = {}
        timeline = []
        
        client = openai.OpenAI()

        for i, vid in enumerate(video_paths):
            cam_key = f"camera_{i+1}"
            set_status("processing", stage=f"analyzing_camera_{i+1}")
            
            # 1. Extract frames (1 per 5 seconds)
            job_dir = os.path.dirname(vid["path"])
            frames_dir = os.path.join(job_dir, f"frames_{cam_key}")
            os.makedirs(frames_dir, exist_ok=True)
            output_pattern = os.path.join(frames_dir, "frame_%03d.jpg")
            
            (
                ffmpeg
                .input(vid["path"])
                .filter("fps", fps="1/5")
                .output(output_pattern)
                .overwrite_output()
                .run(quiet=True)
            )
            
            frames = sorted([
                os.path.join(frames_dir, f)
                for f in os.listdir(frames_dir)
                if f.startswith("frame_") and f.endswith(".jpg")
            ])
            
            detections = []
            
            # Compute file hash
            with open(vid["path"], "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()

            # 2. Analyze each frame with GPT-4o Vision
            for j, frame_path in enumerate(frames):
                with open(frame_path, "rb") as f:
                    frame_bytes = f.read()
                    frame_hash = hashlib.sha256(frame_bytes).hexdigest()
                    b64 = base64.b64encode(frame_bytes).decode("utf-8")
                
                prompt = TACTICAL_PROMPT.format(
                    target_description=target_description,
                    camera_label=vid["label"],
                    frame_hash=frame_hash
                )
                
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "user", "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}}
                        ]}
                    ],
                    temperature=0.0
                )
                
                raw = response.choices[0].message.content.strip()
                raw = raw.replace("```json", "").replace("```", "").strip()
                try:
                    res = json.loads(raw)
                    if res.get("target_visible"):
                        # Add embedding for visual description
                        emb_resp = client.embeddings.create(
                            model="text-embedding-3-small",
                            input=res["visual_description"]
                        )
                        res["embedding"] = emb_resp.data[0].embedding
                        detections.append(res)
                        
                        timeline.append({
                            "camera": vid["label"],
                            "timestamp": res["target_timestamp"] or _format_timestamp(j * 5),
                            "seconds": res["target_seconds"] or float(j * 5),
                            "description": res["visual_description"]
                        })
                except:
                    continue
            
            all_camera_data[cam_key] = {
                "detections": detections,
                "sha256": file_hash,
                "filename": vid["filename"]
            }

        # 3. Matching Targets (Cosine Similarity)
        set_status("processing", stage="matching_targets")
        cross_camera_matches = []
        # Simple linear matching for now as requested by Cam1->Cam2->Cam3->Cam4 chain default
        for i in range(len(video_paths) - 1):
            cam_a = f"camera_{i+1}"
            cam_b = f"camera_{i+2}"
            
            best_match = None
            max_sim = 0
            
            for det_a in all_camera_data[cam_a]["detections"]:
                for det_b in all_camera_data[cam_b]["detections"]:
                    sim = cosine_similarity(det_a["embedding"], det_b["embedding"])
                    if sim > max_sim:
                        max_sim = sim
                        best_match = {
                            "camera_a": vid["label"],
                            "camera_b": video_paths[i+1]["label"],
                            "similarity": round(sim * 100, 2),
                            "matched_at": det_b["target_timestamp"]
                        }
            if best_match and max_sim > 0.7: # Threshold
                cross_camera_matches.append(best_match)

        # 4. Generate Narrative
        set_status("processing", stage="generating_report")
        
        detections_summary = ""
        for cam_key, data in all_camera_data.items():
            cam_label = next(v["label"] for v in video_paths if f"camera_{video_paths.index(v)+1}" == cam_key)
            det_texts = [f"[{d['target_timestamp']}] {d['visual_description']}" for d in data["detections"]]
            detections_summary += f"{cam_label}:\n" + "\n".join(det_texts) + "\n\n"

        narrative_prompt = NARRATIVE_PROMPT.format(
            camera_detections=detections_summary,
            topology="Cam1 -> Cam2 -> Cam3 -> Cam4 (Linear)",
            target_description=target_description
        )
        
        narr_resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": narrative_prompt}]
        )
        narrative = narr_resp.choices[0].message.content.strip()

        # Final Result
        # Remove embeddings from detections before storing to Redis (too large)
        for cam_key in all_camera_data:
            for det in all_camera_data[cam_key]["detections"]:
                if "embedding" in det: del det["embedding"]

        timeline.sort(key=lambda x: x["seconds"])

        result = {
            "cameras": all_camera_data,
            "narrative": narrative,
            "timeline": timeline,
            "cross_camera_matches": cross_camera_matches
        }
        
        set_status("done", result=result)

    except Exception as e:
        set_status("error", result={"error": str(e)})
