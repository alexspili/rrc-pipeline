#!/usr/bin/env python3
"""Read the few identity fields a non-face page carries, and nothing else.

Reassembly settles which pages belong together by agreement on the fields
both pages carry, so it needs those fields read off pages the full extractor
never looks at: sections, continuations, and `other_form` pages that are
plainly a form with no readable number.

**Not the v1 extractor with fields switched off.** Six fields, its own
prompt, its own much smaller output. Cost on this pipeline is 85% output
(docs/modules/extract.md), so a six-field answer is a different price from a
twenty-seven-field one, and the two runs have different cache keys because
they have different prompts.

It serves two cut-order steps and is built once: reassembly needs it to score
a candidate page, and the cross-form disagreement detector needs the same
read on non-completion forms.

**No coordinates are asked for.** The job here is matching, not provenance,
and a value's region is honestly page-level: we know which page it is on and
nothing finer. That is exactly what the `page` source tag in
`pipeline.extract.SOURCES` means, so the existing `Value` type is reused
rather than a second one invented with its own vocabulary (DEFECTS #22).
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline import pageclass as pc
from pipeline import render
from pipeline.extract import Region, Status, Value, _json_object

MODEL = "claude-sonnet-5"
MAX_TOKENS = 2_000
IMAGE_CAP = 1568

#: The five fields reassembly compares, plus the one it uses as
#: corroboration. Kept in step with pipeline.reassemble by a tier-1 test.
FIELDS = ("operator_name", "lease_name", "well_number", "completion_date",
          "rrc_district", "total_depth")

SYSTEM = """You are reading one page of a Texas Railroad Commission well
record. It is often a section, a continuation, or the back of a completion
report, so it may carry no identity block at all.

Return ONLY these six fields, as JSON. Each field names a PRINTED BOX on the
form. Read the printed label, not the position, and do not substitute a
neighbouring field that looks similar.

  operator_name   The operator's name. Printed as "OPERATOR", or "OPERATOR'S
                  NAME (Exactly as shown on Form P-5)". On a Section II it may
                  instead be "Notice of Intention to Drill this Well was filed
                  in Name of", which is the same operator and counts.

  lease_name      Printed as "LEASE NAME", or "Lease". Not the field name and
                  not the well number.

  well_number     Printed as "Well No." or "Well Number".

  completion_date The box labelled "Completion Date", or "Completion or
                  recompletion date". This is field 14 and it is on the FACE
                  of the form.
                  It is NOT the pair of boxes labelled "Commenced" and
                  "Completed" under "Date Plug Back, Deepening, Work Over or
                  Drilling Operations". Those are drilling dates and they are
                  a different field. If the only dates on this page are that
                  Commenced/Completed pair, then completion_date is
                  not_on_this_form.
                  It is also NOT "Date of Test", "Date Permit Issued", or a
                  signature date.

  rrc_district    Printed as "RRC District" or "District No.".

  total_depth     Printed as "Total Depth". Not "P.B. Depth" and not "Top of
                  Pay".

Each is an object: {"status": ..., "raw": ...}.

status is one of:
  present              something is written there and you can read it
  blank                the field is printed on this page and is empty
  illegible            something is written and you cannot make it out
  not_on_this_form     this page does not print this field at all

raw is exactly what is written, as written, or null when status is not
present. Do not normalise dates, strip foot marks, or expand abbreviations.

Do NOT return coordinates. Do not guess, and do not reach for the nearest
similar box: a field whose printed label is not on this page is
not_on_this_form, and a field you cannot read is illegible. Neither is
blank."""

PROMPT_HASH = pc.prompt_hash(SYSTEM)


def build_content(pdf: Path, page: int, cap: int = IMAGE_CAP) -> list[dict]:
    data, _ = render.render_page_png(pdf, page, cap=cap)
    import base64
    return [{"type": "image", "source": {
        "type": "base64", "media_type": "image/png",
        "data": base64.standard_b64encode(data).decode()}},
        {"type": "text", "text": "Read the six fields from this page."}]


def parse(body: str, page: int) -> dict[str, Value]:
    """Model output to Values. A present value gets a page-level region.

    Page-level is the truth here rather than a placeholder: no coordinates
    were asked for, so the honest claim is the page, and the `page` source
    tag exists to say exactly that.
    """
    payload = _json_object(body)
    out = {}
    for field in FIELDS:
        entry = payload.get(field) or {}
        status = Status(str(entry.get("status", "not_on_this_form")).strip())
        raw = entry.get("raw")
        if status is Status.PRESENT and not raw:
            status = Status.ILLEGIBLE
        if status is not Status.PRESENT:
            # DEFECTS #38. The model returns its `raw` field whatever the
            # status says, and a value that is not present carries no text.
            # pipeline/extract.py has done this since it was written; the
            # rule was not carried across when this reader was added.
            raw = None
        region = (Region(page=page, box=(0.0, 0.0, 1.0, 1.0), source="page")
                  if status is Status.PRESENT else None)
        out[field] = Value(status=status, value=raw, raw=raw, region=region)
    return out


def identity_for(values: dict[str, Value]) -> dict[str, str | None]:
    """The plain dict pipeline.reassemble compares."""
    return {name: (value.raw if value.status is Status.PRESENT else None)
            for name, value in values.items()}
