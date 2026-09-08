#!/usr/bin/env python3
"""The template tier at runtime: committed geometry onto a live page.

Wires the stage-five and stage-six passes (docs/modules/extract.md, "The
reopening and the two passes") into the shipped stack: snap where the
text layer matched, then this tier where the page registers and geometry
is asserted, then the model band, then the page. Stage-six measured
geometry is preferred per field and per table; stage-five rule geometry
stands underneath it, which is exactly the composite the 32-of-35
sitting graded.

Runtime inputs are the page's own embedded-layer words and the committed
artifacts under pipeline/templates/. No aliases (unadopted), no model
calls, no AWS: build time stays build time.

Routing: a page whose document carries a model-read revision registers
against that revision's roles and the lower residual wins. A page with
no revision is assigned by residual across every artifact, gated at
MAX_RESIDUAL with the 2x margin the assignment report measured, and
anything else abstains to the tiers below. Regions are clipped to the
page's own paper bounds, because geometry lives in image fractions and
the paper does not fill the image; a region the clip degenerates is an
abstention, never a sliver.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from pathlib import Path

from pipeline import template as tpl
from pipeline.textlayer import Word

TEMPLATES = Path(__file__).resolve().parent / "templates"

#: Assignment margin for unknown-revision pages: next-best residual must
#: be at least this multiple of the best. The measured gap on rev7566
#: was 8x; 2x is the conservative bound the assignment report used.
ASSIGN_MARGIN = 2.0

Key3 = tuple[str, str, str]


@dataclass
class Artifact:
    """One committed template: registration frame plus tiered geometry."""

    template: tpl.Template
    fields: dict[str, tuple[float, float, float, float]]
    blocks: dict[str, tuple[float, float, float, float]]
    rows: dict[str, list[tuple[float, float, float, float]]] = \
        dc_field(default_factory=dict)
    header_rows: dict[str, int] = dc_field(default_factory=dict)
    #: variant revision keys the build folded into this template by
    #: registration (a 1978 W-2 is the 1975 layout reprinted); routing
    #: honors them so a variant page reaches the template that fits it
    folds: dict[str, str] = dc_field(default_factory=dict)


def load_artifacts(directory: Path = TEMPLATES) -> dict[Key3, Artifact]:
    """Stage-five artifacts with stage-six geometry overlaid per field."""
    out: dict[Key3, Artifact] = {}
    for path in sorted(directory.glob("*.json")):
        if path.stem.endswith("_forms"):
            continue
        raw = json.loads(path.read_text())
        anchors = {t: tpl.Anchor(t, tuple(v["box"]), v["pages"],
                                 tuple(v["spread"]))
                   for t, v in raw["anchors"].items()}
        template = tpl.Template(
            revision=raw["revision"], form_class=raw["form_class"],
            page_role=raw["page_role"], anchors=anchors,
            line_height=raw["line_height"])
        artifact = Artifact(
            template=template,
            fields={n: tuple(b) for n, b in raw["fields"].items()},
            blocks={n: tuple(b) for n, b in raw["blocks"].items()},
            folds={variant: raw["revision"]
                   for variant in raw.get("folds", {})})
        forms = path.with_name(path.stem + "_forms.json")
        if forms.exists():
            overlay = json.loads(forms.read_text())
            artifact.fields.update(
                {n: tuple(b) for n, b in overlay["fields"].items()})
            artifact.rows = {n: [tuple(b) for b in rows]
                            for n, rows in overlay["blocks_rows"].items()}
            artifact.header_rows = dict(overlay["header_rows"])
        out[(raw["form_class"], raw["revision"], raw["page_role"])] = \
            artifact
    return out


def route(artifacts: dict[Key3, Artifact], form_class: str,
          revision: str | None, words: list[Word]):
    """(key, Registration) for this page, or None.

    Known revision: that revision's roles compete on residual alone,
    because the roles are structurally different layouts. Unknown
    revision: assignment by residual across everything, gate and margin
    as measured, abstaining beats guessing.
    """
    revision = tpl.revision_key(revision)
    # a variant that folded into more than one template (rev7866 reached
    # both Section II fuels) is not routed by pick-first: every folded
    # target competes and the residual decides
    targets = {artifact.folds[revision]
               for artifact in artifacts.values()
               if revision in artifact.folds} or {revision}
    if revision != "unknown":
        candidates = [(key, artifact) for key, artifact in artifacts.items()
                      if key[0] == form_class and key[1] in targets]
        fits = []
        for key, artifact in candidates:
            reg = tpl.register(artifact.template, words)
            if reg is not None:
                fits.append((reg.residual_median, key, reg))
        if not fits:
            return None
        fits.sort(key=lambda f: f[0])
        return fits[0][1], fits[0][2]
    fits = []
    for key, artifact in artifacts.items():
        reg = tpl.register(artifact.template, words)
        if reg is not None:
            fits.append((reg.residual_median, key, reg))
    if not fits:
        return None
    fits.sort(key=lambda f: f[0])
    if fits[0][0] > tpl.MAX_RESIDUAL:
        return None
    if len(fits) > 1 and fits[1][0] < ASSIGN_MARGIN * fits[0][0]:
        return None
    return fits[0][1], fits[0][2]


def clip(box, bounds):
    """The region inside the paper, or None when nothing usable is."""
    left = max(box[0], bounds[0])
    top = max(box[1], bounds[1])
    right = min(box[2], bounds[2])
    bottom = min(box[3], bounds[3])
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def region_for(artifact: Artifact, registration: tpl.Registration,
               field: str, table_rows: dict[str, int], bounds):
    """(page-space box, source) for one field, or None.

    Scalar fields come from the field table, stage-six cells already
    overlaid. Table fields take the measured rows past the detected
    headers where they pool, else the equal-band rule on the stage-five
    block. Everything maps frame to page through the inverse (DEFECTS
    #79) and is clipped to the paper.
    """
    frame_box, source = None, None
    if field in artifact.fields:
        frame_box, source = artifact.fields[field], "template"
    elif "[" in field:
        table = field.split("[")[0]
        index = int(field.split("[")[1].split("]")[0])
        if table in artifact.rows:
            position = artifact.header_rows.get(table, 0) + index
            if position < len(artifact.rows[table]):
                frame_box = artifact.rows[table][position]
                source = "template_row"
        if frame_box is None and table in artifact.blocks:
            count = max(1, table_rows.get(table, 1))
            band = tpl.row_region(artifact.blocks[table],
                                  index, max(index + 1, count))
            if band is not None:
                frame_box, source = band, "template_row"
    if frame_box is None:
        return None
    clipped = clip(registration.page_box(frame_box), bounds)
    if clipped is None:
        return None
    return clipped, source
