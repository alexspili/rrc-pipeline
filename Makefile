.PHONY: fetch test eval
fetch:
@set -a; . ./.env; set +a; python3 fetch.py $(ARGS)
test:
python3 -m pytest tests/tier1 tests/tier2 -q
eval:
python3 -m pytest tests/tier3 -q
