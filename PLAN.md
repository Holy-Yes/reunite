# Reunite — Campus Lost & Found Intelligence (plan)

## Scope of this task: documents only, no code
Per the user, this task produces **three documents**, not an implementation. They go in `/Volumes/Dawnstrike/reunite/docs/`:
1. **`PRD.md`**: the product requirements document.
   - Problem, goals and non-goals, personas (student loser, finder, security desk admin), user stories.
   - Functional requirements per module: reporting, attribute extraction, matching, swipe matches, claims/verification, handover, notifications, history, insights, 3D ops view.
   - Non-functional requirements: privacy (item-level tracking only, hidden attributes, ID redaction), latency on an 8 GB Mac, offline-capable models.
   - Success metrics (P@1 ≥ 0.6 / P@5 ≥ 0.85 targets, MRR, ECE, time-to-reunite, recovery rate), the evaluation plan, the dataset plan, and hackathon judging mapping.
   - Scope tiers: MVP / extras / stretch. Risks, and open questions (campus name, Cesium token).
2. **`IMPLEMENTATION_PLAN.md`**: the engineering plan, expanded from the Architecture / Work split / Build order sections below.
   - Tech stack, repo layout, DB schema (tables + key columns), and API endpoint list.
   - The ML pipeline and matching formula (features, weights, calibration), and pretrained fallbacks vs the training handoff.
   - The **compute vs non-compute task split** as checklists, a day-by-day 10–14 day schedule with team-role split, the eval harness, and setup/run steps.
3. **`WEBSITE_PROMPT.md`**: a self-contained, copy-paste prompt for an AI website builder (Replit / Lovable / v0 / Bolt) to generate the front end.
   - React + Vite + TS PWA with mock data and a typed API client stub matching the endpoint list, so it plugs into FastAPI later.
   - All pages and states (Report Lost/Found with camera + editable attribute chips, swipe Matches deck with confidence + why-breakdown, claim Q&A, handover QR, notifications, timeline, admin insights, Resium 3D campus view with layers/arcs/heatmap/time slider/NVG-thermal modes, eval page).
   - Explicit design direction (distinctive, non-generic, per the anti-ai-slop skill), plus mobile-first, accessibility, empty/loading/error states and sample mock data.

**Executor handoff:** another session (Sonnet) will run this plan. It should create `reunite/docs/`, write the three files, and write no code. The user's answers above are final, so don't re-ask them. The only unknowns are the campus name and the Cesium ion token: mark them `<<CAMPUS_NAME>>` / `<<CESIUM_ION_TOKEN>>`. Background: `github.com/bilawalsidhu/gods-eye-view` is an MIT CesiumJS 3D globe (vanilla JS + Vite) with layers, NVG/FLIR/CRT post-process shaders, a timeline and a scene director, and it explicitly excludes tracking individuals.

After writing them, give a short summary and offer in one line to publish PRD + plan as a shareable doc. The technical sections below are the source material for the documents.

## Context
Hackathon brief (AI/ML & Data Science track), ~1–2 weeks. Students lose IDs, laptops, books and gadgets, and reuniting them today is manual. We're building a platform where lost and found reports (photo and/or text) are turned into attributes and embeddings. A matching engine ranks candidates from the opposite pool with calibrated confidence scores, backed by real evaluation metrics (precision@k, MRR, calibration). Extras in scope: claim verification, notifications, location/time-aware scoring, an insights dashboard with item history, and a Cesium 3D campus ops view borrowing patterns from bilawalsidhu/gods-eye-view (MIT).

The architecture mirrors a detection→tracking pipeline. Detector plus attribute heads is the "detector". The appearance embedding is re-ID. Location and time gating are motion gating. The ranked association is data association.

**User decisions:** YOLO detector + classifier heads (vision). Sentence-embeddings + spaCy/gazetteer extraction (NLP). React + FastAPI + Postgres(/pgvector). College-email OTP auth. Cesium ion OSM buildings. Open data + self-collected pairs. Project at `/Volumes/Dawnstrike/reunite`. **Split work into compute vs non-compute: I build all non-compute work now; GPU training is packaged for the user to run on Colab/Kaggle.** Every model has a pretrained fallback, so the app works end to end before any training.

**Environment:** Apple Silicon Mac, 8 GB RAM, Python 3.12 (anaconda), Node 24, Postgres 16 via Homebrew (service stopped), no pgvector, no Docker, no Redis. So we use small models (YOLO11n, CLIP ViT-B/32, MiniLM) and in-process background jobs.

**Open inputs from user:** the campus name (for zones and map), and a free Cesium ion token pasted into `.env`. Until then a zone config placeholder is used.

## Architecture
```
report (photo?, text?, zone, time window)
 ├─ vision:  YOLO11n → primary crop → attribute heads (category/color/material) + OCR (brand, ID-card text)
 │           CLIP ViT-B/32 image embedding (instance similarity + cross-modal)
 ├─ text:    spaCy EntityRuler + gazetteers → {category, brand, color, marks, serial/roll no}
 │           MiniLM sentence embedding + CLIP text embedding
 └─ fused attribute record (user can correct in UI → corrections logged as labels)
matching (on every new report, against opposite pool):
 1. candidate gen: category-group + time-window filter → ANN on embeddings (top 50)
 2. rerank: feature vector → weighted score (later logistic calibration) → top-k with "why" breakdown
 3. notify owners above threshold; store matches for swipe UI + feedback
```

### Repo layout (`/Volumes/Dawnstrike/reunite`)
- `backend/` FastAPI app. SQLAlchemy 2 + Alembic, Pydantic v2.
  - `app/api/` for auth (OTP), items, matches, claims, handover, notifications (SSE + Web Push), admin/insights, and eval.
  - `app/ml/vision/detector.py`: Ultralytics YOLO. Loads `weights/detector.pt` if present, else COCO `yolo11n.pt` with a COCO→campus class map. Classes outside COCO (ID card, keys, earbuds, wallet, charger, specs) fall back to CLIP zero-shot on the full image.
  - `app/ml/vision/attributes.py`: category head (trained if `weights/heads.pt` exists, else zero-shot CLIP prompts). Color is always deterministic: k-means on crop pixels, masked to the object, mapped to a named palette in CIELAB. Handles up to 2 colors. OCR via `rapidocr-onnxruntime` for brand text and ID-card roll numbers.
  - `app/ml/vision/embedder.py`: open_clip ViT-B/32 image and text encoders (shared space gives cross-modal text-only-lost ↔ photo-only-found matching).
  - `app/ml/text/parser.py`: spaCy `en_core_web_sm` + EntityRuler. Gazetteers in `app/ml/text/lexicons/*.yaml` cover category synonyms and hierarchy (bag⊃backpack), brands, colors and modifiers ("navy"→blue), campus zone aliases ("lib", "central library"), mark patterns (dent/scratch/sticker/cracked/engraved), and regexes for serials and roll numbers.
  - `app/ml/text/embedder.py`: sentence-transformers `all-MiniLM-L6-v2`.
  - `app/ml/matching/features.py`: per-pair features. Category agreement (hierarchy-aware partial credit), color ΔE similarity, brand match, image↔image cosine, text↔text cosine, cross-modal cosine, marks overlap, zone proximity (walking-graph hops → exp decay) and time plausibility (found must fall after the lost window starts; decay on gap). Missing modalities are masked and the weights renormalized.
  - `app/ml/matching/scorer.py`: hand-set weights at first. `calibrate.py` fits logistic regression on eval pairs (CPU, seconds) and outputs a calibrated probability plus per-feature contributions ("why this match").
  - `app/ml/matching/index.py`: `VectorIndex` interface. Uses pgvector if the extension is available, else an in-memory numpy brute-force index (campus scale is <10k items, which is fast).
  - `app/jobs.py`: DB-backed job table + asyncio worker (ingest → extract → match → notify). No Redis needed.
  - `app/models.py`: users, zones, items (kind lost|found, status, attributes jsonb, hidden_attributes jsonb, zone, occurred_from/to, custody_zone), item_images (path, detections, embedding), matches (score, features, rank, feedback), claims, handovers, item_events (history), notifications, push_subscriptions, otp_codes.
- `frontend/`: React + Vite + TS PWA (camera capture, service worker for push). Build with the anti-ai-slop / frontend-design skills.
  - Pages: Report Lost / Report Found (live attribute extraction preview with editable chips), My Items, Matches (swipe-card deck: confidence, why-breakdown, "That's mine" / "Not mine"), Claim flow, Handover QR/code, Notifications, Item timeline.
  - Admin pages: Insights dashboard, Campus Ops 3D view, Eval report, Claims review queue.
  - `src/ops/`: Resium/CesiumJS campus view. Cesium ion OSM Buildings, zone polygons from `zones.geojson`, lost/found pins at zone level, match arcs colored by confidence, hotspot heatmap, Cesium clock/timeline replay (7 days), and NVG/thermal post-process shaders ported from gods-eye-view with MIT attribution in `THIRD_PARTY_NOTICES.md`. It shows items only; no people or camera tracking.
- `config/campus/`: `zones.geojson` + `zone_graph.json` (adjacency/walking hops), generated by `scripts/build_campus_zones.py` from the OSM Overpass API for the campus bbox.
- `eval/`: `pairs/manifest.csv` (pair_id, side, image, text, zone, timestamp).
  - `run_eval.py` reports precision@1/5/10, recall@k, MRR, mAP, ECE + reliability diagram, a per-category breakdown, and an ablation table (image-only, text-only, +attributes, +cross-modal, +location/time).
  - Writes `eval/reports/<date>.json|md`, which the admin Eval page renders.
  - `synthetic_pairs.py` generates augmentation-based pairs, labelled as optimistic, for use until real pairs exist.
- `training/` (compute bucket; code written now, run later): `01_build_dataset.ipynb` (Open Images/LVIS subsets for ~18 campus classes via FiftyOne), `02_finetune_yolo.ipynb` (YOLO11n, Colab-ready), `03_attribute_heads.ipynb` (frozen CLIP embeddings → MLP heads for category/color/material), `04_metric_learning.ipynb` (stretch: triplet fine-tune of the projection on pairs), and `export.py` (writes `weights/*.pt` + `model_card.json`). The backend hot-loads these weights when present.

### Claim verification (anti-fraud)
- When reporting, the finder marks attributes/marks as **hidden** (sticker, wallpaper, contents, serial fragment). The public listing shows coarse attributes and a blurred photo only.
- The claimant answers auto-generated questions built from the hidden attributes. Each answer is scored with fuzzy + embedding similarity. The claim score combines those answers, the claimant's own lost-report match score, and account signals (verified college email, claim rate limit, one pending claim per item).
- Thresholds: auto-approve low-value items. Laptops, phones and ID cards always go to finder/admin review.
- ID cards get automated verification: OCR'd roll number → direct owner lookup and notification, redacted in public view.
- Handover uses a signed QR + 6-digit code. Scanning it marks the item returned and logs to history. Karma points go to finders.

### Notifications, history, insights
- New report → match job → in-app SSE + Web Push (VAPID via `pywebpush`) + email (console backend in dev, SMTP optional) for matches above threshold. Users can re-run matching on edits.
- `item_events` drives the per-item timeline: reported → matched → claimed → verified → handed over → closed.
- Insights cover:
  - loss hotspots by zone
  - an hour×weekday heatmap
  - category mix
  - recovery rate
  - median time-to-reunite
  - live match precision from user thumbs up/down feedback
  - top finders (community)

## Work split
**Non-compute (I implement now):** everything above running on pretrained inference, with CPU/MPS inference only. This also includes the training code and notebooks, the eval harness, synthetic pairs, calibration, seed demo data, and the launch configs.

**Compute / human (user runs, then drops files in):**
1. Photograph 150–300 real lost/found pairs (same object, different angle/place/time) and fill `eval/pairs/manifest.csv`. A capture guide is in `eval/README.md`.
2. Run `training/01–03` on Colab/Kaggle, then copy `weights/` into `backend/weights/`.
3. Rerun `python -m eval.run_eval` to get the before/after table for the pitch.

## Setup steps needing downloads (approved via this plan)
- pip/npm dependencies.
- Pretrained weights: yolo11n (~6 MB), open_clip ViT-B/32 (~350 MB), MiniLM (~90 MB), spaCy sm (~12 MB), rapidocr (~15 MB).
- ~100 Open Images validation photos for seed/demo data.
- Try building pgvector from source against `postgresql@16`, with the numpy index as fallback.
- Start Postgres with `brew services start postgresql@16`.
- Add `reunite-backend` (port 8010) and `reunite-frontend` (port 5190) to `/Volumes/Dawnstrike/.claude/launch.json`.

## Build order
1. Scaffold backend/frontend, DB models + Alembic, OTP auth, zone config.
2. ML modules (text parser → embedders → detector/attributes → OCR) with unit tests.
3. Features + scorer + index + match job, then the eval harness on synthetic pairs.
4. Report/match/swipe UI with attribute correction.
5. Claims + handover + notifications + history.
6. Insights dashboard + Cesium ops view.
7. Seed data, calibration, eval page, README, and the compute handoff notebooks.

## Verification (for this documents-only task)
- All three files exist in `reunite/docs/`. The PRD and plan agree on endpoints, schema, metrics and scope tiers. The website prompt's page list and API stub match the plan's endpoint list. There are no placeholders except the campus name and Cesium token, which are clearly marked.

## Verification to include inside IMPLEMENTATION_PLAN.md (for the later build)
- `pytest backend/tests`: parser extraction cases ("black Dell laptop, small dent on the lid" → category=laptop, brand=Dell, color=black, marks=[dent]), color naming, feature masking, time/zone gating, scorer monotonicity, claim scoring, handover token.
- `python -m eval.run_eval --pairs synthetic`: produces P@1/5, MRR, ECE and the ablation table without errors.
- Start `reunite-backend` + `reunite-frontend` via preview_start and walk the full end-to-end browser flow:
  1. Sign up with OTP (code from the console).
  2. User A reports a lost item (text only).
  3. User B reports a found item (photo), and the extracted attributes appear.
  4. A's Matches deck shows B's item with a confidence score and why-breakdown, and a notification arrives.
  5. A claims and answers the hidden-attribute questions, B approves, and the handover code completes.
  6. The timeline shows all events.
  7. The admin Insights page, the Cesium view (zones, pins, arcs, time slider) and the Eval page render.
- Check console/network for errors, and screenshot key screens.
