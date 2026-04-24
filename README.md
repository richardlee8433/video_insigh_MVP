# HALOS Video Insight Assistant
### From Footage to Evidence — in Seconds.

A self-initiated MVP built in 7 days to demonstrate how AI can transform passive security footage into an active investigation tool.

> "I built it because I wanted to feel the problem before talking about it."

**Live Demo:** https://videoinsighter.netlify.app
**GitHub:** https://github.com/richardlee8433/video_insigh_MVP

---

## Why I Built This

Investigators today face the same bottleneck: hours of footage, multiple cameras, and no way to quickly answer "where did this person go?" The industry default is manual scrubbing. That is not a product problem — it is a product opportunity.

I built this MVP to explore three questions:
- Can AI reduce Time to Insight from hours to seconds?
- Can a single PM ship a forensic-grade tool without a team?
- Where does HALOS have a structural advantage over Axon?

The answer to all three turned out to be yes.

---

## Version Evolution

| Version | Core Capability | The Shift |
|---------|----------------|-----------|
| v1.0 | Speech-to-text indexing via Whisper | From scrubbing to searching |
| v2.0 / v3.0 | GPT-4o Vision — see + hear combined | From searching to understanding |
| v4.0 | Live CCTV (HLS) + Intelligent Sampling | From reactive to real-time |
| v5.0 | Semantic search across videos | From playback to investigation |
| v6.0 | Crowd density detection + auto URL refresh | From manual ops to zero-maintenance |
| v7.0 | Multi-camera Tactical-Link — spatial tracking | From single lens to evidence chain |
| v8.0 | Body Cam Adaptive Mode — scene-aware analysis | From one-size-fits-all to context-aware |
| v8.1 | Dual-model comparison (GPT-4o ↔ Gemini Flash) | From black-box AI to transparent model selection |

---

## Key Architectural Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Target tracking | Semantic Re-ID (GPT-4o + Embeddings) | Zero training cost; handles unstructured descriptions |
| Spatial analysis | Manual topology + Cosine Similarity | Fastest path to proving cross-camera tracking in demo stage |
| Crowd detection | Quantified thresholds (<10 / 10-20 / >20) | GPT-4o needs explicit baselines to judge "anomaly" |
| Sampling logic | Pixel diff > 15% before AI call | Cost is everything — skip static frames |
| Evidence integrity | Client-side SHA-256 fingerprinting | Establishes chain of custody before data leaves the device |
| URL management | On-demand API via yt-dlp | Solves HLS expiry with zero maintenance overhead |
| Body cam detection | Laplacian sharpness + motion variance heuristic | High-motion scenes need visual-first architecture; audio signal is unreliable |
| Model selection | Parallel GPT-4o + Gemini Flash with toggle UI | Let evidence speak: show investigators the difference rather than making the choice for them |

---

## Tactical-Link — v7.0 Deep Dive

The flagship feature. Built to solve the core investigator pain point: piecing together a subject's movement across multiple cameras.

**How it works:**
1. GPT-4o Vision describes the target (clothing, build, distinguishing features) and vectorises the description
2. Camera topology maps physical relationships between camera positions
3. Cosine similarity (threshold > 0.7) auto-links detections across cameras
4. AI generates a 3-5 sentence forensic narrative — including timestamps where the subject disappears or is occluded

**Frontend:** 2x2 sync player — click any orange detection point on the timeline and all four feeds jump to that moment simultaneously.

**Output:** One-click downloadable evidence file (.txt) containing SHA-256 hash, spatial narrative, and cross-camera similarity scores.

---

## Body Cam Adaptive Mode — v8.0 + v8.1

The failure that became a feature. Testing the MVP against real body camera footage exposed a fundamental architectural flaw: the system was outputting "question about grub" for a 44-second foot pursuit and arrest.

Root cause: `extract_frames` was sampling at 1 frame per 30 seconds. A 44-second video produced 1–2 frames — almost no visual signal. The system fell back entirely on Whisper transcription, which fails in high-action scenes with little dialogue.

**The fix (v8.0):**
1. Raised frame extraction to 1 frame per 5 seconds
2. Added Laplacian sharpness filtering — blurry/shaky frames are discarded before reaching GPT-4o
3. Auto-detection heuristic: if avg_sharpness and motion_variance cross thresholds → route to `bodycam_v3` mode
4. New body cam system prompt built for temporal reasoning across frames, not single-frame analysis

**Before / After:**

| Timestamp | v7.0 output | v8.0 output |
|-----------|-------------|-------------|
| 00:00 | fight mentioned | foot pursuit begins |
| 00:06 | (missing) | suspect jumps fence |
| 00:20 | shootout mentioned | verbal command issued |
| 00:43 | question about grub | suspect apprehended |

**Dual-model comparison (v8.1):**

Added Gemini Flash as a parallel analysis engine. For body cam footage, Gemini uploads the full video natively — no frame extraction required. A toggle button (GPT-4o ↔ Gemini Flash) lets investigators see both analyses side by side.

Gemini captured details GPT-4o missed: the officer exiting the vehicle, two separate fence crossings with pool area context. Cost comparison at 1,000-hour scale: GPT-4o ~$1,440 vs Gemini Flash ~$288.

The roadmap: add an optical flow pre-filter (near-zero CPU cost) to flag only event-containing segments before sending to either model. Projected cost at scale: $288 → under $30.

---

## Competitive Positioning

Axon dominates storage. HALOS wins on investigation experience.

Axon V5 introduced semantic search — but it requires trained models and enterprise infrastructure. Tactical-Link achieves the same outcome using GPT-4o embeddings with zero model training, deployable today.

The moat is not the feature. The moat is the speed at which HALOS can move from "idea" to "in the hands of investigators."

---

## Product Velocity

8 versions. 7 days.

Not because the brief demanded it — because shipping is how I think. Every version answered a real question. Every architectural decision is documented above. Every trade-off was intentional.

This is how I approach product: prototype first, validate fast, iterate with purpose. v8.0 and v8.1 were built in 80 minutes — from identifying a live failure mode to dual-model comparison deployed in production.
