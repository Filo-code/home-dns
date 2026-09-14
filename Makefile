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

.PHONY: help setup test test-py test-web lint check validate-config serve-mock serve-static \
	build-web gen-types check-types _require-setup _dev-admin

# Fixed local-dev-only credentials for `serve`'s required admin user (A7). .local/ is
# gitignored; these are never used outside this machine's throwaway dev database.
DEV_ADMIN_USER     ?= admin
DEV_ADMIN_PASSWORD ?= change-me-dev-only-12

help:
	@echo "make setup            install locked Python + frontend dependencies (needs Internet once)"
	@echo "make test             run Python and frontend tests (offline)"
	@echo "make lint             ruff, mypy --strict, tsc"
	@echo "make check            lint + test + validate-config (development) + type-drift + frontend build"
	@echo "make validate-config  ENV=development|production [PROFILE=path]"
	@echo "make serve-mock       run the API with the development profile on loopback"
	@echo "make serve-static     build the frontend and serve it + the API from one process (A8 rehearsal)"
	@echo "make build-web        build static frontend files into $(WEB_DIR)/dist"
	@echo "make gen-types        regenerate $(WEB_DIR)/src/api/types.generated.ts from the live dev API"
	@echo "make check-types      fail if the committed generated types are stale"

setup:
	$(UV) sync --locked
	cd $(WEB_DIR) && $(NPM) ci
	cd scripts/codegen && $(NPM) ci

_require-setup:
	@test -d .venv || { echo "ERROR: Python environment missing. Run 'make setup' first."; exit 2; }
	@test -d $(WEB_DIR)/node_modules || { echo "ERROR: frontend dependencies missing. Run 'make setup' first."; exit 2; }

# Idempotent: `auth set-password` creates-or-updates and always exits 0. Development only —
# `serve`/`auth` both refuse to run at all in production (unrelated to this convenience).
_dev-admin: _require-setup
	@printf '$(DEV_ADMIN_PASSWORD)\n' | $(HOME_DNS) auth set-password --env development \
		--username $(DEV_ADMIN_USER) --role admin --password-stdin >/dev/null

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
	$(MAKE) check-types
	$(MAKE) build-web
	@echo "check: OK"

serve-mock: _require-setup _dev-admin
	$(HOME_DNS) serve --env development

# Local rehearsal of the A8 hosting model: one process serves both the API and the built
# frontend, same as C4's Raspberry Pi deployment will — still entirely offline, on loopback.
serve-static: _require-setup _dev-admin build-web
	$(HOME_DNS) serve --env development --static-dir $(WEB_DIR)/dist

build-web: _require-setup
	cd $(WEB_DIR) && $(NPM) run build

gen-types: _require-setup
	bash scripts/generate-frontend-types.sh

# Regenerates to a throwaway path and diffs against the committed file, so a forgotten
# `make gen-types` after an API change is caught here rather than shipping stale types.
check-types: _require-setup
	@tmp_dir=$$(mktemp -d) && \
	bash scripts/generate-frontend-types.sh "$$tmp_dir/types.generated.ts" && \
	if diff -q "$$tmp_dir/types.generated.ts" $(WEB_DIR)/src/api/types.generated.ts >/dev/null; then \
		echo "check-types: OK (generated types match the API)"; \
	else \
		echo "ERROR: $(WEB_DIR)/src/api/types.generated.ts is stale — run 'make gen-types' and commit it"; \
		rm -rf "$$tmp_dir"; \
		exit 1; \
	fi; \
	rm -rf "$$tmp_dir"
