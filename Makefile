SHELL := /bin/bash

ROOT := $(abspath .)
UNIFIED_PYTHON := $(ROOT)/.venv/bin/python
UNIFIED_PIP := $(ROOT)/.venv/bin/pip
GATEWAY_PYTHON := $(ROOT)/unified/mcp-gateway/.venv/bin/python
GATEWAY_PIP := $(ROOT)/unified/mcp-gateway/.venv/bin/pip

.PHONY: help check-unified-venv check-gateway-venv bootstrap-unified-venv bootstrap-gateway-venv test-unified test-gateway test

help:
	@echo "Available targets:"
	@echo "  make bootstrap-unified-venv"
	@echo "  make bootstrap-gateway-venv"
	@echo "  make test-unified   # Run unified backend tests with the root virtualenv"
	@echo "  make test-gateway   # Run MCP gateway tests with the gateway virtualenv"
	@echo "  make test           # Run both test suites"

check-unified-venv:
	@test -x "$(UNIFIED_PYTHON)" || (echo "Missing $(UNIFIED_PYTHON)"; exit 1)

check-gateway-venv:
	@test -x "$(GATEWAY_PYTHON)" || (echo "Missing $(GATEWAY_PYTHON)"; exit 1)

bootstrap-unified-venv: check-unified-venv
	"$(UNIFIED_PIP)" install -e ./unified

bootstrap-gateway-venv: check-gateway-venv
	cd unified/mcp-gateway && ./.venv/bin/pip install -e .

test-unified: check-unified-venv
	PYTHONPATH=.:unified "$(UNIFIED_PYTHON)" -m unittest \
		unified.tests.test_access_control \
		unified.tests.test_auth_security \
		unified.tests.test_batch_governance \
		unified.tests.test_export_policy \
		unified.tests.test_maintenance_reports \
		unified.tests.test_metrics \
		unified.tests.test_mcp_transport \
		unified.tests.test_metadata_lineage \
		unified.tests.test_obsidian_cli \
		unified.tests.test_policy_enforcement \
		unified.tests.test_policy_registry \
		unified.tests.test_search_policy \
		unified.tests.test_startup_smoke \
		unified.tests.test_sync_check \
		unified.tests.test_update_memory \
		unified.tests.test_transport_parity \
		unified.tests.test_audit_fixes

test-gateway: check-gateway-venv
	cd unified/mcp-gateway && PYTHONPATH=.:../.. ./.venv/bin/python -m unittest discover -s tests -v

test: test-unified test-gateway
