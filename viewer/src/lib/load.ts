/** Fetch and validate the bundle. The invariants enforced here are the ones
 * pipeline/extract.py enforces when writing (its Value constructor): an
 * unknown status or source is refused, a present value must carry a region,
 * a non-present value must not, and a region must cite a page of its own
 * document. Enforced on the reading side too, so a hand-edited or stale
 * bundle fails loudly instead of rendering nonsense. */

import type {
  Bundle,
  Doc,
  Meta,
  Region,
  SearchRow,
  ViewerValue,
} from "../types";
import { SOURCES, STATUSES } from "../types";

export class BundleError extends Error {}

function fail(where: string, what: string): never {
  throw new BundleError(`${where}: ${what}`);
}

function checkRegion(where: string, region: Region, pages: number[]): void {
  if (!(SOURCES as readonly string[]).includes(region.source))
    fail(where, `unknown region source ${region.source}`);
  if (!pages.includes(region.page))
    fail(where, `region cites page ${region.page}, not in ${pages}`);
  const box = region.box;
  if (!Array.isArray(box) || box.length !== 4)
    fail(where, "box is not four numbers");
  const [l, t, r, b] = box;
  if ([l, t, r, b].some((v) => typeof v !== "number" || v < 0 || v > 1))
    fail(where, `box out of [0,1]: ${box}`);
  if (l >= r || t >= b) fail(where, `box has no area: ${box}`);
}

function checkValue(where: string, value: ViewerValue, pages: number[]): void {
  if (!(STATUSES as readonly string[]).includes(value.status))
    fail(where, `unknown status ${value.status}`);
  if (value.status === "present") {
    if (value.region === null)
      fail(where, "a present value must say where it was read from");
    if (value.raw === null)
      fail(where, "a present value must carry the text as written");
  } else if (value.region !== null) {
    fail(where, `a ${value.status} value has nothing to point at`);
  }
  if (value.region !== null) checkRegion(where, value.region, pages);
}

export function parseBundle(data: unknown): Bundle {
  const bundle = data as Bundle;
  if (!bundle || !Array.isArray(bundle.documents) || !bundle.pages)
    throw new BundleError("not a bundle: documents/pages missing");
  for (const doc of bundle.documents) {
    checkDoc(doc, bundle);
  }
  return bundle;
}

function checkDoc(doc: Doc, bundle: Bundle): void {
  if (!doc.pages.includes(doc.face))
    fail(doc.id, `face ${doc.face} not among pages ${doc.pages}`);
  for (const value of doc.values)
    checkValue(`${doc.id} ${value.field}`, value, doc.pages);
  for (const page of doc.pages) {
    const key = `${doc.record_id}-${doc.file_index}-${page}`;
    if (!bundle.pages[key]) fail(doc.id, `no page metadata for ${key}`);
  }
  for (const att of doc.attachments) {
    if (att.channel !== "identity" && att.channel !== "paper")
      fail(doc.id, `unknown attachment channel ${att.channel}`);
    if (att.channel === "identity" && att.fields.length === 0)
      fail(doc.id, "an identity attachment must name its agreeing fields");
  }
}

async function fetchJson(path: string): Promise<unknown> {
  const response = await fetch(path);
  if (!response.ok)
    throw new BundleError(`${path}: HTTP ${response.status}`);
  return response.json();
}

export interface Loaded {
  bundle: Bundle;
  meta: Meta;
  search: SearchRow[];
}

export async function loadAll(base = ""): Promise<Loaded> {
  const [bundleRaw, meta, search] = await Promise.all([
    fetchJson(`${base}/documents.json`),
    fetchJson(`${base}/meta.json`) as Promise<Meta>,
    fetchJson(`${base}/search.json`) as Promise<SearchRow[]>,
  ]);
  return { bundle: parseBundle(bundleRaw), meta, search };
}
