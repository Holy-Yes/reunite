# Reunite: website prompt for Replit Agent

A copy-paste prompt that builds the Reunite front end on top of **whichever Replit template you choose**. It inspects the template first and conforms to it (framework, language, router, styling, package manager, port) instead of scaffolding its own stack. The endpoint list in §6 is the same one used in `IMPLEMENTATION_PLAN.md`, so the mocked client swaps for the FastAPI backend later without UI changes.

## Before you paste (not part of the prompt)

1. **Create the Repl from the template you want.** Best fit is React + Vite + TypeScript. It also works on Next.js, Vue/Nuxt, SvelteKit, Angular, plain HTML/CSS/JS, and Python or Node web templates (Flask, FastAPI, Django, Express). §1 of the prompt tells Agent how to map onto each.
2. **Add a Secret for the map (optional).** Name it with your template's public prefix: `VITE_CESIUM_ION_TOKEN` on Vite, `NEXT_PUBLIC_CESIUM_ION_TOKEN` on Next.js. The value is your free Cesium ion token (`<<CESIUM_ION_TOKEN>>`). Without it the admin ops page falls back to a flat 2D campus map, so nothing breaks. The landing-page globe (§5.0) does not use the token at all.
3. **Fill in what you know.** Replace `<<CAMPUS_NAME>>` in the prompt before pasting, or change it in `campus.config` after it's built. Only two placeholders exist (`<<CAMPUS_NAME>>` and `<<CESIUM_ION_TOKEN>>`); see §10 of the prompt.
4. **Paste everything between `BEGIN PROMPT` and `END PROMPT`.** If Replit's input box truncates it, save the block as `SPEC.md` in the Repl root and paste the short kickoff at the bottom of this file instead.
5. **Test the camera in a new browser tab.** Replit's embedded preview pane blocks live camera access. The photo-upload fallback works everywhere.
6. **Later:** set the API mode variable to your backend URL (see §6) and the mocks turn off.

---

## BEGIN PROMPT

**Build the front end for "Reunite", a campus lost-and-found web app for <<CAMPUS_NAME>>. Build it on the template already selected in this Repl. Read §1 before writing any code. Where this spec conflicts with the template's runtime constraints, the template wins. On everything else, this spec wins.**

### 0. What you're building

Students report lost items (text, photo, or both). Finders report what they found. The system reads attributes out of photos and text (category, brand, color, marks), ranks candidate matches from the opposite pool with a calibrated confidence and a plain-language "why", then walks the owner through claim verification and a QR handover. Security-desk staff get a claims queue, an insights dashboard, an evaluation report, and a 3D campus view of where items are lost and found.

This task is **the front end only**. Every ML result and every API response is mocked behind a typed client. A FastAPI backend replaces the mocks later, and the UI must not change when it does. Do not build a backend, database, real ML, real push server, or chat between users.

### 1. Template contract (do this first)

**Step 1. Inspect the project that exists.** Read `package.json` / `requirements.txt`, `.replit`, and the framework config files. Write a five-line **template profile** in chat and then continue without waiting for approval:

- framework and version
- language (TypeScript, JavaScript, Python)
- router and how routes are declared
- styling system (Tailwind, CSS modules, a component kit, or none)
- package manager, dev command, port, and the public env-var prefix

**Step 2. Rules that hold for every template.**

- **R1 Keep the scaffold.** Keep the template's entry files, run command, port mapping, package manager, and lint/format config. Add to them. Do not regenerate the project or switch frameworks.
- **R2 Follow its file conventions** for where routes, components, styles, and static files go.
- **R3 Language.** TypeScript: use strict types from §6. JavaScript: same shapes as JSDoc `@typedef`. Server-rendered Python: same shapes as JSDoc in `static/js/types.js`.
- **R4 Styling.** Implement the design tokens in §3 as CSS custom properties in one global stylesheet, whatever the template. If Tailwind is present, map the tokens into the theme (`colors`, `borderRadius`, `fontFamily`) and do not use its default palette classes (`indigo-*`, `slate-*`, `gray-*`). If a component kit is present (shadcn, MUI, Chakra, Mantine, Vuetify), theme it to the tokens: override radius, colors, and typography so no kit default is visible. If there's nothing, write plain CSS.
- **R5 No extra infrastructure.** No backend, database, ORM, auth service, or global-state library beyond what the template already has. Allowed additions: an icon set, a QR library, and (for the ops view) Cesium.
- **R6 Everything in §5 must exist on every template.** Only the mechanism changes. Use this table:

| Template family | Routing | Ops 3D view |
|---|---|---|
| React (Vite, CRA-style) | the template's router, else `react-router` | `cesium` + `resium`; on Vite add `vite-plugin-cesium` |
| Next.js | file-based routes; client components for camera, deck, ops | `cesium` loaded with `dynamic(..., { ssr: false })`; copy assets to `public/cesium` and set `CESIUM_BASE_URL`; env prefix `NEXT_PUBLIC_` |
| Vue / Nuxt | `vue-router` or file-based | CesiumJS directly inside a component's mounted hook |
| Svelte / SvelteKit | file-based | CesiumJS directly in `onMount` |
| Angular | Angular router with lazy-loaded routes | CesiumJS directly; register its assets in `angular.json` |
| Plain HTML / CSS / JS | hash router (`#/report/lost`) in one ES module | Cesium from a CDN, exact version pinned, plus its CSS |
| Python or Node web (Flask, FastAPI, Django, Express) | server-rendered shell in `templates/` + hash routing in `static/js` (vanilla ES modules) | Cesium from a CDN, exact version pinned. **Serve the mock API at `/api/v1/*` from JSON fixtures using the framework's own routing**, so the contract in §6 is real over HTTP |

- **R7 Replit specifics.**
  - The dev server must bind `0.0.0.0` on the template's existing port. If Vite answers "Blocked request. This host is not allowed", set `server.allowedHosts: true`.
  - Secrets arrive as environment variables. Anything the browser reads needs the template's public prefix. The Cesium token is `<PREFIX>CESIUM_ION_TOKEN`. Never hardcode a token. If it's missing, render the 2D fallback and show one line of notice. On a static template with no server, ask for the token once on the ops page and keep it in `localStorage`.
  - Register any service worker **only in production builds**, so the dev preview never serves stale files.
  - The embedded preview blocks live camera access. Always ship the file input (`<input type="file" accept="image/*" capture="environment">`), and if `getUserMedia` is denied show: "Live camera doesn't work in this preview. Open the page in its own tab, or choose a photo."
  - No external image URLs. All imagery (mock photos, logo, favicon) is inline SVG or a file in the repo. Fonts come from Google Fonts. Cesium (ops view) and three.js (landing globe) come from their own packages or a pinned CDN, and the globe's texture is a file in the repo. Nothing else loads from a third party.
  - Load Cesium code only on the ops route (code-split or lazy import). The student screens must stay light on a phone.
- **R8 Verify as you go.** After each milestone (§9) run the app, open the preview, confirm the page actually renders (the app root is not empty), read the browser console, and fix every error before continuing. A blank page is a failed build however clean the code looks.

### 2. Brief

- **Users.** Student who lost something (stressed, on a phone, between lectures). Finder who wants to hand it in fast. Security-desk staff and admins who verify claims and want the campus-wide picture.
- **Core job.** Get a lost thing back to its owner with the fewest steps and the least fraud.
- **Tone.** Calm, quick, trustworthy. Plain sentences, second person, no exclamation marks. Say the specific thing.
- **Constraints.** Mobile-first (360 px base), one-handed use, works on flaky campus Wi-Fi, privacy-first (items only, never people).
- **Vocabulary.** "Lost", "found" (as a report) and "turned in" (as a public listing), "match", "claim", "handover", "ticket". Never "user", "listing", "asset", "solution".
- **Roles.** `student` (default; can report both lost and found), `desk` (handover scan, claims), `admin` (everything a desk can do, plus insights, ops, eval). No real auth. A dev drawer (§5.14) switches roles.

**Voice samples to copy in spirit.**

- Empty home: "Nothing lost, nothing found. If that changes, report it here."
- Empty extraction: "Describe it or take a photo. We list what we can pick out, and you fix what's wrong."
- End of deck: "That's all of them for now. We check again each time something is turned in."
- Network error: "Couldn't reach the server. Your draft is saved on this phone."
- 404: "That item isn't here. It may have been returned or closed."

**Banned in copy:** Elevate, Unlock, Supercharge, Seamless, Empower, Streamline, Leverage, "all-in-one", "not just X, it's Y", tapestry, journey, "Welcome back!", exclamation marks. No fake "updated 2 minutes ago" timestamps. Use real mock timestamps.

### 3. Design system

**Concept: the claim ticket.** Reunite is a claim check for a lost thing. Every item carries a numbered ticket (`RU-L-0142` for lost, `RU-F-0089` for found). The look is light, editorial and exact, in three colors only: white, black and one orange. **Orange is lost, black is found.** Everything else is ink on white. Every use of the pair also carries an icon or a word, so nothing depends on color alone. The reference is the landing page in §5.0: a serif headline with one italic orange line, hairline rules instead of boxes, and a live globe.

**Tokens.** Put these in the global stylesheet. Name tokens semantically. Do not add colors outside this list, except the named item-color palette used only for mock photos.

```css
:root {
  /* ground and ink */
  --ground: #FFFFFF;      /* app background */
  --surface: #FFFFFF;     /* sheets, cards, inputs */
  --surface-2: #F5F3F0;   /* bands, wells, skeletons, disabled */
  --line: #E2DED9;        /* hairline dividers; never on the same element as a shadow */
  --ink: #0B0B0B;
  --ink-2: #3A3A3A;
  --ink-3: #5C5C5C;       /* smallest allowed text color on --ground (4.5:1) */

  /* the one hue. Orange means lost; black (--ink) means found. */
  --orange: #FF6A13;        /* fills, pins, arcs, the primary action */
  --orange-ink: #B84400;    /* orange as text on white (4.5:1) */
  --orange-wash: #FFEBDD;   /* chip and callout backgrounds */

  --danger: #A4123F;      /* errors only, always with an icon and text */

  /* shape: three radii, on purpose */
  --r-1: 3px;   /* inputs, chips, buttons */
  --r-2: 8px;   /* cards, panels */
  --r-3: 16px;  /* sheets, modals, the swipe card */

  /* elevation: flat by default, lift only what moves or floats */
  --e1: 0 1px 2px rgb(11 11 11 / .10);
  --e2: 0 14px 30px -10px rgb(11 11 11 / .28);   /* swipe card while dragging, popovers */
  --e3: 0 24px 60px -16px rgb(11 11 11 / .40);   /* bottom sheets, modals */

  /* motion */
  --ease-out: cubic-bezier(0.2, 0, 0, 1);
  --ease-in: cubic-bezier(0.4, 0, 1, 1);
  --t-fast: 120ms; --t-base: 220ms; --t-slow: 360ms;
}
/* One light theme everywhere, admin and ops included. There is no dark surface. */
```

**Color rules.**

- Primary buttons are **ink fill, white text**. The role buttons are the exception: "I lost something" and the landing page's "Start a report" are `--orange` fill with **ink** text (white on orange fails contrast), and "I found something" is ink fill with white text. Secondary actions are an ink outline, or a text link with an underline on hover. Hover on an orange button turns it ink with white text.
- Orange means lost and black means found, everywhere: chips, pins, ticket stubs, map arcs' endpoints, list markers. A found marker is a black fill or outline plus the word or icon. Orange is also the single accent for the italic line in a headline and for small eyebrows (use `--orange-ink` for text). Nothing else is colored.
- Confidence is **not** red/amber/green. It is the ten-tick meter below, in ink.
- No gradients in UI chrome and no blue anywhere in the UI. The only fade is the globe's mask in §5.0, which is a mask, not a painted gradient. No purple, indigo, or violet (item colors in photos are data, not UI).

**Type.** Load once, with `display=swap` and a `preconnect`:

`https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap`

- **Display: Instrument Serif 400 and italic.** Page titles, section headings, big numerals. Only at 25 px or larger, sentence case, tight tracking (about -0.02em). A headline may end in one italic line set in `--orange-ink`; use that once per section at most.
- **Body/UI: IBM Plex Sans 400/500/600.** Everything else, including card titles and buttons.
- **Data: IBM Plex Mono 400/500.** Only for ticket numbers, roll numbers, handover codes, coordinates, and numeric tables (`font-variant-numeric: tabular-nums`). Not for labels, headers, or decoration.
- Scale (ratio 1.25): 13 (captions only) / 16 / 20 / 25 / 31 / 39 / 49, plus 61 / 76 / 96 for stat numerals. Body is 16 px with 1.5 line height. Set letter-spacing per role, not blanket.

**Icons.** Phosphor, **bold** weight for UI, **fill** for the active tab, **duotone** for mock photo glyphs. Use the package for your template (`@phosphor-icons/react`, `@phosphor-icons/vue`, `@phosphor-icons/web`, and so on). Icons sit next to labels; do not put one centered above every heading.

**Shape and spacing.** Spacing scale 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64. The primary panel on a screen gets more room than the secondary ones. Small controls use `--r-1`. Cards `--r-2`. Sheets and the swipe card `--r-3`. No card inside a card. Surfaces are separated by **either** a `--line` divider **or** a shadow, never both. Most surfaces are flat `--surface` on `--ground` with neither.

**The ticket motif (use it in exactly two places).** The item ticket on Home/My items, and the handover pass. Build it as `--surface` with a stub on one side, two 8 px semicircle notches cut at the stub boundary (a `radial-gradient` mask), and a 1 px dashed perforation. The stub holds the mono ticket number and a lost/found marker. Do not turn every card into a ticket.

**Confidence meter.** Ten ticks in a row. Filled ticks are `--ink`, empty are `--surface-2`. Beside it: the percentage in mono, and a band word. Bands: **Strong** at 0.75 and above, **Possible** from 0.40 to 0.75, **Long shot** below 0.40. Matches below 0.20 are hidden. Keep the thresholds in one constants file.

**Motion.** Transition specific properties only (`transform`, `opacity`, `background-color`, `box-shadow`). Never `transition: all`. Motion is allowed to (1) show a state change (a chip landing in the extraction panel, a card leaving the deck), (2) direct attention (the new-match badge), (3) nothing else. No entrance fade-ins on page load, no floating or breathing effects. Every interactive element has distinct hover, focus-visible, active, and disabled states. Under `prefers-reduced-motion: reduce`, the swipe fly-out becomes a 120 ms crossfade and the ops clock does not autoplay.

**Layout.** Mobile-first at 360 px. Student app: bottom tab bar on mobile (Home, Report, Matches, Alerts), slim top bar on desktop. No dark sidebar in the student app. At 900 px and up, layouts are **asymmetric and weighted**: for example the item list takes 5 of 12 columns and the detail takes 7. The admin shell is the same white ground with hairline rules, so the student app, the dashboards and the 3D view feel like one tool.

**Design do-nots (check these before finishing).** No purple/indigo, no gradient buttons or hero, no glow orbs. No Inter, Geist, Poppins, or system-font stack anywhere. No emoji as icons and no rotated-square bullets. No `transition: all`. No uniform rounded card on every element. No colored left-border strip on cards. No frosted-glass headers. No four-equal-KPI band, no donut chart, no copy of a well-known heatmap. No blue, no dark theme, no dark sidebar. Do not leave a Tailwind or component-kit default look showing.

### 4. App map

| Route | Screen | Roles |
|---|---|---|
| `/welcome` | Landing page (§5.0). Also `/` when signed out | all |
| `/signin` | Email + OTP | all |
| `/` | Home: my items | student |
| `/report/lost`, `/report/found` | Report flow | student |
| `/items/:id` | Item detail + timeline | owner, desk, admin |
| `/matches` | Match deck across my lost items (`?item=:id` filters to one) | student |
| `/turned-in` | Public list of found items (coarse, blurred) | student |
| `/claims/:id` | Claim questions and status | claimant, finder, desk |
| `/claims/:id/handover` | Handover pass (QR and code) | claimant |
| `/handover/confirm` | Scan or type a code to complete a handover | finder, desk, admin |
| `/notifications` | Alerts | all |
| `/admin` | Insights | admin |
| `/admin/claims` | Claims review queue | desk, admin |
| `/admin/ops` | Campus ops 3D view | admin |
| `/admin/eval` | Evaluation report | admin |

### 5. Screens and states

Every screen needs: a **loading** state (skeletons shaped like the real content, not spinners), an **empty** state (one message, one action), an **error** state (inline, with retry), and the happy path. Design for real content: a 30-word description, a long zone name, an item with zero matches, an item still processing.

**5.0 Landing page** (`/welcome`, and `/` when signed out). One long page, light theme, six sections in this order. Copy is fixed; use it as written.

1. **Nav.** Orbit mark and "reunite" on the left. Links: Locations, How it works, For the desk. Right: "Report an item" as an ink-outlined button with an up-right arrow. One hairline under the bar.
2. **Hero.** A large live globe spans the whole hero, solid on the left and dissolving into white behind the copy on the right.
   - Eyebrow "A shorter way home" with an asterisk mark. Headline "What's missing can find its *way back.*" (Instrument Serif, about 96 px on desktop, italic last line in `--orange-ink`). Subcopy: "A calmer path from the moment you lose something to the moment it is safely handed back." Actions: "Start a report" (orange fill, ink text, up-right arrow) and "See how it works" (text link, down arrow).
   - Over the globe: top left "Now viewing", the sector name in serif, and "Campus sector · Live". A vertical coordinates label (mono) near the fade. Bottom left an orange dot and "Live campus pulse", a "Whole Earth" text button (visible only when zoomed to a sector), and a "01 / 03" counter. Far right edge: the vertical caption "Campus lost + found / Est. 2026".
   - On a phone (below 900 px) the globe sits above the copy, about 62% of the screen height, and fades downward instead of rightward.
3. **Location strip.** A serif line "places change. *help moves with them.*" and three numbered buttons: 01 North Hall (blue headphones, 12 open), 02 The Commons (silver water bottle, 08 open), 03 Science Quad (green canvas tote, 15 open). The selected one has an ink outline. Selecting one drives the globe (see below) and the hero labels. On a phone this row scrolls sideways with snap.
4. **The handoff, made clear.** Eyebrow, then "Three small steps. *One less thing to carry.*" and three columns: 01 Tell us what happened. / 02 See why it matches. / 03 Hand it back safely., each with one sentence and a hairline rule on top that ends in a 44 px orange segment. Heading sits right of the eyebrow, not centered.
5. **Desk band.** `--surface-2` ground. "For the people at the desk", "More context *when it matters.*", one sentence, and an "Explore the desk view" outlined button.
6. **Footer.** Logo, "Items only · Privacy first · Made for campus", and "Globe: three.js, Natural Earth · © 2026".

**Globe behavior (build this in one module, `globe.ts`, loaded with a dynamic import after first paint).** It is a real 3D Earth in three.js (`three` from npm, plus `OrbitControls` and the `Line2` fat-line classes from `three/examples/jsm`). No token, no API, and nothing is fetched from a third-party host.

- **Layout.** The globe spans the whole hero and is bigger than it. The container is absolutely positioned, starts about 10vw off the left edge, is about 110vw wide and the full hero height, and the disc's diameter is about 1.32 times the hero height, so it bleeds past the top and bottom. Its mask keeps the left side solid and melts the right side into white so the copy stays readable: `mask-image: linear-gradient(to right, #000 0%, #000 38%, rgb(0 0 0 / .1) 76%, transparent 100%)`. Camera distance is computed from the container size and recomputed on resize (on a phone, fit the width at 1.0 instead). The canvas has `touch-action: pan-y` so a vertical swipe still scrolls the page.
- **Earth.** A sphere with a custom `ShaderMaterial` and one texture, `public/textures/earth-2k.jpg` (2048 x 1024, equirectangular). The texture is the Natural Earth II shaded-relief map (public domain), stitched from the level-2 tiles that ship in the `cesium` npm package with a short Pillow script (`8 x 4` tiles of 256 px, the tile rows flipped because TMS rows count from the south). The shader turns it monochrome:
  - **Sea vs land** from blue dominance (`b - r`). Land is pale relief grey, sea is mid grey.
  - **Light** is a fixed direction in view space, so it stays put on screen while the camera orbits. A wrapped diffuse term gives a soft terminator and no black night side, which keeps the globe light on a white page.
  - **Relief** from a screen-space bump map on the land luminance, at low strength. Fade it out as the camera gets close (it exaggerates the texture's pixels).
  - **Ocean glint** as a Blinn-Phong highlight, masked to the sea.
  - **Limb** with slight darkening and a haze veil at the edge.
- **Clouds.** A second sphere at radius 1.012 with a transparent shader and no texture. Cover comes from domain-warped 3D fbm noise (5 octaves), with a little latitude bias. It rotates a touch faster than the Earth and its noise drifts slowly. The Earth shader samples the same cover, offset away from the sun, to cast soft cloud shadows.
- **Atmosphere.** A back-faced sphere at radius 1.1 with a faint warm-orange halo that falls off to nothing at its outer edge.
- **Markers and routes.** Pings are children of the Earth, so they turn with it: a white disc, a colored core (orange lost, ink found), and a pulsing ring (a scaled `RingGeometry`, opacity animated). Routes are `Line2` dashed lines on great-circle arcs raised by 16% of their length in the middle, with `dashOffset` animated. Scale markers by camera distance so they stay readable from far away and close up. Hover and click use a `Raycaster` against invisible hit spheres plus the Earth (so a ping behind the planet cannot be picked).
- **Motion.** Slow auto-rotation of the Earth group (about 0.04 rad/s, roughly three minutes a turn, eastward) in the overview only. Start facing the sector region.
- **Interaction.** `OrbitControls`: drag rotates with damping, wheel and pinch zoom between 1.25 and 8 Earth radii, pan off. Hovering a sector ping shows a small ink tooltip ("The Commons / silver water bottle · 08 open") and a pointer cursor; clicking it selects that sector. Auto-rotation pauses on any pointer or wheel event and resumes after 3 seconds of quiet.
- **Sector selection.** Selecting a location button (or its ping) sets the hero labels, the counter and the coordinates, stops the auto-rotation, then flies the camera to look straight down at that sector from 1.5 Earth radii over 2.4 s (spherical interpolation of the camera direction, cubic in-out ease). "Whole Earth" or Escape flies back out to the fitted distance. The selected ping is larger with an ink outline.
- **Placeholder geography.** Sector coordinates, the decorative world pings and the routes live in one config file next to `campus.config`. The three sectors are placed about 200 km apart so they stay separate at the texture's resolution (about 20 km per pixel). The world pings and arcs are decoration and must not be presented as data. Street-level views need a real map, which is what the Cesium ops view in §5.12 is for.
- **Loading and failure.** Show a static SVG globe (same size and position) until the texture has loaded and the first frame is drawn, then swap to the live one. If WebGL or the texture fails, keep the SVG, log one console error and show nothing else. Never leave the hero empty. Under `prefers-reduced-motion: reduce` there is no auto-rotation, no cloud drift and no pulsing (rings at a fixed size), and the fly-to is instant.
- **Upgrade path.** For a sharper hero, swap `earth-2k.jpg` for an 8K public-domain Blue Marble or NASA Earth Observatory map, and for real cloud imagery replace the noise with an equirectangular cloud texture (same sphere, same shader). Neither changes the code around it. The reference implementation is in `prototype/globe-hero/` in this repo.


**5.1 Sign in.** Email field, then a six-digit code field. The email must match `ALLOWED_EMAIL_DOMAINS` (mock accepts any, and shows the rule). In mock mode the screen shows the demo code (`123456`) under the field so the flow is testable. Resend with a 30 s cooldown. Wrong code: "That code doesn't match. Check the latest email." Rate-limit state after 5 tries.

**5.2 Home: my items.**
- Two role-colored actions at the top: **I lost something** (orange) and **I found something** (black). Equal weight, not a hero.
- Below, the user's items as **tickets** (§3), newest first: category glyph, one-line description, zone and time, status word (Processing, Open, Matched, Claimed, Returned, Closed), match count if any. Matched lost items show a "3 possible matches" line linking to the deck.
- Desktop: list on the left (5 cols), selected item's detail and timeline on the right (7 cols).
- Empty: the voice sample from §2. Include one processing item and one returned item in the mock data.

**5.3 Report lost / Report found.** One flow with two entry points. Mobile is stepwise (Photo, Describe, Where and when, Check) with a slim progress bar labeled by step name, no numbered circles. Desktop puts the form on the left and the **live extraction panel** sticky on the right.
1. **Photo.** Up to three photos. Live camera (`getUserMedia`) with a shutter button, plus the file-input fallback (R7). Optional for lost, encouraged for found. After capture, draw a detector-style box over the main object (thin ink outline with corner ticks and a label such as `laptop 0.91`). Show a "Reading the photo…" state, then chips.
2. **Describe.** Textarea with the placeholder "Type it how you'd say it: black Dell laptop, small dent on the lid". Debounce 400 ms, then update the chips.
3. **Live extraction panel: "What we picked up".** This is the signature screen. Chips for **category** (one, from the 18 in §6), **brand**, **colors** (up to two, each with a swatch and a name), **marks** (many: dent, scratch, sticker, cracked, engraved), and **serial or roll number** (mono). Each chip shows a source icon (camera, text, scanned text, pencil) and confidence: solid outline at 0.8 and above, dashed below 0.6 with a "check this" hint. Tap a chip to edit or remove it, and use "+ Add detail" for missing ones. An edit sets source to `user` and confidence to 1, and is remembered as a correction. Announce updates to screen readers with `aria-live="polite"`.
   - **Found reports only:** each chip has an eye-off toggle, "Keep private". Private chips are used later to verify the owner and are never shown publicly. Suggest privacy by default for marks, serial numbers, contents, and anything on a screen.
4. **Where and when.** A zone picker (chip grid of the eight zones, plus a small schematic map). Lost: "When did you last have it?" with a from/to range and quick picks (This morning, Yesterday, Pick a time). Found: "When did you find it?" (default now) and "Where is it now?": I'm keeping it / Handed to a security desk (pick which).
5. **Check and submit.** Summary of the ticket. Submit shows a **success ticket** (the ticket motif) with the new ticket number and the line "Comparing against 23 found items…". After ~1.5 s of mock latency it resolves to "3 possible matches" with a **See matches** button, or "Nothing close yet. We'll tell you when something is turned in." The first time a student submits a lost report, show a bottom sheet asking for push permission ("Want a heads-up on this phone when something matches?" Turn on / Not now). Never ask on page load.
- Draft autosave to `localStorage`. Offline submit queues and shows "Saved on this phone. It will send when you're back online."
- An ID-card photo triggers a notice: "This looks like an ID card. We'll try to reach its owner directly and hide the name and number from the public list."

**5.4 Item detail and timeline.** Header with the ticket, category glyph, status. Attributes as read-only chips with an Edit action (re-runs matching, then shows "Checking again…"). Below: the **timeline**, a vertical line with stops for Reported, Matched, Claimed, Verified, Handed over, Closed. Each stop shows time and actor role (student, finder, desk). Completed stops are filled ink, the current stop is ringed, future ones are hollow. Actions: See matches, Close this report (confirmation sheet: "Close this report? You won't get matches for it anymore.").

**5.5 Matches deck (swipe).** The heart of the student experience.
- Top bar: which lost item you're matching (segmented control for up to 3 items, select for more) and "2 of 7".
- **Stacked cards**, top card draggable, the next peeking behind it at scale 0.96. Card content: the found item's photo with a **heavy but recognizable blur** and the caption "Details stay hidden until your claim is verified" (or, with no photo, the category glyph on a color plate); one-line headline ("Black Dell laptop"); confidence meter, percent, and band; where and when ("Turned in at Central Library, Tue 14:20, 2 zones from where you lost it").
- **Why this match**: collapsed on mobile with the top three factors visible as one line, expandable to nine rows (category, color, brand, image, text, text-to-photo, marks, place, time). Each row has a label, a contribution bar, one sentence of detail ("Both black", "Found 6 hours after you lost it"), and a state (match, partial, mismatch, not compared). Missing modalities read "Not compared (no photo)". If one side has no photo, add: "You described it; they photographed it. We compared your words to their photo."
- Actions: **Not mine** (left, ✕ icon), **Not sure** (up, saves for later), **That's mine** (right, check icon, opens the claim flow). Buttons and keys (←, ↑, →) do the same as swiping, and `Z` or an Undo toast (5 s) reverses the last decision. Swipe fly-out at velocity or past 35% of card width. Every decision calls the feedback endpoint.
- Empty: the deck voice sample from §2, plus a link to the public Turned in list.

**5.6 Turned in (public list).** Found items, coarse only: category, colors, brand, zone, date, blurred photo. Filters: zone, category, text search. ID cards appear fully redacted ("ID card. Name and number hidden."). No hidden attributes are ever present in this data (the `PublicItem` type has no such field).

**5.7 Claim.**
- Header: the blurred item and its ticket.
- Three or four **verification questions** generated from the finder's private details, each one of `text`, `choice`, `zone`, `datetime`. Example prompts: "What's on the sticker on the lid?", "What color is the case?", "Where did you last have it?". Line: "Answer only what you remember."
- Submit leads to a status screen: `auto_approved` (go to the handover pass), `pending_review` ("The finder or the desk is reviewing your answers. You'll get an alert."), `needs_more_info` (one extra question), `rejected` (a plain explanation, and the rule "You can try once more after 24 hours"). Only one pending claim per item; a second attempt shows why it's blocked.
- **Category rule to show in the UI:** phones, laptops, and ID cards are always checked by a person ("This kind of item is always checked by a person"). Low-value items may auto-approve.
- **ID-card variant:** no questions. A screen reading "This card carries your roll number, so we've matched it directly. Collect it from <custody desk>." leads to handover.

**5.8 Handover.**
- **Pass** (the second use of the ticket motif): QR code (signed token) and a six-digit code in large mono, expiry countdown (mm:ss, 15 min in the mock), "Collect from: Security desk, Main Gate. Bring your college ID." After expiry: "This code has expired." plus Get a new code.
- **Confirm** screen for finder/desk: scan the QR (use `BarcodeDetector` when available) or type the six digits. Success shows a **Returned** stamp (ink fill, white text), adds a timeline event, and credits the finder ("+10 points"). Wrong code: inline, with attempts left.

**5.9 Notifications.** List grouped Today / Earlier. Types: new match, claim update, handover ready, item returned. Unread is a filled dot plus semibold text. Tap deep-links. "Mark all read". A toast appears for live events (mock: a timer fires one after a minute). Bell badge on the tab bar and top bar.

**5.10 Admin: Insights.** Do **not** make a four-tile KPI row or a donut. Lead with weight:
- One dominant number: **recovery rate** (Instrument Serif at 96 px, with a 7-day trend line beside it).
- Two smaller numbers: **median time to reunite** and **live match precision** (from students' thumbs).
- **Loss hotspots**: zones ranked as horizontal bars, next to a small schematic campus map shaded by count.
- **Hour × weekday** grid, drawn as circles sized by count (not filled squares).
- **Category mix** as a sorted bar list. **Top finders** as a short ranked list with points.
- Range switch: 7 days / 30 days / Term. Charts are hand-drawn inline SVG, no chart library, styled with the tokens. Every chart has a text table alternative reachable by a "Show as table" toggle.

**5.11 Admin: Claims queue.** Table on desktop, stacked list on mobile. Columns: ticket, item, category, score band, age, status. A row opens a **drawer**: the claimant's answers next to the finder's private details with a similarity mark per question, the claimant's own lost-report match score, account signals (verified college email, claims this week, pending claims), and actions **Approve**, **Ask for more**, **Reject** with a note. Phones, laptops, and ID cards are flagged "Person must review".

**5.12 Admin: Campus ops (3D).** Full-bleed view on the same white ground as the rest of the app, with the same globe styling as §5.0. Items only. No people, no cameras.
- **Base.** Cesium with Cesium ion OSM Buildings, camera flown to the campus center (`campus.config`), pitch about −45°, range about 900 m. Zone polygons from a mock `zones.geojson`, filled by a single-hue sequential ramp (`--surface-2` to `--orange`) by open lost count.
- **Layers** (toggle panel, top left): Zones, Pins, Match arcs, Heat (zone fill), Buildings.
- **Pins** sit at zone centroids, never at exact spots. Orange lost, black found, with counts when clustered.
- **Arcs** connect a lost zone to a found zone. Color is a ramp by confidence band (Long shot light grey, Possible orange, Strong ink), backed by width (1 / 2 / 3 px) and dash for Long shot so it does not rely on color alone.
- **Time.** Cesium clock and timeline covering the last 7 days. Entities carry `availability` intervals so the slider filters pins and arcs. Play/pause and 1× / 10× / 60×. Autoplay is off.
- **Modes**: Standard, **NVG** (luminance to green phosphor tint, noise, vignette) and **Thermal** (luminance to a false-color ramp) as optional `PostProcessStage` fragment shaders you write yourself. They are the only place non-palette colors are allowed, they are off by default, and the page chrome stays light while they are on. Do not fetch code from other repos.
- **Zone detail** panel slides in on pick: counts, top categories, recent items.
- **Fallback:** if Cesium fails to initialize or the token is missing, render the same layers over a flat 2D SVG schematic of the zones, with a one-line notice. This screen must never be blank.
- Caption at the bottom: "Shows items and zones only. No people, no cameras."
- Add a `THIRD_PARTY_NOTICES.md` stub listing CesiumJS (Apache-2.0) and a placeholder line reserved for the shader attribution to be added later.

**5.13 Admin: Eval.** A run selector (date) and a badge showing **Synthetic pairs (optimistic)** or **Real pairs**. Lead with **Precision@1** and **Precision@5** as bars against their targets (0.60 and 0.85), with a plain "meets target" or "below target" line. Secondary numbers in mono: Precision@10, Recall@5, MRR, mAP, ECE. Then a **reliability diagram** (10 bins, diagonal reference, dot size by count), a **per-category** table (sortable), and an **ablation** table with bars: image only, text only, + attributes, + text-to-photo, + location and time. Print-friendly.

**5.14 Dev drawer.** Open with `?dev=1` or Ctrl+Shift+D. Controls: switch role, network latency (0 / 300 / 1500 ms), force errors on/off, reset mock data, fire a notification, toggle "sign out". Shows API mode. When in mock mode, a small **"Sample data"** pill sits once in the header (not on every screen).

**5.15 Global states.** Skeletons sized to real content. Inline error with retry. Offline banner. 404 (voice sample §2). Every list handles zero, one, and very many items, and text truncates with an accessible full value.

### 6. Data contract and mock layer

**Types** (TypeScript; use JSDoc `@typedef` in JS templates):

```ts
type Kind = 'lost' | 'found';
type ItemStatus = 'processing' | 'open' | 'matched' | 'claimed' | 'returned' | 'closed';
type Category = 'id_card' | 'laptop' | 'phone' | 'tablet' | 'earbuds' | 'headphones'
  | 'charger' | 'power_bank' | 'wallet' | 'keys' | 'backpack' | 'bottle'
  | 'book' | 'notebook' | 'spectacles' | 'watch' | 'umbrella' | 'calculator';
type Source = 'photo' | 'text' | 'ocr' | 'user';

interface Attr<T = string> { value: T; confidence: number /* 0..1 */; source: Source; hidden?: boolean }
interface Attributes {
  category: Attr<Category>;
  brand?: Attr;
  colors: Attr[];            // 0 to 2 named colors from the taxonomy
  material?: Attr;
  marks: Attr[];             // "dent", "sticker: crescent moon"
  serial?: Attr;             // serial fragment or roll number, shown in mono
}
interface Detection { label: Category; confidence: number; box: [number, number, number, number] /* x,y,w,h in 0..1 */ }

interface Item {
  id: string; ticket_no: string;           // RU-L-0142 / RU-F-0089
  kind: Kind; status: ItemStatus; owner_id: string;
  description: string; attributes: Attributes;
  photos: { id: string; url: string; detections: Detection[] }[];
  zone_id: string; occurred_from: string; occurred_to: string;   // ISO 8601
  custody_zone_id?: string;                // found items: where it is now
  match_count: number; created_at: string; updated_at: string;
}

// what other people are allowed to see. It has no hidden fields, by construction.
interface PublicItem {
  id: string; ticket_no: string; category: Category; colors: string[]; brand?: string;
  zone_id: string; found_at: string; photo?: { url: string; blurred: true }; redacted?: boolean;
}

type FeatureKey = 'category' | 'color' | 'brand' | 'image' | 'text' | 'cross_modal' | 'marks' | 'zone' | 'time';
interface FeatureContribution {
  key: FeatureKey; label: string; weight: number; value: number;      // value: similarity 0..1
  contribution: number;                                               // share of the final score
  state: 'match' | 'partial' | 'mismatch' | 'not_compared'; detail: string;
}
interface Match {
  id: string; lost_item_id: string; candidate: PublicItem;
  score: number; band: 'strong' | 'possible' | 'long_shot'; rank: number;
  why: FeatureContribution[];
  feedback: 'mine' | 'not_mine' | 'unsure' | null; created_at: string;
}

interface Question { id: string; prompt: string; kind: 'text' | 'choice' | 'zone' | 'datetime'; choices?: string[] }
interface Claim {
  id: string; match_id: string; item_id: string; claimant_id: string;
  status: 'draft' | 'pending_review' | 'needs_more_info' | 'auto_approved' | 'approved' | 'rejected' | 'handed_over';
  questions: Question[]; verified_by?: 'answers' | 'roll_number' | 'reviewer'; created_at: string;
}
interface Handover { claim_id: string; qr_payload: string; code: string; expires_at: string; collect_zone_id: string }
interface ItemEvent { id: string; item_id: string; type: 'reported' | 'matched' | 'claimed' | 'verified' | 'handed_over' | 'closed'; actor_role: 'student' | 'finder' | 'desk' | 'system'; at: string; note?: string }
interface AppNotification { id: string; type: 'new_match' | 'claim_update' | 'handover_ready' | 'item_returned'; title: string; body: string; href: string; read: boolean; at: string }
interface Zone { id: string; name: string; short_name: string; kind: 'academic' | 'library' | 'hostel' | 'canteen' | 'sports' | 'gate' | 'admin'; centroid: [number, number] /* lon,lat */ }
interface User { id: string; email: string; role: 'student' | 'desk' | 'admin'; notify_push: boolean; notify_email: boolean; points: number }
```

**Endpoints.** Base path `/api/v1`. The client exposes one function per row, grouped as `api.auth`, `api.ref`, `api.items`, `api.matches`, `api.claims`, `api.handover`, `api.notifications`, `api.admin`.

| Area | Method and path | Request | Response |
|---|---|---|---|
| Auth | `POST /auth/otp/request` | `{ email }` | 204 |
| Auth | `POST /auth/otp/verify` | `{ email, code }` | `{ token, user }` |
| Auth | `GET /me` | | `User` |
| Auth | `PATCH /me` | `{ notify_push?, notify_email?, roll_no? }` | `User` |
| Auth | `POST /me/push-subscription` | `{ endpoint, keys }` | 204 |
| Reference | `GET /taxonomy` | | `{ categories, brands, colors, marks }` |
| Reference | `GET /zones` | | GeoJSON FeatureCollection with `Zone` properties, plus `{ graph }` |
| Items | `POST /items/extract-preview` | multipart: `photo?`, `text?`, `kind?` (`found` suggests private chips) | `{ attributes, detections, ocr_text, zone_hint?, suspected_id_card }` |
| Items | `POST /items` | multipart: `kind`, `text`, `zone_id`, `occurred_from`, `occurred_to`, `custody_zone_id?`, `attributes` (JSON), `photos[]` | `Item` |
| Items | `GET /items` | `?mine=1&kind&status` | `Item[]` |
| Items | `GET /items/public` | `?zone_id&category&q` | `PublicItem[]` |
| Items | `GET /items/{id}` | | `Item` |
| Items | `PATCH /items/{id}` | attribute corrections, hidden flags, zone, times | `Item` (re-runs matching) |
| Items | `POST /items/{id}/close` | `{ reason }` | `Item` |
| Items | `GET /items/{id}/events` | | `ItemEvent[]` |
| Items | `GET /items/{id}/matches` | | `Match[]` |
| Matches | `GET /matches` | `?status=pending` | `Match[]` (all mine) |
| Matches | `POST /matches/{id}/feedback` | `{ verdict: 'mine' \| 'not_mine' \| 'unsure' }` | `Match` |
| Claims | `POST /claims` | `{ match_id }` | `Claim` |
| Claims | `POST /claims/{id}/answers` | `{ answers: { question_id, answer }[] }` | `Claim` |
| Claims | `GET /claims/{id}` | | `Claim` |
| Claims | `GET /claims` | `?role=claimant\|finder` | `Claim[]` |
| Claims | `POST /claims/{id}/decision` | `{ decision: 'approve' \| 'reject' \| 'more_info', note? }` | `Claim` |
| Handover | `GET /claims/{id}/handover` | | `Handover` |
| Handover | `POST /claims/{id}/handover` | | `Handover` (a new code, after the old one expired) |
| Handover | `POST /handover/confirm` | `{ code }` or `{ token }` | `{ claim, item }` |
| Alerts | `GET /notifications` | | `AppNotification[]` |
| Alerts | `POST /notifications/{id}/read` | | 204 |
| Alerts | `POST /notifications/read-all` | | 204 |
| Alerts | `GET /notifications/stream` | SSE | events of `AppNotification` |
| Admin | `GET /admin/claims` | `?status` | claims with score breakdown |
| Admin | `GET /admin/insights/summary` | `?range=7d\|30d\|term` | `{ recovery_rate, median_hours_to_reunite, live_precision, open_lost, open_found, trend[] }` |
| Admin | `GET /admin/insights/hotspots` | `?range` | `{ zone_id, lost, found }[]` |
| Admin | `GET /admin/insights/heatmap` | `?range` | 7×24 matrix of counts |
| Admin | `GET /admin/insights/categories` | `?range` | `{ category, count }[]` |
| Admin | `GET /admin/insights/finders` | `?range` | `{ label, points, returned }[]` |
| Admin | `GET /admin/ops/scene` | `?from&to` | `{ pins[], arcs[], heat[] }` with timestamps |
| Admin | `GET /admin/eval/reports` | | `{ run_id, pairs, created_at }[]` |
| Admin | `GET /admin/eval/reports/{run_id}` | | eval report (shape below) |

Eval report shape: `{ run_id, pairs: 'synthetic' | 'real', n_pairs, metrics: { p_at_1, p_at_5, p_at_10, recall_at_5, mrr, map, ece }, targets: { p_at_1: 0.6, p_at_5: 0.85 }, reliability: { bin, confidence, accuracy, n }[], per_category: { category, p_at_1, p_at_5, n }[], ablation: { name, p_at_1, p_at_5 }[] }`.

**Mock layer rules.**
- One `api` object with the exact function names above. A single env variable (`<PREFIX>API_MODE`) picks the implementation: `mock` (default) or a base URL such as `http://localhost:8010`. Nothing outside `api/` knows which is active.
- The mock database lives in `localStorage` under `reunite.mock.v1`, seeded on first run, resettable from the dev drawer. Swipes, claims, and handovers persist across reloads.
- Latency is 200 to 700 ms with random jitter, adjustable in the dev drawer. A force-error switch makes calls fail so error states can be tested.
- **Mock extraction** is a small keyword parser: category synonyms (laptop, macbook, notebook computer, and so on), a short brand list (Dell, HP, Lenovo, Apple, Samsung, Sony, Casio, Logitech, Nike), color words to the taxonomy, mark words (dent, scratch, sticker, cracked, engraved). It returns per-attribute confidences and updates as the user types. Photos resolve deterministically from a hash of the file name to one of five canned detections, after a 600 ms "reading" delay.
- **Mock matching** returns a fixed, seeded set of `Match` records built from the sample data, with realistic `why` breakdowns (see §7). Seed a PRNG so screenshots are stable.
- **Mock photos** are inline SVG generated in code: a 4:3 plate colored by the item's primary named color, with the category's Phosphor duotone glyph at about 40% of the plate height in a tone-on-tone shade. The "blur" is a CSS `filter: blur()` applied to public/candidate photos. Item-color hex values: black `#1B1D20`, white `#F4F4F2`, grey `#8B9096`, silver `#C3C8CD`, red `#C8322B`, orange `#E8721E`, yellow `#E9C21F`, green `#3E8E52`, blue `#2F5FB8`, navy `#1F2F55`, purple `#6D4A9B`, pink `#E28AA9`, brown `#7A5238`, beige `#CDB697`, gold `#C9A24B`, maroon `#6E1F2E`, teal `#1F8A8A`.

### 7. Sample data

**Zones (eight, generic names; replace later):** Central Library, Block A Lecture Halls, Block B Labs, Main Gate and Security Desk, Canteen Court, Sports Complex, Hostel 3 Common Room, Admin Block. Give each a centroid and a simple polygon around the campus center in `campus.config`.

**Items (about twelve) chosen to exercise hostile cases.**
1. Lost: "black Dell laptop, small dent on the lid, crescent moon sticker" at Central Library. Has two strong matches.
2. Found: black laptop with a photo, custody at the Main Gate desk. Its `why` breakdown is the example below.
3. Found with a **30-word description** and a long zone name, to test truncation.
4. Lost, **text only**: "blue steel water bottle, Milton". Found, **photo only**: earbuds. A cross-modal match between two other items.
5. Found **ID card** with an OCR'd roll number (`CS21B042` style), redacted publicly, auto-notified to the owner.
6. Found grey bag with **low-confidence** attributes (brand undetected, dashed chips).
7. A lost item in **processing** state.
8. A lost item with **zero matches**.
9. A **returned** item with a full six-stop timeline.
10. Two items owned by the current user in different statuses (open, matched).

**One full match example** (use this shape for every seeded match):

```json
{
  "id": "m_01", "lost_item_id": "i_lost_01", "rank": 1, "score": 0.82, "band": "strong",
  "candidate": { "id": "i_found_02", "ticket_no": "RU-F-0089", "category": "laptop",
    "colors": ["black"], "brand": "Dell", "zone_id": "z_gate", "found_at": "2026-09-22T14:20:00Z",
    "photo": { "url": "mock://i_found_02", "blurred": true } },
  "why": [
    { "key": "category", "label": "Type", "weight": 0.18, "value": 1.0, "contribution": 0.18, "state": "match", "detail": "Both are laptops" },
    { "key": "image", "label": "Photo", "weight": 0.18, "value": 0.71, "contribution": 0.13, "state": "partial", "detail": "Similar shape and finish" },
    { "key": "color", "label": "Color", "weight": 0.12, "value": 1.0, "contribution": 0.12, "state": "match", "detail": "Both black" },
    { "key": "brand", "label": "Brand", "weight": 0.10, "value": 1.0, "contribution": 0.10, "state": "match", "detail": "Both Dell" },
    { "key": "zone", "label": "Place", "weight": 0.10, "value": 0.8, "contribution": 0.08, "state": "partial", "detail": "Lost at the library, turned in 2 zones away" },
    { "key": "time", "label": "Time", "weight": 0.08, "value": 0.9, "contribution": 0.07, "state": "match", "detail": "Turned in 6 hours after you lost it" },
    { "key": "marks", "label": "Marks", "weight": 0.06, "value": 0.6, "contribution": 0.04, "state": "partial", "detail": "Dent on the lid in both" },
    { "key": "text", "label": "Words", "weight": 0.10, "value": 0.6, "contribution": 0.06, "state": "partial", "detail": "Descriptions overlap" },
    { "key": "cross_modal", "label": "Words vs photo", "weight": 0.08, "value": 0.0, "contribution": 0.0, "state": "not_compared", "detail": "Not compared" }
  ],
  "feedback": null, "created_at": "2026-09-22T15:02:00Z"
}
```

The contributions above are illustrative and need not add exactly to the score. Keep them plausible and consistent from seed to seed.

Also seed: two claims (one `pending_review`, one `auto_approved`), six notifications (mixed read/unread), 7 days of ops events across the eight zones with a visible hotspot at the library and canteen, an insights summary, and one eval report each for `synthetic` and `real` (label the mock numbers as sample; do not present them as results).

### 8. Accessibility, performance, PWA, privacy

- **Accessibility.** WCAG AA contrast. Visible focus on every control (2 px `--ink` outline with 2 px offset; the same outline on every surface). Touch targets at least 44 px. Every input has a label. The deck is fully keyboard operable. Live regions for extraction updates, new alerts, and toasts. Lost/found and confidence are never conveyed by color alone. Respect `prefers-reduced-motion` everywhere. The whole app is light only and ignores `prefers-color-scheme`.
- **Performance.** Route-level code splitting. Cesium loads only on `/admin/ops`. Fonts subset by weight as listed. Images are SVG. Cold load of the student shell should stay under about 200 KB of JavaScript gzipped, excluding the ops chunk.
- **PWA.** Web manifest (name "Reunite", theme color `--ink`, a simple maskable icon you draw as SVG-to-PNG or inline), installable, offline app shell, and a push-notification handler stub. Register the service worker in production builds only.
- **Privacy.** Items only, never people. Hidden attributes never appear in any client-side type for non-owners. ID cards are always redacted publicly. Do not put emails, roll numbers, or codes in URLs. No analytics or third-party scripts. The ops view aggregates to zones.

### 9. Milestones and definition of done

Work in this order. After each milestone: run the app, check the preview at 360 px and 1280 px, read the console, fix errors, then continue.

1. **M1 Foundations and reporting.** Template profile, tokens and fonts, app shell and navigation, sign-in, Home (tickets), the full Report flow with the live extraction panel, Item detail and timeline, mock API and sample data, dev drawer.
2. **M2 Matching loop.** Matches deck with why-breakdown, Claim flow (all statuses, ID-card variant), Handover pass and confirm, Notifications with a live toast, Turned in list.
3. **M3 Admin.** Insights, Claims queue with drawer, Eval page, Campus ops 3D with the 2D fallback, THIRD_PARTY_NOTICES.md.
4. **M4 Polish.** Every empty, loading, and error state, offline drafts, accessibility pass, PWA, and a `README.md` describing: the template profile you found, the folder map, how to switch `API_MODE` from `mock` to a backend URL, and where the placeholders live.

**Definition of done (verify by actually running these):**
- [ ] Sign in with the demo code, report a lost item by text, and see chips appear as you type. Edit a chip. Submit and see the success ticket.
- [ ] Report a found item with a photo. The detector box and chips appear. Toggle one chip private.
- [ ] Open the deck, swipe right, land in the claim flow, answer the questions, reach the handover pass, then confirm the code on the desk screen. The timeline shows every stop.
- [ ] Notifications show unread and read states and the live toast.
- [ ] All admin screens render, including ops in both Cesium and fallback modes, with NVG and Thermal switching.
- [ ] 360 px, 768 px, and 1280 px layouts are usable. No horizontal scroll at 360 px.
- [ ] Keyboard-only run through the deck and the report form succeeds.
- [ ] Console is clean on every route. The app root is never empty.
- [ ] **Self-audit greps come back empty:** `indigo`, `#6366f1`, `#8b5cf6`, `Inter`, `Poppins`, `Geist`, `Big Shoulders`, `#0A7EA4`, `found-wash`, `data-surface`, `transition: all`, emoji characters used as icons, and the banned words in §2.
- [ ] Turning `API_MODE` to a bogus URL produces the designed error states, not a crash.

### 10. Placeholders

Keep each of these in **one file**, `campus.config`, or the environment, so they are a one-line change:

| Placeholder | Meaning | Until filled |
|---|---|---|
| `<<CAMPUS_NAME>>` | Shown in the header and the manifest. The campus map center (latitude and longitude) and the zone polygons come with it, all in `campus.config`. | Name: "Your Campus". Map center: a temporary default of 17.3850, 78.4867, marked `TEMP_DEFAULT` in the config. |
| `<<CESIUM_ION_TOKEN>>` | Secret `<PREFIX>CESIUM_ION_TOKEN` | 2D fallback |

`ALLOWED_EMAIL_DOMAINS` is ordinary configuration, not a placeholder. It defaults to empty, which means the mock accepts any address.

**Out of scope:** real ML, a real backend, real push delivery, payments, chat between users, any tracking of people or cameras.

## END PROMPT

---

## Short kickoff (paste this if the full prompt is saved as `SPEC.md`)

> Read `SPEC.md` in the project root and build it on this Repl's existing template. The visual direction is light: white, black and one orange, with the serif landing page and Cesium globe in §5.0. Replace any dark or blue styling already in the project. First inspect the template (framework, language, router, styling, package manager, port, public env prefix) and print a five-line profile. Then work through milestones M1 to M4 in order, running the app and checking the preview and the browser console after each one. Keep the template's scaffold and run command. Don't ask me questions unless you're blocked.
