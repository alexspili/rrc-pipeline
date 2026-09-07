import { describe, expect, it } from "vitest";
import { BundleError, parseBundle } from "../load";

const value = {
  field: "identity.lease_name",
  group: "identity",
  status: "present",
  value: "EXAMPLE",
  raw: "EXAMPLE",
  found_in: "18. Lease Name",
  correction: null,
  region: { page: 9, box: [0.1, 0.2, 0.4, 0.25], source: "model" },
};

const doc = {
  id: "r-0-9",
  record_id: "r",
  file_index: 0,
  face: 9,
  pages: [9],
  form_class: "g1",
  form_revision: null,
  attachments: [],
  values: [value],
  findings: [],
};

const bundle = () =>
  JSON.parse(
    JSON.stringify({ documents: [doc], pages: { "r-0-9": { width: 1, height: 1, line_height: null } } }),
  );

describe("parseBundle enforces the writer's invariants on the reader", () => {
  it("accepts a well-formed bundle", () => {
    expect(parseBundle(bundle()).documents).toHaveLength(1);
  });
  it("refuses an unknown status", () => {
    const b = bundle();
    b.documents[0].values[0].status = "maybe";
    expect(() => parseBundle(b)).toThrow(BundleError);
  });
  it("refuses an unknown region source", () => {
    const b = bundle();
    b.documents[0].values[0].region.source = "guessed";
    expect(() => parseBundle(b)).toThrow(BundleError);
  });
  it("refuses a present value with no region", () => {
    const b = bundle();
    b.documents[0].values[0].region = null;
    expect(() => parseBundle(b)).toThrow(/must say where/);
  });
  it("refuses a region on a blank value", () => {
    const b = bundle();
    b.documents[0].values[0].status = "blank";
    expect(() => parseBundle(b)).toThrow(/nothing to point at/);
  });
  it("refuses a region citing a page the document does not have", () => {
    const b = bundle();
    b.documents[0].values[0].region.page = 4;
    expect(() => parseBundle(b)).toThrow(/page 4/);
  });
  it("refuses an identity attachment with no agreeing fields", () => {
    const b = bundle();
    b.documents[0].attachments = [
      { page: 10, channel: "identity", fields: [] },
    ];
    b.documents[0].pages = [9, 10];
    b.pages["r-0-10"] = { width: 1, height: 1, line_height: null };
    expect(() => parseBundle(b)).toThrow(/agreeing fields/);
  });
});
