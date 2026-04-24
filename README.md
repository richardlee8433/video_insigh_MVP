# HALOS Video Insight Assistant
### From Footage to Evidence — in Seconds.

A self-initiated MVP built in 6 days to demonstrate how AI can transform passive security footage into an active investigation tool.

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

## Competitive Positioning

Axon dominates storage. HALOS wins on investigation experience.

Axon V5 introduced semantic search — but it requires trained models and enterprise infrastructure. Tactical-Link achieves the same outcome using GPT-4o embeddings with zero model training, deployable today.

The moat is not the feature. The moat is the speed at which HALOS can move from "idea" to "in the hands of investigators."

---

## Product Velocity

7 versions. 6 days. 150 hours.

Not because the brief demanded it — because shipping is how I think. Every version answered a real question. Every architectural decision is documented above. Every trade-off was intentional.

This is how I approach product: prototype first, validate fast, iterate with purpose.
