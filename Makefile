# Use the venv interpreter, not whatever python3 is on PATH: the deps in
# requirements.txt are installed there (see SETUP.md step 5).
PY := .venv/bin/python

.PHONY: fetch test eval label label2 workbook truthbook arms probe census smoke score findings overlay snap gradebook template probebox demo
fetch:
	@set -a; . ./.env; set +a; $(PY) fetch.py $(ARGS)
test:
	$(PY) -m pytest tests/tier1 tests/tier2 -q
eval:
	$(PY) -m pytest tests/tier3 -q

label:
	$(PY) scripts/sample_labelset.py $(ARGS)

label2:
	$(PY) scripts/sample_stage2.py $(ARGS)

workbook:
	$(PY) scripts/make_label_workbook.py $(ARGS)

truthbook:
	$(PY) scripts/make_extract_workbook.py

probe:
	@set -a; . ./.env; set +a; $(PY) scripts/probe_haiku.py

arms:
	@set -a; . ./.env; set +a; $(PY) scripts/run_arms.py $(ARGS)

census:
	@set -a; . ./.env; set +a; $(PY) -m pipeline.census $(ARGS)

# Both run the Batch API path, the same one the corpus run uses: a score
# taken on the live streamed path measured an instrument, not the product,
# and the two disagreed (DEFECTS #74). The live arm stays reachable by
# calling the scripts directly.
smoke:
	@set -a; . ./.env; set +a; $(PY) scripts/smoke_extract.py --batched $(ARGS)

score:
	$(PY) scripts/score_extract.py --results data/extract/smoke_batched.jsonl --cache data/extract/cache_smoke_batched.jsonl $(ARGS)

findings:
	$(PY) scripts/validate_extract.py $(ARGS)

overlay:
	$(PY) scripts/overlay_boxes.py $(ARGS)

snap:
	$(PY) scripts/snap_coverage.py

gradebook:
	$(PY) scripts/make_grades_workbook.py

template:
	$(PY) scripts/build_template.py $(ARGS)

probebox:
	$(PY) scripts/probe_boxes.py $(ARGS)

demo:
	@test -d data/viewer && echo "data/viewer already present" || ( \
	  echo "downloading the viewer bundle (124 MB, release corpus-v1)..." && \
	  curl -L -o /tmp/rrc-viewer-bundle.tar.gz \
	    https://github.com/alexspili/rrc-pipeline/releases/download/corpus-v1/rrc-viewer-bundle.tar.gz && \
	  tar -xzf /tmp/rrc-viewer-bundle.tar.gz && rm /tmp/rrc-viewer-bundle.tar.gz )
	@echo "now: cd viewer && npm install && npm run dev"
