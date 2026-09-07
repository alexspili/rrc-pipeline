/** Findings ordering and counting. Pure. */

import type { Finding } from "../types";

/** Errors before warnings, then by rule name, stable within a group. */
export function orderFindings(findings: Finding[]): Finding[] {
  return [...findings].sort((a, b) => {
    if (a.severity !== b.severity) return a.severity === "error" ? -1 : 1;
    return a.rule < b.rule ? -1 : a.rule > b.rule ? 1 : 0;
  });
}

export function findingCounts(findings: Finding[]): {
  errors: number;
  warnings: number;
} {
  let errors = 0;
  let warnings = 0;
  for (const f of findings) {
    if (f.severity === "error") errors += 1;
    else warnings += 1;
  }
  return { errors, warnings };
}
