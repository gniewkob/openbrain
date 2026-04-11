SHELL := /bin/bash

ROOT := $(abspath .)
UNIFIED_PYTHON := $(ROOT)/.venv/bin/python
UNIFIED_PIP := $(ROOT)/.venv/bin/pip
GATEWAY_PYTHON := $(ROOT)/unified/mcp-gateway/.venv/bin/python
GATEWAY_PIP := $(ROOT)/unified/mcp-gateway/.venv/bin/pip

.PHONY: help check-unified-venv check-gateway-venv bootstrap-unified-venv bootstrap-gateway-venv test-unified test-gateway test local-guardrails guardrail-tests contract-smoke pr-readiness monitoring-check

help:
	@echo "Available targets:"
	@echo "  make bootstrap-unified-venv"
	@echo "  make bootstrap-gateway-venv"
	@echo "  make test-unified   # Run unified backend tests with the root virtualenv"
	@echo "  make test-gateway   # Run MCP gateway tests with the gateway virtualenv"
	@echo "  make test           # Run both test suites"
	@echo "  make local-guardrails # Run static local guardrails bundle only"
	@echo "  make guardrail-tests # Run only guardrail runner pytest bundle"
	@echo "  make contract-smoke # Run only contract integrity smoke pytest bundle"
	@echo "  make pr-readiness   # Run local guardrails + fast policy/contract checks"

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
		unified.tests.test_db_security \
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

local-guardrails: check-unified-venv
	"$(UNIFIED_PYTHON)" scripts/check_local_guardrails.py

guardrail-tests: check-unified-venv
	"$(UNIFIED_PYTHON)" -m pytest -q \
		unified/tests/test_local_guardrails_runner.py \
		unified/tests/test_pr_readiness_runner.py \
		unified/tests/test_repo_hygiene_guardrail.py \
		unified/tests/test_compose_guardrails.py \
		unified/tests/test_secret_scan_guardrail.py \
		unified/tests/test_capabilities_manifest_parity_guardrail.py \
		unified/tests/test_capabilities_metadata_parity_guardrail.py \
		unified/tests/test_capabilities_health_parity_guardrail.py \
		unified/tests/test_capabilities_tier_status_parity_guardrail.py \
		unified/tests/test_backend_probe_contract_parity_guardrail.py \
		unified/tests/test_request_runtime_parity_guardrail.py \
		unified/tests/test_shared_http_client_reuse_guardrail.py \
		unified/tests/test_tool_signature_parity_guardrail.py \
		unified/tests/test_admin_bounds_parity_guardrail.py \
		unified/tests/test_admin_endpoint_contract_parity_guardrail.py \
		unified/tests/test_tool_inventory_parity_guardrail.py \
		unified/tests/test_capabilities_tools_truthfulness_guardrail.py \
		unified/tests/test_search_filter_parity_guardrail.py \
		unified/tests/test_list_filter_parity_guardrail.py \
		unified/tests/test_response_normalizers_parity_guardrail.py \
		unified/tests/test_http_error_adapter_parity_guardrail.py \
		unified/tests/test_http_error_contract_semantics_guardrail.py \
		unified/tests/test_capabilities_truthfulness_guardrail.py \
		unified/tests/test_audit_semantics_guardrail.py \
		unified/tests/test_cleanup_actor_semantics_guardrail.py \
		unified/tests/test_update_audit_semantics_parity_guardrail.py \
		unified/tests/test_delete_semantics_parity_guardrail.py \
		unified/tests/test_export_contract_guardrail.py \
		unified/tests/test_obsidian_contract_guardrail.py \
		unified/tests/test_mcp_http_session_contract_guardrail.py \
		unified/tests/test_telemetry_contract_parity_guardrail.py \
		unified/tests/test_dashboard_memory_semantics_guardrail.py \
		unified/tests/test_hidden_test_data_alert_parity_guardrail.py \
		unified/tests/test_monitoring_contract_guardrail.py \
		unified/mcp-gateway/tests/test_shared_client_reuse.py

contract-smoke: check-unified-venv
	"$(UNIFIED_PYTHON)" -m pytest -q \
		unified/tests/test_contract_integrity.py \
		unified/tests/test_capabilities_response_contract.py \
		unified/tests/test_health_route_alias_contract.py \
		unified/tests/test_find_endpoint_validation.py \
		unified/tests/test_test_data_hygiene_report.py \
		unified/tests/test_build_test_data_cleanup.py \
		unified/tests/test_admin_openapi_contract.py \
		unified/tests/test_route_registration.py \
		unified/tests/test_transport_parity.py

pr-readiness: check-unified-venv
	"$(UNIFIED_PYTHON)" scripts/check_pr_readiness.py

monitoring-check: check-unified-venv
	"$(UNIFIED_PYTHON)" scripts/validate_monitoring_contract.py
