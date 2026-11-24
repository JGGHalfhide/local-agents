#!/usr/bin/env bash
# Snapshot of a node's capacity, scheduled requests/limits and actual usage,
# per namespace, plus host memory. Input for docs/resource-plan.md.
# Usage: KUBECONFIG=... scripts/node-resources.sh > docs/scans/<name>.txt
# Read-only: kubectl get/describe/top, free on the host and in the guest.
set -euo pipefail

SSH_KEY=${SSH_KEY:-$HOME/.ssh/platform-lab_ecdsa}
SSH_USER=${SSH_USER:-rocky}
NODE=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
NODE_IP=$(kubectl get node "$NODE" -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')

echo "# node-resources $(date -u +%FT%TZ) node=$NODE"
echo
echo "## kubectl version"
kubectl version 2>/dev/null | sed 's/^/  /'
echo
echo "## Capacity and allocatable"
kubectl get node "$NODE" -o jsonpath='capacity:    cpu={.status.capacity.cpu} memory={.status.capacity.memory}{"\n"}allocatable: cpu={.status.allocatable.cpu} memory={.status.allocatable.memory}{"\n"}'
echo
echo "## Allocated resources (kubectl describe node)"
kubectl describe node "$NODE" | sed -n '/^Allocated resources:/,/^Events:/p' | sed '$d'
echo
echo "## Requests and limits per namespace (MiB, millicores; running pods)"
kubectl get pods -A --field-selector=status.phase=Running -o json | python3 -c '
import json, sys, collections
def mem(v):
    if not v: return 0
    u = {"Ki": 1/1024, "Mi": 1, "Gi": 1024, "K": 1/1048.576, "M": 1/1.048576, "G": 1000/1.048576}
    for k, f in u.items():
        if v.endswith(k): return float(v[:-len(k)]) * f
    return float(v) / 1048576
def cpu(v):
    if not v: return 0
    return float(v[:-1]) if v.endswith("m") else float(v) * 1000
t = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
for p in json.load(sys.stdin)["items"]:
    ns = p["metadata"]["namespace"]; t[ns][4] += 1
    for c in p["spec"]["containers"]:
        r = c.get("resources", {})
        t[ns][0] += cpu(r.get("requests", {}).get("cpu"))
        t[ns][1] += mem(r.get("requests", {}).get("memory"))
        t[ns][2] += cpu(r.get("limits", {}).get("cpu"))
        t[ns][3] += mem(r.get("limits", {}).get("memory"))
print("%-24s%5s%9s%9s%9s%9s" % ("namespace", "pods", "cpu req", "mem req", "cpu lim", "mem lim"))
s = [0, 0, 0, 0, 0]
for ns in sorted(t):
    a = t[ns]; s = [x + y for x, y in zip(s, a)]
    print(f"{ns:<24}{a[4]:>5}{a[0]:>9.0f}{a[1]:>9.0f}{a[2]:>9.0f}{a[3]:>9.0f}")
print("%-24s%5d%9.0f%9.0f%9.0f%9.0f" % ("TOTAL", s[4], s[0], s[1], s[2], s[3]))
'
echo
echo "## Actual usage: kubectl top node"
kubectl top node --no-headers 2>&1 | sed 's/^/  /' || true
echo
echo "## Actual usage per namespace (kubectl top pods, MiB / millicores)"
kubectl top pods -A --no-headers 2>/dev/null | awk '
  { m=$4; sub(/Mi$/,"",m); c=$3; sub(/m$/,"",c); mem[$1]+=m; cp[$1]+=c; tm+=m; tc+=c }
  END { printf "%-24s%9s%9s\n","namespace","cpu","mem"; for (n in mem) printf "%-24s%9d%9d\n", n, cp[n], mem[n] | "sort"; close("sort"); printf "%-24s%9d%9d\n","TOTAL",tc,tm }'
echo
echo "## Guest memory (free -m on $NODE)"
ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$NODE_IP" free -m </dev/null 2>&1 | sed 's/^/  /' || echo "  (ssh failed)"
echo
echo "## Guest disk (df -h / /var on $NODE)"
ssh -i "$SSH_KEY" -o BatchMode=yes "$SSH_USER@$NODE_IP" df -h / /var </dev/null 2>/dev/null | sed 's/^/  /' || echo "  (ssh failed)"
echo
echo "## Host memory (free -m on the build host)"
free -m | sed 's/^/  /'
echo
echo "## Running libvirt domains"
virsh -c qemu:///system list 2>&1 | sed 's/^/  /' || true
echo
echo "## libvirt domain size and qemu RSS (host side)"
for d in $(virsh -c qemu:///system list --name 2>/dev/null); do
  virsh -c qemu:///system dominfo "$d" | grep -E '^(Name|CPU\(s\)|Max memory)' | sed 's/^/  /'
done
ps -C qemu-system-x86_64 -o pid=,rss= 2>/dev/null | awk '{printf "  qemu pid %s rss %d MiB\n", $1, $2/1024}'
echo
echo "## Inference pod resources (llm/llama-server spec; replicas may be 0)"
kubectl get deploy llama-server -n llm -o jsonpath='  replicas={.spec.replicas} resources={.spec.template.spec.containers[0].resources}{"\n"}' 2>&1 || true
