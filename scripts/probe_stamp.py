#!/usr/bin/env python3
"""Can the model read the district office's received-date stamp?

Four pages, about three cents, run before the $0.91 field change that would
depend on it. Alex read these stamps by eye during the verification sitting,
so there is ground truth: 1912687 page 2 is stamped Aug 18 2009 and page 6
June 9 2009, and 1510666 pages 1 and 3 carry different stamps from each other.

The stamp is not in the scan's own text layer. Checked across eight pages that
carry one: every "received"-like token is printed form text, and exactly one
fragment got through, `JUN` on 1912687 page 6. The OCR was done on horizontal
form text and the stamps are rotated, so reading them ourselves would mean
adding an OCR engine this repo does not have.

If the model cannot read them, `received_stamp` is dropped before it costs a
re-run and `purpose_of_filing` carries the distinction on its own.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import identity                      # noqa: E402
from pipeline import render                        # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"
PRICE_IN, PRICE_OUT = 2.0, 10.0

#: What Alex read off the paper. The probe is scored against these.
TRUTH = [("1912687", 0, 2, "Aug 18 2009"),
         ("1912687", 0, 6, "June 9 2009"),
         ("1510666", 1, 1, "(unread; must differ from page 3)"),
         ("1510666", 1, 3, "(unread; must differ from page 1)")]

SYSTEM = """You are looking at one page of a scanned Texas Railroad Commission
well record.

Somewhere on the page there may be a RECEIVED stamp from a district office. It
is a rubber stamp, not a printed form field. It is often rotated, sometimes by
45 degrees or more, and it usually sits across a signature block or a margin
rather than inside a box. It normally reads RECEIVED, a district or office
name, and a date.

Return only JSON:

  {"received_stamp": {"status": ..., "raw": ..., "note": ...}}

status is present when you can read a date in such a stamp, illegible when a
stamp is there and you cannot read it, and not_on_this_form when there is no
stamp.

raw is the date exactly as stamped, or null. note says where on the page you
found it and at what rotation, or why you could not.

Do not guess, and do not report a printed form date such as a completion date
or a signature date as a stamp."""


def main() -> None:
    records = {json.loads(l)["record_id"]: json.loads(l)
               for l in MANIFEST.open() if l.strip()}
    import anthropic
    client = anthropic.Anthropic()
    total_in = total_out = 0
    for record_id, file_index, page, truth in TRUTH:
        pdf = RAW / record_id / records[record_id]["files"][file_index]["name"]
        response = client.messages.create(
            model=identity.MODEL, max_tokens=1_000, system=SYSTEM,
            messages=[{"role": "user",
                       "content": identity.build_content(pdf, page)}])
        usage = response.usage
        total_in += usage.input_tokens
        total_out += usage.output_tokens
        body = "".join(b.text for b in response.content if b.type == "text")
        print(f"\n{record_id}-{file_index} p{page}   Alex read: {truth}")
        print(f"  {body.strip()[:400]}")
    cost = (total_in * PRICE_IN + total_out * PRICE_OUT) / 1e6
    print(f"\n  {total_in:,} in, {total_out:,} out, ${cost:.4f} for four pages")


if __name__ == "__main__":
    main()
