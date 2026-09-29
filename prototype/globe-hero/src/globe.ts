import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { ambient, routes, sectors } from "./config";

export type GlobeApi = {
  select(index: number): void;
  overview(): void;
  destroy(): void;
};

type Options = {
  host: HTMLElement;
  onSelect(index: number): void;
  onHover(index: number | null, x: number, y: number): void;
};

const ORANGE = new THREE.Color("#FF6A13");
const INK = new THREE.Color("#0B0B0B");

const FILL = 1.32; // globe diameter as a share of the hero height (it bleeds past the top and bottom)
const FOV = 30;
const SECTOR_DISTANCE = 1.5; // camera distance in Earth radii when a sector is selected
const SPIN_RATE = 0.04; // radians per second, about three minutes a turn
const IDLE_RESUME_MS = 3000;

const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

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

export async function createGlobe({ host, onSelect, onHover }: Options): Promise<GlobeApi> {
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

  const addPing = (lat: number, lon: number, color: THREE.Color, radius: number, sectorIndex?: number): Ping => {
    const pos = toVec(lat, lon, 1.004);
    const group = new THREE.Group();
    group.position.copy(pos);
    group.lookAt(pos.clone().multiplyScalar(2));
    const back = new THREE.Mesh(discGeo, new THREE.MeshBasicMaterial({ color: 0xffffff }));
    back.scale.setScalar(radius * 1.45);
    const core = new THREE.Mesh(coreGeo, new THREE.MeshBasicMaterial({ color }));
    core.scale.setScalar(radius);
    const ring = new THREE.Mesh(
      ringGeo,
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.5, depthWrite: false, side: THREE.DoubleSide }),
    );
    group.add(back, core, ring);
    if (sectorIndex !== undefined) {
      const hit = new THREE.Mesh(coreGeo, hitMat);
      hit.scale.setScalar(radius * 3.2);
      hit.userData.sector = sectorIndex;
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
    const line = new Line2(geo, mat);
    line.computeLineDistances();
    earthGroup.add(line);
    lineMats.push({ mat, period });
  };

  ambient.forEach((p) => addPing(p.lat, p.lon, p.lost ? ORANGE : INK, 0.0062));
  routes.forEach(([lost, found], i) =>
    arc([ambient[lost].lat, ambient[lost].lon], [ambient[found].lat, ambient[found].lon], i % 3 === 0 ? INK : ORANGE, 0.9),
  );
  const sectorPings = sectors.map((s, i) => addPing(s.lat, s.lon, ORANGE, 0.0095, i));
  sectors.forEach((s, i) => {
    const found: [number, number] = [s.lat + (i === 1 ? 0.5 : -0.45), s.lon + (i === 2 ? -0.55 : 0.6)];
    addPing(found[0], found[1], INK, 0.0065);
    arc([s.lat, s.lon], found, i === 0 ? ORANGE : INK, 0.95);
  });

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

  let mode: "overview" | "sector" = "overview";
  let anim: Anim | null = null;
  let lastTouch = -Infinity;
  const touch = () => (lastTouch = performance.now());
  controls.addEventListener("start", touch);
  controls.addEventListener("end", touch);
  canvas.addEventListener("wheel", touch, { passive: true });

  const resize = () => {
    const { w, h } = size();
    renderer.setSize(w, h, false);
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    lineMats.forEach(({ mat }) => mat.resolution.set(w, h));
    if (mode === "overview" && !anim) camera.position.setLength(fitDistance());
  };

  // Start facing India, so the sectors are near the middle of the view.
  earthGroup.rotation.y = -Math.PI / 2 - THREE.MathUtils.degToRad(64);
  camera.position.set(0, 0.25, 1).normalize().multiplyScalar(fitDistance());
  camera.lookAt(0, 0, 0);
  resize();

  // ---- fly-to
  type Anim = { start: number; dur: number; fromDir: THREE.Vector3; toDir: THREE.Vector3; fromDist: number; toDist: number };
  const fly = (toDir: THREE.Vector3, toDist: number) => {
    anim = {
      start: performance.now(),
      dur: reduceMotion() ? 1 : 2400,
      fromDir: camera.position.clone().normalize(),
      toDir: toDir.clone().normalize(),
      fromDist: camera.position.length(),
      toDist,
    };
    controls.enabled = false;
  };
  const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const stepAnim = (now: number) => {
    if (!anim) return;
    const t = Math.min(1, (now - anim.start) / anim.dur);
    const k = ease(t);
    const q = new THREE.Quaternion().setFromUnitVectors(anim.fromDir, anim.toDir);
    const dir = anim.fromDir.clone().applyQuaternion(new THREE.Quaternion().slerp(q, k));
    camera.position.copy(dir.multiplyScalar(THREE.MathUtils.lerp(anim.fromDist, anim.toDist, k)));
    camera.lookAt(0, 0, 0);
    if (t >= 1) {
      anim = null;
      controls.enabled = true;
    }
  };

  // ---- selection, hover, click
  let selected = 0;
  const applySelection = () =>
    sectorPings.forEach((p, i) => {
      const on = i === selected;
      p.base = on ? 0.0135 : 0.0095;
      (p.back.material as THREE.MeshBasicMaterial).color.set(on ? INK : 0xffffff);
      p.back.scale.setScalar(p.base * (on ? 1.55 : 1.45));
      p.core.scale.setScalar(p.base);
    });
  applySelection();

  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  let down: { x: number; y: number } | null = null;
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
    canvas.style.cursor = idx === null ? "grab" : "pointer";
    onHover(idx, x, y);
  });
  canvas.addEventListener("pointerdown", (e) => (down = { x: e.clientX, y: e.clientY }));
  canvas.addEventListener("pointerup", (e) => {
    if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) < 5) {
      const { idx } = pick(e);
      if (idx !== null) onSelect(idx);
    }
    down = null;
  });
  canvas.addEventListener("pointerleave", () => onHover(null, 0, 0));

  const ro = new ResizeObserver(resize);
  ro.observe(host);

  // ---- frame loop
  const clock = new THREE.Clock();
  let time = 0;
  renderer.setAnimationLoop(() => {
    const dt = Math.min(clock.getDelta(), 0.1);
    const now = performance.now();
    const still = reduceMotion();
    if (!still) time += dt;

    stepAnim(now);
    if (mode === "overview" && !anim && !still && now - lastTouch > IDLE_RESUME_MS) earthGroup.rotation.y += SPIN_RATE * dt;
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
    select(index) {
      selected = index;
      applySelection();
      mode = "sector";
      const dir = sectorPings[index].group.getWorldPosition(new THREE.Vector3()).normalize();
      fly(dir, SECTOR_DISTANCE);
    },
    overview() {
      mode = "overview";
      touch();
      fly(camera.position.clone().normalize(), fitDistance());
    },
    destroy() {
      renderer.setAnimationLoop(null);
      ro.disconnect();
      controls.dispose();
      renderer.dispose();
      canvas.remove();
    },
  };
}
