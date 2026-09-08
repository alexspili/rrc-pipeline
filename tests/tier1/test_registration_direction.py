"""DEFECTS #79: a frame-space region must reach the page through the
transform's inverse.

The synthetic page here is the template frame scaled by 1.1 and shifted:
far enough from identity that the forward transform puts a drawn region
two scale-errors from the field, which is exactly how the defect showed
on real paper (a = 0.9394, displacement 0.13).
"""

from pipeline.template import Anchor, Template, register


def scaled(box, scale=1.1, shift=0.02):
    return tuple(v * scale + shift for v in box)


def make_template():
    anchors = {}
    positions = [(0.1, 0.1), (0.5, 0.1), (0.1, 0.5), (0.5, 0.5),
                 (0.3, 0.3), (0.7, 0.2), (0.2, 0.7), (0.6, 0.6)]
    for index, (x, y) in enumerate(positions):
        token = f"anchortoken{index}"
        anchors[token] = Anchor(token, (x, y, x + 0.05, y + 0.01), 3,
                                (0.001, 0.001))
    return Template(revision="test", form_class="w2", page_role="face",
                    anchors=anchors)


def make_page(template):
    return [(*scaled(anchor.box), token)
            for token, anchor in template.anchors.items()]


def test_page_box_lands_on_the_scaled_page():
    template = make_template()
    registration = register(template, make_page(template))
    assert registration is not None
    frame_region = (0.2, 0.2, 0.4, 0.25)
    on_page = registration.page_box(frame_region)
    expected = scaled(frame_region)
    assert all(abs(on_page[i] - expected[i]) < 0.005 for i in range(4)), (
        f"{on_page} should sit at {expected}; the forward transform "
        "would put it near "
        f"{tuple((v - 0.02) / 1.1 for v in frame_region)}")


def test_forward_transform_is_measurably_the_wrong_direction():
    """The regression the defect describes: forward-mapped regions sit
    two scale-errors from the truth on a non-identity registration."""
    template = make_template()
    registration = register(template, make_page(template))
    frame_region = (0.2, 0.2, 0.4, 0.25)
    forward = registration.transform.box(frame_region)
    expected = scaled(frame_region)
    assert max(abs(forward[i] - expected[i]) for i in range(4)) > 0.03
