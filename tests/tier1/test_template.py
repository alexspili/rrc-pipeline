"""Tier 1 for pipeline.template: pure geometry, no I/O, no PDFs.

The plan these pin was approved before the module was written. The load
bearing ones are the abstentions: a template that guesses is worse than one
that declines, because a wrong box looks grounded (DEFECTS #29, and the
design rule that came out of it).
"""

import pytest

from pipeline import template as tpl
from pipeline.formlabels import LabelSpec


def word(x0, y0, x1, y1, text):
    return (x0, y0, x1, y1, text)


def anchor(token, x0, y0, x1=None, y1=None, pages=3):
    x1 = x0 + 0.05 if x1 is None else x1
    y1 = y0 + 0.01 if y1 is None else y1
    return tpl.Anchor(token, (x0, y0, x1, y1), pages, (0.001, 0.001))


# --------------------------------------------------------------------- fit

def test_fit_affine_recovers_a_known_transform():
    truth = tpl.Affine(1.02, 0.01, -0.03, -0.008, 0.99, 0.02)
    source = [(0.1, 0.1), (0.9, 0.15), (0.2, 0.8), (0.85, 0.9), (0.5, 0.5)]
    pairs = [(p, truth.apply(*p)) for p in source]
    got, residuals = tpl.fit_affine(pairs)
    assert got is not None
    for a, b in zip((got.a, got.b, got.c, got.d, got.e, got.f),
                    (truth.a, truth.b, truth.c, truth.d, truth.e, truth.f)):
        assert a == pytest.approx(b, abs=1e-9)
    assert max(residuals) == pytest.approx(0.0, abs=1e-9)


def test_fit_affine_refuses_too_few_and_collinear_points():
    assert tpl.fit_affine([((0.1, 0.1), (0.1, 0.1))])[0] is None
    collinear = [((t, t), (t, t)) for t in (0.1, 0.2, 0.3, 0.4)]
    assert tpl.fit_affine(collinear)[0] is None


# ------------------------------------------------------------- registration

def _template(tokens):
    return tpl.Template("rev7566", "w2", "face",
                        anchors={t: anchor(t, x, y) for t, x, y in tokens})


TEN = [(f"token{i}", 0.1 + 0.08 * (i % 5), 0.1 + 0.09 * (i // 5))
       for i in range(10)]


def test_register_abstains_below_the_anchor_floor():
    template = _template(TEN)
    words = [word(x, y, x + 0.05, y + 0.01, t)
             for t, x, y in TEN[:5]]
    assert tpl.register(template, words) is None


def test_register_abstains_when_the_residual_gate_fails():
    template = _template(TEN)
    words = [word(x, y, x + 0.05, y + 0.01, t) for t, x, y in TEN]
    assert tpl.register(template, words) is not None
    # One anchor torn off to the far corner: the fit is still solvable and
    # the median residual is what refuses it.
    broken = words[:-1] + [word(0.95, 0.95, 0.99, 0.96, TEN[-1][0])]
    registered = tpl.register(template, broken, max_residual=0.0005)
    assert registered is None


def test_register_reports_its_own_quality():
    template = _template(TEN)
    words = [word(x + 0.01, y, x + 0.06, y + 0.01, t) for t, x, y in TEN]
    got = tpl.register(template, words)
    assert got is not None and got.matched == 10
    assert got.residual_median <= 1e-9 and got.residual_p90 <= 1e-9


def test_a_repeated_token_is_not_an_anchor():
    words = [word(0.1, 0.1, 0.2, 0.11, "lease"),
             word(0.6, 0.4, 0.7, 0.41, "lease"),
             word(0.1, 0.3, 0.2, 0.31, "county")]
    assert set(tpl.unique_tokens(words)) == {"county"}


# ------------------------------------------------------------------ pooling

def _grid(offset_x=0.0, offset_y=0.0):
    """Nine tokens on a 3x3 grid, so the fit is determined rather than
    collinear. A page whose shared anchors all sit on one text line cannot
    be registered by an affine at all, which is what fit_affine refuses."""
    return [word(0.1 + 0.3 * (i % 3) + offset_x, 0.3 + 0.2 * (i // 3) + offset_y,
                 0.15 + 0.3 * (i % 3) + offset_x,
                 0.31 + 0.2 * (i // 3) + offset_y, f"token{i}")
            for i in range(9)]


def test_pooling_registers_pages_before_it_pools_them():
    """Three pages of the same form, each scanned at a different offset.
    The template's job is to hold one position for a token, not three."""
    pages = [_grid() + [word(0.10, 0.20, 0.16, 0.21, "lease")],
             _grid(0.02, 0.01) + [word(0.12, 0.21, 0.18, 0.22, "lease")],
             _grid(-0.03, 0.015) + [word(0.07, 0.215, 0.13, 0.225, "lease")]]
    anchors, used, rejected = tpl.build_anchors(pages)
    assert len(used) == 3 and not rejected
    assert anchors["lease"].box[0] == pytest.approx(0.10, abs=1e-6)
    assert anchors["lease"].spread[0] < 1e-6


def test_one_page_disagreeing_about_one_token_does_not_drag_it():
    """The median is here for this. Three pages agree that the lease box is
    at 0.10 and one says 0.40; the pooled position stays with the three."""
    pages = [_grid() + [word(0.10, 0.20, 0.16, 0.21, "lease")],
             _grid() + [word(0.101, 0.20, 0.161, 0.21, "lease")],
             _grid() + [word(0.102, 0.20, 0.162, 0.21, "lease")],
             _grid() + [word(0.40, 0.20, 0.46, 0.21, "lease")]]
    anchors, used, _ = tpl.build_anchors(pages)
    assert len(used) == 4
    assert anchors["lease"].box[0] == pytest.approx(0.101, abs=0.002)
    assert anchors["lease"].spread[0] > 0.2      # and it reports the fight


def test_a_token_on_one_page_only_never_pools():
    pages = [_grid() + [word(0.3, 0.2, 0.4, 0.21, "garbled")],
             _grid(), _grid()]
    anchors, _, _ = tpl.build_anchors(pages)
    assert "garbled" not in anchors
    assert "token0" in anchors


def test_a_page_that_will_not_register_is_rejected_rather_than_pooled():
    pages = [_grid(), _grid(0.01, 0.01),
             [word(0.9 - 0.1 * i, 0.05 + 0.11 * i, 0.95 - 0.1 * i,
                   0.06 + 0.11 * i, f"token{i}") for i in range(9)]]
    anchors, used, rejected = tpl.build_anchors(pages)
    assert rejected == [2]
    assert "token0" in anchors


# ------------------------------------------------------------------- labels

def test_a_label_matching_two_anchors_abstains():
    anchors = {"county": anchor("county", 0.1, 0.2),
               "counly": anchor("counly", 0.7, 0.8)}
    assert tpl.resolve_label(anchors, ("county",), set()) is None


def test_a_label_resolves_through_ocr_garbling():
    anchors = {"complet4on": anchor("complet4on", 0.30, 0.15)}
    assert tpl.resolve_label(anchors, ("completion",), set()) is not None


def test_banned_tokens_are_never_matched():
    anchors = {"completion": anchor("completion", 0.30, 0.15)}
    assert tpl.resolve_label(anchors, ("completion",), {"completion"}) is None


def test_two_agreeing_tokens_widen_the_label_and_two_distant_ones_abstain():
    near = {"location": anchor("location", 0.10, 0.27),
            "survey": anchor("survey", 0.22, 0.27)}
    box = tpl.resolve_label(near, ("location", "survey"), set())
    assert box is not None and box[0] == pytest.approx(0.10)
    far = {"location": anchor("location", 0.10, 0.27),
           "survey": anchor("survey", 0.80, 0.90)}
    assert tpl.resolve_label(far, ("location", "survey"), set()) is None


def test_shared_tokens_are_stripped_from_every_spec():
    specs = {"identity.lease_name": LabelSpec(("lease", "name")),
             "identity.operator_name": LabelSpec(("operator", "name"))}
    from pipeline.template import shared_label_tokens
    assert shared_label_tokens(specs) == {"name"}


# ------------------------------------------------------------------ regions

def test_the_region_is_the_cell_the_label_corners():
    """Rev. 7/5/66 prints the label in a cell's top-left corner and the value
    underneath it, so the region starts at the label's LEFT edge and runs
    down to the next printed line, not rightwards from the label's end."""
    anchors = {"lease": anchor("lease", 0.10, 0.200, 0.16, 0.210),
               "county": anchor("county", 0.50, 0.200, 0.56, 0.210),
               "next": anchor("next", 0.10, 0.260, 0.16, 0.270)}
    box = tpl.value_region(anchors, anchors["lease"].box, 0.010)
    assert box[0] == pytest.approx(0.10)      # the cell, not the label's end
    assert box[2] == pytest.approx(0.50)      # to the next label on the line
    assert box[1] == pytest.approx(0.200)
    assert box[3] == pytest.approx(0.260)     # down to the next printed line


def test_a_cell_with_nothing_under_it_still_gets_a_bounded_region():
    anchors = {"lease": anchor("lease", 0.10, 0.200, 0.16, 0.210)}
    box = tpl.value_region(anchors, anchors["lease"].box, 0.010)
    assert box is not None and box[3] > box[1]
    assert box[3] - box[1] <= tpl.MAX_REGION_HEIGHT + 1e-9


def test_a_region_is_capped_so_a_template_cannot_win_by_drawing_big():
    """The grading protocol was written against model boxes, which were
    small. Nothing in it stops a mechanism scoring `hit` with half a page."""
    anchors = {"lease": anchor("lease", 0.10, 0.200, 0.16, 0.210),
               "far": anchor("far", 0.95, 0.900, 0.98, 0.910)}
    box = tpl.value_region(anchors, anchors["lease"].box, 0.010)
    assert box[2] - box[0] == pytest.approx(tpl.MAX_REGION_WIDTH)
    assert box[3] - box[1] <= tpl.MAX_REGION_HEIGHT + 1e-9


def test_a_label_at_the_right_margin_yields_a_valid_box_not_an_exception():
    anchors = {"county": anchor("county", 0.955, 0.20, 0.999, 0.21)}
    box = tpl.value_region(anchors, anchors["county"].box, 0.012)
    assert box is None or (box[2] > box[0] and box[3] > box[1]
                           and box[2] <= 1.0)


def test_a_checkbox_field_spans_its_options():
    anchors = {"purpose": anchor("purpose", 0.10, 0.20, 0.18, 0.21),
               "initial": anchor("initial", 0.25, 0.20, 0.33, 0.21),
               "retest": anchor("retest", 0.40, 0.20, 0.47, 0.21)}
    box = tpl.value_region(anchors, anchors["purpose"].box, 0.012,
                           checkbox=True)
    assert box[0] == pytest.approx(0.10) and box[2] == pytest.approx(0.47)


def test_row_bands_split_a_block_evenly_and_refuse_a_bad_index():
    block = (0.1, 0.40, 0.9, 0.46)
    first = tpl.row_region(block, 0, 3)
    last = tpl.row_region(block, 2, 3)
    assert first[1] == pytest.approx(0.40) and first[3] == pytest.approx(0.42)
    assert last[1] == pytest.approx(0.44) and last[3] == pytest.approx(0.46)
    assert tpl.row_region(block, 3, 3) is None
    assert tpl.row_region(block, 0, 0) is None


def test_side_by_side_blocks_split_horizontally_not_to_zero_height():
    heads = {"tubing": (0.55, 0.530, 0.70, 0.540),
             "producing_intervals": (0.05, 0.530, 0.40, 0.540),
             "treatments": (0.05, 0.614, 0.30, 0.624)}
    regions = tpl.block_region({}, heads, 0.012)
    assert regions["producing_intervals"][2] == pytest.approx(0.55)
    assert regions["producing_intervals"][3] == pytest.approx(0.614)
    assert regions["tubing"][3] > regions["tubing"][1]


# ------------------------------------------------------------------ keying

def test_one_revision_is_one_template_however_it_is_spelled():
    assert tpl.revision_key("Rev. 4/1/83") == tpl.revision_key("Rev. 4/ 1/ 83")
    assert tpl.revision_key(None) == "unknown"
    assert tpl.revision_key("Rev. 7/5/66") != tpl.revision_key("Rev. 6/30/75")


def test_trimming_keeps_a_page_with_one_bad_anchor_and_records_it():
    good = [((0.1 + 0.3 * (i % 3), 0.3 + 0.2 * (i // 3)),
             (0.1 + 0.3 * (i % 3), 0.3 + 0.2 * (i // 3))) for i in range(9)]
    pairs = good + [((0.10, 0.20), (0.40, 0.20))]
    transform, residuals, kept, trimmed = tpl.robust_fit(pairs)
    assert trimmed == 1 and kept == 9
    assert max(residuals) < 1e-9


def test_trimming_cannot_rescue_a_page_below_the_anchor_floor():
    pairs = [((0.1 + 0.3 * (i % 3), 0.3 + 0.2 * (i // 3)),
              (0.1 + 0.3 * (i % 3), 0.3 + 0.2 * (i // 3))) for i in range(6)]
    pairs += [((0.10, 0.20), (0.40, 0.20)), ((0.20, 0.60), (0.80, 0.10))]
    _, _, kept, trimmed = tpl.robust_fit(pairs)
    assert trimmed == 0 and kept == 8


def test_two_ocr_spellings_of_one_word_in_one_place_are_one_label():
    """The pool holds both `lease` and `leasp` for the same printed word.
    That is one label read twice, not two candidate positions."""
    anchors = {"lease": anchor("lease", 0.48, 0.166, 0.53, 0.176),
               "leasp": anchor("leasp", 0.481, 0.167, 0.531, 0.177)}
    box = tpl.resolve_label(anchors, ("lease",), set())
    assert box is not None
    assert box[0] == pytest.approx(0.48)


def test_two_spellings_in_different_places_still_abstain():
    """`well` heads field 9 and `wells` sits in "Number of Producing Wells"
    much further down. Resolving that by proximity is the nearest-guess."""
    anchors = {"well": anchor("well", 0.38, 0.136, 0.42, 0.146),
               "wells": anchor("wells", 0.30, 0.520, 0.35, 0.530)}
    assert tpl.resolve_label(anchors, ("well",), set()) is None


def test_a_long_printed_phrase_resolves_along_its_line():
    """"6. LOCATION (Section, Block, and Survey)" spans 0.16 of the page."""
    anchors = {"location": anchor("location", 0.12, 0.278, 0.16, 0.288),
               "btock": anchor("btock", 0.22, 0.277, 0.25, 0.287),
               "survey": anchor("survey", 0.28, 0.278, 0.31, 0.288)}
    box = tpl.resolve_label(anchors, ("location", "block", "survey"), set())
    assert box is not None
    assert box[0] == pytest.approx(0.12) and box[2] == pytest.approx(0.31)


def test_the_same_token_on_two_lines_is_settled_by_the_rest_of_the_label():
    """`field` pools twice. The line that also carries `wildcat` is the one
    that is label 1; the other is a lone token and loses."""
    anchors = {"ffeld": anchor("ffeld", 0.12, 0.170, 0.16, 0.180),
               "wildcat": anchor("wildcat", 0.30, 0.170, 0.34, 0.180),
               "fied": anchor("fied", 0.25, 0.305, 0.28, 0.315)}
    box = tpl.resolve_label(anchors, ("field", "records", "wildcat"), set())
    assert box is not None and box[1] == pytest.approx(0.170)


def test_two_lines_carrying_one_token_each_abstain():
    anchors = {"operatar": anchor("operatar", 0.13, 0.250, 0.18, 0.260),
               "opertor": anchor("opertor", 0.20, 0.388, 0.25, 0.398)}
    assert tpl.resolve_label(anchors, ("operator",), set()) is None


def test_a_checkbox_label_may_run_down_the_page():
    anchors = {"purpose": anchor("purpose", 0.77, 0.224, 0.81, 0.232),
               "initial": anchor("initial", 0.76, 0.239, 0.80, 0.247),
               "retest": anchor("retest", 0.77, 0.266, 0.80, 0.274),
               "recloss": anchor("recloss", 0.77, 0.293, 0.81, 0.301)}
    flat = tpl.resolve_label(
        anchors, ("purpose", "initial", "retest", "reclass"), set())
    assert flat is None                       # no two share a printed line
    column = tpl.resolve_label(
        anchors, ("purpose", "initial", "retest", "reclass"), set(),
        checkbox=True)
    assert column is not None
    assert column[1] == pytest.approx(0.224) and column[3] == pytest.approx(0.301)


def test_a_one_anchor_checkbox_label_is_not_a_tie_with_itself():
    """Clustered as a line and as a column it is the same single group."""
    anchors = {"type": anchor("type", 0.14, 0.111, 0.17, 0.119)}
    box = tpl.resolve_label(anchors, ("type", "deepening"), set(),
                            checkbox=True)
    assert box is not None and box[0] == pytest.approx(0.14)
