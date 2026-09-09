#!/usr/bin/env python3
"""Fetch well-record documents from the RRC imaged-records system (Neubus).

Verified call chain (2026-08-28 recon; the chain is documented in
HANDOFF.md, and the raw captures were never committed, a claim dropped
deliberately on 2026-09-09 rather than backfilled with reconstructions):

  1. token   -- 24h public bearer JWT. Paste into NEUBUS_TOKEN daily (see
                mint_token() for the automation TODO).
  2. search  -- POST https://rrcsearch3.neubus.com/getSearchImages
                -> records with metadata + ephemeral doc_id blob.
  3. files   -- POST https://rrcsearch3.neubus.com/getTabFilesOauth
                -> per-file nuid + name/size/page_count, paginated.
  4. bytes   -- GET  https://rrcsearch3fs.neubus.com/api/v1/single/{nuid}?profileId=17
                -> the PDF. Bearer + User-Agent required; UA is enforced.

Facts the design leans on (all observed, none guessed):
  * doc_id blobs and nuids are ephemeral / re-encrypted per response.
    The durable key is the numeric record id (image_fields.id).
    Resolve search -> files -> download within one run; cache by record id.
  * Server declares x-ratelimit-limit: 60/min. We run well under it and
    back off when x-ratelimit-remaining gets low.
  * All dates in metadata are IMAGING time, not filing time.
  * strict:"true" is exact-match on text fields, and is the ONLY value ever
    observed from a working client. We default to it; see DEFECTS #3 and
    the comment at search() for what "false" actually does.
  * profile_type distinguishes POTENTIAL (well files) from WELL LOG etc.
    Server-side filtering on it is unverified, so we filter client-side.

Usage:
  export NEUBUS_TOKEN="eyJ..."          # from DevTools, any request's bearer
  python3 fetch.py --district 03 --from 08/01/2008 --to 09/01/2009 \
      --max-records 50
  python3 fetch.py --district 03 --from 01/01/2007 --to 01/01/2008 \
      --search lease_name=Ducroz --all-types --dry-run

Output:
  data/raw/<record_id>/<original_filename>.pdf
  data/manifest.jsonl   (one line per record: metadata + files as resolved)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import requests

APP = "https://rrcsearch3.neubus.com"
FS = "https://rrcsearch3fs.neubus.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")  # enforced by proxy

DATA = Path("data")
RAW = DATA / "raw"
MANIFEST = DATA / "manifest.jsonl"

BASE_SLEEP = 2.5          # seconds between calls; ~24/min against a 60/min limit
LOW_WATER = 5             # back off when x-ratelimit-remaining drops below this


# --------------------------------------------------------------------------- token

def load_token() -> str:
    tok = os.environ.get("NEUBUS_TOKEN", "").strip()
    if not tok:
        sys.exit("NEUBUS_TOKEN not set. Copy a bearer token from DevTools "
                 "(any request to rrcsearch3) into the environment.")
    warn_if_expiring(tok)
    return tok


def warn_if_expiring(tok: str) -> None:
    """JWT payload is plain base64; check exp so a stale token fails loudly."""
    try:
        payload = tok.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload))["exp"]
    except Exception:
        print("warning: could not parse token expiry; proceeding", file=sys.stderr)
        return
    left = exp - time.time()
    if left <= 0:
        sys.exit("Token is expired. Mint a fresh one (they live 24h).")
    if left < 3600:
        print(f"warning: token expires in {left/60:.0f} min", file=sys.stderr)


def check_order(order: str) -> None:
    """Refuse `desc`, which is accepted by the server and binds to nothing.

    DEFECTS #65. Measured on the district 02 window, 2026-09-07: ascending and
    descending return the same first page, id for id. The payload sends
    `order` and `orderBy` separately and `orderBy` is empty, so there is
    probably no sort key for the direction to apply to; that is a hypothesis
    and stays one, because testing it means inventing an `orderBy` value never
    seen from a working client (standing rule 2).

    A flag that silently does nothing is worse than no flag: two documents
    said this one worked.
    """
    if order != "asc":
        sys.exit(
            "--order desc is accepted by the server and changes nothing "
            "(DEFECTS #65): ascending and descending return the same page, "
            "id for id. Use --start-page to sample elsewhere in a window; "
            "that does work.")


def mint_token() -> str:
    """TODO: automate via pubcore.neubus.com/api.php?function=GetTenantEnvOauth.

    Observed to be the mint, but its own request requirements were not fully
    captured. With a 24h lifetime, a daily paste into NEUBUS_TOKEN is fine
    for this project's scale. Automate only if it stays annoying.
    """
    raise NotImplementedError


# --------------------------------------------------------------------------- session

class Client:
    def __init__(self, token: str):
        self.token = token
        self.s = requests.Session()
        self.s.headers.update({"user-agent": UA})
        self._prime_app_session()

    def _prime_app_session(self) -> None:
        """The search backend binds filters to SERVER-SIDE session state
        (2026-08-28 finding: without a real session, getSearchImages echoes
        your filters in the p-block but queries the whole archive -- 1.9M rows).

        Browser-parity mode (required until the session mint is automated):
        copy from a working getSearchImages request in DevTools into .env:
          NEUBUS_COOKIE = the full Cookie request header value
          NEUBUS_XSRF   = the x-csrf-token header value
        """
        cookie_hdr = os.environ.get("NEUBUS_COOKIE", "").strip()
        xsrf = os.environ.get("NEUBUS_XSRF", "").strip()
        if cookie_hdr:
            self.s.headers["cookie"] = cookie_hdr
        else:
            print("warning: NEUBUS_COOKIE not set; falling back to root-GET "
                  "priming, which is KNOWN to yield unfiltered results",
                  file=sys.stderr)
            r = self.s.get(APP + "/", timeout=30)
            r.raise_for_status()
            xsrf = xsrf or self.s.cookies.get("XSRF-TOKEN", "")
            self.s.cookies.set("AuthToken", self.token,
                               domain="rrcsearch3.neubus.com")
        self.s.headers.update({
            "authorization": f"Bearer {self.token}",
            "x-csrf-token": xsrf,
            "x-requested-with": "XMLHttpRequest",
            "origin": APP,
            "referer": APP + "/",
            "accept": "application/json, text/plain, */*",
        })

    # -- rate limiting ------------------------------------------------------

    def _pace(self, resp: requests.Response) -> None:
        remaining = resp.headers.get("x-ratelimit-remaining")
        if remaining is not None and int(remaining) < LOW_WATER:
            print(f"  rate limit low ({remaining} left); sleeping 60s",
                  file=sys.stderr)
            time.sleep(60)
        else:
            time.sleep(BASE_SLEEP)

    def _post(self, path: str, payload: dict) -> dict:
        r = self.s.post(APP + path, json=payload, timeout=60)
        self._pace(r)
        if os.environ.get("FETCH_DEBUG"):
            print("---- REQUEST ----", file=sys.stderr)
            for k, v in r.request.headers.items():
                shown = v[:40] + "..." if k.lower() in ("authorization",
                                                        "cookie") else v
                print(f"  {k}: {shown}", file=sys.stderr)
            print("  body:", r.request.body[:400], file=sys.stderr)
            print("---- RESPONSE p-block ----", file=sys.stderr)
            try:
                print(json.dumps(r.json()["data"].get("p", {}),
                                 indent=2)[:800], file=sys.stderr)
            except Exception:
                print(r.text[:400], file=sys.stderr)
        r.raise_for_status()
        return r.json()

    # -- the three data calls ----------------------------------------------

    def search(self, *, profile: int, from_date: str, to_date: str,
               items: list[dict], page: int, page_size: int = 100,
               strict: bool = True, order: str = "asc") -> dict:
        # strict:"true" is the ONLY value ever observed in a working request;
        # "false" made the server ignore ALL filters and return the full
        # 1.9M-record archive (2026-08-28). Non-strict matching, if it exists,
        # has to be rediscovered deliberately via --no-strict, never defaulted.
        payload = {
            "excludeName": "", "excludeValue": None, "extraParams": "",
            "includeName": "", "order": order, "orderBy": "",
            "page": page, "pageSize": page_size, "profile": profile,
            "recordFromDate": from_date, "recordToDate": to_date,
            "saveSearch": "true",
            "Searchitems": {"item": items},
            "strict": "true" if strict else "false",
        }
        return self._post("/getSearchImages", payload)

    def tab_files(self, *, profile: int, image_id: str, page: int,
                  page_size: int = 50) -> dict:
        payload = {"profile_id": profile, "image_id": image_id,
                   "page": page, "page_size": page_size,
                   "order_by": "", "order": ""}
        return self._post("/getTabFilesOauth", payload)

    def download(self, nuid: str, profile: int, dest: Path,
                 expect_size: int | None) -> None:
        url = f"{FS}/api/v1/single/{nuid}?profileId={profile}"
        r = self.s.get(url, headers={"authorization": f"Bearer {self.token}",
                                     "user-agent": UA}, timeout=120)
        self._pace(r)
        r.raise_for_status()
        if not r.content.startswith(b"%PDF"):
            raise RuntimeError(f"{nuid}: response is not a PDF "
                               f"({r.content[:60]!r})")
        if expect_size and len(r.content) != expect_size:
            raise RuntimeError(f"{nuid}: size {len(r.content)} != "
                               f"manifest file_size {expect_size}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)


# --------------------------------------------------------------------------- helpers

def fields_to_dict(image: dict) -> dict:
    return {f["field_name"]: f["field_value"] for f in image["image_fields"]}


def load_done() -> set[str]:
    if not MANIFEST.exists():
        return set()
    done = set()
    with MANIFEST.open() as fh:
        for line in fh:
            try:
                done.add(json.loads(line)["record_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def parse_search_items(pairs: list[str]) -> list[dict]:
    items = []
    for pair in pairs:
        key, _, value = pair.partition("=")
        if not value:
            sys.exit(f"--search wants key=value, got {pair!r}")
        items.append({"key": key, "value": value, "label": key,
                      "type": "TEXT"})
    return items


# --------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--district", default="03")
    ap.add_argument("--from", dest="from_date", required=True,
                    help="record (imaging) date MM/DD/YYYY")
    ap.add_argument("--to", dest="to_date", required=True)
    ap.add_argument("--profile", type=int, default=17)
    ap.add_argument("--search", action="append", default=[],
                    metavar="KEY=VALUE",
                    help="extra Searchitems, e.g. lease_name=Ducroz")
    ap.add_argument("--all-types", action="store_true",
                    help="keep every profile_type, not just POTENTIAL")
    ap.add_argument("--max-records", type=int, default=None)
    ap.add_argument("--max-pages", type=int, default=None,
                    help="hard stop after N search pages")
    ap.add_argument("--force", action="store_true",
                    help="proceed even if the match count looks unfiltered")
    ap.add_argument("--order", choices=["asc", "desc"], default="asc",
                    help="result order by record id. Only asc does anything: "
                         "desc is accepted by the server and binds to nothing "
                         "(DEFECTS #65). Use --start-page instead.")
    ap.add_argument("--start-page", type=int, default=1,
                    help="skip into the middle of a large window")
    ap.add_argument("--no-strict", action="store_true",
                    help="EXPERIMENTAL: send strict:false, known to break "
                         "filter binding entirely as of 2026-08-28")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be fetched; download nothing")
    args = ap.parse_args()
    if args.dry_run and not args.max_records and not args.max_pages:
        args.max_pages = 3
        print("dry run: defaulting to --max-pages 3", file=sys.stderr)

    check_order(args.order)
    client = Client(load_token())
    done = load_done()
    DATA.mkdir(exist_ok=True)

    items = [{"key": "district", "value": args.district,
              "label": "District", "type": "DROPDOWN"}]
    items += parse_search_items(args.search)

    fetched = skipped = 0
    page = args.start_page - 1
    total = None
    manifest_fh = None if args.dry_run else MANIFEST.open("a")

    try:
        while True:
            page += 1
            resp = client.search(profile=args.profile,
                                 from_date=args.from_date,
                                 to_date=args.to_date,
                                 items=items, page=page,
                                 strict=not args.no_strict,
                                 order=args.order)
            body = resp["data"]["data"]
            if not isinstance(body, dict) or "search_results" not in body:
                print("0 records match (server returned empty-result shape)")
                break
            if total is None:
                total = body["meta"]["num_images"]
                print(f"{total} records match; paging at 100")
                if total > 200_000 and not args.force:
                    sys.exit("ABORT: match count is archive-scale, so the "
                             "server ignored the filters (missing/stale "
                             "session?). Refresh NEUBUS_COOKIE / NEUBUS_XSRF "
                             "from DevTools, or pass --force if intentional.")
            images = body["search_results"]["images"]
            if not images:
                break

            for image in images:
                meta = fields_to_dict(image)
                record_id = meta.get("id") or "unknown"
                ptype = (meta.get("profile_type") or "").upper()

                if not args.all_types and ptype != "POTENTIAL":
                    continue
                if record_id in done:
                    skipped += 1
                    continue
                if not image.get("allow_access", False):
                    print(f"  {record_id}: allow_access false, skipping")
                    continue
                if args.max_records and fetched >= args.max_records:
                    raise StopIteration

                print(f"[{record_id}] {ptype} {meta.get('lease_name')} / "
                      f"{meta.get('operator_name')} ({meta.get('county')})")
                if args.dry_run:
                    fetched += 1
                    continue

                files_out = []
                fpage = 0
                while True:
                    fpage += 1
                    tf = client.tab_files(profile=args.profile,
                                          image_id=image["doc_id"],
                                          page=fpage)
                    tab = tf["data"]["data"]
                    for f in tab["files"]:
                        dest = RAW / record_id / f["name"]
                        if dest.exists() and dest.stat().st_size == int(f["file_size"]):
                            print(f"    have {f['name']}")
                        else:
                            print(f"    get  {f['name']} "
                                  f"({int(f['file_size'])//1024} KB, "
                                  f"{f['page_count']} pp)")
                            client.download(f["nuid"], args.profile, dest,
                                            int(f["file_size"]))
                        files_out.append({
                            "name": f["name"],
                            "pages": int(f["page_count"]),
                            "bytes": int(f["file_size"]),
                            "document_type": f.get("document_type"),
                            "uploaded_on": f.get("uploaded_on"),
                        })
                    if fpage * 50 >= int(tab["total_files"]):
                        break

                manifest_fh.write(json.dumps({
                    "record_id": record_id,
                    "profile_type": ptype,
                    "meta": meta,
                    "files": files_out,
                    "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                time.gmtime()),
                }) + "\n")
                manifest_fh.flush()
                done.add(record_id)
                fetched += 1

            if args.max_pages and page >= args.max_pages:
                print(f"stopping at --max-pages {args.max_pages}")
                break
            if page * 100 >= total:
                break
    except StopIteration:
        pass
    finally:
        if manifest_fh:
            manifest_fh.close()

    print(f"\ndone: {fetched} records fetched, {skipped} already cached, "
          f"{total} matched the search")


if __name__ == "__main__":
    main()
