# local-agents

Airgapped AI agents on Kubernetes, CPU-only, calling the local LLM endpoint
from local-airgap-LLM. Built connected on the build cluster, packaged with
Zarf, deployed with no internet to the airgap VM. Phase 3, after
platform-lab (Phase 1, v1.0 11/18) and local-airgap-LLM (Phase 2, v1.1
11/23), in its own repo. About 7-10 hours per week.

## Relationship to the other two repos
- platform-lab (~/projects/platform-lab) provides the clusters: VMs
  (Terraform), OS hardening, RKE2, Argo CD, Zot, Kyverno and its policies,
  cosign key and lab CA, monitoring (Prometheus, Grafana, Loki, Alloy),
  Velero, KEDA, Zarf init and the airgap flow.
- local-airgap-LLM (~/projects/local-airgap-LLM) provides the model
  endpoint: llama-server with Qwen3.5 4B Q4_K_M, OpenAI-compatible, at
  `http://llm-api.llm.svc:8080` through the KEDA interceptor, scale to zero,
  the model as a signed OCI image volume.
- This repo provides the agents: agent workloads and their identity, tools,
  prompts and tool configs, tracing, the evaluation set and its
  results, the Zarf packages for all of it.
- Changes to the clusters are made in platform-lab; changes to the endpoint
  (auth, flags, a second model) in local-airgap-LLM, each with that repo's
  conventions, and noted in both repos. Reuse their scripts (platform-lab
  `make image`, `scripts/lib.sh`, `airgap-packages.sh`; local-airgap-LLM's
  `make model` pattern for any new model) rather than copying them.
- Read their CLAUDE.md, README.md and docs/ (platform-lab: stack.md,
  supply-chain.md, policy-map.md, airgap-runbook.md; local-airgap-LLM:
  stack.md, scaling.md, load-test.md, airgap-runbook.md, ADR 0006) before
  changing anything that touches them.

## Hardware
- Build host: GMKtec K8 Plus (Ryzen 7 8845HS, 8 cores / 16 threads,
  AVX-512, 32 GB RAM, ~28 GiB usable), Arch Linux, libvirt/QEMU/KVM at
  qemu:///system. Radeon 780M iGPU unused (CPU-only; iGPU deferred).
- build-node-01 (192.168.122.10) and airgap-rehearsal (192.168.122.20):
  both 12 vCPU / 20 GiB since 11/23 (platform-lab terraform vars vcpus,
  memory_mib, rehearsal_vcpus, rehearsal_memory_mib; docs/resource-plan.md),
  run ONE AT A TIME: one VM leaves the host about 5 GiB of its 28 GiB;
  2 x 20 GiB does not fit. Zarf packages are built while the build VM runs,
  then the VMs are switched.
- Node budget (docs/resource-plan.md): 12 CPU / 19.3 GiB allocatable;
  platform requests 3.35 CPU / 6.8 GiB, inference pod 4 CPU / 5 GiB
  (limit 6 GiB); about 4.6 CPU / 7.4 GiB of requests left for the agent
  stack (estimated 1.8 CPU / 2.7 GiB). Disk is the next limit: 27 of 39 GiB
  on build-node-01, image GC at 85%.
- Switch VMs with platform-lab's `make vm-stop VM=<name>` and
  `make vm-start VM=<name>` (scripts/vm-power.sh): start refuses while the
  other lab VM runs or the host lacks the VM's memory + 2 GiB. Terraform
  starts a VM only when it creates it (rocky-vm ignores `running` after
  that), and `make up` / `make rehearsal` run the same check first. Never
  `virsh start` a lab VM directly.
  After a host reboot every apply also replaces each VM's cloud-init seed
  volume (provider ISO in tmpfs /tmp): harmless, same content.

## Inherited facts about the endpoint (local-airgap-LLM v1.1)
- One stream: 14.3 tok/s, TTFT 1.9 s (213-token prompt). 4 slots; 18.2 tok/s
  at 4 concurrent; above 4, requests queue (TTFT 22 s at 8). Prompt
  processing ~110 tok/s. 32k context shared by the 4 slots.
- Cold start from zero ~6 s; scales to zero after 5 min idle. A KEDA
  operator restart scales it to zero at once.
- Memory under agent tool loops (11/24, found by this repo's ADR 0002
  smoke test): with llama-server's default 32 context checkpoints per slot,
  each tool-loop turn added 50-250 MiB and the pod was OOMKilled at 6 GiB.
  Fixed in local-airgap-LLM 98a86aa (ADR 0007 there): --ctx-checkpoints 4,
  peak 5.3 GiB flat. The 32k context is one unified KV pool shared by the 4
  slots (docs/scans/week1-llm-slots.txt).
- Thinking is OFF by default (ADR 0006 there). An agent opts in per request
  with `chat_template_kwargs: {"enable_thinking": true}`; the server caps
  thinking at 1024 tokens. Measured: thinking fixed 3/3 multi-step errors
  but looped to 8,192 tokens with no answer on 3/3 open-ended triage
  questions at temperature 0; a 256 budget made answers worse.
- Tool calling and JSON-schema output pass (5/5) with thinking on or off.
- Access: NetworkPolicy only, no API key (ADR 0001). A client must be a
  pod labelled `inference.local-airgap-llm/client: "true"` IN a namespace
  with the same label (both, one `from` entry in platform-lab
  gitops/keda/networkpolicy-interceptor.yaml).

## Decisions so far (11/24)
- Separate repo; same conventions as the other two.
- The endpoint stays fast, bounded and predictable by default; this repo
  decides when to pay for slower, better answers (thinking, longer
  contexts, a second model).
- Both VMs 12 vCPU / 20 GiB, one at a time (docs/resource-plan.md).
- Endpoint access: NetworkPolicy only, no API key (ADR 0001). Only agent
  pods get the client label (namespace and pod, via GitOps); tools stay
  unlabelled; agent/tool RBAC must not create pods or edit labels.
- First agent (ADR 0003, 11/24): a read-only platform STATUS REPORTER,
  scored automatically by fault injection in disposable `agent-eval-*`
  namespaces (docs/eval-status.md; no fault injected without the user's OK,
  platform components only with approval of the specific fault). Own
  ServiceAccount; get/list/watch only on pods, events, workloads,
  namespaces, nodes, PVCs, Argo CD Applications, KEDA objects; no Secrets,
  no pods/exec, no pods/log in v1.
- One agent only (ADR 0006, 11/24): no triage agent, no retrieval. The
  project shows the whole lab end to end: airgapped cluster, local LLM,
  one agent. Eval set v0 stays as the Week 1 baseline record.
- Tools (ADR 0007, 11/24): in-process functions in the agent image; no
  tool servers or MCP unless a second consumer or a write action needs one.
- Agent runtime (ADR 0002, 11/24): a plain tool loop on the openai SDK.
  Thinking off by default; per-request opt-in tested only after agent 1
  works. Client config backend-neutral (base URL, model, key from config);
  no hosted-model run planned yet.
- Everything else is open: see ROADMAP.md and Open questions.

## Conventions (same as platform-lab and local-airgap-LLM)
- Everything reproducible from the repos: no manual steps on VMs or clusters.
- Ansible idempotent (second run changed=0); Terraform typed vars with
  descriptions.
- Pin every version: images by digest (publish with `make image
  IMAGE=<ref>:<tag>@sha256:<digest>`: a tag alone can move upstream, as
  postgres did on 11/23), tools by version + checksum, models by SHA-256.
- Every image and model through the supply chain: SBOM, Trivy gate, cosign
  signature with the lab key, verified by Kyverno at admission.
- Run linters before committing (yamllint, plus whatever this repo adds).
- Conventional commits (feat:, fix:, docs:, chore:).
- No AI attribution in commits or PRs (no Co-Authored-By or "Generated with"
  lines).
- Tag the repo at the end of each week (v0.1, v0.2, ...). Each week ends
  with a rebuild check.
- ADRs in docs/adr/NNNN-title.md: decision and context only, with a
  "Status: accepted (Week N, MM/DD)" line; list each in docs/adr/README.md.
- Keep docs/stack.md, the README (status, results, diagram, image card if
  one is added) and CLAUDE.md current EVERY week, not at the end (at
  local-airgap-LLM's v1.0 they had drifted and landed after the tag).
- Numbers in docs come from measurements, with the raw output committed
  (docs/scans/ or results/) and the method stated.
- Secrets, kubeconfigs, model weights and state files are never committed.
  Secrets go in platform-lab's Ansible Vault (key
  ~/.config/platform-lab/vault-pass) unless this repo gets its own.
- Ask before terraform destroy or anything that deletes VMs, volumes or
  cluster state.
- Commit or push only when the user asks.

## How the user likes to work
- Decide by measurement: benchmark or test the options, then write the ADR.
  Give a recommendation, not a survey.
- Explain new concepts when asked (e.g. "what is thinking, why useful, why
  counterproductive"), plainly, while long jobs run.
- Scope calls: say which repo a change belongs in and why.
- Report failures and snags honestly, with the cause found before the fix;
  don't call a check passed until its exit code and output agree.
- Look before deleting (compare against what is committed; keep anything
  unique).
- Employer check: the user signs off; the agent lists every domain,
  hostname and email it finds.

## Ground rules
- Built from scratch on personal hardware.
- No configs, naming, hostnames, or architecture from any employer system.
- Models and data used: openly licensed; record source, license and SHA-256.

## Host safety notes (carried over)
- NEVER touch enp3s0 / NetworkManager "Wired connection 2": it is the
  Raspberry Pi wake-on-LAN link. eno1 was the iMac cable.
- In Claude Code sessions run ansible with `</dev/null`.
- Lab SSH key is ~/.ssh/platform-lab_ecdsa (FIPS rejects ed25519).
- After a platform-lab rebuild the registry is empty: republish every image
  with `make image` by tag@digest (both READMEs list them).
- Long steps (package builds, airgap-up/deploy, model pulls, evaluation
  runs): run detached (setsid nohup, logs in build/); session cut-offs kill
  background jobs.
- After a VM boot, let the cluster settle before deploying or testing: etcd
  and kube-apiserver restart a few times while RKE2 comes up (wait until
  they go 2 minutes without a restart), and KEDA's operator with them.
- `zarf init` cannot be re-run on the airgap cluster once the Kyverno
  policies are deployed (planned fix in platform-lab ROADMAP); an
  interrupted init means a fresh airgap VM.
- The airgap VM is left with egress blocked; `make airgap-reconnect` in
  platform-lab reopens it.

## Session notes
Running notes for the user live in ./NOTES.txt (same style as
~/platform-project.txt and local-airgap-LLM/NOTES.txt: dated entries,
numbered sections, what/why/result, "NEXT:" and "STILL OPEN:" lines).
Append to it at the end of each session. NOTES.txt is gitignored.

Standing preferences for the notes (user, 11/20):
- Every new tool gets links to its documentation and, where possible, videos,
  preferably from the vendor/project itself (official docs, project or CNCF
  channels). Check links resolve before adding; label non-vendor ones.
- When the user says they are done for the session: append the day's entry
  to NOTES.txt and email it with
  `~/scripts/sendme -s "<subject>" NOTES.txt [drafts...]` (short summary as
  the body, piped on stdin).

## Current status
Week 0 (11/23): planning only. This directory has CLAUDE.md, ROADMAP.md,
NOTES.txt, README.md (stub), LICENSE (MIT), .gitignore, .yamllint,
.github/workflows/ci.yml (yamllint + gitleaks, same pins as
local-airgap-LLM), Makefile (`make lint`), docs/adr/README.md (index, no
ADRs yet), docs/stack.md (skeleton).
Week 1 started (11/23): git repo created and pushed to
github.com/JGGHalfhide/local-agents (public, main); first CI run green
(yamllint + gitleaks, no leaks). gitleaks is not installed on the host, so
CI is the only secret scan. Resource plan accepted and applied: both VMs
12 vCPU / 20 GiB (docs/resource-plan.md, scripts/node-resources.sh,
docs/scans/week1-node-resources*.txt). Endpoint access decided: ADR 0001.
Eval set v0: 22 cases in eval/cases/ (all reconstructed from the notes,
error strings verbatim), docs/eval.md, `make eval-check` (also in CI);
scoring accepted 11/23: pattern first pass + the user's review of every
0, every harmful flag and 1 in 4 of the 2s.
Baseline tooling committed (eval/run_baseline.py, eval/review_sheet.py,
eval/prompts/baseline-system.txt); baseline run 11/23 (88/88 answers,
0 errors) into results/week1-baseline/; scores final 11/24 (pattern first
pass, scores assigned by Claude in chat for the 80 flagged answers,
finalized by the user): points of 88 off-greedy 38, off-qwen 30, on-greedy
49, on-qwen 42 (docs/eval.md). Runtime candidates
measured offline (scripts/runtime-footprint.sh,
docs/scans/week1-runtime-footprint.txt); the endpoint spike for ADR 0002
waits for the baseline (it would share the 4 slots).
Pivot 11/24 (ADR 0003): agent 1 = status reporter (triage dropped 11/24,
ADR 0006); ROADMAP.md, docs/eval.md updated; docs/eval-status.md (fault
injection spec) approved 11/24: faults f01 f02 f04-f08 f10, controls k1-k5,
f09 dropped, caps 1k tokens/tool result, 8 calls, 12k input/run; per-slot
n_ctx is one unified 32k pool (docs/scans/week1-llm-slots.txt). Stubs in
eval/status/ refuse to run; nothing injected yet.
Endpoint fix 11/24: agent tool loops OOMKilled llama-server; cause and fix
measured in local-airgap-LLM (ADR 0007, --ctx-checkpoints 4).
ADR 0002 (11/24): agent runtime = plain tool loop on the openai SDK (spike of
5 runtimes, eval/spike/, docs/scans/week1-runtime-spike.txt; plain loops 4/4,
langgraph 3/4, smolagents 2/4, pydantic-ai 0/4). Endpoint quirks every loop
must handle are in the ADR. Report quality was weak for all (false faults
from boot-time warnings and KEDA scale-to-zero): Week 2 tool design.
Scope (user, 11/24): smallest test that decides.
Week 1 tagged v0.1 (11/24; employer check signed off by the user).
Week 2 step 1 done (11/24, ADR 0004): agent image built with crane
(`make agent-image`, reproducible, locked wheels), published through
platform-lab's supply chain (`make image IMAGE=oci-layout:<dir>
NAME=<repo>:<tag>`, platform-lab 47c3d56): local-agents/agent:0.1.0 signed
and admitted; an unsigned test copy (tag 0.1.0-unsigned-test) is rejected
and stays in Zot as a test image. Gap for Week 2: no container image
builder on the host -> closed.
Week 2 step 2 done (11/24): the status reporter (agent/: k8s.py stdlib API
access GET only, tools.py 7 tools with the spike's lessons, loop.py openai
loop with turn cap, sanitising, look-first and grounding). First live run:
6 tool calls, 76 s, 0 false faults (docs/scans/week2-status-reporter-live.txt).
Week 2 step 3 done (11/24): deployed by Argo CD (platform-lab 55545f1 ->
deploy/ at 69b8cc3): namespace agents, ServiceAccount status-reporter,
read-only ClusterRole, NetworkPolicies, hourly CronJob (image
local-agents/agent:d0b286f, signed). Smoke (docs/scans/week2-identity-smoke.txt):
Secrets/logs/exec/writes denied; labelled pod reaches the endpoint, unlabelled
blocked; in-cluster report in 142 s with 1 false fault (llama-server
scaled-to-zero despite the KEDA label; proposed fix: drop such faults in code).
Note: `kubectl auth can-i get pods/log` means a pod named "log"; use
--subresource=log.
Week 2 step 4 + operator interface done (11/24): API v1 + agentctl (ADR 0005,
docs/interface.md), deployed (image e6ae522, signed); fault-injection eval
through the API: faults 8/8, controls 5/5 (results/week2-status-eval/,
first pass kept). f06/f08 are rejected by Kyverno at creation: visible only
as PolicyViolation events. Week 2 over its 7-10 h budget; web view is a
Week 5-6 stretch.
Week 2 close (11/24): tool interface decided (ADR 0007: tools stay
in-process functions, no MCP); docs/stack.md pipeline, data flow and
diagram written, Mermaid diagram in the README; eval follow-ups moved to
Week 3. Tagged v0.2 (11/24; employer check signed off; image rebuilt
byte-identical to the deployed digest).
Week 3 (11/24): follow-ups closed (images c4f5677, f906bd3; deployed
3cafb55): agentctl exit 3 = busy, the CronJob counts it as skipped;
negative-polarity conditions shown only when True; PolicyViolation events
located at the blocked object ("blocked at admission by <policy>").
Eval rerun: 8/8, 5/5, f06/f08 scored strictly, no ambient findings,
median 48.9 s (results/week3-status-eval/; first pass 7/8 and an f06
rerun kept). A leftover failed Job (Week 2's 429) pulled the model off f06;
deleted with the user's OK. The eval assumes an otherwise healthy cluster.
Tagged v0.3 (11/24; employer check signed off; image rebuilt
byte-identical). Next: Week 4 (tracing, prompts via GitOps, thinking opt-in).
Week 4 step 1 done (11/25, ADR 0008): tracing. Tempo 3.1.1 in platform-lab
(62262d6, grafana-community chart 3.2.1, monitoring ns, 7 days, Grafana
datasource); agent traces with the OpenTelemetry SDK (e06d4f4, image
sha256:14cece9d, deployed 1984e04): one trace per run, chat/execute_tool
spans, metadata only (no prompt, output or tool text), trace_id in the run
object. One run = 18 spans, 8.2 KiB; Tempo 29-152 MiB
(docs/scans/week4-tracing.txt). Follow-up: list_events still shows a
CronJob's boot-time FailedCreate (Kyverno/Zot not ready) after a later
SuccessfulCreate: one false fault in the traced run -> fixed (393577d).
Week 4 step 2 done (11/25): prompts and limits as files in
deploy/agents/prompts/ (configMapGenerator, hash suffix rolls the
Deployment; agent/profile.py loads them, AGENT_PROMPTS_DIR); runs record
config_sha256 (b085a9e3); CI fails unless results/*-status-eval/ has all 13
cases with the current config_sha256 (eval/status/check_config.py, in
`make eval-check`). Image 393577d, deployed 7e81b03. Eval: 8/8, 5/5, no
ambient findings, median 49.4 s (results/week4-status-eval/). Traces: the
final structured request is 35-45 s of every run.
Week 4 step 3 done (11/25): dashboard as code in platform-lab (1b20d42,
gitops/monitoring/dashboards/local-agents.json; 9 panels, TraceQL metrics
from Tempo; sits in platform-lab because Grafana's sidecar reads only the
monitoring namespace).
Week 4 step 4 done (11/25, ADR 0009): thinking on, same 13 cases: 8/8,
5/5, no ambient findings, median 149.8 s vs 49.4 s off: thinking stays off
for the status reporter (results/week4-thinking-status-eval/).
Snag 11/25: Tempo OOMKilled twice (512 MiB limit) while ~20 traces were read
in a row; idle 46 MiB, memory steps up per read. Probable cause: no
GOMEMLIMIT; proposed fix in platform-lab (limit 1 GiB, GOMEMLIMIT ~80%).
All 26 eval traces survived. Fixed in platform-lab a7ecf2c (limit 1 GiB,
GOMEMLIMIT 800MiB, request 256Mi): the same 26 reads in a row, 0 restarts,
618 MiB seen (docs/scans/week4-tempo-memory.txt). Thinking tokens:
median output 1,299 vs 231, none cut at max_tokens
(docs/scans/week4-thinking-tokens.txt).
Tagged v0.4 (11/25; employer check signed off; image at 393577d rebuilt
byte-identical, sha256:1c670a10).
Week 5 (11/25, docs/airgap-runbook.md): zarf/agents (0.5.1, image 854e81c
sha256:26e744ae, deployed on the build cluster 312ad1e); `make
airgap-packages` / `make airgap-deploy` reuse platform-lab's script and
zarf role. Rebuilt stale packages: platform-lab monitoring 0.8.0 (Tempo,
datasource, dashboard) and policies 0.8.0 (Tempo exception; Kyverno had
denied Tempo), the zarf role's version pins (261711e, 221693e);
local-airgap-LLM llm 0.7.0 (--ctx-checkpoints 4). Egress blocked; unsigned
image rejected with it present in the Zarf registry; 0 pull errors from the
deploys (KEDA pulls before the Zarf registry at boot: recovered).
inject.sh/cleanup.sh accept the airgap cluster (192.168.122.20); case
namespaces get Zarf's pull Secret except f02 (fault = missing pull
credential there). Eval there: 8/8, 5/5 healthy, no ambient findings,
median 47.7 s (results/week5-airgap-status-eval/; first pass kept: 7/13
runs reported RKE2's boot-time ApplyManifestFailed, fixed in 854e81c with
RESOLVED_BY in agent/tools.py). A failed CronJob Job (VM shut down mid-run)
and two unsigned-test events deleted with the user's OK. Lessons: bump the
zarf role pin with the package; a package built from a kustomization goes
stale with its sources; avoid the top of the hour (CronJob -> 429).
CI: gitleaks had failed since 98f6777 (v0.4 tagged on red CI, missed): a
false positive ("finish_reason=length" in a scan header); ignored by its
one fingerprint in .gitleaksignore with the user's OK (7bdedf3, CI green).
Check CI for the tagged commit before every tag.
Tagged v0.5 (11/25; employer check signed off; image at 854e81c rebuilt
byte-identical).
Week 6 (11/25): ADR 0010 no write actions (user's choice). Web view
(agent/web.py, demo mode; strict CSP; planted HTML/script rendered no tag).
Prompt-injection cases i1 (readiness probe output) and i2 (object name),
approved by the user: instruction never followed in 6 runs; i2's first run
ended unknown from a one-character name-copy slip -> near-miss name
correction in grounding (3afc620). Regression on 3afc620: f01 missed twice
identically (the 4B model's verdict flipped with unrelated overview counts)
-> the hand-scaled row states "a fault" (5386613, deployed both clusters
8ed0846, agents 0.6.1). Final eval on the airgap (results/week6-status-eval/):
10/10 faults incl. i1/i2, 5/5 controls, no ambient findings, median 48.7 s.
docs/results.md (all measured results), README rewritten (results,
screenshots, GIF, quickstart, timeline), docs/media/ (agentctl.cast/.gif via
scripts/record-agentctl.sh; web view PNGs via headless Firefox with its own
profile, since the user's Firefox is open). Open: Grafana and Tempo
screenshots (need the Grafana login), the from-zero build guide, the full
rebuild of both clusters from fresh clones (user: last, before v1.0), v1.0.
v1.0 (11/25): full rebuild from fresh clones (docs/scans/week6-rebuild.txt):
make down (after platform-lab 5c1bef5: destroy failed with the VM off),
fresh clones, build cluster 22m40s to a working agent; model and agent
images byte-identical to their pins; fresh airgap VM, zarf init, 9
packages Succeeded, 0 pull errors, egress blocked, unsigned image rejected.
The rebuilt airgap VM's controls failed 0/5 (boot-time restarts read as
crash loops) -> fixed before v1.0 (user's choice: 7229ac8, dba61ba; image
dba61ba sha256:3d131df5, deployed 2cc1602, agents 0.6.2). Final eval on
both rebuilt clusters: 10/10, 5/5 clean, no ambient findings
(results/v1.0-*-status-eval/). Stale events from the publish window, the
unsigned test and KEDA's boot warning deleted with the user's OK. After
every VM boot the eval waits until no restarted container has run < 10 min.
The rebuilt clusters' Terraform state, kubeconfigs and packages were made in
~/projects/freshclone-1125/ and copied back to the working repos.
Tagged v1.0 (11/25; employer check signed off).
Lab: all VMs shut off at the end of 11/25 (both rebuilt 11/25; image dba61ba on both; fresh clones and *.pre-v1.0 copies deleted) (a libvirt domain named
`laboratory`, 2 vCPU / 4 GiB, also exists, not part of these repos: leave
it alone); the working platform-lab holds both clusters' Terraform state
and kubeconfigs.
See ROADMAP.md for the checklist.
