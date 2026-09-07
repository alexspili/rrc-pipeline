/** Client-side search over the identity fields. Pure. */

export function tokenize(query: string): string[] {
  return query
    .toLowerCase()
    .split(/[^0-9a-z]+/)
    .filter((t) => t.length > 0);
}

/** Score one row against one token: 2 for a whole-word match, 1 for a
 * substring, 0 for a miss. A token that misses every field disqualifies
 * the row: every word the user typed has to land somewhere. */
export function tokenScore(row: object, token: string): number {
  let best = 0;
  for (const value of Object.values(row)) {
    if (value === null || value === undefined) continue;
    if (typeof value !== "string" && typeof value !== "number") continue;
    const text = String(value).toLowerCase();
    if (!text.includes(token)) continue;
    const whole = text
      .split(/[^0-9a-z]+/)
      .some((word) => word === token);
    best = Math.max(best, whole ? 2 : 1);
    if (best === 2) break;
  }
  return best;
}

export function matches<T extends object>(rows: T[], query: string): T[] {
  const tokens = tokenize(query);
  if (tokens.length === 0) return rows;
  const scored: Array<[number, T]> = [];
  for (const row of rows) {
    let total = 0;
    let miss = false;
    for (const token of tokens) {
      const s = tokenScore(row, token);
      if (s === 0) {
        miss = true;
        break;
      }
      total += s;
    }
    if (!miss) scored.push([total, row]);
  }
  scored.sort((a, b) => b[0] - a[0]);
  return scored.map(([, row]) => row);
}
