#!/usr/bin/env bash
# Build the agent image reproducibly with crane, no daemon and no root
# (docs/image-build.md, option A). Output: an OCI layout for platform-lab's
# publish script (SBOM, Trivy gate, push to Zot, cosign sign + verify).
#
#   scripts/build-agent-image.sh            (or: make agent-image)
#
# 1. Install agent/requirements.lock (hashes required, wheels only, no .pyc)
#    plus the agent/ package into a staging tree under /opt/agent.
# 2. Pack it as one layer: sorted entries, fixed owner, mode and mtime
#    (SOURCE_DATE_EPOCH = the last commit's time), so the same inputs give
#    the same bytes.
# 3. Serve a throwaway in-memory registry (crane registry serve), copy the
#    pinned base into it (linux/amd64 only), append the layer and set
#    entrypoint, user, workdir and environment with crane mutate, then pull
#    the result as an OCI layout to build/agent-image/oci.
# 4. Import check: the host's CPython (same 3.14 line as the base) imports
#    openai and agent from the staged tree.
# Prints the image digest; building twice from the same commit gives the
# same digest.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# python:3.14.9-slim-trixie, built 10/21; Trivy gate passed 11/24 (0 CRITICAL).
BASE="${BASE:-docker.io/library/python:3.14.9-slim-trixie@sha256:35caba83af2fe6da9a5d922f9b0156f21d1246a48278c58a08bd253303ba42e8}"
PY_VERSION="${PY_VERSION:-3.14}"
PORT="${PORT:-5011}"
USER_ID=65532
OUT="$ROOT/build/agent-image"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git -C "$ROOT" log -1 --format=%ct)}"

rm -rf "$OUT/stage" "$OUT/oci" "$OUT/layer.tar" "$OUT/wheels"
mkdir -p "$OUT/stage/opt/agent/site-packages" "$OUT/stage/opt/agent/app" "$OUT/wheels"

echo "==> Dependencies from agent/requirements.lock (hashes required)"
python3 -m pip download -q --disable-pip-version-check --only-binary=:all: --require-hashes \
  --python-version "$PY_VERSION" --implementation cp \
  --platform manylinux_2_28_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux2014_x86_64 \
  -d "$OUT/wheels" -r "$ROOT/agent/requirements.lock"
python3 -m pip install -q --disable-pip-version-check --no-index --find-links "$OUT/wheels" \
  --require-hashes --only-binary=:all: --no-compile --no-deps \
  --python-version "$PY_VERSION" --implementation cp \
  --platform manylinux_2_28_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux2014_x86_64 \
  --target "$OUT/stage/opt/agent/site-packages" -r "$ROOT/agent/requirements.lock"
# pip's own records hold install-time paths and are not needed at run time.
find "$OUT/stage/opt/agent/site-packages" -name RECORD -path '*.dist-info/*' -delete
find "$OUT/stage/opt/agent/site-packages" -name INSTALLER -path '*.dist-info/*' -delete
find "$OUT/stage" -name __pycache__ -type d -prune -exec rm -rf {} +

echo "==> Agent code"
(cd "$ROOT" && find agent -name '*.py' -not -path '*/__pycache__/*' -print0 |
  xargs -0 -I{} cp --parents {} "$OUT/stage/opt/agent/app/")

echo "==> Layer (reproducible tar, mtime $SOURCE_DATE_EPOCH)"
chmod -R u=rwX,go=rX "$OUT/stage"
tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner \
  --pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime \
  -C "$OUT/stage" -cf "$OUT/layer.tar" opt
sha256sum "$OUT/layer.tar" | awk '{print "    layer sha256:" $1}'

echo "==> Image (crane, in-memory registry on 127.0.0.1:$PORT)"
crane registry serve --address "127.0.0.1:$PORT" >"$OUT/registry.log" 2>&1 &
reg_pid=$!
trap 'kill $reg_pid 2>/dev/null' EXIT
for _ in $(seq 50); do curl -sf "http://127.0.0.1:$PORT/v2/" >/dev/null && break; sleep 0.1; done
local_base="127.0.0.1:$PORT/base"
crane copy --platform linux/amd64 "$BASE" "$local_base:src" >/dev/null
crane mutate --insecure "$local_base:src" \
  --append "$OUT/layer.tar" \
  --entrypoint python3,-m,agent \
  --env PYTHONPATH=/opt/agent/site-packages:/opt/agent/app \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --user "$USER_ID:$USER_ID" \
  --workdir /opt/agent \
  -l org.opencontainers.image.source=https://github.com/JGGHalfhide/local-agents \
  -l org.opencontainers.image.revision="$(git -C "$ROOT" rev-parse HEAD)" \
  -l org.opencontainers.image.base.name="${BASE%@*}" \
  -l org.opencontainers.image.base.digest="${BASE#*@}" \
  -t "127.0.0.1:$PORT/local-agents/agent:build" >/dev/null
crane pull --insecure --format=oci "127.0.0.1:$PORT/local-agents/agent:build" "$OUT/oci"
digest="$(crane digest --insecure "127.0.0.1:$PORT/local-agents/agent:build")"

echo "==> Import check (host CPython $(python3 -c 'import sys; print(sys.version.split()[0])'))"
python3 -S -c "
import sys
sys.path[:0] = ['$OUT/stage/opt/agent/site-packages', '$OUT/stage/opt/agent/app']
sys.argv = ['agent', '--version']
import agent.__main__ as m
import agent.loop, agent.tools, agent.k8s  # every module imports, not only the entry point
sys.exit(m.main())"

echo "$digest" >"$OUT/digest"
echo "==> Built $digest (OCI layout $OUT/oci)"
