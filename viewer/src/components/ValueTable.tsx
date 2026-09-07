import type { Doc, ViewerValue } from "../types";

const GROUP_ORDER = ["document", "identity", "completion", "test"];

const STATUS_LABEL: Record<string, string> = {
  present: "",
  blank: "blank",
  illegible: "illegible",
  not_on_this_form: "not on this form",
  page_not_in_document: "page not in document",
};

function groupsOf(doc: Doc): Array<[string, ViewerValue[]]> {
  const groups = new Map<string, ViewerValue[]>();
  for (const value of doc.values) {
    const list = groups.get(value.group) ?? [];
    list.push(value);
    groups.set(value.group, list);
  }
  const names = [...groups.keys()].sort((a, b) => {
    const ia = GROUP_ORDER.indexOf(a);
    const ib = GROUP_ORDER.indexOf(b);
    if (ia !== -1 || ib !== -1)
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    return a < b ? -1 : 1;
  });
  return names.map((n) => [n, groups.get(n)!]);
}

export function ValueTable(props: {
  doc: Doc;
  selectedField: string | null;
  onSelect: (field: string | null) => void;
}) {
  return (
    <div className="values">
      {groupsOf(props.doc).map(([group, values]) => (
        <section key={group}>
          <h2>{group}</h2>
          <table>
            <tbody>
              {values.map((v) => (
                <tr
                  key={v.field}
                  className={
                    (v.region ? "locatable" : "") +
                    (v.field === props.selectedField ? " selected" : "")
                  }
                  onClick={() => v.region && props.onSelect(v.field)}
                >
                  <td className="field">
                    {v.field.replace(`${group}.`, "")}
                  </td>
                  <td className="raw">
                    {v.status === "present" ? (
                      <>
                        {v.raw}
                        {v.correction && (
                          <span className="correction">
                            {" "}
                            struck: {v.correction}
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="absent">{STATUS_LABEL[v.status]}</span>
                    )}
                  </td>
                  <td className="tags">
                    {v.region && (
                      <span className={`tag tag-${v.region.source}`}>
                        {v.region.source}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}
