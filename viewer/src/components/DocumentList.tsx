import type { Doc, SearchRow } from "../types";
import { findingCounts } from "../lib/disagree";

export function DocumentList(props: {
  rows: SearchRow[];
  docs: Map<string, Doc>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <ul className="doc-list">
      {props.rows.map((row) => {
        const doc = props.docs.get(row.id);
        if (!doc) return null;
        const counts = findingCounts(doc.findings);
        return (
          <li
            key={row.id}
            className={row.id === props.selectedId ? "selected" : ""}
            onClick={() => props.onSelect(row.id)}
          >
            <div className="doc-title">
              <span className="doc-id">{row.id}</span>
              <span className="doc-form">
                {doc.form_class}
                {doc.form_revision ? ` · ${doc.form_revision}` : ""}
              </span>
            </div>
            <div className="doc-sub">
              {row.operator_name ?? "operator unread"}
              {row.lease_name ? ` · ${row.lease_name}` : ""}
            </div>
            <div className="doc-badges">
              <span className="badge">
                {doc.pages.length} page{doc.pages.length > 1 ? "s" : ""}
              </span>
              {doc.attachments.map((a) => (
                <span key={a.page} className={`badge badge-${a.channel}`}>
                  p{a.page} by {a.channel}
                </span>
              ))}
              {counts.errors > 0 && (
                <span className="badge badge-error">
                  {counts.errors} error{counts.errors > 1 ? "s" : ""}
                </span>
              )}
              {counts.warnings > 0 && (
                <span className="badge badge-warning">
                  {counts.warnings} warning{counts.warnings > 1 ? "s" : ""}
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
