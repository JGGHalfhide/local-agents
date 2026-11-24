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
  retrieval, prompts and tool configs, tracing, the evaluation set and its
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
  both 8 vCPU / 16 GiB today (platform-lab terraform vars vcpus, memory_mib,
  rehearsal_vcpus, rehearsal_memory_mib), run ONE AT A TIME (2 x 16 GiB does
  not fit in 28 GiB with the host). Zarf packages are built while the build
  VM runs, then the VMs are switched.
- The inference pod takes 5-6 GiB (limit 6 GiB) of a 16 GiB node. Agents,
  tools, an embedding model and a vector store must fit next to it: sizing
  is a Week 1 decision (bigger VMs, still one at a time).

## Inherited facts about the endpoint (local-airgap-LLM v1.1)
- One stream: 14.3 tok/s, TTFT 1.9 s (213-token prompt). 4 slots; 18.2 tok/s
  at 4 concurrent; above 4, requests queue (TTFT 22 s at 8). Prompt
  processing ~110 tok/s. 32k context shared by the 4 slots.
- Cold start from zero ~6 s; scales to zero after 5 min idle. A KEDA
  operator restart scales it to zero at once.
- Thinking is OFF by default (ADR 0006 there). An agent opts in per request
  with `chat_template_kwargs: {"enable_thinking": true}`; the server caps
  thinking at 1024 tokens. Measured: thinking fixed 3/3 multi-step errors
  but looped to 8,192 tokens with no answer on 3/3 open-ended triage
  questions at temperature 0; a 256 budget made answers worse.
- Tool calling and JSON-schema output pass (5/5) with thinking on or off.
- Access today: NetworkPolicy only. Clients must be pods or namespaces
  labelled `inference.local-airgap-llm/client: "true"`; no API key yet.

## Decisions so far (11/23)
- Separate repo; same conventions as the other two.
- The endpoint stays fast, bounded and predictable by default; this repo
  decides when to pay for slower, better answers (thinking, longer
  contexts, a second model).
- Everything else is open: see ROADMAP.md Week 1 and Open questions.

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
ADRs yet), docs/stack.md (skeleton). No git repo yet: creating it (and the
GitHub repo) is the first Week 1 task.
Lab: both VMs powered down; the working platform-lab holds both clusters'
Terraform state and kubeconfigs.
See ROADMAP.md for the checklist.
