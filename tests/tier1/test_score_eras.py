"""The era table's buckets are revisions, not spellings.

Origin: DEFECTS #81. The ground truth carries `Rev. 4/1/83` on three
documents and `Rev. 4/ 1/ 83` on a fourth, because that is how the paper
was keyed, and the scorer bucketed on the raw string. One revision came
out as two rows of the README's era table.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts import score_extract as se      # noqa: E402
from pipeline import template as tpl         # noqa: E402


def row(revision: str) -> dict:
    return {"revision": revision, "status_ok": True, "want_status": "present",
            "got_status": "present", "equivalent": True}


def test_one_revision_is_one_era_however_it_is_spelled():
    rows = [row("Rev. 4/1/83"), row("Rev. 4/ 1/ 83"), row("Rev. 7/5/66")]
    buckets = dict(se.era_buckets(rows))
    assert len(buckets) == 2
    assert sum(len(g) for g in buckets.values()) == len(rows)
    assert sorted(len(g) for g in buckets.values()) == [1, 2]


def test_the_bucket_key_is_the_pipeline_s_own_revision_key():
    rows = [row("Rev. 4/1/83"), row("Rev. 4/ 1/ 83")]
    (_, group), = se.era_buckets(rows)
    assert len(group) == 2
    assert tpl.revision_key("Rev. 4/1/83") == tpl.revision_key("Rev. 4/ 1/ 83")


def test_a_missing_revision_still_buckets_as_unknown():
    (label, group), = se.era_buckets([row(""), row("")])
    assert label == "unknown" and len(group) == 2
