# Targets are added as the weeks need them (ROADMAP.md); same style as
# platform-lab and local-airgap-LLM: one line per target, a comment above it.

.PHONY: lint eval-check agent-image agent-lock

PLATFORM_LAB ?= $(abspath ../platform-lab)
LOCAL_AIRGAP_LLM ?= $(abspath ../local-airgap-LLM)

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
