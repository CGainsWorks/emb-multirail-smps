# Everything this repository produces comes from `make demo`.
PY ?= python

.DEFAULT_GOAL := help

help:
	@echo "make setup   install the dependencies"
	@echo "make demo    regenerate every result, plot, CSV and generated document"
	@echo "make quick   the same without the switching simulator sweeps"
	@echo "make test    run the test suite"
	@echo "make headline check the numbers the README quotes are still true"
	@echo "make spice   run the generated decks in ngspice, if it is installed"
	@echo "make check   test, then demo, then confirm nothing changed"
	@echo "make ci      everything CI does, locally, for no minutes"
	@echo "make clean   remove generated outputs"

setup:
	$(PY) -m pip install -r requirements.txt

demo:
	$(PY) simulation/run_all.py

quick:
	$(PY) simulation/run_all.py --quick

test:
	$(PY) -m pytest tests -q

headline:
	$(PY) scripts/check_headline.py

spice:
	$(PY) scripts/run_ngspice.py --skip-missing

# The check a reviewer should run: the results in the repository have to be
# what the code produces today, not what it produced when somebody last
# remembered to regenerate them. The comparison is against HEAD, so after
# changing a model the order is: make demo, commit, then make check.
check: test demo
	$(PY) scripts/check_outputs_current.py

clean:
	rm -rf outputs/netlists outputs/*.csv outputs/*.json
	rm -rf test-results/bode test-results/efficiency test-results/thermal
	rm -rf test-results/emc-prescan test-results/load-regulation
	rm -rf test-results/line-regulation test-results/transient
	rm -f test-results/power_tree.png
	rm -rf .pytest_cache **/__pycache__

# Exactly what the GitHub Actions job does, in the same order. Running this
# before pushing costs nothing and saves a round trip through a runner, which
# on a free account is the whole point.
ci: test demo
	$(PY) scripts/check_outputs_current.py
	@for f in test-results/power_tree.png test-results/bode/*.png \
		test-results/efficiency/*.png test-results/thermal/*.png \
		test-results/emc-prescan/*.png test-results/*-regulation/*.png \
		test-results/transient/*.png; do \
		[ -s "$$f" ] || { echo "missing or empty: $$f"; exit 1; }; \
	done
	@echo "all plots present"
	$(PY) scripts/run_ngspice.py --skip-missing
	$(PY) scripts/check_headline.py

.PHONY: help setup demo quick test headline spice check ci clean
