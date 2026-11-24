# Targets are added as the weeks need them (ROADMAP.md); same style as
# platform-lab and local-airgap-LLM: one line per target, a comment above it.

.PHONY: lint eval-check

PLATFORM_LAB ?= $(abspath ../platform-lab)
LOCAL_AIRGAP_LLM ?= $(abspath ../local-airgap-LLM)

lint:
	yamllint -s .

# Validate the evaluation cases (schema, patterns, leak check); docs/eval.md.
eval-check:
	python3 eval/check.py
