import { useEffect, useMemo, useState } from "react";
import { DocumentList } from "./components/DocumentList";
import { FindingsPanel } from "./components/FindingsPanel";
import { PagePane } from "./components/PagePane";
import { ValueTable } from "./components/ValueTable";
import type { Loaded } from "./lib/load";
import { loadAll } from "./lib/load";
import { SITE_BASE } from "./lib/paths";
import { matches } from "./lib/search";
import type { Doc } from "./types";

export function App() {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedField, setSelectedField] = useState<string | null>(null);

  useEffect(() => {
    loadAll(SITE_BASE)
      .then(setLoaded)
      .catch((e: unknown) => setError(String(e)));
  }, []);

  const docs = useMemo(() => {
    const byId = new Map<string, Doc>();
    for (const doc of loaded?.bundle.documents ?? []) byId.set(doc.id, doc);
    return byId;
  }, [loaded]);

  const shown = useMemo(
    () => matches(loaded?.search ?? [], query),
    [loaded, query],
  );

  const selected = selectedId ? (docs.get(selectedId) ?? null) : null;

  if (error)
    return (
      <div className="error">
        <h1>No bundle</h1>
        <p>{error}</p>
        <p>
          The viewer reads data/viewer/, which scripts/export_viewer.py
          writes from a finished extraction run. That directory is never
          committed: the pages carry personal information.
        </p>
      </div>
    );
  if (!loaded) return <div className="loading">loading…</div>;

  return (
    <div className="app">
      <header>
        <h1>RRC completion reports</h1>
        <span className="meta">
          {loaded.meta.documents} documents · {loaded.meta.pages} pages ·
          prompt {loaded.meta.prompt_hash}
        </span>
        <details className="caveats">
          <summary>what the highlights can and cannot claim</summary>
          <ul>
            {loaded.meta.caveats.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </details>
      </header>
      <div className="columns">
        <aside className="list-pane">
          <input
            type="search"
            placeholder="operator, lease, county, API…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <DocumentList
            rows={shown}
            docs={docs}
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id);
              setSelectedField(null);
            }}
          />
        </aside>
        <main className="page-pane">
          {selected ? (
            <PagePane
              doc={selected}
              pages={loaded.bundle.pages}
              selectedField={selectedField}
              onSelectField={setSelectedField}
            />
          ) : (
            <p className="hint">pick a document</p>
          )}
        </main>
        <aside className="value-pane">
          {selected && (
            <>
              <ValueTable
                doc={selected}
                selectedField={selectedField}
                onSelect={setSelectedField}
              />
              <FindingsPanel findings={selected.findings} />
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
