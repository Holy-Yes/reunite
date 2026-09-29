# Reunite: Implementation Plan

Engineering plan for the build. Read [`PRD.md`](PRD.md) for what and why, and [`WEBSITE_PROMPT.md`](WEBSITE_PROMPT.md) for the front-end prompt. Endpoints, schema, metrics, categories, thresholds, and scope tiers here are the same as in those two documents.

Open placeholders: `<<CAMPUS_NAME>>` and `<<CESIUM_ION_TOKEN>>`. Everything else is decided.

## Contents
1. Principles
2. Environment
3. Tech stack
4. Repo layout
5. Architecture
6. Database schema
7. API endpoints
8. ML pipeline and matching
9. Claims, handover, notifications, insights
10. Front end and integration
11. Evaluation harness
12. Compute vs non-compute split
13. Schedule and team roles
14. Setup and run
15. Verification
16. Configuration reference

---

## 1. Principles

- **Pretrained first.** Every model has a pretrained or rule-based fallback, so the whole app works end to end on day 3 with no training. Trained weights, when present, are loaded automatically.
- **Mirror the detection-and-tracking pipeline.** Detector plus attribute heads, embedding as re-ID, zone and time as motion gating, ranked association.
- **Measure everything.** The eval harness exists before the UI is finished. Every claim in the pitch comes from a report file.
- **Small and local.** Small models, in-process jobs, no Redis, no Docker, no external inference APIs.
- **Items, not people.** No person tracking anywhere, and location is zone level.
- **One seam between front and back end.** The typed API client. Swapping `mock` for a URL is the whole integration.

## 2. Environment

| Item | State |
|---|---|
| Machine | Apple-silicon Mac, 8 GB RAM |
| Python | 3.12 (anaconda). Use a project virtualenv. |
| Node | 24 |
| Postgres | 16 via Homebrew, service currently stopped |
| pgvector | Not installed. Try building from source against `postgresql@16`; the numpy index is the fallback. |
| Docker, Redis | Not available, and not needed |
| Project root | `/Volumes/Dawnstrike/reunite` (external volume) |

Model choices follow from the 8 GB limit: YOLO11n, CLIP ViT-B/32, MiniLM-L6, spaCy small, RapidOCR. Inference runs on MPS where supported, else CPU, one inference thread at a time.

## 3. Tech stack

| Layer | Choice |
|---|---|
| API | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, `uvicorn` |
| Database | PostgreSQL 16, optional `pgvector` |
| Auth | Email OTP, JWT (HS256) in the `Authorization` header |
| Jobs | DB-backed `jobs` table plus an asyncio worker (no Redis) |
| Vision | Ultralytics YOLO11n, `open_clip` ViT-B/32, OpenCV (GrabCut, k-means), `rapidocr-onnxruntime` |
| Text | spaCy `en_core_web_sm` with `EntityRuler`, `sentence-transformers` `all-MiniLM-L6-v2`, `rapidfuzz` |
| Matching | numpy, scikit-learn (logistic regression, calibration), `colormath`-style CIEDE2000 (own small implementation) |
| Notifications | SSE (in-process pub/sub), `pywebpush` (VAPID), SMTP or console email |
| Front end | Built from `WEBSITE_PROMPT.md` on the template you choose in Replit, then run locally from `frontend/`. Recommended stack: React, Vite, TypeScript PWA. 3D view: CesiumJS (Resium on React). |
| Tests | `pytest`, `httpx` test client |
| Training | Notebooks for Colab or Kaggle GPU (compute bucket) |

## 4. Repo layout

```
reunite/
├── PLAN.md
├── README.md
├── THIRD_PARTY_NOTICES.md
├── .env.example
├── docs/                          PRD.md, IMPLEMENTATION_PLAN.md, WEBSITE_PROMPT.md
├── backend/
│   ├── alembic.ini, alembic/
│   ├── requirements.txt
│   ├── weights/                   detector.pt, heads.pt, model_card.json (optional, hot-loaded)
│   ├── tests/
│   └── app/
│       ├── main.py, config.py, db.py, deps.py, models.py, schemas.py, jobs.py, security.py
│       ├── api/                   auth.py items.py matches.py claims.py handover.py
│       │                          notifications.py admin.py eval.py reference.py
│       ├── services/              claims.py handover.py notify.py insights.py events.py media.py
│       └── ml/
│           ├── registry.py        lazy model loading, device selection
│           ├── vision/            detector.py attributes.py embedder.py ocr.py color.py
│           ├── text/              parser.py embedder.py lexicons/*.yaml
│           └── matching/          features.py scorer.py calibrate.py index.py candidates.py
├── frontend/                      the exported Replit project (see §10)
├── config/campus/                 zones.geojson, zone_graph.json
├── eval/
│   ├── README.md                  capture guide for real pairs
│   ├── pairs/manifest.csv
│   ├── synthetic_pairs.py
│   ├── run_eval.py
│   └── reports/<date>.json|md
├── training/
│   ├── 01_build_dataset.ipynb
│   ├── 02_finetune_yolo.ipynb
│   ├── 03_attribute_heads.ipynb
│   ├── 04_metric_learning.ipynb   (stretch)
│   └── export.py
├── scripts/
│   ├── build_campus_zones.py      OSM Overpass to zones.geojson and zone_graph.json
│   ├── download_weights.py
│   ├── seed_demo.py
│   └── gen_vapid.py
└── data/                          media/ (uploads), seed/
```

## 5. Architecture

```
report (photo?, text?, zone, time)
 ├─ vision:  YOLO11n → primary crop → attribute heads (category / color / material) + OCR (brand, ID text)
 │           CLIP ViT-B/32 image embedding (instance similarity and cross-modal)
 ├─ text:    spaCy EntityRuler + gazetteers → {category, brand, color, marks, serial / roll no}
 │           MiniLM sentence embedding + CLIP text embedding
 └─ fused attribute record (user can correct in the UI; corrections logged as labels)

matching (on every new or edited report, against the opposite pool):
 1. candidate generation: category group + time gate → nearest neighbors on embeddings (top 50)
 2. rerank: feature vector → weighted score (later calibrated) → top-k with a "why" breakdown
 3. store matches for the deck and feedback; notify owners above threshold
```

**Job pipeline:** `ingest` (save, strip EXIF, resize, make the blurred copy) → `extract` (vision and text) → `match` → `notify`. Each stage is a row in `jobs`, run by one asyncio worker, with model calls dispatched to a single-thread executor.

**Status flow:** an item is created as `processing`, becomes `open` after extraction, `matched` when at least one candidate has a score of 0.40 or more, `claimed` while a claim is pending or approved, `returned` when a handover is confirmed, and `closed` when the owner or a desk closes it.

## 6. Database schema

PostgreSQL 16. All ids are UUIDs except `zones.id` (text) and `ticket_no`. Timestamps are `timestamptz`. Embeddings are stored as `bytea` (float32, little-endian) as the canonical copy. If pgvector is available, a migration adds `vector` mirror columns and an HNSW index, and `VectorIndex` uses them.

| Table | Key columns |
|---|---|
| `users` | `id`, `email` (unique), `role` (`student`/`desk`/`admin`), `roll_no` (nullable, unique, uppercase), `points` int, `notify_push`, `notify_email`, `created_at` |
| `otp_codes` | `id`, `email`, `code_hash`, `expires_at`, `attempts`, `consumed_at`, `created_at` |
| `zones` | `id` (text, e.g. `z_library`), `name`, `short_name`, `kind`, `centroid_lon`, `centroid_lat`, `polygon` (jsonb GeoJSON), `aliases` (jsonb) |
| `items` | `id`, `ticket_no` (unique; `RU-L-0142` or `RU-F-0089`), `kind` (`lost`/`found`), `status`, `owner_id` → users, `description` text, `attributes` jsonb, `hidden_attributes` jsonb, `category` (indexed), `category_group` (indexed), `zone_id` → zones, `occurred_from`, `occurred_to`, `custody_zone_id` → zones (nullable), `value_tier` (`low`/`high`), `redacted` bool, `text_embedding` bytea (384), `clip_text_embedding` bytea (512), `created_at`, `updated_at`, `closed_at` |
| `item_images` | `id`, `item_id`, `path`, `public_path` (blurred), `sha256`, `width`, `height`, `detections` jsonb, `primary_crop` jsonb, `ocr_text`, `embedding` bytea (512) |
| `matches` | `id`, `lost_item_id`, `found_item_id`, `score` real, `band`, `rank`, `features` jsonb (the why breakdown), `model_version`, `feedback` (`mine`/`not_mine`/`unsure`/null), `feedback_at`, `notified_at`, `created_at`; unique (`lost_item_id`, `found_item_id`) |
| `claims` | `id`, `match_id` (nullable), `item_id` (the found item), `claimant_id`, `status`, `questions` jsonb, `answers` jsonb, `answer_scores` jsonb, `score` real, `signals` jsonb, `verified_by`, `decided_by` → users, `decision_note`, `created_at`, `updated_at`; partial unique index on (`item_id`, `claimant_id`) where status in (`draft`, `pending_review`, `needs_more_info`) |
| `handovers` | `id`, `claim_id` (unique), `code_hash`, `token_jti`, `expires_at`, `attempts`, `confirmed_at`, `confirmed_by` → users, `id_checked` bool |
| `item_events` | `id`, `item_id`, `type` (`reported`/`matched`/`claimed`/`verified`/`handed_over`/`closed`), `actor_id`, `actor_role`, `payload` jsonb, `at` |
| `attribute_labels` | `id`, `item_id`, `field`, `old_value` jsonb, `new_value` jsonb, `source`, `created_at` (user corrections, used as training labels) |
| `notifications` | `id`, `user_id`, `type`, `title`, `body`, `href`, `data` jsonb, `read_at`, `channels` jsonb, `created_at` |
| `push_subscriptions` | `id`, `user_id`, `endpoint` (unique), `p256dh`, `auth`, `created_at` |
| `jobs` | `id`, `kind` (`ingest`/`extract`/`match`/`notify`), `payload` jsonb, `status` (`queued`/`running`/`done`/`failed`), `attempts`, `run_after`, `last_error`, `created_at`, `finished_at` |

**Attribute JSON** (in `items.attributes`): `{ category: {value, confidence, source}, brand?, colors: [...], material?, marks: [...], serial? }`, each attribute in the same `{value, confidence, source, hidden?}` shape as the `Attr` type in `WEBSITE_PROMPT.md` §6. Attributes marked `hidden` are copied into `hidden_attributes` and stripped from any public response by the serializer, so `PublicItem` cannot contain them by construction.

**Indexes:** `items(kind, status, category_group, occurred_from)`, `matches(lost_item_id, score desc)`, `item_events(item_id, at)`, `notifications(user_id, read_at)`, `jobs(status, run_after)`.

## 7. API endpoints

Base path `/api/v1`. JSON unless stated. Auth is a bearer token, except the OTP endpoints. Roles are enforced per row.

| Area | Method and path | Request | Response | Role |
|---|---|---|---|---|
| Auth | `POST /auth/otp/request` | `{ email }` | 204 | public |
| Auth | `POST /auth/otp/verify` | `{ email, code }` | `{ token, user }` | public |
| Auth | `GET /me` | | `User` | any |
| Auth | `PATCH /me` | `{ notify_push?, notify_email?, roll_no? }` | `User` | any |
| Auth | `POST /me/push-subscription` | `{ endpoint, keys }` | 204 | any |
| Reference | `GET /taxonomy` | | `{ categories, brands, colors, marks }` | any |
| Reference | `GET /zones` | | GeoJSON FeatureCollection plus `{ graph }` | any |
| Items | `POST /items/extract-preview` | multipart `photo?`, `text?`, `kind?` | `{ attributes, detections, ocr_text, zone_hint?, suspected_id_card }` | any |
| Items | `POST /items` | multipart: `kind`, `text`, `zone_id`, `occurred_from`, `occurred_to`, `custody_zone_id?`, `attributes` (JSON), `photos[]` | `Item` (status `processing`) | any |
| Items | `GET /items` | `?mine=1&kind&status` | `Item[]` | any |
| Items | `GET /items/public` | `?zone_id&category&q` | `PublicItem[]` | any |
| Items | `GET /items/{id}` | | `Item` | owner, desk, admin |
| Items | `PATCH /items/{id}` | attribute corrections, hidden flags, zone, times | `Item`, and re-runs matching | owner |
| Items | `POST /items/{id}/close` | `{ reason }` | `Item` | owner, desk, admin |
| Items | `GET /items/{id}/events` | | `ItemEvent[]` | owner, desk, admin |
| Items | `GET /items/{id}/matches` | | `Match[]` | owner |
| Matches | `GET /matches` | `?status=pending` | `Match[]` (all mine) | any |
| Matches | `POST /matches/{id}/feedback` | `{ verdict: 'mine' \| 'not_mine' \| 'unsure' }` | `Match` | owner |
| Claims | `POST /claims` | `{ match_id }` | `Claim` with generated `questions` | any |
| Claims | `POST /claims/{id}/answers` | `{ answers: [{ question_id, answer }] }` | `Claim` (scored, status set) | claimant |
| Claims | `GET /claims/{id}` | | `Claim` | claimant, finder, desk, admin |
| Claims | `GET /claims` | `?role=claimant\|finder` | `Claim[]` | any |
| Claims | `POST /claims/{id}/decision` | `{ decision: 'approve' \| 'reject' \| 'more_info', note? }` | `Claim` | finder, desk, admin |
| Handover | `GET /claims/{id}/handover` | | `Handover` | claimant |
| Handover | `POST /claims/{id}/handover` | | `Handover` (a new code, after the old one expired) | claimant |
| Handover | `POST /handover/confirm` | `{ code }` or `{ token }`, plus `{ id_checked }` | `{ claim, item }` | finder, desk, admin |
| Alerts | `GET /notifications` | | `AppNotification[]` | any |
| Alerts | `POST /notifications/{id}/read` | | 204 | any |
| Alerts | `POST /notifications/read-all` | | 204 | any |
| Alerts | `GET /notifications/stream` | SSE | `AppNotification` events | any |
| Admin | `GET /admin/claims` | `?status` | claims with score breakdown | desk, admin |
| Admin | `GET /admin/insights/summary` | `?range=7d\|30d\|term` | `{ recovery_rate, median_hours_to_reunite, live_precision, open_lost, open_found, trend[] }` | admin |
| Admin | `GET /admin/insights/hotspots` | `?range` | `{ zone_id, lost, found }[]` | admin |
| Admin | `GET /admin/insights/heatmap` | `?range` | 7 by 24 matrix of counts | admin |
| Admin | `GET /admin/insights/categories` | `?range` | `{ category, count }[]` | admin |
| Admin | `GET /admin/insights/finders` | `?range` | `{ label, points, returned }[]` | admin |
| Admin | `GET /admin/ops/scene` | `?from&to` | `{ pins[], arcs[], heat[] }` with timestamps, no user ids | admin |
| Admin | `GET /admin/eval/reports` | | `{ run_id, pairs, created_at }[]` | admin |
| Admin | `GET /admin/eval/reports/{run_id}` | | eval report | admin |

**Notes**
- SSE: `EventSource` cannot set headers, so the client uses a fetch-based SSE reader with the `Authorization` header. Tokens are never put in URLs.
- Media: public photos are served from `/media/public/{image_id}.jpg` (blurred, or a solid plate for redacted ID cards). Originals are served from `/media/original/{image_id}` only to the owner, desk, and admin.
- Errors use a single shape: `{ error: { code, message, fields? } }`. Rate-limited calls return 429 with `Retry-After`.
- The eval report shape is the one in `WEBSITE_PROMPT.md` §6.

## 8. ML pipeline and matching

### 8.1 Vision (`app/ml/vision/`)

**Detector (`detector.py`).** Loads `weights/detector.pt` if present, else COCO `yolo11n.pt`.
- COCO to campus mapping: `laptop`→laptop, `cell phone`→phone, `backpack` and `handbag`→backpack, `bottle`→bottle, `book`→book, `umbrella`→umbrella.
- Classes with no COCO equivalent (id_card, keys, earbuds, headphones, wallet, charger, power_bank, spectacles, watch, calculator, tablet, notebook) fall back to **CLIP zero-shot** on the full image.
- Primary crop: the mapped detection with the highest confidence times area; if none, the full image.

**Attribute heads (`attributes.py`).** Category comes from the trained head in `weights/heads.pt` if present (an MLP on frozen CLIP embeddings), else zero-shot CLIP prompts (`"a photo of a {category}"` with a few templates, averaged). Material follows the same rule.

**Color (`color.py`), always deterministic.** Take the primary crop, mask it to the object (GrabCut seeded by a center-weighted rectangle), run k-means (k = 3) in CIELAB, map cluster centers to a named palette by CIEDE2000, and keep up to two colors with a cluster share of at least 15%. The named palette is the 17 colors used in `WEBSITE_PROMPT.md` §6.

**OCR (`ocr.py`).** `rapidocr-onnxruntime` on the crop, and on the full image for suspected ID cards. Brand text is matched to the brand gazetteer with fuzzy matching (score 90 or more). Roll numbers use the campus regex from config (`ROLL_NO_REGEX`, default matches `CS21B042` style).

**Embedder (`embedder.py`).** `open_clip` ViT-B/32 (OpenAI weights) image and text encoders. The shared space is what lets a text-only lost report match a photo-only found report.

### 8.2 Text (`app/ml/text/`)

**Parser (`parser.py`).** spaCy `en_core_web_sm` with an `EntityRuler`. Gazetteers in `lexicons/*.yaml`:
- `categories.yaml`: synonyms and hierarchy (`bag` ⊃ `backpack`), plus sibling credit (for example earbuds and headphones share a group).
- `brands.yaml`, `colors.yaml` (with modifiers, so "navy" becomes blue), `marks.yaml` (dent, scratch, sticker, cracked, engraved), `zones.yaml` (aliases such as "lib" and "central library", generated from the campus zones).
- Regexes for serial fragments and roll numbers.
- Confidence: exact gazetteer hit 0.95, fuzzy hit at 90 or more about 0.70.

The reference case: "black Dell laptop, small dent on the lid" gives category `laptop`, brand `Dell`, color `black`, marks `[dent]`.

**Embedder (`embedder.py`).** `all-MiniLM-L6-v2` (384 dimensions) for text-to-text similarity, and the CLIP text encoder (512 dimensions) for text-to-photo.

### 8.3 Matching (`app/ml/matching/`)

**Candidate generation (`candidates.py`).** From the opposite pool, keep items with `status` in (`open`, `matched`), the same `category_group` (relaxed when either side's category confidence is below 0.5), and a passing time gate. Then take the top 50 by the best available embedding similarity (image to image, text to text, or text to image). If neither side has an embedding, fall back to recency within the category group.

**Features (`features.py`).** For each candidate pair, a value in [0, 1] and a mask for each feature:

| Feature | Definition | Mask when |
|---|---|---|
| `category` | 1.0 same category; partial credit for same group or parent (bag to backpack, earbuds to headphones); 0 otherwise | never |
| `color` | best pairing of named colors, `exp(-ΔE00 / 12)` | either side has no color |
| `brand` | 1.0 same normalized brand, 0.0 both present and different | either side has no brand |
| `image` | image-to-image CLIP cosine `c`, mapped as `clip((c - 0.55) / 0.35, 0, 1)` | either side has no photo |
| `text` | MiniLM cosine `c`, mapped as `clip((c - 0.20) / 0.60, 0, 1)` | either side has no text |
| `cross_modal` | CLIP text-to-image cosine `c` (one side's text, the other side's photo), mapped as `clip((c - 0.15) / 0.20, 0, 1)` | no text-photo pairing exists |
| `marks` | Jaccard over normalized marks with synonyms | either side has none |
| `zone` | `exp(-hops / 6)`, hops from the walking graph between the lost zone and the found zone | never |
| `time` | 1.0 if the found moment is inside the lost window; after the window, `exp(-gap_hours / 72)`; **hard gate**: a found moment before the lost window starts is excluded | never |

The mapping constants are starting values, refit by `calibrate.py`.

**Scorer (`scorer.py`).** Hand-set weights first:

| category | color | brand | image | text | cross_modal | marks | zone | time |
|---|---|---|---|---|---|---|---|---|
| 0.18 | 0.12 | 0.10 | 0.18 | 0.10 | 0.08 | 0.06 | 0.10 | 0.08 |

They sum to 1.00. With mask `m_i` and value `s_i`:

```
raw       = Σ w_i · s_i · m_i  /  Σ w_i · m_i
coverage  = Σ w_i · m_i
score     = raw · (0.5 + 0.5 · coverage)          # less evidence, less confidence
share_i   = score · (w_i · s_i · m_i) / Σ_j (w_j · s_j · m_j)     # contribution to the why breakdown
```

Each feature is reported with a `state`: `match` (value ≥ 0.85), `partial` (0.40 to 0.85), `mismatch` (below 0.40), `not_compared` (masked), and a one-sentence `detail` from templates ("Both black", "Turned in 6 hours after you lost it").

**Calibration (`calibrate.py`).** Once evaluation pairs exist: fit logistic regression (L2, scikit-learn, CPU, seconds) on `[s_i · m_i]` plus mask indicators for image, text, cross_modal, brand, and marks. Positives are the true pairs. Negatives are the hard negatives from the candidate generator. Output a calibrated probability, and contributions as `share_i = p · (β_i · x_i)⁺ / Σ_j (β_j · x_j)⁺`, so the breakdown still sums to the score. Fitting uses the 70% pair-ID split; ECE is reported on the held-out 30%. The fitted model is saved with a `model_version` that is stored on every match.

**Bands and thresholds.** Strong at 0.75 and above, Possible from 0.40 to below 0.75, Long shot below 0.40. Hidden below 0.20. Notify at 0.60 and above. All from config.

**Index (`index.py`).** A `VectorIndex` interface with two implementations: pgvector (HNSW, cosine) when the extension exists, and an in-memory numpy brute-force index, rebuilt from `bytea` at startup, which is fast enough for campus scale (under 10,000 items).

### 8.4 Pretrained fallbacks versus trained weights

| Stage | Fallback (works on day 3) | Trained (compute bucket) | How it is picked up |
|---|---|---|---|
| Detector | COCO YOLO11n plus CLIP zero-shot for non-COCO classes | YOLO11n fine-tuned on ~18 campus classes (`02`) | `backend/weights/detector.pt` exists |
| Category / material | CLIP zero-shot prompts | MLP heads on frozen CLIP embeddings (`03`) | `backend/weights/heads.pt` exists |
| Color | Deterministic k-means in CIELAB | none | n/a |
| Text extraction | spaCy plus gazetteers | none | n/a |
| Embedding projection | Raw CLIP and MiniLM | Triplet fine-tune of the projection (`04`, stretch) | `weights/projection.pt` exists |
| Scorer | Hand-set weights | Logistic calibration (`calibrate.py`, CPU) | `weights/calibration.json` exists |

`training/export.py` writes `weights/*.pt` and `model_card.json` (class list, metrics, data sources, date). The registry loads whatever is present at startup and logs which path each stage took, and `GET /admin/eval/reports` shows the model card alongside the results.

### 8.5 Jobs (`app/jobs.py`)

A `jobs` table plus a single asyncio worker that polls every 500 ms with `SELECT … FOR UPDATE SKIP LOCKED`. Stages are chained: creating an item enqueues `ingest`, which enqueues `extract`, then `match`, then `notify`. Editing an item enqueues `extract` (if text or photos changed) and `match`. Retries: 3 attempts with exponential backoff, then `failed` with the error stored. Model calls run in a one-thread executor to keep memory flat.

## 9. Claims, handover, notifications, insights

### 9.1 Claim verification (`services/claims.py`)

**Hiding.** On a found report, attributes marked private go to `hidden_attributes`. Public responses carry only coarse attributes and a blurred photo.

**Questions.** On `POST /claims`, generate three or four questions from the hidden attributes and a few safe coarse ones: text ("What's on the sticker on the lid?"), choice (colors, with distractors), zone, and datetime. Specific attributes (serial fragment, marks, contents) are weighted higher.

**Scoring.** Text answers: `max(rapidfuzz token_set_ratio / 100, mapped MiniLM cosine)`. Choice and zone: exact. Datetime: 1.0 within 3 hours, decaying after. Then:

```
A = weighted mean of answer scores           (weights: serial 2.0, marks 1.5, others 1.0)
M = claimant's own lost-report match score for this item (0 if none)
S = account signals score  (verified college email required; penalties for prior rejected claims)
C = 0.60·A + 0.25·M + 0.15·S
```

**Decisions.**
- Hard blocks: unverified email, more than 3 claims in 24 hours, a second open claim on the same item.
- `C < 0.45`: rejected, retry after 24 hours.
- `0.45 ≤ C < 0.75`: `pending_review`, or `needs_more_info` once.
- `C ≥ 0.75`: `auto_approved` if the item's `value_tier` is `low`, otherwise `pending_review`.
- **Always human review** for categories in `ALWAYS_REVIEW` (default `laptop`, `phone`, `id_card`), whatever the score.
- Finder or desk can approve, reject, or ask for more information through `POST /claims/{id}/decision`.

**ID cards.** OCR extracts the roll number, which is looked up against `users.roll_no`. On an exact match the owner is notified directly, the claim is created with `verified_by = roll_number` and skips the questions. The human check happens at handover: the desk must confirm `id_checked` when confirming the code. The card is redacted in all public views.

### 9.2 Handover (`services/handover.py`)

On approval, create a handover: a signed token (`{claim_id, jti, exp}`, 15 minutes) rendered as a QR, and a random six-digit code stored as a salted hash. `POST /handover/confirm` (finder, desk, admin) accepts the code or the token, allows 5 attempts, then on success sets the claim to `handed_over`, the item to `returned`, writes an `item_events` row, adds 10 points to the finder, and notifies both parties. An expired handover can be re-issued by the claimant.

### 9.3 Notifications (`services/notify.py`)

After a `match` job, for each match with score at or above `NOTIFY_THRESHOLD` (0.60) and no prior notification for that user and match:
1. Insert a `notifications` row.
2. Publish to the user's in-process SSE queue.
3. Send Web Push (`pywebpush`, VAPID keys from `scripts/gen_vapid.py`) if the user has a subscription and `notify_push` is on.
4. Send email if `notify_email` is on (console backend in development, SMTP when configured).

Claim, handover, and return events create notifications the same way.

### 9.4 History (`services/events.py`)

Every state change writes an `item_events` row: reported, matched, claimed, verified, handed over, closed. Attribute edits write `attribute_labels`, not timeline events. The timeline endpoint returns only the six public types.

### 9.5 Insights (`services/insights.py`)

- **Hotspots:** lost count per zone in range.
- **Hour by weekday grid:** midpoint of each lost window, bucketed 7 by 24.
- **Category mix:** lost counts per category.
- **Recovery rate:** returned lost reports divided by all lost reports in range.
- **Median time to reunite:** median hours from a lost report's creation to its handover confirmation.
- **Live match precision:** `mine / (mine + not_mine)` from match feedback in range (`unsure` excluded).
- **Top finders:** points and returned counts with an anonymized label (`Finder A`, `B`, …), never an email.
- **Ops scene:** zone-level pins with timestamps, match arcs between zones with band and score, per-zone heat counts. No user ids, no exact positions.

## 10. Front end and integration

**Decision for now:** the front end is generated in Replit from `WEBSITE_PROMPT.md` on the template you pick, with a mocked API client. The client's function names and shapes match §7 exactly.

**Path A, the default: Replit-generated.**
1. Generate in Replit (milestones M1 to M4 in the prompt).
2. Export the project (download a zip or sync to a Git repository) into `frontend/`.
3. Run it locally: `npm install` and the template's dev command, on port 5190 (or the template's port if it cannot be changed).
4. Set the API mode variable (with the template's public prefix, for example `VITE_API_MODE`) from `mock` to `http://localhost:8010`.
5. Add the front end's origin to the backend `CORS_ORIGINS`.

Do **not** point the Replit-hosted preview at `localhost:8010`: Replit runs remotely and cannot reach the Mac. Either run the exported front end locally (recommended) or expose the backend through a tunnel and add that origin to CORS.

**Path B, fallback:** build the front end in this repo with Claude Code and the anti-ai-slop and frontend-design skills, using the same prompt as the spec.

**Integration checklist.**
- [ ] Every function in the client maps to a §7 row. Mismatches are fixed on the backend if the client shape is right, and on the client otherwise.
- [ ] SSE uses a fetch-based reader with the `Authorization` header.
- [ ] Media URLs come from the API. The client never builds paths.
- [ ] `GET /taxonomy` drives the chip vocabulary and the color hex values.
- [ ] `GET /zones` replaces the mock GeoJSON, and the ops view reads `campus.config` for the map center.
- [ ] The service worker registers only in production builds.

The 3D view uses Cesium ion OSM Buildings, zone polygons from `zones.geojson`, lost and found pins at zone level, match arcs colored by confidence, a hotspot layer, a Cesium clock and timeline replay over seven days, and NVG and thermal post-process shaders (stretch) ported from `gods-eye-view` with MIT attribution in `THIRD_PARTY_NOTICES.md`. It shows items only. It falls back to a 2D schematic when the token or WebGL is missing.

## 11. Evaluation harness

**Manifest.** `eval/pairs/manifest.csv` with `pair_id, side, image, text, zone, timestamp`. Each `pair_id` has one `lost` and one `found` row.

**`run_eval.py`.** Runs the extraction and matching functions directly (no database needed) on the manifest:
1. Extract attributes and embeddings for every row, using the same code paths as the API.
2. For each lost query, generate candidates from **all** found rows, score, and rank.
3. Compute P@1, P@5, P@10 (success@k), Recall@k, MRR, mAP.
4. Calibrate on the 70% pair-ID split, and compute ECE and reliability bins (10 equal-width) on the held-out 30%.
5. Compute the per-category breakdown.
6. Run the **ablation** by masking feature groups: image only, text only, + attributes, + text-to-photo, + location and time.
7. Write `eval/reports/<date>.json` (shape in `WEBSITE_PROMPT.md` §6) and a matching `.md` summary that names the pair set.

Flags: `--pairs synthetic|real|both`, `--seed`, `--pool-size`, `--no-calibrate`.

**`synthetic_pairs.py`.** From about 100 public photos: a "lost" view and a "found" view made by augmentation (crop, rotation, color jitter, blur, brightness, background shift), with text generated from ground-truth attributes plus noise (dropped attributes, synonyms, typos), and zones and times drawn from plausible walks. The output is tagged `pairs: synthetic` and labeled optimistic everywhere it is shown.

## 12. Compute vs non-compute split

### Non-compute (built in this repo, running on pretrained inference)

- [x] Repo scaffold, `.env.example`, launch configs
- [x] DB models, Alembic migrations, OTP auth, zone config and `build_campus_zones.py`
- [x] Text parser, lexicons, embedders, unit tests
- [x] Detector with fallback, attribute heads with fallback, color, OCR
- [x] Features, scorer, candidate generation, index, jobs, match job
- [x] All API endpoints in §7
- [x] Claims, handover, notifications, history, insights, ops scene
- [x] Eval harness, synthetic pairs, calibration code
- [x] Seed demo data and `seed_demo.py`
- [x] Training notebooks and `export.py` (written now, run later)
- [x] Front-end integration (§10), README, `THIRD_PARTY_NOTICES.md`

### Compute and human (you run these, then drop files in)

- [ ] **Photograph 150 to 300 real lost/found pairs** (same object, different angle, place, and time) and fill `eval/pairs/manifest.csv`. The capture guide is in `eval/README.md`.
- [ ] **Run `training/01` to `03` on Colab or Kaggle GPU**, then copy the exported `weights/` into `backend/weights/`. (`04` is stretch.)
- [ ] **Rerun `python -m eval.run_eval`** for the before and after table used in the pitch.
- [ ] Paste the Cesium ion token into `.env` and, if you use Web Push, run `scripts/gen_vapid.py` once.
- [ ] Generate the front end in Replit from `WEBSITE_PROMPT.md` and export it into `frontend/`.

## 13. Schedule and team roles

**Roles** (merge them if the team is smaller):
- **A. Backend and ML lead:** API, database, jobs, ML modules, matching.
- **B. Front-end lead:** Replit generation, export, integration, polish.
- **C. Data and eval:** pair collection, synthetic pairs, eval harness, notebooks on Colab.
- **D. Pitch, QA, and design:** PRD sign-off, demo script, bug bash, slides.

Assume a 12-day plan. Days 11 and 12 are buffer, so a slip on any day up to 10 does not cost the demo.

| Day | A. Backend / ML | B. Front end | C. Data / eval | D. Pitch / QA |
|---|---|---|---|---|
| 1 | Scaffold, models, Alembic, OTP auth, zone config | Paste `WEBSITE_PROMPT.md` into Replit, start M1 | Capture guide, start photographing pairs | Sign off PRD, outline the pitch |
| 2 | Text parser, lexicons, embedders, tests | Finish M1 (report flow, live chips) | Fetch Open Images subset (FiftyOne) | Review M1, write demo script draft |
| 3 | Detector, attributes, color, OCR (pretrained) | M2: deck, claim, handover, notifications on mocks | Synthetic pair generator, notebook 01 | Pick demo scenario and seed items |
| 4 | Features, scorer, index, candidates, match job | Finish M2 | Eval harness skeleton | Review M2 |
| 5 | End-to-end `extract` to `match`; `run_eval --pairs synthetic` | Export to `frontend/`, switch items and matches to live | Run first eval, fix harness | Test the flow on a phone |
| 6 | Claims and handover services | Wire claim and handover screens | Run notebook 02 (YOLO fine-tune) on Colab | Claim-fraud test cases |
| 7 | Notifications (SSE, Push, email), item events | Wire notifications and timeline | Notebook 03 (attribute heads) | Accessibility check |
| 8 | Insights endpoints, ops scene endpoint | M3: admin screens on live data | First real-pair eval (pretrained baseline) | Draft pitch numbers |
| 9 | Zones from OSM, `calibrate.py` on real pairs | Cesium view wired to the scene endpoint | Drop trained weights, rerun eval (before and after) | Update slides with real numbers |
| 10 | Seed data, README, full end-to-end walkthrough | M4 polish, empty and error states | Final eval report and reliability diagram | Bug bash, demo rehearsal 1 |
| 11 | Buffer, fixes, optional stretch (metric learning `04`) | Buffer, NVG and thermal polish | Ablation and per-category write-up | Demo rehearsal 2 |
| 12 | Freeze | Freeze | Freeze | Record a backup demo video, final slides |

Days 13 and 14, if the schedule allows, go to the stretch items in the PRD.

## 14. Setup and run

**One-time setup (needs downloads).**

```bash
cd /Volumes/Dawnstrike/reunite
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python -m spacy download en_core_web_sm
brew services start postgresql@16
createdb reunite
cp .env.example .env               # fill DATABASE_URL, JWT_SECRET, ALLOWED_EMAIL_DOMAINS
python scripts/download_weights.py # yolo11n, CLIP ViT-B/32, MiniLM, RapidOCR models
```

Approximate downloads: `yolo11n` about 6 MB, CLIP ViT-B/32 about 350 MB, MiniLM about 90 MB, spaCy small about 12 MB, RapidOCR about 15 MB, plus about 100 Open Images validation photos for seed data.

**Try pgvector (optional, with a fallback).**

```bash
git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git /tmp/pgvector
cd /tmp/pgvector && make && make install PG_CONFIG="$(brew --prefix postgresql@16)/bin/pg_config"
psql reunite -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

If any step fails, leave it. The numpy index is used automatically.

**Database and seed.**

```bash
alembic -c backend/alembic.ini upgrade head
python scripts/build_campus_zones.py --bbox <lat_s,lon_w,lat_n,lon_e>   # after the campus is known
python scripts/seed_demo.py
python scripts/gen_vapid.py        # only if you use Web Push
```

**Run.** Add `reunite-backend` (port 8010) and `reunite-frontend` (port 5190) to `/Volumes/Dawnstrike/.claude/launch.json`, or run by hand:

```bash
cd backend && uvicorn app.main:app --port 8010 --reload
cd frontend && npm install && npm run dev -- --port 5190
```

## 15. Verification

**Unit tests (`pytest backend/tests`).**
- Parser: "black Dell laptop, small dent on the lid" gives category `laptop`, brand `Dell`, color `black`, marks `[dent]`; further cases for synonyms, hierarchy, roll-number and serial regexes.
- Color naming from cluster centers to the palette.
- Feature masking: masked features are excluded from the score and from `coverage`.
- Time and zone gating: found before the lost window starts is excluded; decay is monotonic.
- Scorer monotonicity: raising any feature value never lowers the score; shares sum to the score.
- Claim scoring: thresholds, hard blocks, and the always-review categories.
- Handover token: valid, expired, tampered, wrong code, and attempt limit.

**Evaluation smoke test.** `python -m eval.run_eval --pairs synthetic` produces P@1, P@5, MRR, ECE and the ablation table without errors, and writes both report files.

**End-to-end in the browser** (start `reunite-backend` and `reunite-frontend`):
1. Sign up with OTP (the code is in the backend console).
2. User A reports a lost item, text only.
3. User B reports a found item with a photo. The extracted attributes appear as chips.
4. A's deck shows B's item with a confidence and a why-breakdown, and a notification arrives.
5. A claims and answers the private-attribute questions, B approves, and the handover code completes the return.
6. The timeline shows every event.
7. The admin Insights page, the Cesium view (zones, pins, arcs, time slider), and the Eval page render.

Check the browser console and network tab for errors, and screenshot the key screens.

## 16. Configuration reference

All in `.env` (see `.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://localhost/reunite` | Postgres connection |
| `JWT_SECRET` | none, required | Token signing |
| `ALLOWED_EMAIL_DOMAINS` | empty (accept any address in development) | Sign-in rule; set to the campus domain(s) |
| `CORS_ORIGINS` | `http://localhost:5190` | Allowed front-end origins |
| `MEDIA_DIR` | `data/media` | Upload storage |
| `DEVICE` | `auto` | `mps`, `cpu`, or auto |
| `NOTIFY_THRESHOLD` | `0.60` | Notify at or above |
| `BAND_STRONG` / `BAND_POSSIBLE` / `MIN_SHOW` | `0.75` / `0.40` / `0.20` | Confidence bands |
| `ALWAYS_REVIEW` | `laptop,phone,id_card` | Categories that always need a person |
| `ROLL_NO_REGEX` | `[A-Z]{2}\d{2}[A-Z]\d{3}` | ID-card roll number pattern (campus-specific) |
| `RETENTION_DAYS` | `90` | Purge closed items after |
| `EMAIL_BACKEND` | `console` | `console` or `smtp` |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` | unset | Email delivery |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_SUBJECT` | unset | Web Push |
| `CAMPUS_NAME` | `<<CAMPUS_NAME>>` | Copy and manifest |
| `CESIUM_ION_TOKEN` | `<<CESIUM_ION_TOKEN>>` | 3D buildings (front-end variable, with the template's public prefix) |

## 17. Implementation notes (where the build differs from the design above)

Written after the non-compute work was finished, so this is what is true, not what was intended.

- **Category as a distribution.** The photo classifier keeps its top guesses (`category.alts`), and the `category` feature is the *expected* credit over both sides' distributions (1.0 same category, 0.5 same group, 0 otherwise, 0.3 for probability the classifier left unassigned). Candidate generation gates on the probability that both items share a category group (at least 0.10, or a side is unsure with under 0.5 of its probability classified). This replaced a first version that relaxed the whole gate whenever one guess was under 0.5 confidence, which let a lost laptop match a found bottle.
- **Text parsing.** spaCy's `EntityRuler` runs on `spacy.blank("en")` (tokenizer only) rather than `en_core_web_sm`: the gazetteer lookups need no statistical model. A rapidfuzz pass (score 90 or more, same first letter) handles typos.
- **Handover codes** are derived with HMAC from the claim and a per-issue id, so the claimant's app can show the code again after a reload; only a salted hash is stored for checking. Wrong-code attempts are limited per confirming user (5 per 15 minutes), because code entry does not say which handover is meant. `POST /claims/{id}/handover` re-issues an expired one.
- **Zone questions** in claim verification are scored by walking hops (same zone 1.0, one hop 0.8, two 0.5, else 0.2), not exact match: the claimant was where they lost it, the finder where they found it.
- **Recall@k** in the eval report is candidate generation alone (is the true match in the top k by embedding similarity?); P@k is end to end. With one true match per query, P@k equals success@k, and mAP equals MRR.
- **Vector index.** `NumpyIndex` and `PgVectorIndex` (HNSW, cosine, mirror columns from `scripts/enable_pgvector.py`) are implemented and tested against each other, but the match job brute-forces the gated pool in Python, which is fast at campus scale. Wire the index in only if a pool passes a few thousand items.
- **OCR** is capped at 512 px on the object crop (960 px on the full image for a suspected ID card), single-threaded by default (`OCR_THREADS`). More threads were slower on a busy 8 GB machine. Categories that rarely carry printed brands (umbrella, keys, spectacles) skip OCR.
- **Postgres on macOS** needs `LC_ALL=en_US.UTF-8` in its environment or it aborts with "postmaster became multithreaded during startup".
- **Seed and eval photos** cover 11 of the 18 categories (Open Images has no class for ID cards, keys, earbuds, wallets, chargers, power banks). Those appear as text-only synthetic pairs, and the seed draws an ID card and uses procedural plates where a photo is missing.
- **Not run:** the training notebooks (they need a GPU), and the eval on real pairs (they need your photographs).
