import { describe, expect, it } from "vitest";
import { matches, tokenScore, tokenize } from "../search";

const rows = [
  { id: "a", operator_name: "HUMBLE OIL & REFINING", county: "Chambers" },
  { id: "b", operator_name: "Exxon", county: "Wharton" },
  { id: "c", operator_name: "HUMBLE PIPE LINE", county: "Liberty" },
];

describe("tokenize", () => {
  it("casefolds and splits on non-alphanumerics", () => {
    expect(tokenize("Humble  OIL&refining")).toEqual([
      "humble",
      "oil",
      "refining",
    ]);
  });
});

describe("tokenScore", () => {
  it("prefers a whole-word match over a substring", () => {
    expect(tokenScore(rows[0]!, "oil")).toBe(2);
    expect(tokenScore(rows[0]!, "hum")).toBe(1);
    expect(tokenScore(rows[1]!, "oil")).toBe(0);
  });
});

describe("matches", () => {
  it("requires every token to land somewhere in the row", () => {
    expect(matches(rows, "humble wharton").map((r) => r.id)).toEqual([]);
    expect(matches(rows, "humble liberty").map((r) => r.id)).toEqual(["c"]);
  });
  it("ranks whole-word rows above substring rows", () => {
    expect(matches(rows, "humble oil").map((r) => r.id)).toEqual(["a"]);
  });
  it("returns everything for an empty query", () => {
    expect(matches(rows, "  ")).toHaveLength(3);
  });
});
