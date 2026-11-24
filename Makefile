# Targets are added as the weeks need them (ROADMAP.md); same style as
# platform-lab and local-airgap-LLM: one line per target, a comment above it.

.PHONY: lint

PLATFORM_LAB ?= $(abspath ../platform-lab)
LOCAL_AIRGAP_LLM ?= $(abspath ../local-airgap-LLM)

lint:
	yamllint -s .
