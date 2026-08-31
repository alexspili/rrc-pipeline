#!/usr/bin/env python3
"""Which stage-2 stratum a census row belongs to.

Pure. The whole point of stage 2 is that the strata are decided by the census
and the OCR header scan before the draw, so this function is separated from
everything that touches disk and pinned by tier-1 tests.

The design and the reasoning behind each stratum are in
docs/labeling-protocol-stage2.md. This module is the executable half.
"""

from __future__ import annotations

from pipeline import pageclass as pc

#: A completion face whose printed form number did not survive imaging. The
#: contested half of the sample: no independent signal, and the near-identical
#: G-1 and W-2 layouts are all the model has to go on.
G1_FACE_SILENT = "A_g1_face_ocr_silent"
G1_FACE_CORROBORATED = "B_g1_face_ocr_g1"
W2_FACE_SILENT = "C_w2_face_ocr_silent"

#: Predicted a W-2 face while the page's own header reads W-15. Seven pages,
#: drawn whole. Alex hit this confusion twice by hand while verifying the
#: census, on records 1995379 and 2396691.
W2_FACE_W15_HEADER = "D_w2_face_ocr_w15"
W2_FACE_CORROBORATED = "E_w2_face_ocr_w2"

#: Predicted part of a completion report but not its face: Section II, Section
#: III, a continuation, a printed back. None of these carries a form number,
#: and G-1 and W-2 share a layout, so the census attributed them by guess.
COMPLETION_NON_FACE = "F_completion_non_face"

#: Not predicted as a completion report, but the classes a completion face
#: would plausibly be mistaken for. The only recall instrument in the design,
#: and thin enough that it supports a bound rather than an estimate.
CONFUSABLE = "G_confusable_not_completion"

OVERSIZE = "H_oversize"
PARSE_FAILURE = "I_parse_failure"

#: Pages sampled per stratum. From the protocol, fixed before the draw.
ALLOCATION = {
    G1_FACE_SILENT: 22,
    G1_FACE_CORROBORATED: 8,
    W2_FACE_SILENT: 25,
    W2_FACE_W15_HEADER: 7,
    W2_FACE_CORROBORATED: 8,
    COMPLETION_NON_FACE: 15,
    CONFUSABLE: 20,
    OVERSIZE: 23,
    PARSE_FAILURE: 15,
}

#: Strata that carry a prediction and are scored for accuracy. H has one too,
#: but it measures R1 rather than the completion split; I has none at all.
SCORED = (G1_FACE_SILENT, G1_FACE_CORROBORATED, W2_FACE_SILENT,
          W2_FACE_W15_HEADER, W2_FACE_CORROBORATED, COMPLETION_NON_FACE,
          CONFUSABLE)

#: Classes a completion face could be confused with, either direction.
#:
#: `l1` is here for a specific reason: the L-1 face prints "with Forms W-2,
#: G-1, and GT-1" in its own instructions, which is how DEFECTS #15 and #16
#: were found. If any page in this corpus invites the confusion, it is that one.
CONFUSABLE_CLASSES = frozenset({
    pc.PageClass.W15, pc.PageClass.G5, pc.PageClass.L1,
    pc.PageClass.WS1_SW1, pc.PageClass.OTHER_FORM,
})


def assign_stratum(form_class: str | None,
                   part: str | None,
                   oversize: bool,
                   parse_failed: bool,
                   header_tokens: frozenset[str] | set[str]) -> str | None:
    """The stratum for one census row, or None if it is outside the frame.

    Precedence is fixed here rather than left to the order of a chain of ifs,
    because the strata have to stay disjoint no matter what a future census
    run produces. A parse failure has no prediction to stratify on, and an
    oversize page is claimed by H even if it is also a predicted G-1 face:
    today no oversize page is one, and a tier-2 test says so, but the
    disjointness must not depend on that staying true.
    """
    if parse_failed:
        return PARSE_FAILURE
    if oversize:
        return OVERSIZE

    tokens = {t.upper() for t in header_tokens}
    is_face = part == pc.Part.FACE.value

    if form_class == pc.PageClass.G1.value:
        if not is_face:
            return COMPLETION_NON_FACE
        return G1_FACE_CORROBORATED if "G-1" in tokens else G1_FACE_SILENT

    if form_class == pc.PageClass.W2.value:
        if not is_face:
            return COMPLETION_NON_FACE
        if "W-2" in tokens:
            return W2_FACE_CORROBORATED
        if "W-15" in tokens:
            return W2_FACE_W15_HEADER
        return W2_FACE_SILENT

    if form_class in {c.value for c in CONFUSABLE_CLASSES}:
        if is_face:
            return CONFUSABLE
        # A form page that names no form could be a completion section. A
        # printed reverse could not be a completion *face*, which is what G
        # exists to look for, and predicted-completion backs are already in F.
        if (form_class == pc.PageClass.OTHER_FORM.value
                and part != pc.Part.BACK_INSTRUCTIONS.value):
            return CONFUSABLE
    return None
