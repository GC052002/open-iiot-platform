import { describe, expect, it } from "vitest";
import { applyTagValues, type TagMap } from "./tagStore";
import type { TagValue } from "../api/types";

function tv(tag_id: string, value: unknown, quality: TagValue["quality"] = "good"): TagValue {
  return { tag_id, value, quality, ts: "2026-08-02T00:00:00Z" };
}

describe("applyTagValues", () => {
  it("es inmutable: no muta el estado previo", () => {
    const prev: TagMap = {};
    const next = applyTagValues(prev, [tv("t1", 5)]);
    expect(prev).toEqual({});
    expect(next.t1.value).toBe(5);
  });

  it("devuelve el mismo objeto si el lote está vacío", () => {
    const prev: TagMap = { t1: { value: 1, quality: "good", ts: "x", trend: [1] } };
    expect(applyTagValues(prev, [])).toBe(prev);
  });

  it("acumula tendencia sólo para valores numéricos", () => {
    let s: TagMap = {};
    s = applyTagValues(s, [tv("t1", 1)]);
    s = applyTagValues(s, [tv("t1", 2)]);
    s = applyTagValues(s, [tv("t1", "texto")]);
    expect(s.t1.trend).toEqual([1, 2]);
    expect(s.t1.value).toBe("texto");
  });

  it("acota el buffer de tendencia a 60 muestras", () => {
    let s: TagMap = {};
    for (let i = 0; i < 100; i++) s = applyTagValues(s, [tv("t1", i)]);
    expect(s.t1.trend).toHaveLength(60);
    expect(s.t1.trend[0]).toBe(40);
    expect(s.t1.trend.at(-1)).toBe(99);
  });

  it("propaga la calidad de la última muestra", () => {
    const s = applyTagValues({}, [tv("t1", 0, "bad")]);
    expect(s.t1.quality).toBe("bad");
  });
});
