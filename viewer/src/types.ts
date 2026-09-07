/** Mirrors pipeline/extract.py. The vocabularies are pinned against the
 * Python source by tests/tier2/test_viewer_types.py, so the two schemas
 * cannot drift silently. */

export const STATUSES = [
  "present", "blank", "illegible", "not_on_this_form", "page_not_in_document",
] as const;
export type Status = (typeof STATUSES)[number];

export const SOURCES = [
  "text_layer", "template", "template_row", "model", "page",
] as const;
export type RegionSource = (typeof SOURCES)[number];

/** [left, top, right, bottom], fractions of the page. */
export type Box = readonly [number, number, number, number];

export interface Region {
  page: number;
  box: Box;
  source: RegionSource;
}

export interface ViewerValue {
  field: string;
  group: string;
  status: Status;
  value: string | null;
  raw: string | null;
  found_in: string | null;
  correction: string | null;
  region: Region | null;
}

export interface Attachment {
  page: number;
  channel: "identity" | "paper";
  fields: string[];
}

export interface Finding {
  rule: string;
  severity: "error" | "warning";
  message: string;
  fields: string[];
}

export interface Doc {
  id: string;
  record_id: string;
  file_index: number;
  face: number;
  pages: number[];
  form_class: string;
  form_revision: string | null;
  attachments: Attachment[];
  values: ViewerValue[];
  findings: Finding[];
}

export interface PageMeta {
  width: number;
  height: number;
  line_height: number | null;
}

export interface Bundle {
  documents: Doc[];
  pages: Record<string, PageMeta>;
}

export interface Meta {
  exported: string;
  prompt_hash: string;
  documents: number;
  unparsed: number;
  pages: number;
  regions_by_source: Record<string, number>;
  snap_joined: boolean;
  findings_joined: boolean;
  caveats: string[];
}

export interface SearchRow {
  id: string;
  record_id: string;
  form_class: string;
  form_revision: string | null;
  operator_name: string | null;
  lease_name: string | null;
  well_number: string | null;
  field_name: string | null;
  county: string | null;
  api_number: string | null;
}

export const pageKey = (doc: Doc, page: number): string =>
  `${doc.record_id}-${doc.file_index}-${page}`;
