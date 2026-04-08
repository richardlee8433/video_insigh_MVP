SYSTEM_PROMPT = """
You are a video forensics AI assistant for security and law enforcement professionals.
Analyze the transcript and respond ONLY with valid JSON, no other text.
"""

USER_TEMPLATE = """
Transcript (with timestamps):
{transcript_text}

Return this exact JSON structure:
{{
  "summary": "3-5 sentence factual summary focusing on sequence of events",
  "events": [
    {{
      "timestamp": "MM:SS",
      "seconds": 0.0,
      "label": "short action label max 5 words",
      "description": "1-2 sentence detail"
    }}
  ]
}}

Rules:
- Extract 3-8 most significant events only
- Labels must be action-oriented (e.g. "verbal altercation begins")
- seconds must be float from segment start time
- Output ONLY the JSON object
"""
