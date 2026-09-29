import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { ambient, vnr, routes } from "./config";
import type { Theme } from "../theme";

export type GlobeApi = {
  /** Spin very fast, then land facing VNR VJIET with the camera diving in. Resolves when the dive ends. */
  launchToCampus(): Promise<void>;
  setTheme(theme: Theme): void;
  /** Live spin state, for debugging and tests. */
  state(): { rotationY: number; omega: number; spinDir: 1 | -1; mode: string };
  destroy(): void;
};

/** Hover index of the VNR VJIET marker. It is the only marker you can point at. */
export const CAMPUS_HOVER = -1;

type Options = {
  host: HTMLElement;
  theme: Theme;
  onHover(index: number | null, x: number, y: number): void;
};

const ORANGE = new THREE.Color("#FF6A13");
const INK = new THREE.Color("#0B0B0B");

const FILL = 1.32; // globe diameter as a share of the hero height (it bleeds past the top and bottom)
const FOV = 30;
const SPIN_RATE = 0.04; // radians per second, about three minutes a turn
const SPIN_SETTLE_S = 2.5; // time constant for a flung globe to ease back to the base rate
const LAUNCH_MS = 2800;
const LAUNCH_TURNS = 3; // full extra turns before landing on the campus
const CAMPUS_DISTANCE = 1.13; // camera distance in Earth radii at the end of the dive
const INK_LIGHT = new THREE.Color("#0B0B0B");
const INK_DARK = new THREE.Color("#F4F1EC");
const PAPER_LIGHT = new THREE.Color("#FFFFFF");
const PAPER_DARK = new THREE.Color("#04060D");

const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const mod = (a: number, n: number) => ((a % n) + n) % n;

/** Latitude and longitude to a point on the unit sphere. Longitude 0 faces +X, 90E faces -Z, matching SphereGeometry's UVs. */
const toVec = (lat: number, lon: number, r = 1) => {
  const la = THREE.MathUtils.degToRad(lat);
  const lo = THREE.MathUtils.degToRad(lon);
  return new THREE.Vector3(Math.cos(la) * Math.cos(lo), Math.sin(la), -Math.cos(la) * Math.sin(lo)).multiplyScalar(r);
};

// ---- shaders ---------------------------------------------------------------

const NOISE = /* glsl */ `
  float hash(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
  float noise(vec3 x) {
    vec3 i = floor(x); vec3 f = fract(x); f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash(i), hash(i + vec3(1,0,0)), f.x), mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
               mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x), mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y), f.z);
  }
  float fbm(vec3 p) {
    float a = 0.5, s = 0.0;
    for (int i = 0; i < 5; i++) { s += a * noise(p); p = p * 2.03 + vec3(1.7, 9.2, 3.1); a *= 0.5; }
    return s;
  }
  // Cloud cover 0..1 for a direction on the sphere. Domain-warped noise reads as swirled weather, not blobs.
  float cloudCover(vec3 dir, float t) {
    vec3 p = dir * 3.1;
    vec3 w = vec3(noise(p * 1.6 + t * 0.02), noise(p * 1.6 + 7.3), noise(p * 1.6 + 13.1)) - 0.5;
    float n = fbm(p + w * 1.1);
    float lat = abs(dir.y);
    n += 0.10 * smoothstep(0.55, 0.9, lat) - 0.06 * smoothstep(0.0, 0.25, 1.0 - abs(lat - 0.25));
    return smoothstep(0.40, 0.63, n);
  }
`;

const EARTH_VERT = /* glsl */ `
  varying vec2 vUv; varying vec3 vN; varying vec3 vP; varying vec3 vDir;
  void main() {
    vUv = uv; vDir = normalize(position);
    vN = normalize(normalMatrix * normal);
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vP = mv.xyz;
    gl_Position = projectionMatrix * mv;
  }
`;

const EARTH_FRAG = /* glsl */ `
  uniform sampler2D uMap; uniform vec3 uLight; uniform float uRel; uniform float uTime; uniform float uBump;
  varying vec2 vUv; varying vec3 vN; varying vec3 vP; varying vec3 vDir;
  ${NOISE}
  vec3 rotY(vec3 p, float a) { float c = cos(a), s = sin(a); return vec3(c * p.x + s * p.z, p.y, -s * p.x + c * p.z); }
  vec3 bump(vec3 N, vec3 P, float h, float k) {
    vec3 sx = dFdx(P), sy = dFdy(P);
    vec3 r1 = cross(sy, N), r2 = cross(N, sx);
    float det = dot(sx, r1);
    vec3 g = sign(det) * (dFdx(h) * r1 + dFdy(h) * r2);
    return normalize(abs(det) * N - k * g);
  }
  void main() {
    vec3 tex = texture2D(uMap, vUv).rgb;                       // linear
    float lum = dot(tex, vec3(0.30, 0.59, 0.11));
    float ocean = smoothstep(0.02, 0.12, tex.b - tex.r);

    // Monochrome: pale relief land, mid-grey sea.
    float land = mix(0.30, 0.78, smoothstep(0.06, 0.5, lum));
    float sea = 0.36 + 0.10 * smoothstep(0.05, 0.3, lum);
    float base = mix(land, sea, ocean);

    vec3 N0 = normalize(vN);
    vec3 N = bump(N0, vP, lum * (1.0 - ocean), uBump);
    vec3 V = normalize(-vP);
    float ndl = dot(N, uLight);
    float lit = mix(0.52, 1.06, smoothstep(-0.4, 0.85, ndl));   // soft terminator, no black night side

    vec3 col = vec3(base) * lit;

    // sun glint on water
    vec3 H = normalize(uLight + V);
    col += vec3(pow(max(dot(N, H), 0.0), 70.0) * ocean * 0.5);

    // cloud shadows: the same cover, nudged away from the sun
    float cs = cloudCover(rotY(vDir, uRel) + vec3(0.02, -0.03, 0.0), uTime);
    col *= 1.0 - 0.30 * cs;

    // limb: slight darkening, then a veil of haze
    float fres = pow(1.0 - max(dot(N0, V), 0.0), 3.0);
    col = mix(col, col * 0.62, fres * 0.55);
    col = mix(col, vec3(0.93), fres * 0.28);

    gl_FragColor = vec4(col, 1.0);
    #include <colorspace_fragment>
  }
`;

const CLOUD_FRAG = /* glsl */ `
  uniform vec3 uLight; uniform float uTime;
  varying vec3 vN; varying vec3 vP; varying vec3 vDir; varying vec2 vUv;
  ${NOISE}
  void main() {
    float cov = cloudCover(vDir, uTime);
    vec3 N = normalize(vN); vec3 V = normalize(-vP);
    float lit = mix(0.7, 1.0, smoothstep(-0.4, 0.85, dot(N, uLight)));
    float fres = pow(1.0 - max(dot(N, V), 0.0), 2.0);
    float a = cov * (0.92 + 0.08 * fres);
    gl_FragColor = vec4(vec3(lit), a);
    #include <colorspace_fragment>
  }
`;

const HALO_FRAG = /* glsl */ `
  varying vec3 vN;
  void main() {
    float nd = clamp(-dot(normalize(vN), vec3(0.0, 0.0, 1.0)), 0.0, 1.0);
    float i = pow(smoothstep(0.0, 0.42, nd), 2.2);
    gl_FragColor = vec4(vec3(1.0, 0.62, 0.36), i * 0.34);
    #include <colorspace_fragment>
  }
`;
const HALO_VERT = /* glsl */ `
  varying vec3 vN;
  void main() { vN = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
`;

// ---- module ----------------------------------------------------------------

export async function createGlobe({ host, theme, onHover }: Options): Promise<GlobeApi> {
  // Ink (found items, selected marker) and paper (marker backing) swap in dark mode.
  const ink = () => (theme === "dark" ? INK_DARK : INK_LIGHT);
  const paper = () => (theme === "dark" ? PAPER_DARK : PAPER_LIGHT);
  const inkMats: THREE.Material[] = [];
  const paperMats: THREE.MeshBasicMaterial[] = [];

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setClearColor(0x000000, 0);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const canvas = renderer.domElement;
  host.appendChild(canvas);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.02, 60);
  const size = () => ({ w: Math.max(host.clientWidth, 1), h: Math.max(host.clientHeight, 1) });

  const texture = await new THREE.TextureLoader().loadAsync("/textures/earth-2k.jpg");
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = renderer.capabilities.getMaxAnisotropy();

  const light = new THREE.Vector3(-0.55, 0.45, 0.7).normalize(); // view space: fixed to the screen

  // ---- Earth, clouds, halo
  const earthGroup = new THREE.Group();
  scene.add(earthGroup);

  const earthMat = new THREE.ShaderMaterial({
    uniforms: { uMap: { value: texture }, uLight: { value: light }, uRel: { value: 0 }, uTime: { value: 0 }, uBump: { value: 0.09 } },
    vertexShader: EARTH_VERT,
    fragmentShader: EARTH_FRAG,
  });
  const earth = new THREE.Mesh(new THREE.SphereGeometry(1, 128, 96), earthMat);
  earthGroup.add(earth);

  const cloudMat = new THREE.ShaderMaterial({
    uniforms: { uLight: { value: light }, uTime: { value: 0 } },
    vertexShader: EARTH_VERT,
    fragmentShader: CLOUD_FRAG,
    transparent: true,
    depthWrite: false,
  });
  const clouds = new THREE.Mesh(new THREE.SphereGeometry(1.012, 96, 72), cloudMat);
  scene.add(clouds);

  const halo = new THREE.Mesh(
    new THREE.SphereGeometry(1.1, 64, 48),
    new THREE.ShaderMaterial({
      vertexShader: HALO_VERT,
      fragmentShader: HALO_FRAG,
      side: THREE.BackSide,
      transparent: true,
      depthWrite: false,
    }),
  );
  scene.add(halo);

  // ---- pings and arcs (children of the Earth so they turn with it)
  type Ping = { group: THREE.Group; ring: THREE.Mesh; core: THREE.Mesh; back: THREE.Mesh; phase: number; base: number };
  const pings: Ping[] = [];
  const hitTargets: THREE.Mesh[] = [];
  const hitMat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, colorWrite: false });
  const discGeo = new THREE.CircleGeometry(1, 32);
  const ringGeo = new THREE.RingGeometry(0.86, 1, 48);
  const coreGeo = new THREE.SphereGeometry(1, 20, 14);

  const addPing = (lat: number, lon: number, color: THREE.Color, radius: number, hoverIndex?: number): Ping => {
    const pos = toVec(lat, lon, 1.004);
    const group = new THREE.Group();
    group.position.copy(pos);
    group.lookAt(pos.clone().multiplyScalar(2));
    const back = new THREE.Mesh(discGeo, new THREE.MeshBasicMaterial({ color: paper() }));
    paperMats.push(back.material as THREE.MeshBasicMaterial);
    back.scale.setScalar(radius * 1.45);
    const core = new THREE.Mesh(coreGeo, new THREE.MeshBasicMaterial({ color }));
    core.scale.setScalar(radius);
    const ring = new THREE.Mesh(
      ringGeo,
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.5, depthWrite: false, side: THREE.DoubleSide }),
    );
    if (color === INK) inkMats.push(core.material as THREE.Material, ring.material as THREE.Material);
    group.add(back, core, ring);
    if (hoverIndex !== undefined) {
      const hit = new THREE.Mesh(coreGeo, hitMat);
      hit.scale.setScalar(radius * 3.2);
      hit.userData.sector = hoverIndex;
      group.add(hit);
      hitTargets.push(hit);
    }
    earthGroup.add(group);
    const ping = { group, ring, core, back, phase: Math.random(), base: radius };
    pings.push(ping);
    return ping;
  };

  const lineMats: { mat: LineMaterial; period: number }[] = [];
  const arc = (a: [number, number], b: [number, number], color: THREE.Color, opacity: number) => {
    const va = toVec(a[0], a[1]);
    const vb = toVec(b[0], b[1]);
    const ang = va.angleTo(vb);
    const steps = 64;
    const flat: number[] = [];
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const v = va
        .clone()
        .multiplyScalar(Math.sin((1 - t) * ang))
        .add(vb.clone().multiplyScalar(Math.sin(t * ang)))
        .divideScalar(Math.sin(ang))
        .normalize()
        .multiplyScalar(1.006 + Math.sin(Math.PI * t) * ang * 0.16);
      flat.push(v.x, v.y, v.z);
    }
    const geo = new LineGeometry();
    geo.setPositions(flat);
    const period = (ang * 1.15) / 18;
    const mat = new LineMaterial({
      color: color.getHex(),
      linewidth: 2,
      dashed: true,
      dashSize: period * 0.55,
      gapSize: period * 0.45,
      transparent: true,
      opacity,
    });
    if (color === INK) inkMats.push(mat);
    const line = new Line2(geo, mat);
    line.computeLineDistances();
    earthGroup.add(line);
    lineMats.push({ mat, period });
  };

  ambient.forEach((p) => addPing(p.lat, p.lon, p.lost ? ORANGE : INK, 0.0062));
  routes.forEach(([lost, found], i) =>
    arc([ambient[lost].lat, ambient[lost].lon], [ambient[found].lat, ambient[found].lon], i % 3 === 0 ? INK : ORANGE, 0.9),
  );
  // The real campus: always orange with an ink halo so it reads as the destination.
  const campusPing = addPing(vnr.lat, vnr.lon, ORANGE, 0.0125, CAMPUS_HOVER);
  campusPing.back.scale.setScalar(campusPing.base * 1.6);
  const campusBack = campusPing.back.material as THREE.MeshBasicMaterial;
  paperMats.splice(paperMats.indexOf(campusBack), 1);
  campusBack.color.copy(ink());

  // ---- camera and controls
  const controls = new OrbitControls(camera, canvas);
  controls.enablePan = false;
  controls.enableDamping = true;
  controls.dampingFactor = 0.07;
  controls.rotateSpeed = 0.45;
  controls.zoomSpeed = 0.7;
  controls.minDistance = 1.25; // closer than this the 2K texture goes blocky
  controls.maxDistance = 8;
  canvas.style.touchAction = "pan-y"; // let a vertical swipe scroll the page on phones

  const fitDistance = () => {
    const { w, h } = size();
    const aspect = w / h;
    const tanHalf = Math.tan(THREE.MathUtils.degToRad(FOV / 2));
    const tanMin = aspect >= 1 ? tanHalf : tanHalf * aspect;
    const fill = aspect >= 1 ? FILL : 1.0; // on a phone, fit the width
    return 1 / Math.sin(Math.atan(fill * tanMin));
  };

  let mode: "overview" | "launch" = "overview";

  // ---- perpetual spin. The globe never stops; a drag only decides which way it turns.
  // OrbitControls moves the camera, so the Earth's spin is the opposite of the camera's azimuth motion.
  let spinDir: 1 | -1 = 1;
  let omega = SPIN_RATE; // current angular velocity of the Earth, rad/s (signed)
  let dragging = false;
  let azPrev = 0;
  let azUnwrapped = 0;
  let dragStartAz = 0;
  const azSamples: { t: number; az: number }[] = [];
  const camAzimuth = () => Math.atan2(camera.position.x, camera.position.z);
  controls.addEventListener("start", () => {
    dragging = true;
    azPrev = camAzimuth();
    azUnwrapped = 0;
    dragStartAz = 0;
    azSamples.length = 0;
  });
  controls.addEventListener("end", () => {
    dragging = false;
    // Prefer the release velocity (last ~150 ms); if the pointer paused before release, use the whole drag.
    const last = azSamples[azSamples.length - 1];
    const recent = azSamples.find((s) => last && last.t - s.t <= 150);
    let v = 0;
    if (last && recent && last.t - recent.t > 30) v = (last.az - recent.az) / ((last.t - recent.t) / 1000);
    if (Math.abs(v) < 0.05 && Math.abs(azUnwrapped - dragStartAz) > 0.05) v = azUnwrapped - dragStartAz;
    if (Math.abs(v) >= 0.05) {
      spinDir = v > 0 ? -1 : 1;
      // A hard flick briefly spins faster, then settles back to the base rate.
      omega = spinDir * Math.max(SPIN_RATE, Math.min(Math.abs(v) * 0.25, 0.6));
    }
  });

  const resize = () => {
    const { w, h } = size();
    renderer.setSize(w, h, false);
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    lineMats.forEach(({ mat }) => mat.resolution.set(w, h));
    if (mode === "overview") camera.position.setLength(fitDistance());
  };

  // Start facing India, over the campus's side of the world.
  earthGroup.rotation.y = -Math.PI / 2 - THREE.MathUtils.degToRad(64);
  camera.position.set(0, 0.25, 1).normalize().multiplyScalar(fitDistance());
  camera.lookAt(0, 0, 0);
  resize();

  // ---- launch: spin very fast, land on the campus, dive
  type Launch = { start: number; r0: number; total: number; fromDir: THREE.Vector3; toDir: THREE.Vector3; fromDist: number; resolve(): void };
  let launch: Launch | null = null;
  const easeQuad = (t: number) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
  const stepLaunch = (now: number) => {
    if (!launch) return;
    const t = Math.min(1, (now - launch.start) / LAUNCH_MS);
    earthGroup.rotation.y = launch.r0 + launch.total * easeQuad(t);
    const kc = t < 0.4 ? 0 : easeQuad((t - 0.4) / 0.6);
    const q = new THREE.Quaternion().setFromUnitVectors(launch.fromDir, launch.toDir);
    const dir = launch.fromDir.clone().applyQuaternion(new THREE.Quaternion().slerp(q, kc));
    camera.position.copy(dir.multiplyScalar(THREE.MathUtils.lerp(launch.fromDist, CAMPUS_DISTANCE, kc)));
    camera.lookAt(0, 0, 0);
    if (t >= 1) {
      const done = launch.resolve;
      launch = null;
      done();
    }
  };

  // ---- hover
  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const pick = (e: PointerEvent) => {
    const r = canvas.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
    const hit = raycaster.intersectObjects([...hitTargets, earth], false)[0];
    const idx = hit && typeof hit.object.userData.sector === "number" ? (hit.object.userData.sector as number) : null;
    return { idx, x: e.clientX - r.left, y: e.clientY - r.top };
  };
  canvas.addEventListener("pointermove", (e) => {
    if (e.buttons) return;
    const { idx, x, y } = pick(e);
    canvas.style.cursor = idx === null ? "grab" : idx === CAMPUS_HOVER ? "help" : "pointer";
    onHover(idx, x, y);
  });
  canvas.addEventListener("pointerleave", () => onHover(null, 0, 0));

  const ro = new ResizeObserver(resize);
  ro.observe(host);

  // ---- frame loop
  let lastFrame = performance.now();
  let time = 0;
  renderer.setAnimationLoop(() => {
    const now = performance.now();
    const dt = Math.min((now - lastFrame) / 1000, 0.1);
    lastFrame = now;
    const still = reduceMotion();
    if (!still) time += dt;

    stepLaunch(now);
    if (dragging) {
      const az = camAzimuth();
      let d = az - azPrev;
      if (d > Math.PI) d -= 2 * Math.PI;
      else if (d < -Math.PI) d += 2 * Math.PI;
      azUnwrapped += d;
      azPrev = az;
      azSamples.push({ t: now, az: azUnwrapped });
      if (azSamples.length > 40) azSamples.shift();
    } else if (mode === "overview" && !still) {
      omega += (spinDir * SPIN_RATE - omega) * (1 - Math.exp(-dt / SPIN_SETTLE_S));
      earthGroup.rotation.y += omega * dt;
    }
    clouds.rotation.y = earthGroup.rotation.y + time * 0.006;
    earthMat.uniforms.uRel.value = -time * 0.006;
    earthMat.uniforms.uTime.value = time;
    // Relief only reads well from far away: up close it would exaggerate the texture's pixels.
    earthMat.uniforms.uBump.value = 0.09 * THREE.MathUtils.smoothstep(camera.position.length(), 1.4, 2.6);
    cloudMat.uniforms.uTime.value = time;

    // Keep markers a sensible size at every zoom level.
    const zoom = THREE.MathUtils.clamp((camera.position.length() - 1) / 1.6, 0.16, 1);
    for (const p of pings) {
      const phase = still ? 0.55 : (time * 0.45 + p.phase) % 1;
      p.group.scale.setScalar(zoom);
      p.ring.scale.setScalar(p.base * (1.4 + phase * 4.2));
      (p.ring.material as THREE.MeshBasicMaterial).opacity = (1 - phase) * 0.55;
    }
    const offset = still ? 0 : (time * 0.25) % 1;
    lineMats.forEach(({ mat, period }) => (mat.dashOffset = -offset * period));

    controls.update();
    renderer.render(scene, camera);
  });

  return {
    launchToCampus() {
      if (reduceMotion() || launch) return Promise.resolve();
      mode = "launch";
      dragging = false;
      controls.enabled = false;
      // Rotate the Earth so VNR VJIET faces the camera's azimuth: a point at azimuth a sits at a + r after rotating by r.
      const v = toVec(vnr.lat, vnr.lon);
      const aCam = Math.atan2(camera.position.x, camera.position.z);
      const r0 = earthGroup.rotation.y;
      const delta = mod(spinDir * (aCam - Math.atan2(v.x, v.z) - r0), 2 * Math.PI); // distance to travel in the spin direction
      const total = spinDir * (delta + 2 * Math.PI * LAUNCH_TURNS);
      const la = THREE.MathUtils.degToRad(vnr.lat);
      const toDir = new THREE.Vector3(Math.cos(la) * Math.sin(aCam), Math.sin(la), Math.cos(la) * Math.cos(aCam));
      return new Promise<void>((resolve) => {
        launch = { start: performance.now(), r0, total, fromDir: camera.position.clone().normalize(), toDir, fromDist: camera.position.length(), resolve };
      });
    },
    setTheme(next) {
      theme = next;
      inkMats.forEach((m) => (m as THREE.MeshBasicMaterial | LineMaterial).color.set(ink()));
      paperMats.forEach((m) => m.color.copy(paper()));
      campusBack.color.copy(ink());
    },
    state: () => ({ rotationY: earthGroup.rotation.y, omega, spinDir, mode }),
    destroy() {
      renderer.setAnimationLoop(null);
      ro.disconnect();
      controls.dispose();
      renderer.dispose();
      canvas.remove();
    },
  };
}
