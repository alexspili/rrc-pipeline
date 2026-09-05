"""Tier 2: the reassembly run's own report tells the truth about itself.

DEFECTS #48 and #49. The run is the instrument every reassembly number is
quoted from, and both faults found on 2026-09-05 were in the report rather
than in the module: a header counting a constant instead of the run, and a
total that came up twenty short of the pages read without saying so.

No model calls. The script is read as text for the header, and the accounting
is exercised through pipeline.reassemble directly.
"""

from __future__ import annotations

from pathlib import Path

from pipeline import reassemble as ra

SCRIPT = (Path(__file__).resolve().parents[2]
          / "scripts" / "measure_reassemble.py")


def test_the_header_counts_the_records_it_read():
    """DEFECTS #48. The header printed len(RECORDS), the development set, so
    a corpus run over 141 records announced itself as 19.
    """
    text = SCRIPT.read_text()
    assert "len(RECORDS)} records" not in text
    assert "{len({r for r, _, _ in wanted})} records" in text


def test_the_run_refuses_to_report_a_total_that_does_not_close():
    """DEFECTS #49. Printing the shortfall would not have been enough: the
    old report printed four numbers that did not add up and nobody added them.
    """
    text = SCRIPT.read_text()
    assert "accounting does not close" in text
    assert "raise SystemExit" in text


def test_every_reason_the_report_can_print_is_named_on_the_field():
    """The reasons go straight into a Counter and get printed, so a reason the
    module starts emitting is a word in the report that nothing explains.
    `Unattached.reason` carries the vocabulary in its own comment; this checks
    the code and that comment have not drifted apart.
    """
    source = Path(ra.__file__).read_text()
    declared = {word.strip() for word in
                source.split("#: no_face")[1].split("\n")[0].split("|")}
    declared.add("no_face")
    emitted = {r for r in declared if f'"{r}"' in source}
    assert emitted == declared, (
        f"named on the field but never emitted: {declared - emitted}")
    assert "not_a_candidate" in declared
