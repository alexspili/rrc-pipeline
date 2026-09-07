/** Pure geometry: fractions to pixels, the R5 band, the zoom viewport.
 * Every constant here is a display rule and says where it came from. */

import type { Box } from "../types";

/** Fallback line height when a page has no text layer. The measured median
 * on the graded page was 0.0073 of page height (docs/modules/extract.md,
 * "the shipped experience"); pages without a layer get that number rather
 * than a guess of a different order. */
export const FALLBACK_LINE = 0.0073;

/** R5: the measured drift of a model box is DOWNWARD by one to two field
 * rows, so its band widens upward by two rows, against the bias, never
 * symmetrically (docs/modules/extract.md R5, DEFECTS #29). */
export const BAND_ROWS = 2;

/** The zoom rule of 2026-09-03: a region is shown zoomed to readable scale,
 * tight enough that one field row is a large fraction of the viewport.
 * Eight rows of height makes a row an eighth of the view; the minimum width
 * keeps enough context to read the printed label. Display choices, named. */
export const VIEW_ROWS = 8;
export const MIN_VIEW_WIDTH = 0.35;

const clamp01 = (v: number): number => Math.min(1, Math.max(0, v));

export function lineHeightOf(measured: number | null): number {
  return measured ?? FALLBACK_LINE;
}

/** The model box as the band the viewer draws: top edge lifted by
 * BAND_ROWS line heights, other edges untouched. */
export function bandBox(box: Box, lineHeight: number | null): Box {
  const lh = lineHeightOf(lineHeight);
  const [left, top, right, bottom] = box;
  return [left, clamp01(top - BAND_ROWS * lh), right, bottom];
}

export interface PixelRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export function toPixels(box: Box, width: number, height: number): PixelRect {
  const [l, t, r, b] = box;
  return {
    left: l * width,
    top: t * height,
    width: (r - l) * width,
    height: (b - t) * height,
  };
}

/** The viewport that shows one region at readable scale, clamped to the
 * page. Centred on the region; at least VIEW_ROWS line heights tall and
 * MIN_VIEW_WIDTH wide; never smaller than the region itself. */
export function zoomViewport(box: Box, lineHeight: number | null): Box {
  const lh = lineHeightOf(lineHeight);
  const [l, t, r, b] = box;
  const height = Math.max(VIEW_ROWS * lh, b - t + 2 * lh);
  const width = Math.max(MIN_VIEW_WIDTH, r - l + 4 * lh);
  const cx = (l + r) / 2;
  const cy = (t + b) / 2;
  let left = cx - width / 2;
  let top = cy - height / 2;
  left = Math.min(Math.max(left, 0), Math.max(0, 1 - width));
  top = Math.min(Math.max(top, 0), Math.max(0, 1 - height));
  return [left, top, Math.min(1, left + width), Math.min(1, top + height)];
}
