"""Tier 2: the identity reader's prompt says what each field means.

Origin: DEFECTS #40. The prompt listed six bare field names and defined none
of them. Shown a Section II printing "Commenced" and "Completed", and asked
for a "completion date", the model read the Completed date, which is a
different field. That is a reasonable reading of an unreasonable instruction,
and it made reassembly's date veto fire on a value that should never have
been there.

The definitions already existed in docs/labeling-protocol-extract.md. This
test exists because the failure was not inventing them, it was writing a new
reader without carrying across a schema the repo had already written down.
"""

from __future__ import annotations

from pipeline import identity
from pipeline import reassemble as ra


def test_the_prompt_defines_every_field_it_asks_for():
    """Every field name is followed by the printed label it means."""
    prompt = identity.SYSTEM
    for field in identity.FIELDS:
        assert field in prompt, field
        after = prompt.split(field, 1)[1][:400]
        assert "Printed as" in after or "labelled" in after or "printed" in after, (
            f"{field} is asked for but never defined by its printed label")


def test_the_prompt_rules_out_the_field_that_was_actually_confused():
    """Record 1495193 page 8: 8/30/79 is the "Completed" half of the drilling
    operations field, not field 14. The prompt now says so by name."""
    prompt = identity.SYSTEM
    assert "Commenced" in prompt and "Completed" in prompt
    assert "not_on_this_form" in prompt.split("completion_date", 1)[1][:900]
    for other in ("Date of Test", "Date Permit Issued"):
        assert other in prompt, f"{other} is not ruled out"


def test_the_prompt_and_reassembly_still_agree_on_the_field_list():
    assert set(identity.FIELDS) == set(ra.IDENTITY_FIELDS) | set(ra.BONUS_FIELDS)


def test_changing_the_prompt_changed_its_hash():
    """CLAUDE.md rule 7: the prompt is half the cache key, so a definition
    change invalidates the cache by construction rather than by anybody
    remembering to clear it."""
    from pipeline import pageclass as pc
    assert identity.PROMPT_HASH == pc.prompt_hash(identity.SYSTEM)
    assert identity.PROMPT_HASH != pc.prompt_hash("")
