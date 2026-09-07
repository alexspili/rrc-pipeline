import { describe, expect, it } from "vitest";
import { findingCounts, orderFindings } from "../disagree";
import type { Finding } from "../../types";

const findings: Finding[] = [
  { rule: "dates.order", severity: "warning", message: "w", fields: [] },
  { rule: "api.county_prefix", severity: "error", message: "e", fields: [] },
  { rule: "depths.order", severity: "warning", message: "w", fields: [] },
];

describe("orderFindings", () => {
  it("puts errors first, then rules alphabetically", () => {
    expect(orderFindings(findings).map((f) => f.rule)).toEqual([
      "api.county_prefix",
      "dates.order",
      "depths.order",
    ]);
  });
  it("does not mutate its input", () => {
    orderFindings(findings);
    expect(findings[0]!.rule).toBe("dates.order");
  });
});

describe("findingCounts", () => {
  it("counts by severity", () => {
    expect(findingCounts(findings)).toEqual({ errors: 1, warnings: 2 });
  });
});
