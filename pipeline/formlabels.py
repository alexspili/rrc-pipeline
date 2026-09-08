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
    # Stage five, written 2026-09-08 from the Textract line dumps of each
    # template's seed page, before any stage-five sitting. The 1983 W-2
    # face runs its Section I test block, which holds date_of_test, down
    # to the REMARKS band at 0.56; the G-1's date_of_test sits at 0.37
    # with Section II pressure calculations (v2, no specs) below.
    ("w2", "rev4183", "face"): (0.08, 0.60),
    ("w2", "rev4183", "sec_ii"): (0.02, 0.95),
    ("g1", "rev4183", "face"): (0.08, 0.40),
    ("w2", "rev63075", "face"): (0.06, 0.47),
    ("w2", "rev63075", "sec_ii"): (0.04, 0.95),
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
    # The 1983 W-2 masthead is the 1966 one reworded; IMPORTANT opens the
    # Section I instruction line.
    ("w2", "rev4183", "face"): (
        "railroad", "commission", "texas", "division", "potential",
        "completion", "recompletion", "report", "section", "test",
        "important", "hours", "unless", "otherwise", "specified", "rules"),
    ("w2", "rev4183", "sec_ii"): (
        "section", "data", "completion", "well"),
    # "Gas Well Back Pressure Test, Completion or Recompletion Report, and
    # Log", then "Section I GAS MEASUREMENT DATA" and "Section II FIELD
    # DATA AND PRESSURE CALCULATIONS". `field` is NOT a decoy despite the
    # Section II heading: it is field_name's own token, and the heading's
    # copy is handled by per-page uniqueness rather than by a ban that
    # would silence the field everywhere.
    ("g1", "rev4183", "face"): (
        "railroad", "commission", "texas", "division", "pressure",
        "completion", "recompletion", "report", "section", "measurement",
        "data", "test", "calculations"),
    ("w2", "rev63075", "face"): (
        "railroad", "commission", "texas", "division", "potential",
        "completion", "recompletion", "report", "section", "test",
        "hours", "unless", "otherwise", "specified", "rules", "note"),
    ("w2", "rev63075", "sec_ii"): (
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

    # ------------------------------------------------------------------
    # Stage five, written 2026-09-08 from the Textract line dumps of the
    # seed pages, before any stage-five sitting. Same discipline as
    # above: no invented tokens, so a label printed only in words under
    # four characters or words the page repeats gets no spec and the
    # field abstains. On the 1983 face those are well_number ("9. Well
    # No."), rrc_well_id ("8. RRC Lease No.", colliding with LEASE NAME)
    # and api_number ("API No."); on the 1983 G-1, well_number and
    # rrc_well_id ("8. RRC Gas ID No."); on the 1983 Section II,
    # date_permit_issued ("25. Permit to Drill, Plug Back or Deepen"
    # prints no unique word: permit appears five times), top_of_pay and
    # plug_back_depth.
    # ------------------------------------------------------------------
    ("w2", "rev4183", "face"): {
        "identity.field_name": LabelSpec(("field", "records", "wildcat")),
        "identity.lease_name": LabelSpec(("lease",)),
        # "3. OPERATOR'S NAME (Exactly as shown on Form P-5, Organization
        # Report)". `operators` rather than `operator`, because the page
        # also prints "RRC Operator No." and "name former operator".
        "identity.operator_name": LabelSpec(("operators", "organization")),
        "identity.operator_address": LabelSpec(("address",)),
        "identity.county": LabelSpec(("county",)),
        "identity.rrc_district": LabelSpec(("district",)),
        "identity.location_survey": LabelSpec(("location", "block",
                                               "survey")),
        "identity.distance_to_town": LabelSpec(("distance", "direction",
                                                "nearest", "town")),
        "identity.purpose_of_filing": LabelSpec(
            ("purpose", "initial", "retest", "reclass"), checkbox=True),
        "identity.completion_date": LabelSpec(("date",)),
        "identity.logs_run": LabelSpec(("electric",)),
        "test.date_of_test": LabelSpec(("date",)),
    },
    ("w2", "rev4183", "sec_ii"): {
        "completion.type_of_completion": LabelSpec(
            ("type", "deepening"), checkbox=True),
        "completion.drilling_commenced": LabelSpec(("commenced",)),
        "completion.drilling_completed": LabelSpec(("completed",)),
        "completion.total_depth": LabelSpec(("total",)),
        "completion.elevation": LabelSpec(("elevation",)),
        "completion.directional_survey": LabelSpec(
            ("directional", "made"), checkbox=True),
        "completion.drilling_contractor": LabelSpec(("contractor",)),
    },
    ("g1", "rev4183", "face"): {
        "identity.field_name": LabelSpec(("field", "records", "wildcat")),
        "identity.lease_name": LabelSpec(("lease",)),
        "identity.operator_name": LabelSpec(("operators", "organization")),
        "identity.operator_address": LabelSpec(("address",)),
        "identity.county": LabelSpec(("county",)),
        "identity.rrc_district": LabelSpec(("district",)),
        "identity.location_survey": LabelSpec(("location", "block",
                                               "survey")),
        "identity.distance_to_town": LabelSpec(("distance", "direction",
                                                "nearest", "town")),
        "identity.purpose_of_filing": LabelSpec(
            ("purpose", "initial", "retest", "reclass"), checkbox=True),
        "identity.pipeline_connection": LabelSpec(("pipe", "connection")),
        "identity.completion_date": LabelSpec(("date",)),
        "identity.logs_run": LabelSpec(("electric",)),
        "test.date_of_test": LabelSpec(("date",)),
    },
    ("w2", "rev63075", "face"): {
        "identity.field_name": LabelSpec(("field", "records", "wildcat")),
        "identity.lease_name": LabelSpec(("lease",)),
        "identity.operator_name": LabelSpec(("operator",)),
        "identity.operator_address": LabelSpec(("address",)),
        "identity.county": LabelSpec(("county",)),
        "identity.rrc_district": LabelSpec(("district",)),
        "identity.location_survey": LabelSpec(("location", "block",
                                               "survey")),
        "identity.well_number": LabelSpec(("well", "number")),
        "identity.purpose_of_filing": LabelSpec(
            ("purpose", "initial", "retest", "reclass"), checkbox=True),
        "identity.completion_date": LabelSpec(("date",)),
        "identity.logs_run": LabelSpec(("electric",)),
        "test.date_of_test": LabelSpec(("date",)),
    },
    ("w2", "rev63075", "sec_ii"): {
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
    # Both later W-2 reverses print the same table headings the 1966 one
    # does; the fuzzy match covers 1983's singular "perforation".
    ("w2", "rev4183", "sec_ii"): {
        "casing_strings": ("casingrecord", "casing"),
        "liner_strings": ("liner",),
        "tubing": ("tubingrecord", "tubing"),
        "producing_intervals": ("perforations",),
        "treatments": ("fracture", "squeeze"),
    },
    ("w2", "rev63075", "sec_ii"): {
        "casing_strings": ("casingrecord", "casing"),
        "liner_strings": ("liner",),
        "tubing": ("tubingrecord", "tubing"),
        "producing_intervals": ("perforations",),
        "treatments": ("fracture", "squeeze"),
    },
}
