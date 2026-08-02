/**
 * Store de tags en tiempo real (Zustand).
 *
 * Recibe los `tag_update` del WS y mantiene la última-lectura-conocida por
 * `tag_id`, más un pequeño buffer de tendencia para sparklines (F3.2). El
 * reducer `applyTagValues` es **puro** y se testea sin React ni WS.
 */

import { create } from "zustand";
import type { Quality, TagValue } from "../api/types";

const TREND_LEN = 60;

export interface TagState {
  value: unknown;
  quality: Quality;
  ts: string;
  /** Muestras numéricas recientes (para sparklines). */
  trend: number[];
}

export type TagMap = Record<string, TagState>;

/** Reducer puro: aplica un lote de `TagValue` sobre el mapa previo (inmutable). */
export function applyTagValues(prev: TagMap, values: TagValue[]): TagMap {
  if (values.length === 0) return prev;
  const next: TagMap = { ...prev };
  for (const v of values) {
    const existing = next[v.tag_id];
    const trend = existing ? existing.trend.slice() : [];
    if (typeof v.value === "number") {
      trend.push(v.value);
      if (trend.length > TREND_LEN) trend.shift();
    }
    next[v.tag_id] = { value: v.value, quality: v.quality, ts: v.ts, trend };
  }
  return next;
}

interface TagStore {
  tags: TagMap;
  dropped: number; // muestras descartadas por backpressure (OverflowMsg)
  applyUpdate: (values: TagValue[]) => void;
  addDropped: (n: number) => void;
  reset: () => void;
}

export const useTagStore = create<TagStore>((set) => ({
  tags: {},
  dropped: 0,
  applyUpdate: (values) => set((s) => ({ tags: applyTagValues(s.tags, values) })),
  addDropped: (n) => set((s) => ({ dropped: s.dropped + n })),
  reset: () => set({ tags: {}, dropped: 0 }),
}));
