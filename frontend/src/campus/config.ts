// The one file to edit when the campus details change.
//
// Sources
//  - Names and facilities: the official site, https://www.vnrvjiet.ac.in (campus life and sports pages):
//    Central Library, Kode Venkatadri Chowdary Sports Complex, food courts, transport (bus fleet), 24/7 security.
//  - Positions: OpenStreetMap (c) contributors, ODbL. Footprints for the 3D view come from scripts/build_campus_buildings.py.
//  - Neither source lists a lost-and-found desk, so every pickup spot below is a suggestion until the college confirms one.
export const campus = {
  short: "VNR VJIET",
  name: "VNR Vignana Jyothi Institute of Engineering and Technology",
  place: "Bachupally, Hyderabad",
  // Middle of the built-up part of the campus (the OSM outline for the campus is only approximate).
  lat: 17.5388,
  lon: 78.386,
  /** Radius in metres of the sphere the camera frames for the whole-campus view. */
  radius: 260,
};

export type PickupPoint = {
  id: string;
  name: string;
  note: string;
  lat: number;
  lon: number;
  /** True when the position itself is a guess. Positions taken from OpenStreetMap are false. */
  approximate: boolean;
  /** Where the position comes from, shown to whoever is choosing where to collect. */
  source: string;
  /** OpenStreetMap building id, so the 3D view can light up the building when the spot is chosen. */
  buildingId?: number;
};

export const pickupPoints: PickupPoint[] = [
  {
    id: "gate",
    name: "Main gate, security desk",
    note: "Security is on duty around the clock. Unclaimed items are routed here first.",
    lat: 17.5416,
    lon: 78.38679,
    approximate: false,
    source: "Gate on OpenStreetMap, next to the ATM",
  },
  {
    id: "library",
    name: "Central library",
    note: "Books, notebooks, stationery and ID cards.",
    lat: 17.5372,
    lon: 78.3863,
    approximate: true,
    source: "Approximate: the library is not marked on OpenStreetMap",
  },
  {
    id: "sports",
    name: "Sports complex",
    note: "Kode Venkatadri Chowdary Sports Complex: bags, bottles and sports gear.",
    lat: 17.54066,
    lon: 78.38545,
    approximate: false,
    source: "OpenStreetMap",
    buildingId: 158309000,
  },
  {
    id: "sac",
    name: "SAC and food outlets",
    note: "Student activity centre beside the food outlets: bottles, lunch boxes and jackets.",
    lat: 17.53843,
    lon: 78.38478,
    approximate: false,
    source: "OpenStreetMap",
    buildingId: 158309248,
  },
  {
    id: "bus",
    name: "Student bus stop",
    note: "Items left on the college buses are brought here.",
    lat: 17.53985,
    lon: 78.38621,
    approximate: false,
    source: "OpenStreetMap",
  },
];

/** Labels for context on the map. All positions are from OpenStreetMap. */
export const landmarks: { name: string; lat: number; lon: number }[] = [
  { name: "D-Block", lat: 17.53668, lon: 78.38506 },
  { name: "Vignana Jyothi Institute of Management", lat: 17.54124, lon: 78.38577 },
  { name: "Workshops", lat: 17.53728, lon: 78.38526 },
  { name: "Amphitheatre", lat: 17.54128, lon: 78.3859 },
  { name: "Student parking", lat: 17.5401, lon: 78.38624 },
  { name: "Training and placement cell", lat: 17.53677, lon: 78.38423 },
  { name: "Football and cricket ground", lat: 17.53959, lon: 78.3854 },
  { name: "Tennis courts", lat: 17.54077, lon: 78.38643 },
];
