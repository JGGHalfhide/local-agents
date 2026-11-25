# Targets are added as the weeks need them (ROADMAP.md); same style as
# platform-lab and local-airgap-LLM: one line per target, a comment above it.

.PHONY: lint eval-check agent-image agent-lock airgap-packages airgap-deploy

PLATFORM_LAB ?= $(abspath ../platform-lab)
LOCAL_AIRGAP_LLM ?= $(abspath ../local-airgap-LLM)
AIRGAP_OUT := $(CURDIR)/build/airgap/packages
LLM_OUT := $(LOCAL_AIRGAP_LLM)/build/airgap/packages
AGENTS_VERSION := $(shell sed -n 's/^  version: //p' zarf/agents/zarf.yaml)
LLM_VERSION := $(shell sed -n 's/^  version: //p' $(LOCAL_AIRGAP_LLM)/zarf/llm/zarf.yaml)
SMOKE_VERSION := $(shell sed -n 's/^  version: //p' $(LOCAL_AIRGAP_LLM)/zarf/llm-smoke/zarf.yaml)

lint:
	yamllint -s .

# Validate the evaluation cases (schema, patterns, leak check); docs/eval.md.
eval-check:
	python3 eval/check.py
	python3 eval/status/check_config.py

# Lock the agent image's Python dependencies with hashes (agent/requirements.lock).
agent-lock:
	scripts/lock-agent-deps.sh

# Build the agent image reproducibly with crane (ADR 0004); OCI layout in
# build/agent-image/oci, published with platform-lab's `make image
# IMAGE=oci-layout:<that dir> NAME=local-agents/agent:<version>`.
agent-image:
	scripts/build-agent-image.sh

# --- Airgap (Week 5; docs/airgap-runbook.md) ---------------------------------

# Build and sign the Zarf package zarf/agents with platform-lab's script and
# lab cosign key. Needs the build cluster running: the agent image and its
# signature come from its registry.
airgap-packages:
	ZARF_SRC=$(CURDIR)/zarf OUT=$(AIRGAP_OUT) $(PLATFORM_LAB)/scripts/airgap-packages.sh agents

# Deploy on the airgapped node with platform-lab's zarf role: platform-lab's
# packages, then local-airgap-LLM's llm and llm-smoke (built there with its
# make airgap-packages), then agents. Unchanged packages are skipped. Run
# platform-lab's make airgap-up and airgap-disconnect first.
airgap-deploy:
	@test -f $(AIRGAP_OUT)/SHA256SUMS || { echo "run make airgap-packages first"; exit 1; }
	@test -f $(LLM_OUT)/SHA256SUMS || { echo "run make airgap-packages in local-airgap-LLM first"; exit 1; }
	cd $(PLATFORM_LAB)/ansible && ansible-playbook airgap-deploy.yml </dev/null \
	  -e '{"zarf_extra_packages": [{"name": "llm", "version": "$(LLM_VERSION)", "dir": "$(LLM_OUT)"}, {"name": "llm-smoke", "version": "$(SMOKE_VERSION)", "dir": "$(LLM_OUT)"}, {"name": "agents", "version": "$(AGENTS_VERSION)", "dir": "$(AIRGAP_OUT)"}]}'
