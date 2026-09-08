import { describe, expect, it } from "vitest";

import { fieldLabel, rowIndex } from "../fields";

describe("fieldLabel", () => {
  it("strips the group from a scalar", () => {
    expect(fieldLabel("identity.county")).toBe("county");
  });

  it("strips the table and row index from a cell", () => {
    expect(fieldLabel("casing_strings[0].hole_size")).toBe("hole_size");
    expect(fieldLabel("formation_tops[12].formation")).toBe("formation");
  });

  it("leaves an unprefixed name alone", () => {
    expect(fieldLabel("form_revision")).toBe("form_revision");
  });
});

describe("rowIndex", () => {
  it("reads the row of a table cell", () => {
    expect(rowIndex("casing_strings[1].hole_size")).toBe(1);
  });

  it("is null for a scalar", () => {
    expect(rowIndex("identity.county")).toBeNull();
  });
});
