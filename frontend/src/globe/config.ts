import { campus } from "../campus/config";

// Decorative points and routes for the whole-Earth view. They are not data.
export const ambient: { lat: number; lon: number; lost: boolean }[] = [
  { lat: 51.5, lon: -0.12, lost: false },
  { lat: 40.7, lon: -74.0, lost: true },
  { lat: 37.4, lon: -122.1, lost: false },
  { lat: -33.9, lon: 151.2, lost: true },
  { lat: 35.7, lon: 139.7, lost: false },
  { lat: 1.35, lon: 103.8, lost: true },
  { lat: -1.29, lon: 36.8, lost: false },
  { lat: -23.5, lon: -46.6, lost: true },
  { lat: 30.0, lon: 31.2, lost: true },
  { lat: 55.7, lon: 37.6, lost: false },
  { lat: 28.6, lon: 77.2, lost: true },
  { lat: 6.5, lon: 3.4, lost: false },
];

// Index pairs into `ambient` joined by an arc (lost end first).
export const routes: [number, number][] = [
  [1, 0],
  [3, 4],
  [5, 4],
  [7, 6],
  [8, 9],
  [10, 9],
  [1, 2],
];


/** Where the launch dive ends (camera height in metres); the campus map page carries on from here. */
export const DIVE_HEIGHT = 80_000;

/** The real campus. Clicking Log in or Report an item spins the globe here. */
export const vnr = { name: campus.short, place: "Hyderabad", lat: campus.lat, lon: campus.lon };
