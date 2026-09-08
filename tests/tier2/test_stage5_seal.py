"""No stage-five template is built from a record its rule can grade.

DEFECTS #78: the escape document's pages entered the rev63075 fuel through
the ordinary labeled-revision path, and record 1495195's other filings sat
in the rev7566 fuel besides. A template scored against a page whose word
positions it pooled would not look like an error; this pin is what makes
the seal survive refactors.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "pipeline" / "templates"

#: The two records the stage-five decision rule can grade: the primary
#: document and the elected escape's.
SEALED = ("1493608", "1495195")


def test_no_committed_template_is_built_from_a_sealed_record():
    paths = sorted(TEMPLATES.glob("*.json"))
    assert paths, "no stage-five templates committed"
    for path in paths:
        raw = json.loads(path.read_text())
        for page_id in raw.get("built_from", []):
            record = page_id.split("-")[0]
            assert record not in SEALED, (
                f"{path.name} is built from {page_id}, a page of sealed "
                f"record {record} (DEFECTS #78)")
