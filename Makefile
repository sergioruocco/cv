PYTHON ?= python3

.PHONY: all academic industry consulting site citations reference clean

all:
	$(PYTHON) build.py --all

academic:
	$(PYTHON) build.py --profile academic

industry:
	$(PYTHON) build.py --profile industry

consulting:
	$(PYTHON) build.py --profile consulting

site:
	$(PYTHON) build.py --site

citations:
	$(PYTHON) tools/update_citations.py

reference:
	$(PYTHON) tools/make_reference_docx.py

clean:
	rm -rf output
	rm -f docs/index.html docs/publications.html docs/style.css
	rm -rf docs/files
