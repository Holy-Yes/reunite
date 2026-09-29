// Placeholder geography. Real coordinates come from campus.config in the full app.
// The three sectors are spread ~200 km apart on purpose: the 2K Earth texture has no
// street detail, so sectors closer together would collapse into one dot.
export type Sector = {
  id: string;
  name: string;
  lat: number;
  lon: number;
  item: string;
  open: number;
};

export const sectors: Sector[] = [
  { id: "north-hall", name: "North Hall", lat: 18.5204, lon: 73.8567, item: "blue headphones", open: 12 },
  { id: "commons", name: "The Commons", lat: 17.05, lon: 75.15, item: "silver water bottle", open: 8 },
  { id: "science-quad", name: "Science Quad", lat: 20.0, lon: 72.55, item: "green canvas tote", open: 15 },
];

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
