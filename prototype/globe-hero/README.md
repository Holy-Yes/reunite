# Reunite landing page and globe (prototype)

Reference implementation for §5.0 of `../../docs/WEBSITE_PROMPT.md`: the light landing page with a real 3D Earth (three.js) in the hero.

```bash
npm install
npm run dev      # http://127.0.0.1:5192
npm run build
```

- `src/globe.ts`: the globe. Relief-lit monochrome Earth, procedural drifting clouds with cloud shadows, ocean glint, atmosphere halo, pulsing pings, flowing arcs, orbit controls, fly-to. Loaded with a dynamic import, so three.js stays out of the first page load.
- `src/config.ts`: placeholder sector coordinates, decorative world pings and routes.
- `public/textures/earth-2k.jpg`: 2048 x 1024 Natural Earth II relief map (public domain), stitched from the level-2 tiles in the `cesium` npm package. No download was needed.
- `?noglobe` in the URL skips the globe, for debugging the page on its own.
- No token or API key. A static globe shows until the live one is ready.
