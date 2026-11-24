# Resource plan: agents next to the inference pod

Status: accepted and applied (Week 1, 11/23). Both VMs 12 vCPU / 20 GiB,
one at a time; changed in platform-lab (terraform/variables.tf).

The question: do agents, tools, an embedding model, a vector store and
tracing fit on a node that already runs the platform and the inference pod,
with the two VMs still running one at a time on one host? The answer
depends on the measured platform, the measured inference pod, and an agent
stack that is estimated until it is built (Weeks 2-4).

## Measured (11/23)

Raw output: [scans/week1-node-resources.txt](scans/week1-node-resources.txt),
from [scripts/node-resources.sh](../scripts/node-resources.sh) (read-only:
`kubectl describe node`, `kubectl top`, `free` and `df` in the guest, `free`
and qemu RSS on the host). Taken on build-node-01 (8 vCPU / 16 GiB, RKE2
v1.36.5) after the post-boot settle (etcd and kube-apiserver 2 minutes
without a restart), with the inference pod scaled to zero.

| | CPU | Memory |
|---|---|---|
| Node allocatable | 8 | 15,732 MiB |
| Platform requests (42 pods, 10 namespaces) | 3,350 m | 6,976 MiB |
| Platform actual (`kubectl top pods`, idle) | 0.24 cores | 7,744 MiB |
| Inference pod requests (`llm/llama-server`, scaled to zero at the time) | 4,000 m | 5,120 MiB (limit 6,144) |
| **Requests with the inference pod** | **7,350 m** | **12,096 MiB** |
| **Left for the agent stack (requests)** | **650 m** | **3,636 MiB** |

- The platform grew since local-airgap-LLM's 11/22 measurement (10.2 GiB
  requested with the pod, before KEDA and the dashboards): now 11.8 GiB.
  KEDA alone requests 600 m CPU and 600 MiB.
- Actual platform memory (7.7 GiB) is above its requests (7.0 GiB):
  requests understate what the node really carries.
- The inference pod's process peaks at 4.66 GiB, but its cgroup sits at the
  6 GiB limit with the model file's page cache charged to it
  (local-airgap-LLM docs/resource-plan.md). Plan for 6 GiB actual.
- Guest disk: 27 of 39 GiB used (69%), 13 GiB free. Kubelet's default
  image garbage collection starts at 85% (33 GiB).
- Host: 28,884 MiB total; with build-node-01 running, qemu RSS is
  16,311 MiB (the whole guest is backed) and the host's own use is about
  3 GiB; 9.5 GiB available.

## Agent stack: estimated budget

Estimates until each piece is built and measured; each row is replaced by
a measurement in the week shown.

| Component | CPU request | Memory request | Measured in |
|---|---|---|---|
| Triage agent (one replica, plain loop or framework, ADR 0001) | 100 m | 256 MiB | Week 1 spike / Week 2 |
| Read-only tools (Kubernetes, Prometheus, Loki), in-process or 3 small servers | 150 m | 192 MiB | Week 2 |
| Embedding model (llama-server embedding mode, small model, CPU) | 1,000 m | 1,024 MiB | Week 3 |
| Vector store (pgvector) | 250 m | 512 MiB | Week 3 |
| Tracing backend (single binary, local storage; OTLP via Alloy) | 200 m | 512 MiB | Week 4 |
| Eval runner (Job, while an eval runs) | 100 m | 256 MiB | Week 1 |
| **Total** | **1,800 m** | **2,752 MiB** | |

Disk, same method: agent and tool images, the embedding model (registry
copy plus the node's copy), pgvector, the tracing backend, the index and
traces add an estimated 4-6 GiB, which puts build-node-01 at 31-33 of
39 GiB, at or near the image-GC threshold.

## Does it fit at 8 vCPU / 16 GiB?

| | Requested | Allocatable | |
|---|---|---|---|
| CPU | 7,350 + 1,800 = 9,150 m | 8,000 m | **Does not schedule** |
| Memory (requests) | 12,096 + 2,752 = 14,848 MiB | 15,732 MiB | Fits, 0.9 GiB slack |
| Memory (expected actual) | 7.7 + 6.0 + 2.7 = 16.4 GiB | 15.4 GiB | **Over** |

CPU requests do not fit: the inference pod's 4-CPU request leaves 650 m.
Cutting requests to squeeze in does not help at run time either: during a
triage run, llama-server uses 6-8 threads on prompts while the embedding
model embeds the query and the tools run on the same 8 vCPUs. Memory fits
by requests only, with less than 1 GiB slack, and does not fit by expected
actual use.

## Recommendation: 12 vCPU / 20 GiB per VM, still one at a time

| | Allocatable (est.) | Requested | Slack |
|---|---|---|---|
| CPU | 12 | 9.15 | 2.85 cores |
| Memory | about 19.3 GiB (20,480 - 653 MiB, as at 16 GiB) | 14.5 GiB | about 4.9 GiB (about 3 GiB by expected actual use) |
| Host left with one VM running | | | about 5 GiB (28.2 - 20 - 3 host) |

- **Why 20 GiB, not 24:** at 24 GiB the host keeps about 1.5 GiB, too
  little for `zarf package create` and the image builds that run on the host
  while the build VM is up. At 20 GiB the slack (about 5 GiB) covers the
  estimates being wrong by half, or a second embedding/reranker model.
- **Why 12 vCPUs, not 16:** 4 host threads stay free for the host's
  builds. Inference speed is limited by memory bandwidth, not cores
  (local-airgap-LLM benchmarks: 4 threads within 3% of 8), so llama-server
  keeps `-t 6 -tb 8`; the extra cores go to the agents, tools and
  embeddings running next to it.
- **Still one VM at a time:** 2 x 20 GiB does not fit in 28.2 GiB (neither
  does 2 x 16 today).
- **Disk:** build-node-01's 40 GiB disk cannot grow in place (libvirt
  provider 0.9.x replaces volumes). Measure disk in Week 2 as images land;
  if it passes 80%, either prune old images or grow the disk at the Week 6
  full rebuild (that rebuilds the VMs anyway). The rehearsal VM has 60 GiB.

## Change in platform-lab (11/23)

- `terraform/variables.tf` defaults: `vcpus = 12`, `memory_mib = 20480`,
  `rehearsal_vcpus = 12`, `rehearsal_memory_mib = 20480`; descriptions
  point here.
- Applies in place but needs a power cycle (`virsh shutdown` + `virsh
  start`); `terraform apply` starts both VMs, so shut the idle one down
  straight after.
- Re-measure with this script after the change and record the result here.
- Note the change in local-airgap-LLM's resource-plan.md (the node it
  sized).

## As applied (11/23)

Raw output:
[scans/week1-node-resources-12cpu-20g.txt](scans/week1-node-resources-12cpu-20g.txt),
same script, build-node-01 after the post-boot settle, inference pod
scaled to zero.

| | Before (8 vCPU / 16 GiB) | After (12 vCPU / 20 GiB) |
|---|---|---|
| Node allocatable | 8 CPU / 15,732 MiB | 12 CPU / 19,739 MiB |
| Platform requests | 3,350 m / 6,976 MiB | unchanged |
| Left for the agent stack, with the inference pod's requests | 650 m / 3,636 MiB | 4,650 m / 7,643 MiB |
| Guest `free` available (pod at zero) | 9,155 MiB | 13,442 MiB |
| Host available, one VM running | 9,573 MiB | 7,214 MiB (qemu RSS 19,121 MiB, still growing to about 20 GiB as the guest touches its memory) |

The rehearsal VM was resized the same way and checked from inside the
guest (12 CPUs, 19,738 MiB), then shut down again; its cluster was not
started.

How it was applied (platform-lab, from `terraform/`), one VM at a time
because both modules set `running = true` and a full apply (or `make up`)
would start both, 40 GiB on a 28 GiB host:

1. `virsh shutdown build-node-01`; `terraform plan -target=module.build_node
   -var airgap_rehearsal=true`; check the plan; `terraform apply` of that
   plan (starts the VM at the new size).
2. Settle, measure, then `virsh shutdown build-node-01`.
3. Same for `-target=module.airgap_rehearsal`; check the guest; `virsh
   shutdown airgap-rehearsal`; `virsh start build-node-01`.

`-var airgap_rehearsal=true` is needed while that VM is in state: the
default (`false`) plans to destroy it (`make` sets it from the state).

Snag found: each plan also replaced the VM's cloud-init seed volume
(`<vm>-seed.iso`). Cause: the libvirt provider keeps the generated ISO in
`/tmp/terraform-provider-libvirt-cloudinit/`, which is tmpfs on the host and
was cleared by the host reboot at 18:31; Terraform then sees the cloud-init
disk as deleted. The rebuilt ISO has the same content and instance-id, so
cloud-init does not run again; the root disks were not touched. This
happens on any apply after a host reboot.

Follow-up, done the same day in platform-lab: Terraform now starts a VM
only when it creates it (`lifecycle { ignore_changes = [running] }` in
modules/rocky-vm), and `scripts/vm-power.sh` (`make vm-start` /
`make vm-stop`) runs the VMs one at a time: it refuses to start one while
the other runs, or when the host's available memory is below the VM's size
plus 2 GiB. `make up` and `make rehearsal` run the same check before
Terraform. Tested 11/23 with build-node-01 running: starting the rehearsal
VM was refused (build VM running; and, with that check skipped, 6,103 MiB
available against 22,528 MiB needed); both plans show no changes. The IP
outputs are null while a VM is off, so `make inventory` falls back to the
reserved addresses.
