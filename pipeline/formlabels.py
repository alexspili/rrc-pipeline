#!/usr/bin/env python3
"""Printed field labels, per form revision. Data, not logic.

Every entry here is the label **printed on the paper**, taken from the field
table in docs/labeling-protocol-extract.md, which was written on 2026-08-31
before any box was drawn and is not derived from any model output. Tokens are
normalised the way pipeline.textlayer normalises words.

Only Rev. 7/5/66 of the W-2 is filled in. That is the revision the probe
tests and the worst-measured era bucket. The other eleven or so templates are
not written until a number says the mechanism is worth having.

Three things this file deliberately does not do.

**It does not invent tokens the OCR cannot produce.** A label whose tokens
are all shorter than four characters, "35. Top of Pay" or "37. P.B. Depth",
gets no spec and the field abstains. Padding a spec with a guess to raise
coverage is the nearest-guess the design rules forbid, wearing a hat.

**It lists the form's own title and headings as DECOYS.** Those are printed
text that looks exactly like a field label to a fuzzy matcher and sits
nowhere near a value. "COMPLETION OR RECOMPLETION REPORT AND LOG" is the
page's masthead, and without this it would capture `identity.completion_date`
and park it under the title. Decoys are short and each one is a heading
actually observed in the fuel pages' text layer, not a guess at what might
collide. Repeated words need no decoy: a token appearing twice on a page is
not unique, so it never becomes an anchor in the first place.

**It bounds where a field label can be.** Every field on the 1966 face is
above the instructions and affidavit, which fill the bottom half with prose
that no field's value is anywhere near. BODY is that bound, and it does the
work a fifty-word decoy list would otherwise have to do badly.
"""

from __future__ import annotations

from dataclasses import dataclass

Key = tuple[str, str, str]          # form class, revision key, page role


@dataclass(frozen=True)
class LabelSpec:
    tokens: tuple[str, ...]
    checkbox: bool = False


#: Where on the page a field label may be found, as page fractions.
BODY: dict[Key, tuple[float, float]] = {
    ("w2", "rev7566", "face"): (0.04, 0.47),
    ("w2", "rev7566", "sec_ii"): (0.04, 0.95),
}

#: Printed headings, banned from field-label matching. Not banned from block
#: matching: a table's heading is exactly what finds the table.
DECOYS: dict[Key, tuple[str, ...]] = {
    # "RAILROAD COMMISSION OF TEXAS / OIL AND GAS DIVISION", "OIL WELL
    # POTENTIAL TEST", "COMPLETION OR RECOMPLETION REPORT AND LOG",
    # "SECTION I POTENTIAL TEST DATA", and the NOTE line under it.
    ("w2", "rev7566", "face"): (
        "railroad", "commission", "texas", "division", "potential",
        "completion", "recompletion", "report", "section", "test",
        "hours", "unless", "otherwise", "specified", "rules", "note"),
    # "SECTION II DATA ON WELL COMPLETION AND LOG".
    ("w2", "rev7566", "sec_ii"): (
        "section", "data", "completion", "well"),
}

#: field name -> the printed label beside its value.
LABELS: dict[Key, dict[str, LabelSpec]] = {
    ("w2", "rev7566", "face"): {
        "identity.field_name": LabelSpec(("field", "records", "wildcat")),
        "identity.lease_name": LabelSpec(("lease",)),
        "identity.operator_name": LabelSpec(("operator",)),
        "identity.operator_address": LabelSpec(("address",)),
        "identity.county": LabelSpec(("county",)),
        "identity.rrc_district": LabelSpec(("district",)),
        "identity.location_survey": LabelSpec(("location", "block",
                                               "survey")),
        "identity.well_number": LabelSpec(("well", "number")),
        # "Workover" is a G-1 option and is NOT one of this form's: on
        # Rev. 7/5/66 the word prints at field 12, "If Workover give former
        # Field", a third of a page away from the purpose checkboxes.
        "identity.purpose_of_filing": LabelSpec(
            ("purpose", "initial", "retest", "reclass"), checkbox=True),
        "identity.completion_date": LabelSpec(("date",)),
        "identity.logs_run": LabelSpec(("electric",)),
        "test.date_of_test": LabelSpec(("date",)),
    },
    ("w2", "rev7566", "sec_ii"): {
        "completion.type_of_completion": LabelSpec(
            ("type", "deepening"), checkbox=True),
        "completion.date_permit_issued": LabelSpec(("issued",)),
        "completion.drilling_commenced": LabelSpec(("commenced",)),
        "completion.drilling_completed": LabelSpec(("completed",)),
        "completion.total_depth": LabelSpec(("total",)),
        "completion.elevation": LabelSpec(("elevation",)),
        "completion.directional_survey": LabelSpec(
            ("directional", "made"), checkbox=True),
        "completion.drilling_contractor": LabelSpec(("contractor",)),
    },
}

#: Table headings, for the "template region plus row k of n" tier. The one
#: declared guess in the design; reported separately so it cannot inflate
#: the headline.
BLOCKS: dict[Key, dict[str, tuple[str, ...]]] = {
    ("w2", "rev7566", "sec_ii"): {
        "casing_strings": ("casingrecord", "casing"),
        "liner_strings": ("liner",),
        "tubing": ("tubingrecord", "tubing"),
        "producing_intervals": ("perforations",),
        "treatments": ("fracture", "squeeze"),
    },
}
