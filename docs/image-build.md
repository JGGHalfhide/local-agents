# Building the agent image

Status: **decided** (Week 2, 11/24): option A, crane
([ADR 0004](adr/0004-agent-image-built-with-crane.md)). Implemented:
`make agent-image` (scripts/build-agent-image.sh), `make agent-lock`, and
platform-lab's `make image IMAGE=oci-layout:<dir> NAME=<repo>:<tag>`. The
comparison below is kept as the record of the options.

## What exists (checked 11/24)

- Nothing in the lab builds images. platform-lab's `make image`
  (`scripts/publish-image.sh`, [supply-chain.md](../../platform-lab/docs/supply-chain.md))
  **copies** upstream images: crane pulls the index as an OCI layout, Syft
  writes SBOMs, Trivy gates on fixable CRITICAL findings, crane pushes to
  Zot with the digest unchanged, cosign signs the digest and attests the
  SPDX SBOM with the lab key (tag-based layout, no transparency log).
- Steps 2-5 already work from an OCI layout on disk; only step 1 assumes an
  upstream reference.
- On the host: crane (Arch package `crane 0.22.1-1`; `crane version` prints
  `(devel)`), cosign, syft, trivy. Not installed: podman, docker, buildah,
  buildkitd, nerdctl, skopeo, ko, apko, melange, umoci.
- platform-lab's docs/stack.md lists crane without a version: a gap in the
  pinning rule, whichever option is chosen.
- Admission: images from `127.0.0.1:30500` must be pinned by digest and
  signed with the lab key; restricted Pod Security (non-root, no privilege
  escalation, seccomp, all capabilities dropped); `app.kubernetes.io/name`
  label; requests and limits.

## What the agent image needs

A Python interpreter (version chosen with the base image), the runtime
chosen in ADR 0002 and its wheels (pinned, with hashes), the agent code and
prompts, a non-root user, no shell needed at run time. No compiler: every
dependency comes as a wheel (checked per candidate in the ADR 0002 spike).

## Options

| | A. crane append / mutate (daemonless) | B. buildah or podman, rootless, on the host | C. Build in the cluster (BuildKit rootless or the kaniko fork, as a Job) |
|---|---|---|---|
| How | Base image pinned by digest; wheels installed on the host into a directory (`pip install --target --no-deps --require-hashes` from vendored wheels); the directory and the code packed into one tarball with fixed owners, order and mtimes (`SOURCE_DATE_EPOCH`); `crane append` adds it as a layer to an OCI layout of the base; `crane mutate` sets entrypoint, user (65532), workdir, labels | Containerfile with `FROM <base>@sha256:...`, `COPY` wheels, `RUN pip install`; `buildah build --timestamp` for reproducibility | A build Job reads the context from Git and pushes to Zot |
| New tools | None | buildah (or podman) from pacman, plus subuid/subgid for rootless; pin version and checksum | BuildKit or kaniko images, published through `make image` |
| Host or cluster change | None | Host packages and user-namespace config (Ansible in platform-lab's host bootstrap) | Pod Security and Kyverno exceptions: BuildKit rootless needs unconfined seccomp/AppArmor or user namespaces; the kaniko fork runs as root in its container. Push credentials for Zot in the cluster |
| `RUN` steps inside the image | Not possible: everything is prepared on the host. Enough for pure Python + wheels; not for `apt-get` | Yes | Yes |
| Reproducibility | Deterministic given the same base digest and tarball: crane computes digests from bytes. Checkable by building twice | Possible with `--timestamp` and pinned inputs; layers from `RUN` need care (pip caches, pyc timestamps) | As B, plus the build pod's environment |
| Fits the existing chain | Output is an OCI layout: the input `publish-image.sh` already uses for steps 2-5 | Export to an OCI layout (`oci:` / `oci-archive:`), then the same | Pushes directly; scan/sign would have to run after, outside the script |
| Cost (estimate) | ~2-3 h: a build script, the `publish-image.sh` change in platform-lab, a twice-built digest check | ~3-4 h + host config | Most: exceptions, credentials, a second path for scan and sign |
| Risk | Base image must already contain the interpreter; a wheel/base ABI mismatch (glibc vs musl, Python version) fails at import, so the build ends with an import check | One more privileged-ish host tool | Weakens the platform's admission rules for a build workload |

## Proposed (for the user's decision)

**A, crane.** No new tool, no host or cluster change, deterministic, and
its output is exactly what platform-lab's script already scans, pushes and
signs. Its limit (no `RUN`) does not bite for a pure-Python agent with
vendored wheels.

Steps if accepted:

1. platform-lab: `publish-image.sh` accepts a local OCI layout as the
   source (skips the pull; the tag comes from an argument). Same SBOM, gate,
   push, sign and verify steps. Recorded in platform-lab's supply-chain.md
   and noted here. Pin crane's version in platform-lab's stack.md.
2. This repo: `make agent-image`: vendored wheels (`--require-hashes`, from
   ADR 0002's lock file) + agent code -> reproducible tarball -> `crane
   append` onto the pinned base -> `crane mutate` (non-root user,
   entrypoint) -> OCI layout in build/ -> an import check of the result
   (run the image's Python on the host against the layer contents) ->
   platform-lab's publish step.
3. Check: build twice from a clean tree, same digest; Kyverno admits it,
   and rejects the same image unsigned (as platform-lab's admission test).

Open for the user, measured before choosing:

- Base image: a Python slim image, a distroless Python image, or an Alpine
  Python image (musllinux wheels). Choose by Trivy findings (the gate fails
  on fixable CRITICAL), size and Python version, with one candidate per
  family scanned with `PUSH=0` (no push, no key).
- Option B instead, if an image later needs `RUN` steps (system packages).

## Documentation (vendor first; videos: none confirmed)

- crane: [README](https://github.com/google/go-containerregistry/blob/main/cmd/crane/README.md),
  [crane append](https://github.com/google/go-containerregistry/blob/main/cmd/crane/doc/crane_append.md),
  [crane mutate](https://github.com/google/go-containerregistry/blob/main/cmd/crane/doc/crane_mutate.md)
- buildah: [buildah.io](https://buildah.io/); podman build:
  [docs.podman.io](https://docs.podman.io/en/latest/markdown/podman-build.1.html)
- BuildKit: [github.com/moby/buildkit](https://github.com/moby/buildkit),
  [docs.docker.com/build/buildkit](https://docs.docker.com/build/buildkit/)
- kaniko: the original [GoogleContainerTools/kaniko](https://github.com/GoogleContainerTools/kaniko)
  is archived; maintained fork [chainguard-dev/kaniko](https://github.com/chainguard-dev/kaniko)
- `SOURCE_DATE_EPOCH`: [reproducible-builds.org](https://reproducible-builds.org/docs/source-date-epoch/)
