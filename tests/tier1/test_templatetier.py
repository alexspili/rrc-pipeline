"""The template tier's pure rules: routing, preference, clipping, rows.

What must hold: stage-six geometry wins per field with stage five
underneath (the composite the 32-of-35 sitting graded); an unknown page
assigns only past the gate and margin; a clipped-away region abstains
rather than shipping a sliver; and the paper bounds find the sheet on a
dark surround.
"""

import pytest
from PIL import Image

from pipeline.render import sheet_bounds
from pipeline.template import IDENTITY, Registration, Template
from pipeline.templatetier import (ASSIGN_MARGIN, Artifact, clip,
                                   region_for, route)
from tests.tier1.test_registration_direction import make_page, make_template

IDENTITY_REG = Registration(transform=IDENTITY, matched=10,
                            residual_median=0.001, residual_p90=0.002)

BOUNDS = (0.05, 0.05, 0.95, 0.95)


def artifact(**overrides):
    base = dict(template=make_template(),
                fields={"identity.county": (0.1, 0.2, 0.3, 0.25)},
                blocks={"casing_strings": (0.1, 0.5, 0.9, 0.8)})
    base.update(overrides)
    return Artifact(**base)


def test_scalar_field_ships_as_template():
    box, source = region_for(artifact(), IDENTITY_REG, "identity.county",
                             {}, BOUNDS)
    assert source == "template"
    assert box == (0.1, 0.2, 0.3, 0.25)


def test_measured_rows_win_past_the_header():
    art = artifact(rows={"casing_strings": [(0.1, 0.50, 0.9, 0.55),
                                            (0.1, 0.55, 0.9, 0.60),
                                            (0.1, 0.60, 0.9, 0.65)]},
                   header_rows={"casing_strings": 1})
    box, source = region_for(art, IDENTITY_REG, "casing_strings[0].size",
                             {"casing_strings": 2}, BOUNDS)
    assert source == "template_row"
    assert box[1] == 0.55  # row after the detected header


def test_row_past_the_measured_grid_falls_back_to_the_band():
    art = artifact(rows={"casing_strings": [(0.1, 0.5, 0.9, 0.55)]},
                   header_rows={"casing_strings": 1})
    box, source = region_for(art, IDENTITY_REG, "casing_strings[0].size",
                             {"casing_strings": 2}, BOUNDS)
    assert source == "template_row"
    assert box[1] == pytest.approx(0.5)  # equal band over the block


def test_unknown_field_abstains():
    assert region_for(artifact(), IDENTITY_REG, "identity.lease_name",
                      {}, BOUNDS) is None


def test_region_clipped_to_paper_and_degenerate_clip_abstains():
    art = artifact(fields={"identity.county": (0.90, 0.2, 1.0, 0.25)})
    box, _ = region_for(art, IDENTITY_REG, "identity.county", {}, BOUNDS)
    assert box[2] == 0.95
    off_paper = artifact(fields={"identity.county": (0.96, 0.2, 1.0, 0.25)})
    assert region_for(off_paper, IDENTITY_REG, "identity.county",
                      {}, BOUNDS) is None


def test_clip_is_an_intersection():
    assert clip((0.0, 0.0, 0.5, 0.5), BOUNDS) == (0.05, 0.05, 0.5, 0.5)
    assert clip((0.0, 0.0, 0.04, 0.5), BOUNDS) is None


def test_known_revision_routes_to_its_own_template():
    template = make_template()
    artifacts = {("w2", "rev7566", "face"): Artifact(
        template=template, fields={}, blocks={})}
    words = make_page(template)
    key, reg = route(artifacts, "w2", "Rev. 7/5/66", words)
    assert key == ("w2", "rev7566", "face")
    assert reg.matched >= 8


def test_unknown_revision_needs_the_margin():
    """Two near-identical templates must NOT split an unknown page by a
    coin toss: within the margin the page abstains."""
    template = make_template()
    twin = Template(revision="twin", form_class="w2", page_role="face",
                    anchors=dict(template.anchors))
    artifacts = {("w2", "rev7566", "face"): Artifact(
                     template=template, fields={}, blocks={}),
                 ("w2", "twin", "face"): Artifact(
                     template=twin, fields={}, blocks={})}
    words = make_page(template)
    assert route(artifacts, "w2", None, words) is None
    only = {("w2", "rev7566", "face"): artifacts[("w2", "rev7566", "face")]}
    routed = route(only, "w2", None, words)
    assert routed is not None and routed[0][1] == "rev7566"
    assert ASSIGN_MARGIN == 2.0


def test_sheet_bounds_find_the_paper_on_a_dark_surround():
    img = Image.new("L", (100, 100), 0)
    img.paste(255, (10, 20, 90, 95))
    left, top, right, bottom = sheet_bounds(img)
    assert (left, top, right, bottom) == (0.1, 0.2, 0.9, 0.95)
    assert sheet_bounds(Image.new("L", (10, 10), 0)) == (0, 0, 1, 1)


def test_a_folded_variant_routes_to_its_committed_template():
    """The build folds sub-floor revisions into a template by registration
    (rev61278 pages register onto the rev63075 face at margin), but route()
    only matched exact revision keys, so a 1978 W-2 fell to the model band
    with a template that fits it sitting on disk. The fold table travels
    with the artifact and routing honors it; the registration gate still
    decides."""
    template = make_template()
    artifacts = {("w2", "rev63075", "face"): Artifact(
        template=template, fields={}, blocks={},
        folds={"rev61278": "rev63075"})}
    words = make_page(template)
    routed = route(artifacts, "w2", "Rev. 6/12/78", words)
    assert routed is not None
    assert routed[0] == ("w2", "rev63075", "face")
