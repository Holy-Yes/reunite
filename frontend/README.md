# Front end

The student and admin UI is generated in Replit from [`docs/WEBSITE_PROMPT.md`](../docs/WEBSITE_PROMPT.md) on the template you pick, with a mocked API client whose function names and shapes match the backend's endpoint table exactly. The landing page and its 3D globe are already built as a reference in [`prototype/globe-hero`](../prototype/globe-hero).

**Path A (default): Replit-generated**

1. Generate in Replit (milestones M1 to M4 in the prompt).
2. Export the project into this folder (zip download, or Git sync).
3. Run it here: `npm install`, then the template's dev command on port 5190 (`npm run dev -- --port 5190`).
4. Set the API mode variable (with the template's public prefix, for example `VITE_API_MODE`) from `mock` to `http://localhost:8010`.
5. Make sure the front end's origin is in the backend's `CORS_ORIGINS` (default: `http://localhost:5190`).

Do **not** point the Replit-hosted preview at `localhost:8010`: Replit runs remotely and cannot reach this machine. Run the exported front end locally, or expose the backend through a tunnel and add that origin to `CORS_ORIGINS`.

**Path B (fallback):** build it in this repo from the same prompt.

**Integration checklist**

- [ ] Every function in the client maps to a row of the endpoint table (`backend/tests/test_contract.py` keeps the docs and the API identical).
- [ ] Notifications: read `GET /notifications/stream` with `fetch` and an `Authorization` header. `EventSource` cannot set headers, and tokens never go in URLs.
- [ ] Originals (`/media/original/{id}`) need the bearer token: fetch them as blobs. Public photos (`/media/public/{id}.jpg`) work in plain `<img>` tags.
- [ ] Media URLs come from the API; the client never builds paths.
- [ ] `GET /taxonomy` drives the chip vocabulary and the color hex values. `GET /zones` replaces the mock GeoJSON.
- [ ] Errors are `{ error: { code, message, fields? } }`; rate limits send `Retry-After`.
- [ ] Register the service worker in production builds only.
- [ ] Claim answers: send choice answers as the choice text, zones as a zone id, dates as ISO 8601.

**Path B status (2026-09-26):** built here, not exported from Replit. It runs on port 5191 (it was moved off 5190 while the globe prototype held that port; the prototype now uses 5192) and proxies `/api` to :8010 through `vite.config.ts`. See the "Path B front end" section of the root [README](../README.md) for what it covers and what is missing. If you export a Replit project into this folder instead, keep a copy of `src/` first.
