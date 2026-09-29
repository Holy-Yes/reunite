# Reunite: campus lost and found

A lost report and a found report, each a photo, some words, or both, become attributes and embeddings. A matcher ranks the opposite pool with a calibrated confidence and a plain-language "why". Claims are verified against details only the finder saw, and the return is confirmed with a QR or a six-digit code. Everything runs locally: small models, no Redis, no Docker, no external inference APIs. Items only, never people.

| | |
|---|---|
| `docs/` | [PRD](docs/PRD.md), [implementation plan](docs/IMPLEMENTATION_PLAN.md), [front-end prompt](docs/WEBSITE_PROMPT.md) |
| `backend/` | FastAPI, SQLAlchemy 2, Alembic. The ML pipeline, matcher, claims, handover, notifications, insights |
| `eval/` | the harness, synthetic pairs, and the guide for photographing real ones ([eval/README.md](eval/README.md)) |
| `training/` | four notebooks for the GPU work, and `export.py` ([training/README.md](training/README.md)) |
| `scripts/` | zones, seed data, weights, VAPID keys, pgvector |
| `prototype/globe-hero/` | the landing page with the 3D Earth (see the front-end note below) |

## Run it

One time (needs the network; about 1.7 GB of packages and 0.7 GB of models):

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
python -m spacy download en_core_web_sm
cp .env.example .env                      # set JWT_SECRET; leave the rest for now
python scripts/download_weights.py        # yolo11n, CLIP ViT-B/32, MiniLM, RapidOCR
```

Postgres 16 (Homebrew). On macOS, start it with a locale set, or it refuses with "postmaster became multithreaded during startup":

```bash
export LC_ALL=en_US.UTF-8
pg_ctl -D /opt/homebrew/var/postgresql@16 -l /tmp/pg.log start      # or: LC_ALL=en_US.UTF-8 brew services start postgresql@16
createdb reunite
cd backend && alembic upgrade head && cd ..
python scripts/build_campus_zones.py --placeholder                  # 8 generic zones until the campus is known
python scripts/fetch_seed_photos.py                                  # ~90 public photos for seed data and synthetic eval
python scripts/seed_demo.py --reset                                  # add --light for a fast run with stand-in models
cd backend && uvicorn app.main:app --port 8010 --reload
```

Sign in with any seeded address (`asha@vnrvjiet.ac.in` student, `desk@vnrvjiet.ac.in`, `guard@vnrvjiet.ac.in` security guard, `admin@vnrvjiet.ac.in`). The one-time code is printed in the backend console. Interactive API docs are at http://localhost:8010/docs.

Optional: `python scripts/enable_pgvector.py --build` (compiles pgvector; the numpy index is used automatically without it), `python scripts/gen_vapid.py` (Web Push keys).

## Tests and evaluation

```bash
cd backend && pytest                                                              # about 150 tests, SQLite, light models, under a minute
TEST_DATABASE_URL=postgresql+psycopg://localhost/reunite_test pytest              # the same suite on Postgres (and pgvector)
python -m eval.synthetic_pairs && python -m eval.run_eval --pairs synthetic       # pipeline check with the real models
```

The unit tests use `ML_MODE=light` (tiny deterministic stand-ins) so they need no downloads. The evaluation and the app use the real models.

## How it works

```
report (photo?, text?, zone, time window)
 |- vision: YOLO11n -> crop -> category and material (CLIP), color (GrabCut + k-means in CIELAB), OCR (brand, roll number)
 |          CLIP ViT-B/32 image embedding
 |- text:   spaCy EntityRuler + gazetteers -> category, brand, colors, marks, serial; MiniLM and CLIP text embeddings
 '- fuse:   agreeing sources raise confidence; the user's edits always win (and are logged as labels)
match (every new or edited report, against the opposite pool):
 1. candidates: category group and time gate, then the top 50 by embedding similarity
 2. features: category, color, brand, image, text, text-to-photo, marks, zone (walking hops), time. Masked when not comparable
 3. score = weighted mean over what was compared, discounted by how much was compared; logistic calibration when fitted
 4. store the "why" breakdown; notify the owner at 0.60 and above
```

Pipeline stages run as rows in a `jobs` table (ingest, extract, match, notify) on one asyncio worker with retries. Model calls share a single thread to keep memory flat on an 8 GB machine.

Privacy rules that are enforced by construction, and tested:
* `PublicItem` is built from a whitelist (category, colors, brand, zone, date, blurred photo). Private marks and serials cannot appear in it.
* Uploads are re-encoded, so EXIF (location, device, time) is dropped. Public photos are blurred; ID cards get a solid plate, and their roll number is used only to notify the owner.
* The ops scene is zone level and carries no user ids. Finders appear as "Finder A", never by email.
* Claim questions are generated from private details; the expected answers never leave the server.

## Pretrained now, trained later

Every model has a fallback, so the whole app works before any training. Files dropped into `backend/weights/` are picked up at startup, and the log says which path each stage took (`GET /health` shows it too).

| Stage | Works today | After the GPU work |
|---|---|---|
| detector | COCO YOLO11n, plus CLIP zero-shot for classes COCO lacks | `detector.pt` |
| category, material | CLIP zero-shot prompts | `heads.pt` |
| scorer | hand-set weights | `calibration.json` (fit on real pairs) |
| image embedding | raw CLIP | `projection.pt` (stretch) |

## What is not done, on purpose

* **Real-pair numbers.** `eval/reports/*-synthetic.*` are optimistic and say so. Photograph 150 to 300 pairs ([eval/README.md](eval/README.md)) and run `python -m eval.run_eval --pairs real` for numbers you can quote.
* **Training.** Notebooks `01` to `03` (and `04`, stretch) are written and syntax-checked but not run; they need a GPU on Colab or Kaggle. `training/export.py` validates and installs the results.
* **The campus.** Zones are eight generic placeholders (`TEMP_DEFAULT`, centred on 17.3850, 78.4867). Run `python scripts/build_campus_zones.py --bbox <south,west,north,east>` once the campus is known.
* **Cesium ion token** for the 3D ops view lives in the front end's environment (`<<CESIUM_ION_TOKEN>>`); the backend does not need it.
* **The student and admin front end** is generated in Replit from `docs/WEBSITE_PROMPT.md` and exported into `frontend/` (see [frontend/README.md](frontend/README.md)). This repo has the API it will call, and a contract test that keeps the endpoint tables in the docs identical to the real routes.

## Known limits

* OCR is the slowest stage (2 to 5 seconds per photo on CPU here). Photos are processed in the background, so reports return immediately in `processing`.
* Zero-shot CLIP tells a laptop from a phone well and one black laptop from another poorly. That is what the trained heads and the optional adapter are for; the "look-alikes" in the real-pair guide are how you measure it.
* `ultralytics` (YOLO) is AGPL-3.0; see `THIRD_PARTY_NOTICES.md` before distributing.

## Path B front end and the extras built on top (2026-09-26)

`frontend/` now holds a working React + Vite + TypeScript app built in this repo (Path B), talking to the live API. It runs on port **5191** (`prototype/globe-hero` uses 5192). Vite proxies `/api` and `/media` to :8010, so no CORS setup is needed.

```bash
cd frontend && npm install && npm run dev      # http://127.0.0.1:5191
```

`.claude/launch.json` has `reunite-backend` and `reunite-frontend`. Sign-in codes appear in the backend log while `EMAIL_BACKEND=console`.

What the app does: 3-step report (photo or words, editable chips with private toggles, place and time), match deck with the plain-language why, claim questions, approve or reject for the finder, handover pass (QR + code), desk screen (confirm handover, review queue, batch logging), alerts, profile with roll number and language (English, Hindi, Telugu).

Added on the backend, each with tests in `backend/tests/test_extras.py` and `test_tags.py`:

| Feature | Endpoints |
|---|---|
| Relay chat after approval; phone numbers and emails are masked | `GET/POST /claims/{id}/messages` |
| Trust score (returns, approved claims, rejections) | `GET /users/me/trust`; `counterpart` on a claim |
| Unclaimed found items go to a desk after `UNCLAIMED_ROUTE_DAYS` | runs at startup; `POST /admin/maintenance/route-unclaimed` |
| Desk batch logging | `POST /items/bulk` (desk or admin) |
| Thank-you pledge, recorded only | `POST /claims/{id}/tip` |
| QR tags; the finder needs no account | `/tags`, `/public/tags/{code}` |

Migrations `0002` and `0003` add the tables and columns. Run `make migrate` (or `alembic upgrade head`).

Known gaps in the front end: notifications are polled every 20 s rather than read from `/notifications/stream`; no service worker or Web Push registration; no Cesium ops view or eval page yet; the new endpoints are not yet in the docs' endpoint tables (check `test_contract.py` before extending them).

Still roadmap: SMS or offline fallback (needs a gateway account), real venue integrations, NFC tags, real payments, and matching on Hindi or Telugu descriptions.

## Deploy

Docker Compose is the recommended path for a production VPS deploy. Local development without Docker (above, "Run it") is unaffected and still supported -- this is additive, not a replacement.

```bash
cp .env.production.example .env.production   # fill in real values, see that file's comments
docker compose build
docker compose up -d
```

Migrations and the demo seed run automatically every time the `backend` container starts (`backend/docker-entrypoint.sh`): it waits for Postgres, runs `alembic upgrade head`, then seeds the demo accounts with `--light` if the database is empty (a safe no-op once it isn't). To run either step by hand instead:

```bash
docker compose run --rm --entrypoint "" backend sh -c "cd backend && python -m alembic -c alembic.ini upgrade head"
docker compose run --rm --entrypoint "" backend python scripts/seed_demo.py --reset   # higher-fidelity demo matches (slower, real models)
```

The ~0.7GB of ML weights (yolo11n, CLIP, MiniLM) are baked into the `backend` image at build time via `scripts/download_weights.py`, so the container needs network access only during `docker compose build`, not at runtime.

**Before going live:** generate a fresh `JWT_SECRET` and Postgres password for `.env.production` -- never reuse the dev `.env`'s values (rotating a JWT secret invalidates existing sessions, which is expected for a prod cutover but shouldn't be done to the shared dev `.env`). Set `CORS_ORIGINS` to the real frontend origin, and leave `DEMO_OTP` blank.

**Verify after first deploy:**
- `curl http://<host>/health` returns `{"ok": true, ...}`.
- Sign in as a demo account (`asha@vnrvjiet.ac.in` student, `desk@vnrvjiet.ac.in`, `guard@vnrvjiet.ac.in` security guard, `admin@vnrvjiet.ac.in`); the sign-in code appears in `docker compose logs backend` while `EMAIL_BACKEND=console`.
- Send a real chat message each way on an approved claim, and check a public QR-tag thread (`/t/{code}`) -- confirms the 5s-poll fetches still work through nginx's `/api` proxy.
- As `guard@vnrvjiet.ac.in`, confirm a handover by scanning the QR from a claimant's pass screen (or the 6-digit code fallback), and confirm the nav shows "Guard", not "Desk".
