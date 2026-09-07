import { describe, expect, it } from "vitest";
import {
  BAND_ROWS,
  FALLBACK_LINE,
  MIN_VIEW_WIDTH,
  VIEW_ROWS,
  bandBox,
  toPixels,
  zoomViewport,
} from "../geometry";
import type { Box } from "../../types";

const box: Box = [0.1, 0.2, 0.4, 0.25];

describe("bandBox (R5: widen upward, against the measured downward drift)", () => {
  it("lifts only the top edge, by BAND_ROWS line heights", () => {
    const lh = 0.01;
    expect(bandBox(box, lh)).toEqual([0.1, 0.2 - BAND_ROWS * lh, 0.4, 0.25]);
  });
  it("falls back to the measured median when the page has no layer", () => {
    expect(bandBox(box, null)[1]).toBeCloseTo(0.2 - BAND_ROWS * FALLBACK_LINE);
  });
  it("clamps at the page top rather than going negative", () => {
    expect(bandBox([0.1, 0.005, 0.4, 0.05], 0.01)[1]).toBe(0);
  });
});

describe("toPixels", () => {
  it("scales fractions by the rendered page size", () => {
    const rect = toPixels(box, 1000, 2000);
    expect(rect.left).toBeCloseTo(100);
    expect(rect.top).toBeCloseTo(400);
    expect(rect.width).toBeCloseTo(300);
    expect(rect.height).toBeCloseTo(100);
  });
});

describe("zoomViewport (the 2026-09-03 rule: readable scale, never full page)", () => {
  it("is at least VIEW_ROWS line heights tall for a tiny box", () => {
    const [, top, , bottom] = zoomViewport([0.4, 0.5, 0.42, 0.507], 0.01);
    expect(bottom - top).toBeCloseTo(VIEW_ROWS * 0.01);
  });
  it("is at least MIN_VIEW_WIDTH wide", () => {
    const [left, , right] = zoomViewport([0.4, 0.5, 0.42, 0.507], 0.01);
    expect(right - left).toBeGreaterThanOrEqual(MIN_VIEW_WIDTH - 1e-9);
  });
  it("contains the region it zooms to", () => {
    const [l, t, r, b] = zoomViewport(box, 0.01);
    expect(l).toBeLessThanOrEqual(0.1);
    expect(t).toBeLessThanOrEqual(0.2);
    expect(r).toBeGreaterThanOrEqual(0.4);
    expect(b).toBeGreaterThanOrEqual(0.25);
  });
  it("clamps to the page at every edge", () => {
    for (const corner of [
      [0.0, 0.0, 0.05, 0.01],
      [0.95, 0.99, 1.0, 1.0],
    ] as Box[]) {
      const [l, t, r, b] = zoomViewport(corner, 0.01);
      expect(l).toBeGreaterThanOrEqual(0);
      expect(t).toBeGreaterThanOrEqual(0);
      expect(r).toBeLessThanOrEqual(1);
      expect(b).toBeLessThanOrEqual(1);
    }
  });
});
