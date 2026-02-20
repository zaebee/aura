# Kinetic Research: Visual Synthesis & Metabolic Overhead

## 1. Remotion CLI Integration
The Hive will utilize the Remotion CLI to transform metabolic data into cinematic artifacts.

### Execution Pattern
- **Command:** `npx remotion render <entry-point> <composition-id> <output-location> --props=<json-path>`
- **Headless Requirements:**
    - **Chromium:** Required for rendering the React components. In Docker, use `chromium-browser` and set `REMOTE_BROWSER_EXECUTABLE` or use `--browser-executable`.
    - **FFmpeg:** Required for video encoding (H.264/AAC).
    - **Node.js:** Runtime for Remotion.

### Parameter Passing
Data from `VehicleAttributes` and `Observation` protos will be serialized into a `props.json` file. This prevents shell escaping issues with complex JSON strings.

## 2. Metabolic Identity Mapping (Transcriptional Enzymes)
To ensure every asset has a unique "Visual DNA," the `KineticSkill` maps domain attributes to visual styles.

| Domain | Identity Signal | Primary Color | Secondary Color | Style |
|--------|-----------------|---------------|-----------------|-------|
| Vehicle | Brand: Hyundai  | #003478       | #A4A4A4         | Modern |
| Vehicle | Brand: Tesla    | #E81922       | #FFFFFF         | Minimal |
| Property| Universal       | #2D5A27       | #F5F5F5         | Organic |
| Workspace| Universal      | #6A0DAD       | #E6E6FA         | Corporate |
| Default | Aura Gold       | #FFD700       | #000000         | Hive |

## 3. Metabolic Cost Analysis (Toxicity Report)
Video synthesis is a **High-Metabolic Activity**.

### Resource Consumption
- **CPU:** High (Encoding consumes multiple cores if `--concurrency` is high).
- **Memory:** Moderate to High (Chromium instances can consume 500MB+ each).
- **Latency:** High (15s video may take 30-60s to render on standard CPUs).

### Recommendation: Kinetic Worker Pattern
- **Hackathon Deployment:** Run as an async subprocess within the `core` container. Use `asyncio.create_task` to avoid blocking the main metabolic loop.
- **Production Scale:** Offload to a dedicated **Kinetic Worker** (T4/L4 GPU nodes).
    - **Trigger:** NATS Subject `aura.kinetic.v1.render`.
    - **Result:** Upload to S3 and emit `aura.kinetic.v1.artifact_ready`.

## 4. Design Decisions
- **Artifact Storage:** Resulting MP4s will be stored in a persistence-backed volume or S3 bucket.
- **Cleanup Enzyme:** Temporary `props.json` and local render artifacts must be purged after export to prevent disk bloat.
