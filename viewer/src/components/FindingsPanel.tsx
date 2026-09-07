import type { Finding } from "../types";
import { orderFindings } from "../lib/disagree";

export function FindingsPanel(props: { findings: Finding[] }) {
  if (props.findings.length === 0)
    return <div className="findings clean">no findings</div>;
  return (
    <div className="findings">
      <h2>findings</h2>
      <ul>
        {orderFindings(props.findings).map((f, i) => (
          <li key={`${f.rule}-${i}`} className={`finding-${f.severity}`}>
            <span className={`tag tag-${f.severity}`}>{f.severity}</span>
            <span className="rule">{f.rule}</span>
            <p>{f.message}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
