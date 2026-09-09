import type { Box, Doc, PageMeta, Region, ViewerValue } from "../types";
import { pageKey } from "../types";
import { bandBox, toPixels, zoomViewport } from "../lib/geometry";
import { pageUrl } from "../lib/paths";

/** Rendered width of a page column, px. A display choice. */
const PAGE_WIDTH = 760;
const ZOOM_WIDTH = 720;

function displayBox(region: Region, lineHeight: number | null): Box {
  // R5: only the model tier is a band, widened upward against the measured
  // downward drift. A snapped box is the matched line run and is shown as
  // it is; widening it would blur the one tier that is actually grounded.
  return region.source === "model"
    ? bandBox(region.box, lineHeight)
    : region.box;
}

function ZoomCard(props: {
  value: ViewerValue;
  doc: Doc;
  pages: Record<string, PageMeta>;
}) {
  const region = props.value.region;
  if (!region) return null;
  const key = pageKey(props.doc, region.page);
  const meta = props.pages[key];
  if (!meta) return null;

  const box = displayBox(region, meta.line_height);
  const [l, t, r, b] = zoomViewport(box, meta.line_height);
  const imgWidth = ZOOM_WIDTH / (r - l);
  const imgHeight = (imgWidth * meta.height) / meta.width;
  const cardHeight = (b - t) * imgHeight;
  const rect = toPixels(box, imgWidth, imgHeight);

  return (
    <figure className="zoom-card">
      <div
        className="zoom-window"
        style={{ width: ZOOM_WIDTH, height: cardHeight }}
      >
        <img
          src={pageUrl(key)}
          alt={key}
          style={{
            width: imgWidth,
            height: imgHeight,
            left: -l * imgWidth,
            top: -t * imgHeight,
          }}
        />
        <div
          className={`overlay overlay-${region.source}`}
          style={{
            left: rect.left - l * imgWidth,
            top: rect.top - t * imgHeight,
            width: rect.width,
            height: rect.height,
          }}
        />
      </div>
      <figcaption>
        {props.value.found_in ?? props.value.field}
        <span className={`tag tag-${region.source}`}>{region.source}</span>
      </figcaption>
    </figure>
  );
}

export function PagePane(props: {
  doc: Doc;
  pages: Record<string, PageMeta>;
  selectedField: string | null;
  onSelectField: (field: string | null) => void;
}) {
  const { doc } = props;
  const selected =
    doc.values.find((v) => v.field === props.selectedField) ?? null;

  return (
    <div className="pages">
      {selected && (
        <ZoomCard value={selected} doc={doc} pages={props.pages} />
      )}
      {doc.pages.map((page) => {
        const key = pageKey(doc, page);
        const meta = props.pages[key];
        if (!meta) return null;
        const height = (PAGE_WIDTH * meta.height) / meta.width;
        return (
          <div
            key={key}
            className="page"
            style={{ width: PAGE_WIDTH, height }}
          >
            <img src={pageUrl(key)} alt={key} width={PAGE_WIDTH} />
            {doc.values
              .filter((v) => v.region && v.region.page === page)
              .map((v) => {
                const region = v.region!;
                const rect = toPixels(
                  displayBox(region, meta.line_height),
                  PAGE_WIDTH,
                  height,
                );
                return (
                  <div
                    key={v.field}
                    title={`${v.field} (${region.source})`}
                    className={
                      `overlay overlay-${region.source}` +
                      (v.field === props.selectedField ? " selected" : "")
                    }
                    style={rect}
                    onClick={() => props.onSelectField(v.field)}
                  />
                );
              })}
            <span className="page-label">
              p{page}
              {page === doc.face ? " · face" : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}
