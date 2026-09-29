import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type Taxonomy, type Zone } from "./api";
import { useAuth } from "./auth";

type Ref = { zones: Zone[]; tax: Taxonomy | null; zoneName: (id: string | null | undefined) => string };
const C = createContext<Ref>({ zones: [], tax: null, zoneName: () => "" });

export function RefProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [zones, setZones] = useState<Zone[]>([]);
  const [tax, setTax] = useState<Taxonomy | null>(null);
  useEffect(() => {
    if (!user) return;
    api.zones().then((z) => setZones(z.features.map((f) => f.properties))).catch(() => {});
    api.taxonomy().then(setTax).catch(() => {});
  }, [user]);
  const zoneName = (id: string | null | undefined) => zones.find((z) => z.id === id)?.name ?? (id ?? "").replace(/^z_/, "").replace(/_/g, " ");
  return <C.Provider value={{ zones, tax, zoneName }}>{children}</C.Provider>;
}
export const useRef_ = () => useContext(C);
