import { useEffect, useRef, useState } from "react";
import type { CampusScene, Marker } from "../campus/scene";

type Props = {
  markers: Marker[];
  /** Fly to this point whenever it changes. */
  focus?: { lat: number; lon: number } | null;
  /** Tap to drop a pin: called with where the person tapped. */
  onGround?(lat: number, lon: number): void;
  hint?: string;
  height?: number;
};

/** A small 3D map of the campus for choosing a spot or showing one. Cesium loads only when one of these appears. */
export default function PlaceMap({ markers, focus, onGround, hint, height = 300 }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const scene = useRef<CampusScene | null>(null);
  const latest = useRef({ markers, onGround });
  latest.current = { markers, onGround };
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let dead = false;
    let made: CampusScene | null = null;
    import("../campus/scene").then(({ createCampusScene }) => {
      if (dead || !host.current) return;
      made = createCampusScene({
        host: host.current,
        pickups: false,
        range: 520,
        onGround: (lat, lon) => latest.current.onGround?.(lat, lon),
        onFail: () => setFailed(true),
      });
      scene.current = made;
      made?.setMarkers(latest.current.markers);
    }).catch(() => setFailed(true));
    return () => {
      dead = true;
      scene.current = null;
      made?.destroy();
    };
  }, []);

  const key = JSON.stringify(markers);
  useEffect(() => scene.current?.setMarkers(markers), [key]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (focus) scene.current?.focus(focus.lat, focus.lon, 200);
  }, [focus?.lat, focus?.lon]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="placemap" style={{ height }}>
      <div ref={host} className="placemap__host" />
      {failed ? <p className="placemap__fail">The map isn't available. The place list above still works.</p> : hint ? <p className="placemap__hint">{hint}</p> : null}
    </div>
  );
}
