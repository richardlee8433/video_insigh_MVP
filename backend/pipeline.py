import os
import json
import ffmpeg
import openai
from prompts import SYSTEM_PROMPT, USER_TEMPLATE


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


def analyze(segments: list) -> dict:
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
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw)
    return result
