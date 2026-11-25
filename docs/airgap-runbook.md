# Airgap runbook

How the status reporter gets onto the disconnected cluster (the
`airgap-rehearsal` VM, 192.168.122.20, standing in for the iMac) and is
checked there. Same flow as
[platform-lab](https://github.com/JGGHalfhide/platform-lab/blob/main/docs/airgap-runbook.md)
and
[local-airgap-LLM](https://github.com/JGGHalfhide/local-airgap-LLM/blob/main/docs/airgap-runbook.md):
everything is built and signed on the connected build host, carried over
as Zarf packages, and deployed with the node's egress blocked. Their
scripts are reused, not copied: platform-lab's `scripts/airgap-packages.sh`
(build and sign) and its `zarf` Ansible role (deploy), local-airgap-LLM's
`scripts/zarf-pull-secret.sh` (eval namespaces).

## What goes over

| Package | Repo | Version | Size | Contents |
|---|---|---|---|---|
| agents | local-agents (`zarf/agents`) | 0.5.1 | 50 MB | `deploy/agents` as Argo CD syncs it on the build cluster (namespace, RBAC, NetworkPolicies, the prompts ConfigMap from `deploy/agents/prompts/`, Deployment, Service, hourly CronJob); the agent image by digest with its cosign `.sig` and SBOM `.att` |
| monitoring | platform-lab | 0.8.0 | 1.1 GB | Prometheus, Grafana, Loki, Alloy and Tempo (traces, ADR 0008), the Grafana Tempo datasource, the dashboards including the status reporter's |
| policies | platform-lab | 0.8.0 | 8 KB | the Kyverno policies; `platform-bootstrap-images` lists `docker.io/grafana/tempo:` |
| llm, llm-smoke | local-airgap-LLM | 0.7.0, 0.5.0 | 3.5 GB, 2.9 GB | the endpoint with `--ctx-checkpoints 4` and thinking off by default; llm-smoke also carries the signed alpine image the eval cases use |
| platform, sample-app, keda | platform-lab | 0.6.0, 0.6.0, 0.8.0 | as built 11/23 | unchanged; sample-app carries the signed podinfo image the eval cases use |

The agent image is the one the build cluster runs
(`local-agents/agent:854e81c`, `sha256:26e744ae...`); the Zarf agent
rewrites it to `127.0.0.1:31999/...` and Kyverno verifies its signature
through the Zarf registry.

## Steps

### 1. Build the packages (build host, build-node-01 running)

Images and signatures come from the build cluster's registry.

```bash
make airgap-packages                                  # this repo: agents
make -C ../local-airgap-LLM airgap-packages           # llm, llm-smoke
cd ../platform-lab && scripts/airgap-packages.sh policies monitoring
```

Each package is signed with the lab cosign key and checked against
`pki/cosign.pub`. Bump a package's version in its `zarf.yaml` **and** in
platform-lab's `ansible/roles/zarf/defaults/main.yml` (platform-lab's own
packages are deployed at the pinned version; see Results).

### 2. Switch VMs

```bash
cd ../platform-lab && make vm-stop VM=build-node-01 && make vm-start VM=airgap-rehearsal
```

Wait until etcd and kube-apiserver go 2 minutes without a restart, and the
Zarf registry and agent are Ready.

### 3. Deploy (egress blocked)

```bash
make airgap-deploy
```

Runs platform-lab's `airgap-deploy.yml`: platform-lab's packages at their
pinned versions, then llm, llm-smoke (from local-airgap-LLM's build
directory) and agents. Unchanged packages are skipped; `zarf init` is
skipped when its record exists (it must not re-run under the policies).

### 4. Verify

- `curl https://github.com` on the node fails (`No route to host`).
- Every package record in `zarf/zarf-package-*` has all components
  `Succeeded`.
- 0 image pull errors after the deploy started.
- Unsigned image: deploy platform-lab's `admission-test-unsigned` package
  (the image is then in the Zarf registry), apply
  `tests/airgap/unsigned-pod.yaml`: denied for the signature.
- One status run (`agentctl status` through a port-forward) and its trace
  in this cluster's Tempo.

### 5. Evaluation on the airgapped cluster

```bash
KUBECONFIG=../platform-lab/kubeconfig-airgap eval/status/run_eval.py results/week5-airgap-status-eval
```

`inject.sh` and `cleanup.sh` accept the build cluster and this cluster
only. Each case namespace gets a copy of Zarf's pull Secret
(local-airgap-LLM `scripts/zarf-pull-secret.sh`), except f02: here
`127.0.0.1:31999` is the real Zarf registry, so f02's image-pull fault is
the missing pull credential (`no basic auth credentials`), the airgap's own
pull failure. Avoid the top of the hour: the hourly CronJob holds the API
for about a minute and a case then gets 429 (busy).

## Results (11/25, airgap-rehearsal, egress blocked)

| Step | Result |
|---|---|
| Packages built and signed | agents 50 MB (3 s), monitoring 1.1 GB (63 s), llm 3.5 GB (39 s), llm-smoke 2.9 GB (20 s), policies 8 KB (1 s) |
| `make airgap-deploy` | llm, llm-smoke, agents 73 s; policies and monitoring 82 s; agents 0.5.1 55 s; `zarf init` skipped every time |
| Package records | 10 packages (with admission-test-unsigned), every component `Succeeded` |
| Image pull errors | 0 from the deploys. 18 events in `keda` at the two boots (14:54, 15:10): KEDA's pods pull before the Zarf registry pod is Ready; all recovered within seconds |
| Images in the pods | `127.0.0.1:31999/local-agents/agent@sha256:26e744ae...`, `127.0.0.1:31999/grafana/tempo@sha256:64e2fbd5...` (with `GOMEMLIMIT`), the signed digests |
| Unsigned image | rejected: `Policy verify-platform-images failed: image is not signed with the platform-lab cosign key` (image present in the Zarf registry) |
| Status run | 66.8 s, 8 tool calls, 2 real findings (a CronJob Job that missed its deadline while the VM was off; the unsigned test pod); trace of 14 spans in Tempo; dashboard loaded |
| Fault-injection eval | **faults 8/8, controls 5/5 healthy, no ambient findings**, median 47.7 s (build cluster: 49.4 s); `results/week5-airgap-status-eval/` |

Raw output: [scans/week5-airgap-verify.txt](scans/week5-airgap-verify.txt).

Found during the run and fixed:

- **Three stale packages.** monitoring and llm were built 11/23, before
  Tempo and the `--ctx-checkpoints` fix; both were bumped and rebuilt.
  Then the zarf role still deployed monitoring 0.7.0 (its version pin is
  separate from `zarf.yaml`; platform-lab 261711e), and Kyverno denied
  Tempo: the policies package predated Tempo's entry in
  `platform-bootstrap-images` (policies 0.8.0, 221693e). Check every
  package whose sources changed since its build, including those built
  from a kustomization (`zarf/policies` reads `gitops/policies`).
- **A boot-time warning as a false fault.** RKE2's addon controller failed
  to apply local-path-storage while Kyverno started
  (`ApplyManifestFailed`), then applied it seconds later. The first eval
  pass reported it in 7 of 13 runs (every control came back `fault`;
  `first-pass/`). `list_events` now treats a failure followed by its
  success on the same object as resolved (`RESOLVED_BY` in
  agent/tools.py; image 854e81c).
- **A CronJob run across a VM shutdown** misses its 420 s deadline and
  stays a failed Job: the agent reports it (correctly). The failed Job and
  the unsigned test's events were deleted (the user's OK) before the eval.
- **The hourly CronJob collided with f10** (429 twice); f10 was rerun
  alone.
- The monitoring 0.8.0 archive built first kept an older description; it
  was rebuilt with the policies package so the archive matches the repo.
