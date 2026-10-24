SPHINXOPTS    ?= -W
SPHINXBUILD   ?= uv run --group docs sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

.PHONY: help html linkcheck clean

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  html       Build the HTML documentation"
	@echo "  linkcheck  Check the external links"
	@echo "  clean      Remove the build directory"

html:
	$(SPHINXBUILD) $(SPHINXOPTS) -b html $(SOURCEDIR) $(BUILDDIR)/html
	@echo "The documentation is in $(BUILDDIR)/html/index.html"

linkcheck:
	$(SPHINXBUILD) $(SPHINXOPTS) -b linkcheck $(SOURCEDIR) $(BUILDDIR)/linkcheck

clean:
	rm -rf $(BUILDDIR)
