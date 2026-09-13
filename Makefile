# home-dns development tasks. Everything here runs on the development machine,
# offline after `make setup`. Nothing here touches the Raspberry Pi or the network.

UV      ?= uv
NPM     ?= npm
WEB_DIR := dashboard/frontend
ENV     ?= development

# Import from src/ explicitly instead of relying on the editable-install .pth file:
# some macOS setups flag .pth files as hidden and recent Python versions skip them.
export PYTHONPATH := $(CURDIR)/src
HOME_DNS := $(UV) run --locked python -m home_dns.cli

.PHONY: help setup test test-py test-web lint check validate-config serve-mock build-web _require-setup

help:
	@echo "make setup            install locked Python + frontend dependencies (needs Internet once)"
	@echo "make test             run Python and frontend tests (offline)"
	@echo "make lint             ruff, mypy --strict, tsc"
	@echo "make check            lint + test + validate-config (development) + frontend build"
	@echo "make validate-config  ENV=development|production [PROFILE=path]"
	@echo "make serve-mock       run the API with the development profile on loopback"
	@echo "make build-web        build static frontend files into $(WEB_DIR)/dist"

setup:
	$(UV) sync --locked
	cd $(WEB_DIR) && $(NPM) ci

_require-setup:
	@test -d .venv || { echo "ERROR: Python environment missing. Run 'make setup' first."; exit 2; }
	@test -d $(WEB_DIR)/node_modules || { echo "ERROR: frontend dependencies missing. Run 'make setup' first."; exit 2; }

test: _require-setup test-py test-web

test-py:
	$(UV) run --locked pytest

test-web:
	cd $(WEB_DIR) && $(NPM) test

lint: _require-setup
	$(UV) run --locked ruff check src tests
	$(UV) run --locked ruff format --check src tests
	$(UV) run --locked mypy
	cd $(WEB_DIR) && $(NPM) run typecheck

validate-config: _require-setup
	$(HOME_DNS) validate-config --env $(ENV) $(if $(PROFILE),--profile $(PROFILE),)

check: lint test
	$(MAKE) validate-config ENV=development
	$(MAKE) build-web
	@echo "check: OK"

serve-mock: _require-setup
	$(HOME_DNS) serve --env development

build-web: _require-setup
	cd $(WEB_DIR) && $(NPM) run build
