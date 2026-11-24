#!/usr/bin/env bash
# Footprint of each agent-runtime candidate (ADR 0002): what it adds on top
# of a Python base image. For each candidate: a clean venv with the pinned
# packages, then package count, installed size, import time and memory,
# licences (syft SBOM) and known vulnerabilities (trivy rootfs). No endpoint
# calls. pip is uninstalled from each venv before the SBOM and the scan: the
# runtime image does not need it, and its vendored copies (urllib3, msgpack,
# setuptools, ...) would otherwise be counted against every candidate.
# (`trivy fs` reads lock files only and finds nothing in a venv: measured
# 11/23, 0 results; `rootfs` reads the installed packages.) Work files in build/runtime-footprint/ (gitignored); the summary
# goes to stdout (commit it to docs/scans/).
#
# Versions: the highest release on or before 2026-11-09 (two weeks before
# the measurement), per the repo's pinning rule.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${WORK:-$ROOT/build/runtime-footprint}"
PY="${PY:-python3}"

# name | pip requirements | modules to import
CANDIDATES=(
  "plain-stdlib||json,urllib.request"
  "plain-openai|openai==3.46.0|openai"
  "pydantic-ai|pydantic-ai-slim[openai]==2.66.0|pydantic_ai,pydantic_ai.models.openai"
  "langgraph|langgraph==1.2.20 langchain-openai==1.7.4|langgraph.prebuilt,langchain_openai"
  "smolagents|smolagents==1.26.0 openai==3.46.0|smolagents"
)

mkdir -p "$WORK"
echo "# runtime-footprint $(date -u +%FT%TZ)"
echo "# $("$PY" --version), pip $("$PY" -m pip --version | awk '{print $2}'), $(trivy --version | head -1), $(syft version 2>/dev/null | awk '/^Version/ {print "syft " $2}')"
echo
printf '%-14s %5s %9s %10s %10s  %s\n' candidate pkgs "size MiB" "import s" "RSS MiB" "vulns C/H/M/L"
for c in "${CANDIDATES[@]}"; do
  IFS='|' read -r name reqs mods <<<"$c"
  d="$WORK/$name"
  rm -rf "$d" && "$PY" -m venv "$d/venv"
  if [[ -n "$reqs" ]]; then
    # shellcheck disable=SC2086
    "$d/venv/bin/pip" install -q --no-cache-dir --disable-pip-version-check $reqs >"$d/pip.log" 2>&1 ||
      { echo "$name: pip install failed (see $d/pip.log)"; continue; }
  fi
  "$d/venv/bin/pip" list --format=json --disable-pip-version-check >"$d/packages.json"
  site="$("$d/venv/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
  # Packages the candidate adds (pip itself comes with every venv).
  pkgs=$("$PY" -c 'import json,sys; print(len([p for p in json.load(open(sys.argv[1])) if p["name"] != "pip"]))' "$d/packages.json")
  pip_kib=$(du -sk "$site"/pip "$site"/pip-*.dist-info 2>/dev/null | awk '{s+=$1} END {print s+0}')
  size=$(du -sk "$site" | awk -v p="$pip_kib" '{printf "%.1f", ($1 - p) / 1024}')
  imp=$("$d/venv/bin/python" - "$mods" <<'EOF'
import importlib, resource, sys, time
t = time.perf_counter()
for m in sys.argv[1].split(","):
    importlib.import_module(m)
dt = time.perf_counter() - t
print(f"{dt:.2f} {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f}")
EOF
)
  "$d/venv/bin/python" -m pip uninstall -y -q pip >/dev/null 2>&1
  syft scan "dir:$site" -q -o spdx-json="$d/sbom.spdx.json" -o syft-json="$d/sbom.syft.json" 2>/dev/null
  trivy rootfs -q --scanners vuln --list-all-pkgs --format json -o "$d/trivy.json" "$site" 2>/dev/null
  vulns=$("$PY" - "$d/trivy.json" <<'EOF'
import json, sys, collections
c = collections.Counter()
n = 0
for r in json.load(open(sys.argv[1])).get("Results") or []:
    n += len(r.get("Packages") or [])
    for v in r.get("Vulnerabilities") or []:
        c[v["Severity"]] += 1
print("/".join(str(c[s]) for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")) + f" ({n} pkgs scanned)")
EOF
)
  printf '%-14s %5s %9s %10s %10s  %s\n' "$name" "$pkgs" "$size" ${imp} "$vulns"
done

echo
echo "## Packages and licences per candidate (from the syft SBOM)"
for c in "${CANDIDATES[@]}"; do
  name="${c%%|*}"
  f="$WORK/$name/sbom.syft.json"
  [[ -f "$f" ]] || continue
  echo "### $name"
  "$PY" - "$f" <<'EOF'
import json, sys
arts = json.load(open(sys.argv[1]))["artifacts"]
rows = sorted({(a["name"], a["version"], ", ".join(sorted({l.get("value") or l.get("spdxExpression") or "?" for l in a.get("licenses") or []})) or "UNKNOWN") for a in arts if a["name"] != "pip"})
for n, v, l in rows:
    print(f"  {n}=={v}  {l}")
EOF
done

echo
echo "## Vulnerabilities found (trivy rootfs)"
for c in "${CANDIDATES[@]}"; do
  name="${c%%|*}"
  f="$WORK/$name/trivy.json"
  [[ -f "$f" ]] || continue
  "$PY" - "$f" "$name" <<'EOF'
import json, sys
for r in json.load(open(sys.argv[1])).get("Results") or []:
    for v in r.get("Vulnerabilities") or []:
        print(f"  {sys.argv[2]}: {v['PkgName']} {v['InstalledVersion']} {v['VulnerabilityID']} {v['Severity']} fixed in {v.get('FixedVersion') or '-'}")
EOF
done
