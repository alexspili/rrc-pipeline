# Use the venv interpreter, not whatever python3 is on PATH: the deps in
# requirements.txt are installed there (see SETUP.md step 5).
PY := .venv/bin/python

.PHONY: fetch test eval label workbook arms probe census
fetch:
	@set -a; . ./.env; set +a; $(PY) fetch.py $(ARGS)
test:
	$(PY) -m pytest tests/tier1 tests/tier2 -q
eval:
	$(PY) -m pytest tests/tier3 -q

label:
	$(PY) scripts/sample_labelset.py $(ARGS)

workbook:
	$(PY) scripts/make_label_workbook.py

probe:
	@set -a; . ./.env; set +a; $(PY) scripts/probe_haiku.py

arms:
	@set -a; . ./.env; set +a; $(PY) scripts/run_arms.py $(ARGS)

census:
	@set -a; . ./.env; set +a; $(PY) -m pipeline.census $(ARGS)
