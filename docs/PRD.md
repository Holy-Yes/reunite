# Reunite: Product Requirements Document

Campus lost-and-found intelligence. Hackathon build, AI/ML and Data Science track, 10 to 14 days.

Companion documents: [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) (engineering plan, schema, endpoints, schedule) and [`WEBSITE_PROMPT.md`](WEBSITE_PROMPT.md) (front-end prompt for Replit). Where they overlap, the endpoint list, schema, metrics, and scope tiers are the same in all three.

Placeholders that are still open: `<<CAMPUS_NAME>>` (zones, map, copy) and `<<CESIUM_ION_TOKEN>>` (3D view). Nothing else blocks the build.

---

## 1. Problem

Students lose ID cards, laptops, books, chargers, earbuds, and bottles. Finders hand items to a security desk, or leave them where they were found. Reuniting the two today is manual: a notice board, a WhatsApp group, a register at the desk. Three things go wrong:

- **Nobody can search the other side well.** A loser says "black bag", the finder says "dark rucksack, zip broken". Keywords don't line up, photos aren't compared, and place and time are ignored.
- **Claims are unverified.** Whoever asks first and sounds confident gets the item, so honest owners lose out and fraud is easy.
- **The desk has no picture of the whole.** Nobody sees which places lose the most, how long items sit, or how many come home.

## 2. Product in one paragraph

Reunite turns a lost or found report (photo, text, or both) into structured attributes and embeddings, then ranks candidates from the opposite pool with a **calibrated confidence** and a plain-language **why**. The owner reviews candidates in a swipe deck, proves ownership by answering questions built from details only the finder recorded, and collects the item with a signed QR and six-digit code. Staff get a claims queue, an insights dashboard, and a 3D campus view of items. The pipeline mirrors detection and tracking: a detector plus attribute heads is the detector, the appearance embedding is re-identification, location and time gates are motion gating, and the ranked association is data association.

## 3. Goals and non-goals

### Goals

1. **Rank the right item near the top.** Success@1 of at least 0.60 and Success@5 of at least 0.85 on the evaluation pairs (definition in §8).
2. **Honest confidence.** Scores are calibrated, so "80% likely" is right about 80% of the time (ECE reported).
3. **Explainable matches.** Every candidate shows which attributes helped and which did not.
4. **Fraud-resistant claims.** Verification uses details hidden from the public listing.
5. **Works on a laptop.** Full stack runs on an 8 GB Apple-silicon Mac with small, offline-capable models. The app works end to end before any GPU training.
6. **Measured, not claimed.** An evaluation harness produces before/after tables that go straight into the pitch.

### Non-goals

- Tracking people, faces, or movement. Items only, and location is always at zone level.
- Camera or CCTV integration.
- Payments, rewards with cash value, or chat between users. Contact happens only through claims and handover.
- A native mobile app. A PWA is enough.
- Training a model from scratch. We fine-tune small heads and, optionally, a detector.

## 4. Personas

| Persona | Situation | Wants | Fears |
|---|---|---|---|
| **The loser** (student) | Just realized something is gone. On a phone, between lectures. | To describe it in seconds and be told when it turns up. | Wasting time; the finder never seeing the report. |
| **The finder** (any student or staff) | Picked up something that isn't theirs. | To hand it in fast and know it reached the owner. | Being accused; handing it to the wrong person. |
| **The desk** (security staff, admin) | Holds items and answers "has anyone found my…?" all day. | A queue of claims to verify, proof they gave it to the right person, a campus-wide view. | Fraudulent claims; an unmanageable stack of items. |

## 5. User stories

**Loser**
- US-1. I can report a lost item with only text, only a photo, or both, and correct anything the system got wrong.
- US-2. I see ranked candidates with a confidence and the reasons, and can say "that's mine" or "not mine" with one gesture.
- US-3. I'm told when a new candidate appears, without checking the app.
- US-4. I can prove the item is mine without the public seeing its identifying details.
- US-5. I collect the item with a code I can show on my phone, then see the whole story on a timeline.

**Finder**
- US-6. I can report a found item with a photo in under a minute and mark details as private.
- US-7. I can say where the item is now (with me, or at a desk).
- US-8. I see when my item is claimed and get credit when it's returned.

**Desk**
- US-9. I review claims in a queue, with the answers beside the details they should match.
- US-10. Laptops, phones, and ID cards always reach me for a human decision.
- US-11. I confirm a handover by scanning or typing a code, which closes the item and logs it.
- US-12. I see where items are lost most, at which hours, and how many are returned and how fast.
- US-13. I see the campus in 3D with item pins, match arcs, and a replay of the last week.

**Everyone**
- US-14. I sign in with my college email and a one-time code.
- US-15. If my ID card is found, I'm told directly, without answering questions.
- US-16. Nothing about me as a person is tracked or shown publicly.

## 6. Functional requirements

Tier tags: **[MVP]** must ship, **[EXTRA]** in scope, built after MVP, **[STRETCH]** only if time remains. Tiers are consolidated in §10.

### 6.1 Authentication (FR-AUT)
- FR-AUT-1 [MVP] College-email OTP sign-in. Domain allow-list from config. Codes expire in 10 minutes, 5 attempts, resend cooldown 30 s.
- FR-AUT-2 [MVP] Roles: `student`, `desk`, `admin`. Token-based sessions.
- FR-AUT-3 [EXTRA] Optional roll number on the profile, used only for ID-card lookup.

### 6.2 Reporting (FR-REP)
- FR-REP-1 [MVP] Report **lost** or **found** with any of: 1 to 3 photos, free text, zone, time (lost is a window, found is a moment).
- FR-REP-2 [MVP] Found reports record custody (with finder, or at a named desk).
- FR-REP-3 [MVP] Camera capture in the browser, with a file-upload fallback.
- FR-REP-4 [MVP] Live extraction preview before submit; every extracted attribute is editable, removable, and addable.
- FR-REP-5 [MVP] Corrections are stored as labels for later training.
- FR-REP-6 [EXTRA] Finders mark attributes as private (used only to verify claims).
- FR-REP-7 [EXTRA] Drafts survive a refresh and offline; submit queues when offline.
- FR-REP-8 [MVP] Uploaded photos have EXIF stripped (including GPS) and are resized on ingest.

### 6.3 Attribute extraction (FR-EXT)
- FR-EXT-1 [MVP] Vision: detect the main object; classify category (18 classes, listed in §11); read up to two colors; OCR for brand text and ID-card text.
- FR-EXT-2 [MVP] Text: extract category, brand, color, marks, serial or roll number from free text using gazetteers and synonyms.
- FR-EXT-3 [MVP] Every attribute carries a confidence and a source (`photo`, `text`, `ocr`, `user`). Low-confidence attributes are flagged in the UI.
- FR-EXT-4 [MVP] Every model has a pretrained or rule-based fallback, so extraction works before any training.
- FR-EXT-5 [EXTRA] Trained weights, if present, are loaded automatically and override the fallback.

### 6.4 Matching (FR-MAT)
- FR-MAT-1 [MVP] Each new or edited report is matched against the opposite pool by a background job.
- FR-MAT-2 [MVP] Candidate generation: opposite kind, open status, category group, time gate, then nearest neighbors by embedding (top 50).
- FR-MAT-3 [MVP] Rerank with a weighted feature score over: category (hierarchy-aware), color, brand, image similarity, text similarity, text-to-photo similarity, marks, zone, time. Missing modalities are masked and the score is renormalized with an evidence penalty.
- FR-MAT-4 [MVP] Output a score in [0, 1], a band (Strong at 0.75 and above, Possible from 0.40, Long shot below), a rank, and a per-feature breakdown.
- FR-MAT-5 [EXTRA] Logistic-regression calibration fitted on evaluation pairs, producing a probability and per-feature contributions.
- FR-MAT-6 [EXTRA] Zone proximity from a walking-graph (hops), time plausibility with decay.
- FR-MAT-7 [MVP] Text-only reports match against photo-only reports (shared image-text embedding space).
- FR-MAT-8 [STRETCH] Metric-learning fine-tune of the embedding projection on collected pairs.

### 6.5 Matches and swipe deck (FR-SWP)
- FR-SWP-1 [MVP] A card deck of candidates with confidence meter, band, headline, place and time.
- FR-SWP-2 [MVP] "Why this match" breakdown with plain-language detail per feature.
- FR-SWP-3 [MVP] Actions: That's mine, Not mine, Not sure. Available by swipe, buttons, and keyboard. Undo the last decision.
- FR-SWP-4 [MVP] Every decision is stored as feedback and feeds the live-precision metric.
- FR-SWP-5 [MVP] Candidate photos are blurred and private attributes withheld until verification.

### 6.6 Claims and verification (FR-CLM)
- FR-CLM-1 [EXTRA] "That's mine" starts a claim with three or four questions generated from the finder's private attributes.
- FR-CLM-2 [EXTRA] Each answer is scored by fuzzy string and embedding similarity. The claim score combines answer score, the claimant's own lost-report match score, and account signals.
- FR-CLM-3 [EXTRA] Outcomes: auto-approve (low-value items above threshold), pending review, needs more info, rejected (retry after 24 h).
- FR-CLM-4 [EXTRA] Laptops, phones, and ID cards always go to human review.
- FR-CLM-5 [EXTRA] Limits: one open claim per claimant per item, claim rate limit per account, verified email required.
- FR-CLM-6 [EXTRA] ID cards: the OCR'd roll number is matched to a user, who is notified directly and skips the questions. A person still checks the college ID at handover.
- FR-CLM-7 [EXTRA] Finder or desk can approve, reject, or ask for more information, with a note.

### 6.7 Handover (FR-HND)
- FR-HND-1 [EXTRA] An approved claim produces a handover pass: signed QR and a six-digit code, expiring in 15 minutes and renewable.
- FR-HND-2 [EXTRA] Finder or desk confirms by scanning or typing the code. Attempts are limited.
- FR-HND-3 [EXTRA] Confirmation marks the item returned, writes the timeline event, credits the finder with points, and notifies both sides.

### 6.8 Notifications (FR-NTF)
- FR-NTF-1 [EXTRA] In-app notifications delivered live over SSE.
- FR-NTF-2 [EXTRA] Web Push (VAPID) and email for matches at or above the notify threshold (default 0.60).
- FR-NTF-3 [EXTRA] At most one notification per user per match. Users can turn push and email on or off.
- FR-NTF-4 [EXTRA] Editing a report re-runs matching.

### 6.9 Item history (FR-HIS)
- FR-HIS-1 [EXTRA] A per-item timeline: reported, matched, claimed, verified, handed over, closed.
- FR-HIS-2 [EXTRA] Each event records time and actor role.

### 6.10 Insights (FR-INS)
- FR-INS-1 [EXTRA] Recovery rate, median time to reunite, live match precision (from thumbs).
- FR-INS-2 [EXTRA] Loss hotspots by zone, an hour-by-weekday grid, category mix, top finders (anonymized).
- FR-INS-3 [EXTRA] Range: 7 days, 30 days, term. Every chart has a table alternative.

### 6.11 Campus ops 3D view (FR-OPS)
- FR-OPS-1 [EXTRA] Cesium view with OSM Buildings, zone polygons, zone-level lost and found pins.
- FR-OPS-2 [EXTRA] Match arcs colored by confidence, a hotspot layer, a seven-day replay with a time slider.
- FR-OPS-3 [EXTRA] A 2D fallback when the Cesium token or WebGL is missing.
- FR-OPS-4 [STRETCH] NVG and thermal post-process modes ported from `gods-eye-view` (MIT) with attribution in `THIRD_PARTY_NOTICES.md`.
- FR-OPS-5 [EXTRA] Constraint on the whole view: items and zones only. No people, no cameras, no exact positions.

### 6.12 Evaluation (FR-EVL)
- FR-EVL-1 [MVP] A harness that runs the full matching pipeline on a pair manifest and reports success@1/5/10, recall@k, MRR, mAP, ECE with a reliability diagram, a per-category breakdown, and an ablation table.
- FR-EVL-2 [MVP] Synthetic-pair generator, clearly labeled optimistic.
- FR-EVL-3 [EXTRA] Reports written to `eval/reports/<date>.json` and `.md`, rendered on the admin Eval page.

## 7. Non-functional requirements

**Privacy and safety**
- Item-level tracking only. No user location, no face processing, no people in the 3D view.
- Public listings show coarse attributes (category, colors, brand, zone, date) and a **blurred** photo. Blurring is done server-side; the original is available only to the owner, desk, and admin.
- Private attributes never leave the server except to the owner of the found item and to desk and admin.
- ID cards are redacted in public views, and roll numbers are never placed in URLs.
- EXIF and GPS are stripped on upload. Uploaded images are re-encoded.
- Rate limits on OTP, claims, and handover confirmation. Tokens and codes are stored hashed.
- Closed items are purged after a retention period (default 90 days, configurable).

**Performance targets on an 8 GB Apple-silicon Mac (targets, to be measured)**
- Text-only extraction preview: under 300 ms.
- Photo extraction preview: under 3 s at the 95th percentile.
- Matching one new report against 10,000 items: under 2 s.
- All models resident: under 3 GB of backend memory.

**Offline and portability**
- All models run locally after a one-time download. No calls to external inference APIs.
- Postgres 16 required. pgvector is optional; a numpy brute-force index is the fallback.

**Accessibility and UX**
- WCAG AA contrast, keyboard operable, reduced-motion respected, 44 px touch targets, mobile-first.
- Empty, loading, and error states for every screen.

**Reliability**
- The matching job is idempotent and retried. Failures surface as a visible "checking again" state, never a silent gap.

## 8. Success metrics and evaluation plan

### Definitions

The brief asks for P@1 and P@5. Every query has exactly one true counterpart, so strict precision at 5 could never exceed 0.2. We therefore report **success@k** (the true counterpart appears in the top k) under the name P@k, matching the brief's wording. The two names mean the same thing in `IMPLEMENTATION_PLAN.md`, the eval harness, and the admin Eval page.

| Metric | Definition | Target |
|---|---|---|
| **P@1** (success@1) | Share of queries whose true match is ranked first | ≥ 0.60 |
| **P@5** (success@5) | Share of queries whose true match is in the top 5 | ≥ 0.85 |
| P@10, Recall@k | Same idea at k = 10; recall@k equals success@k with one counterpart, and is kept for pools with duplicates | reported |
| **MRR** | Mean of 1 / rank of the true match | reported |
| mAP | Mean average precision over queries | reported |
| **ECE** | Expected calibration error, 10 equal-width bins, on held-out (query, candidate) pairs | lower is better; reported with a reliability diagram |
| **Time to reunite** | Median hours from lost report to confirmed handover | tracked live |
| **Recovery rate** | Returned lost reports divided by all lost reports in range | tracked live |
| **Live match precision** | "That's mine" divided by ("That's mine" plus "Not mine") | tracked live |

Targets for P@1 and P@5 are goals, not claims. The pitch shows measured numbers with the pair set named (synthetic or real).

### Evaluation plan
1. **Pair manifest.** `eval/pairs/manifest.csv` with columns `pair_id, side, image, text, zone, timestamp`. Each `pair_id` has one lost side and one found side of the same object.
2. **Pool.** For each lost query, rank against **all** found items in the manifest. Larger pools make the test harder and more honest.
3. **Splits.** Calibration is fitted on 70% of pair IDs and evaluated on the held-out 30%. No pair appears on both sides of the split.
4. **Ablation table.** image only, text only, + attributes, + text-to-photo, + location and time.
5. **Per-category breakdown** to expose weak classes.
6. **Before and after.** Run once with pretrained fallbacks, again after the trained weights and calibration are in.
7. **Synthetic pairs** (labeled optimistic) exist so the harness runs from day one. Real pairs are the numbers that go on the slide.

### Dataset plan
- **Real pairs (human task):** photograph 150 to 300 lost/found pairs of the same object from different angles, places, and times, and write a short text for each side. A capture guide lives in `eval/README.md`.
- **Public data:** about 100 Open Images validation photos for demo seed data; Open Images and LVIS subsets for the roughly 18 campus classes to train the detector (via FiftyOne).
- **Synthetic pairs:** augmentation of public photos (crop, rotation, color jitter, blur, brightness) with generated, noisy text descriptions.
- **Corrections:** every edit a user makes to an extracted attribute is stored as a label for future fine-tuning.

## 9. Hackathon judging map

Assumed rubric (replace with the organizers' actual one if it differs):

| Criterion | Where we show it |
|---|---|
| Problem and impact | §1; recovery rate and time-to-reunite tracked live |
| Technical depth (AI/ML) | Detector plus attribute heads, image-text embeddings, hierarchy-aware features, calibrated ranking |
| Data and evaluation rigor | Eval harness, ablations, reliability diagram, real-pair numbers next to synthetic |
| Working demo | Full flow: report, match, claim, handover, timeline, insights, 3D view |
| Responsible design | Item-only tracking, private attributes, blurred photos, ID redaction, EXIF stripping |
| UX and polish | Swipe deck with a why-breakdown, live extraction chips, distinct visual identity |
| Feasibility | Runs on an 8 GB laptop with offline models; every stage has a fallback |

## 10. Scope tiers

| Tier | Contents |
|---|---|
| **MVP** | Auth (OTP), report lost/found with photo and text, attribute extraction with editable chips, matching with scores, bands, and why-breakdown, swipe deck with feedback, eval harness on synthetic pairs, in-app item status |
| **Extras** (build in this order) | Claim verification, handover QR and code, in-app plus Web Push plus email notifications, item timeline, location and time-aware scoring, calibration, insights dashboard, ID-card roll-number lookup, Cesium ops view (with 2D fallback), eval page, trained weights from the notebooks |
| **Stretch** | NVG and thermal modes, metric-learning fine-tune, top-finder gamification beyond points, multi-campus support |

## 11. Reference data

**Categories (18):** `id_card`, `laptop`, `phone`, `tablet`, `earbuds`, `headphones`, `charger`, `power_bank`, `wallet`, `keys`, `backpack`, `bottle`, `book`, `notebook`, `spectacles`, `watch`, `umbrella`, `calculator`.

**Confidence bands:** Strong at 0.75 and above, Possible from 0.40 to below 0.75, Long shot below 0.40. Below 0.20 is hidden. Notifications fire at 0.60 and above. All three thresholds are configuration.

**Item lifecycle:** `processing` → `open` → `matched` → `claimed` → `returned` → `closed`.

**Claim lifecycle:** `draft` → `pending_review` | `needs_more_info` | `auto_approved` | `rejected` → `approved` → `handed_over`.

**Module to API mapping** (full list in `IMPLEMENTATION_PLAN.md` §7 and `WEBSITE_PROMPT.md` §6):

| Module | Endpoint group |
|---|---|
| Auth | `/auth/otp/*`, `/me` |
| Reporting, extraction | `/items`, `/items/extract-preview`, `/taxonomy`, `/zones` |
| Matching, deck | `/items/{id}/matches`, `/matches`, `/matches/{id}/feedback` |
| Claims | `/claims`, `/claims/{id}/answers`, `/claims/{id}/decision` |
| Handover | `/claims/{id}/handover`, `/handover/confirm` |
| Notifications | `/notifications`, `/notifications/stream` |
| History | `/items/{id}/events` |
| Insights, ops, eval | `/admin/insights/*`, `/admin/ops/scene`, `/admin/eval/*` |

## 12. Risks and mitigations

| Risk | Effect | Mitigation |
|---|---|---|
| COCO detector misses campus classes (ID card, keys, earbuds, wallet, charger, specs) | Poor category on photos | CLIP zero-shot on the full image as fallback; fine-tune YOLO11n on Colab later |
| Few real pairs | Weak or noisy evaluation | Start capturing on day 1; report synthetic and real numbers separately and label synthetic as optimistic |
| Cold start: few items in the pool | Deck looks empty in the demo | Seed data; text-to-photo matching; "we check again" messaging |
| Claim fraud | Wrong person collects an item | Private attributes, human review for high-value items, rate limits, code plus college ID at handover |
| 8 GB memory pressure | Slow or crashing backend | Small models, one inference thread, lazy loading, in-process jobs, no Redis |
| OCR misreads an ID number | Wrong owner notified | Notify only on exact match to a registered roll number; handover still checks the physical ID |
| Cesium token or WebGL missing on the demo machine | Blank 3D screen | 2D SVG fallback with the same layers |
| The Replit-built front end cannot reach a local backend | Integration friction | Export the project to `frontend/` and run locally; the API client is the only seam (see plan §10) |
| Time | Scope overrun | Tiers in §10; build order in the plan; days 11 and 12 are buffer |

## 13. Assumptions

These are defaults we chose, not open questions. Each is a config value.

- Roll-number format is campus-specific. The default pattern matches the sample style `CS21B042` and lives in config.
- Retention 90 days after closure. OTP domain allow-list comes from `.env`.
- Email is printed to the console in development. SMTP is optional.
- Points for finders: 10 per confirmed return.

## 14. Open items

| Item | Needed for | Until then |
|---|---|---|
| `<<CAMPUS_NAME>>` | Zones, map center, copy | Placeholder zone config in `config/campus/` |
| `<<CESIUM_ION_TOKEN>>` (free, pasted into `.env`) | 3D buildings | 2D fallback |
