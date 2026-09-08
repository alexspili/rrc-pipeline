/** Display names for field paths.
 *
 * The section header already says the group, so the row label should
 * not repeat it: `identity.county` reads as `county`, and
 * `casing_strings[0].hole_size` as `hole_size`. The row index is not
 * noise, though: two casing strings both print a `hole_size`, so the
 * table view separates rows with a small `row N` label instead of
 * repeating `casing_strings[1].` on every line.
 */

/** The bare field name, group prefix and row index stripped. */
export function fieldLabel(field: string): string {
  const dot = field.lastIndexOf(".");
  return dot === -1 ? field : field.slice(dot + 1);
}

/** The row index of a table field, or null for a scalar. */
export function rowIndex(field: string): number | null {
  const match = field.match(/\[(\d+)\]/);
  return match ? Number(match[1]) : null;
}
