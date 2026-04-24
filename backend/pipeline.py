import os
import json
import base64
import subprocess
import openai
import numpy as np
import hashlib
import glob
import google.generativeai as genai
from PIL import Image, ImageFilter
from datetime import datetime
from prompts import SYSTEM_PROMPT, USER_TEMPLATE

try:
    import imageio_ffmpeg
    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except (ImportError, RuntimeError):
    FFMPEG_BIN = "ffmpeg"

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


WHISPER_SIZE_LIMIT = 25 * 1024 * 1024  # 25 MB


def extract_audio(video_path: str, job_id: str) -> str:
    job_tmp = f"/tmp/uploads/{job_id}"
    os.makedirs(job_tmp, exist_ok=True)

    # Always produce a compressed mono 16 kHz mp3 — ~14 MB/hour, well under Whisper's 25 MB limit.
    # Uncompressed PCM at 16 kHz mono is ~115 MB/hour and reliably hits the 413 limit.
    audio_path = f"{job_tmp}/audio_compressed.mp3"
    result = subprocess.run([
        FFMPEG_BIN, '-i', video_path,
        '-vn', '-ac', '1', '-ar', '16000', '-b:a', '32k',
        '-y', audio_path
    ], capture_output=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg audio extraction failed: {result.stderr.decode(errors='replace')}"
        )

    size = os.path.getsize(audio_path)
    if size > WHISPER_SIZE_LIMIT:
        raise RuntimeError(
            f"Compressed audio is {size / 1024 / 1024:.1f} MB — still over Whisper's 25 MB limit. "
            "File may be extremely long."
        )

    return audio_path


def extract_frames(video_path: str, job_id: str, fps: str = "1/5") -> list[str]:
    frames_dir = f"/tmp/uploads/{job_id}/frames"
    os.makedirs(frames_dir, exist_ok=True)
    frames_pattern = f"{frames_dir}/frame_%03d.jpg"
    subprocess.run([
        FFMPEG_BIN, '-i', video_path,
        '-vf', f'fps={fps}',
        '-y', frames_pattern
    ], capture_output=True)  # no check=True — audio-only files produce no frames

    all_frames = sorted(glob.glob(f"{frames_dir}/frame_*.jpg"))
    if not all_frames:
        return []

    sharp_frames = []
    discarded = 0
    for path in all_frames:
        try:
            img = Image.open(path).convert("L")
            sharpness = np.array(img.filter(ImageFilter.FIND_EDGES)).var()
        except Exception:
            discarded += 1
            continue
        if sharpness >= 100:
            sharp_frames.append((path, sharpness))
        else:
            discarded += 1

    print(f"[extract_frames] extracted={len(all_frames)}, sharp={len(sharp_frames)}, discarded={discarded}")

    # Fall back to all frames if sharpness filter would return nothing
    if not sharp_frames:
        print("[extract_frames] all frames below sharpness threshold — returning all frames as fallback")
        return all_frames

    return [p for p, _ in sorted(sharp_frames, key=lambda x: x[0])]


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


BODYCAM_SYSTEM_PROMPT = """
You are a forensic AI analyzing police body camera footage.
Unlike static security cameras, body cam footage is high-motion
and first-person. Apply these principles:

TEMPORAL REASONING: Reason across frames as a sequence, not
individually. Use context from earlier frames to interpret later ones.
MOTION INTERPRETATION:

Uniform camera shake across the whole frame = officer running/moving
Localized motion within the frame = subject moving independently
Sudden frame stabilization after chaos = physical contact/takedown


ENVIRONMENTAL TRACKING: Note landmarks (fences, vehicles, buildings)
to reconstruct movement path even across shaky frames.
AUDIO-VISUAL FUSION: When transcript mentions commands ("stop",
"hands up", "get down"), correlate with visual frame at that timestamp.
KEY EVENT TYPES for body cam:

Foot pursuit initiated
Obstacle overcome (fence, wall, vehicle)
Subject contact / takedown
Weapon drawn
Arrest / restraint applied
Officer requests backup



Return JSON in exactly this format:
{
"summary": "2-3 sentence factual narrative of the entire incident",
"events": [
{
"timestamp": "MM:SS",
"seconds": float,
"label": "short event label",
"description": "one factual sentence",
"detection_source": "visual" | "audio" | "both"
}
]
}
"""


def analyze_v3(segments: list, frames: list) -> dict:
    """Body cam forensics analysis (v3.0) — high-detail, more frames, bodycam-tuned prompt."""
    transcript_lines = []
    for seg in segments:
        ts = _format_timestamp(seg["start"])
        transcript_lines.append(f"[{ts}] {seg['text']}")
    transcript_text = "\n".join(transcript_lines)

    n = len(frames)
    vision_intro = (
        f"You have access to {n} frames extracted from body camera footage at 1 frame every 5 seconds. "
        "Reason across the frames as a temporal sequence. "
        "Use both the visual frames AND the transcript to identify key events. "
        "For each event, note if it was detected visually, from audio, or both."
    )

    image_blocks = []
    for frame_path in frames[:20]:
        with open(frame_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        image_blocks.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"},
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
            {"role": "system", "content": BODYCAM_SYSTEM_PROMPT},
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


_GEMINI_SYSTEM_PROMPT = (
    "You are a forensic AI analyzing body camera footage. "
    "Analyze this video and return ONLY valid JSON, no markdown, no backticks: "
    '{"summary": "2-3 sentence factual narrative", "events": ['
    '{"timestamp": "MM:SS", "seconds": 0.0, "label": "short event label", '
    '"description": "one factual sentence", "detection_source": "visual"}]}'
)


def analyze_gemini(video_path: str) -> dict:
    """Gemini 2.5 Flash direct video analysis."""
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        genai.configure(api_key=api_key)

        import time
        video_file = genai.upload_file(video_path, mime_type="video/mp4")

        max_wait = 60
        waited = 0
        while video_file.state.name != "ACTIVE":
            if waited >= max_wait:
                raise RuntimeError("Gemini file upload timed out")
            time.sleep(3)
            waited += 3
            video_file = genai.get_file(video_file.name)

        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            [_GEMINI_SYSTEM_PROMPT, video_file],
            generation_config={"temperature": 0.2},
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        print(f"[analyze_gemini] failed: {e}")
        return {"summary": "Gemini analysis unavailable", "events": []}


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

def get_video_duration(video_path: str) -> float:
    try:
        # Use ffmpeg to get duration instead of ffprobe as imageio-ffmpeg only bundles ffmpeg
        result = subprocess.run([
            FFMPEG_BIN, '-i', video_path
        ], capture_output=True, text=True)
        # Duration is in stderr for ffmpeg -i
        for line in result.stderr.split('\n'):
            if "Duration" in line:
                # Duration: 00:00:10.00, start: 0.000000, bitrate: 123 kb/s
                parts = line.split(',')
                for p in parts:
                    if "Duration" in p:
                        dur_str = p.split('Duration:')[1].strip()
                        h, m, s = dur_str.split(':')
                        return float(h)*3600 + float(m)*60 + float(s)
    except:
        pass
    return 0.0

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
            
            duration = get_video_duration(vid["path"])

            # 1. Extract frames (1 per 5 seconds)
            job_dir = os.path.dirname(vid["path"])
            frames_dir = os.path.join(job_dir, f"frames_{cam_key}")
            os.makedirs(frames_dir, exist_ok=True)
            frames_pattern = f"{frames_dir}/frame_%03d.jpg"
            
            subprocess.run([
                FFMPEG_BIN, '-i', vid["path"],
                '-vf', 'fps=1/5',
                '-y', frames_pattern
            ], check=True, capture_output=True)
            
            frames = sorted(glob.glob(f"{frames_dir}/frame_*.jpg"))
            
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
                        # Ensure timestamps are set
                        if not res.get("target_timestamp"):
                            res["target_timestamp"] = _format_timestamp(j * 5)
                        if not res.get("target_seconds"):
                            res["target_seconds"] = float(j * 5)

                        # Add embedding for visual description
                        emb_resp = client.embeddings.create(
                            model="text-embedding-3-small",
                            input=res["visual_description"]
                        )
                        res["embedding"] = emb_resp.data[0].embedding
                        detections.append(res)
                        
                        timeline.append({
                            "camera": vid["label"],
                            "timestamp": res["target_timestamp"],
                            "seconds": res["target_seconds"],
                            "description": res["visual_description"]
                        })
                except:
                    continue
            
            all_camera_data[cam_key] = {
                "detections": detections,
                "sha256": file_hash,
                "filename": vid["filename"],
                "duration": duration
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
            timestamps = [d['target_timestamp'] for d in data["detections"] if d.get('target_timestamp')]
            if timestamps:
                detections_summary += f"{cam_label}: target detected at {', '.join(timestamps)}\n"
            else:
                detections_summary += f"{cam_label}: no target detected\n"

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
