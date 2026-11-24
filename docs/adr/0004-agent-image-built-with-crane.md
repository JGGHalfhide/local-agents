# 0004. Agent image built with crane, no daemon

Status: accepted (Week 2, 11/24)

## Context

Nothing in the lab built container images: platform-lab's `make image`
copies upstream images through the supply chain (SBOM, Trivy gate, push to
Zot, cosign signature and SBOM attestation, verified by Kyverno at
admission). The agent (ADR 0002) is pure Python plus 14 binary wheels, so
its image needs no `RUN` step.

Options compared in [image-build.md](../image-build.md): crane append/mutate
on the host (already installed, no daemon, no root); buildah or podman on the
host (new tool, user-namespace setup in platform-lab's host bootstrap); a
build Job in the cluster (Pod Security and Kyverno exceptions, push
credentials in the cluster, scan and sign outside the existing script).

Measured 11/24:

- Base `python:3.14.9-slim-trixie@sha256:35caba83…` (built 10/21; the 11/24
  build of 3.14.10 was too new for the two-week rule): Trivy 0 CRITICAL;
  HIGH 61 (8 with a fix). The gate (fixable CRITICAL) passes.
- `scripts/build-agent-image.sh`: dependencies installed from
  `agent/requirements.lock` (14 packages, SHA-256 hashes, wheels only, no
  `.pyc`), one layer packed with sorted entries, fixed owner, mode and mtime
  (the commit time), appended with `crane mutate` in a throwaway in-memory
  registry; entrypoint `python3 -m agent`, user 65532. Built twice: same
  digest (`sha256:fabf4863…`), same layer bytes. The host's CPython 3.14
  imports `openai` and `agent` from the staged tree.
- platform-lab's script with the layout as source, `PUSH=0`: SBOM 110
  packages, the same findings as the base (the locked wheels add none),
  gate passed. The upstream path still works unchanged.

## Decision

Build the agent image with crane on the host (`make agent-image`), and
publish it with platform-lab's `make image IMAGE=oci-layout:<dir>
NAME=local-agents/agent:<version>` (that script now accepts a local OCI
layout; change made in platform-lab 47c3d56, documented in its
supply-chain.md).
Dependencies change only through `make agent-lock`.

- crane is pinned at 0.22.1 in platform-lab's stack.md (it was listed
  without a version).
- The image is single-platform (linux/amd64), like the lab.
- Revisit (new ADR) if an image needs system packages or a `RUN` step: then
  buildah, as image-build.md describes.
