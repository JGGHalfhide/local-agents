"""The status reporter's read-only tools (ADR 0003, docs/eval-status.md).

Each tool reads raw list JSON from agent/k8s.py and returns compact text
rows, capped at MAX_RESULT_CHARS (~1,000 tokens). Pod specs, env values and
Secret names are never returned.

Built in from the ADR 0002 spike (every report there listed 4-7 false
faults):
- list_events shows only warnings whose object is NOT healthy now (and says
  how many resolved ones it hid); a failure followed by a later success
  on the same object counts as resolved (RESOLVED_BY: FailedCreate then
  SuccessfulCreate, ApplyManifestFailed then AppliedManifest);
- workload rows say when a KEDA ScaledObject scales them; a KEDA workload
  at zero replicas is marked as expected;
- list_nodes exists, so node health is read, not guessed.
"""
import datetime as dt
import re
import json
import pathlib

MAX_RESULT_CHARS = 3500
# Warning reason -> the Normal reason that means the same object has succeeded
# since (list_events hides the warning then).
RESOLVED_BY = {
    "FailedCreate": "SuccessfulCreate",             # Job, ReplicaSet, StatefulSet, DaemonSet, CronJob controllers
    "ApplyManifestFailed": "AppliedManifest",       # RKE2's addon controller (server/manifests)
}
KINDS = ["Pod", "Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob", "ScaledObject", "Node"]


def _now(src):
    rec = getattr(src, "path", None)
    if rec and (pathlib.Path(rec) / "recorded-at.txt").exists():
        return dt.datetime.fromisoformat((pathlib.Path(rec) / "recorded-at.txt").read_text().strip().replace("Z", "+00:00"))
    return dt.datetime.now(dt.UTC)


def _age(now, ts):
    if not ts:
        return ""
    s = (now - dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds()
    return f"{int(s // 86400)}d" if s >= 86400 else f"{int(s // 3600)}h" if s >= 3600 else f"{int(s // 60)}m"


# Conditions where False is the healthy state (a Job that is not suspended and
# has not failed): reported only when True. Week 2 eval: a completed Job's
# Suspended=False(JobResumed) was printed as a bad condition and reported.
NEGATIVE_CONDITIONS = {"Suspended", "Failed", "FailureTarget", "ReplicaFailure"}


def _bad_conditions(conds):
    return ",".join(f"{c['type']}={c['status']}" + (f"({c.get('reason')})" if c.get("reason") else "")
                    for c in conds or [] if c["type"] != "Progressing"
                    and (c.get("status") == "True" if c["type"] in NEGATIVE_CONDITIONS else c.get("status") != "True")) or "-"


# Kyverno files a PolicyViolation event under the policy (namespace default)
# and names the blocked object only in the message: "DaemonSet agent-eval-f08/hostnet: fail (blocked); ...".
_POLICY_TARGET = re.compile(r"^([A-Z][A-Za-z]+) ([a-z0-9]([-a-z0-9]*[a-z0-9])?)/([a-z0-9]([-.a-z0-9]*[a-z0-9])?): ")


class Cluster:
    """Rows derived from one snapshot of the cluster (cached per run)."""

    def __init__(self, src):
        self.src, self.now = src, _now(src)
        self._pods = self._wl = self._keda = self._ns = None

    def keda(self):
        if self._keda is None:
            self._keda = []
            for kind, res in (("ScaledObject", "scaledobjects.keda.sh"), ("HTTPScaledObject", "httpscaledobjects.http.keda.sh")):
                for o in self.src.items(res):
                    sp = o.get("spec", {})
                    conds = {c["type"]: c["status"] for c in o.get("status", {}).get("conditions") or []}
                    tgt = sp.get("scaleTargetRef", {})
                    self._keda.append({
                        "namespace": o["metadata"]["namespace"], "kind": kind, "name": o["metadata"]["name"],
                        "target": f"{tgt.get('kind', 'Deployment')}/{tgt.get('name')}",
                        "min": sp.get("minReplicaCount", (sp.get("replicas") or {}).get("min", "")),
                        "max": sp.get("maxReplicaCount", (sp.get("replicas") or {}).get("max", "")),
                        "ready": conds.get("Ready", "-"), "active": conds.get("Active", "-"),
                        "paused": conds.get("Paused", "-")})
        return self._keda

    def pods(self):
        if self._pods is None:
            self._pods = []
            for p in self.src.items("pods"):
                st = p.get("status", {})
                cs = st.get("containerStatuses") or []
                ready = sum(bool(c.get("ready")) for c in cs)
                waiting = ",".join(c["state"]["waiting"].get("reason", "") for c in cs if "waiting" in c.get("state", {})) or "-"
                last = ",".join(f"{c['lastState']['terminated'].get('reason')}({c['lastState']['terminated'].get('exitCode')})"
                                for c in cs if "terminated" in c.get("lastState", {})) or "-"
                phase = st.get("phase", "")
                ok = phase == "Succeeded" or (phase == "Running" and ready == len(cs) and waiting == "-")
                self._pods.append({
                    "namespace": p["metadata"]["namespace"], "name": p["metadata"]["name"], "phase": phase,
                    "ready": f"{ready}/{len(cs)}", "restarts": sum(c.get("restartCount", 0) for c in cs),
                    "waiting": waiting, "last_terminated": last, "ok": ok,
                    "owner": ",".join(f"{o['kind']}/{o['name']}" for o in p["metadata"].get("ownerReferences", [])) or "-"})
        return self._pods

    def workloads(self):
        if self._wl is None:
            scaled = {(k["namespace"], k["target"]): k for k in self.keda()}
            self._wl = []
            for kind, res in (("Deployment", "deployments.apps"), ("StatefulSet", "statefulsets.apps"),
                              ("DaemonSet", "daemonsets.apps"), ("ReplicaSet", "replicasets.apps"), ("Job", "jobs.batch")):
                for o in self.src.items(res):
                    s, sp = o.get("status", {}), o.get("spec", {})
                    if kind == "DaemonSet":
                        desired, ready = s.get("desiredNumberScheduled", 0), s.get("numberReady", 0)
                    elif kind == "Job":
                        desired, ready = sp.get("completions", 1), s.get("succeeded", 0)
                    else:
                        desired, ready = sp.get("replicas", 0), s.get("readyReplicas", 0)
                    if kind == "ReplicaSet" and desired == 0 and not s.get("replicas"):
                        continue                    # old ReplicaSets of a Deployment
                    ns, name = o["metadata"]["namespace"], o["metadata"]["name"]
                    k = scaled.get((ns, f"{kind}/{name}"))
                    note = "-"
                    orphaned = []
                    if k:
                        note = f"scaled by KEDA {k['kind']}/{k['name']} ({k['min']}-{k['max']})"
                        if desired == 0:
                            note += "; at zero by design, not a fault"
                    elif desired == 0 and kind in ("Deployment", "StatefulSet"):
                        tmpl = ((sp.get("template") or {}).get("metadata") or {}).get("labels") or {}
                        orphaned = [svc["metadata"]["name"] for svc in self.src.items("services")
                                    if svc["metadata"]["namespace"] == ns and (svc.get("spec") or {}).get("selector")
                                    and all(tmpl.get(a) == b for a, b in svc["spec"]["selector"].items())]
                        note = (f"0 replicas, not autoscaled; Service/{','.join(orphaned)} selects it and has no pods"
                                if orphaned else "0 replicas, not autoscaled; no Service selects it")
                    conds = _bad_conditions(s.get("conditions"))
                    complete = kind == "Job" and any(c["type"] == "Complete" and c["status"] == "True" for c in s.get("conditions") or [])
                    ok = (complete or (ready >= desired and conds in ("-",)) or (k is not None and desired == 0)) and not orphaned
                    self._wl.append({"namespace": ns, "kind": kind, "name": name, "desired": desired, "ready": ready,
                                     "conditions": conds, "autoscaler": note, "ok": ok})
        return self._wl

    def namespaces(self):
        if self._ns is None:
            self._ns = {n["metadata"]["name"] for n in self.src.items("namespaces")}
        return self._ns

    def keda_managed(self, ns, kind, name):
        """True if a KEDA object scales this workload (or is this object)."""
        return any(k["namespace"] == ns and (k["target"] == f"{kind}/{name}" or k["name"] == name) for k in self.keda())

    def pvcs(self):
        classes = {c["metadata"]["name"] for c in self.src.items("storageclasses.storage.k8s.io")}
        rows = []
        for c in self.src.items("persistentvolumeclaims"):
            sc = (c.get("spec") or {}).get("storageClassName") or "(default)"
            rows.append({"namespace": c["metadata"]["namespace"], "name": c["metadata"]["name"],
                         "phase": (c.get("status") or {}).get("phase", ""), "storage_class": sc,
                         "class_exists": "yes" if sc == "(default)" or sc in classes else "NO",
                         "capacity": ((c.get("status") or {}).get("capacity") or {}).get("storage", "-")})
        return rows

    def argocd_apps(self):
        rows = []
        for a in self.src.items("applications.argoproj.io"):
            st = a.get("status") or {}
            rows.append({"namespace": a["metadata"]["namespace"], "name": a["metadata"]["name"],
                         "sync": (st.get("sync") or {}).get("status", "-"),
                         "health": (st.get("health") or {}).get("status", "-"),
                         "message": " ".join(((st.get("health") or {}).get("message") or "").split())[:160]})
        return rows

    def pod_metrics(self, ns):
        limits = {}
        for p in self.src.items("pods"):
            if p["metadata"]["namespace"] != ns:
                continue
            for c in (p.get("spec") or {}).get("containers") or []:
                limits[(p["metadata"]["name"], c["name"])] = ((c.get("resources") or {}).get("limits") or {}).get("memory", "-")
        rows = []
        for m in self.src.items("pods.metrics.k8s.io"):
            if m["metadata"]["namespace"] != ns:
                continue
            for c in m.get("containers") or []:
                rows.append({"namespace": ns, "pod": m["metadata"]["name"], "container": c["name"],
                             "cpu": c["usage"].get("cpu"), "memory": c["usage"].get("memory"),
                             "memory_limit": limits.get((m["metadata"]["name"], c["name"]), "-")})
        return rows

    def nodes(self):
        rows = []
        for n in self.src.items("nodes"):
            conds = {c["type"]: c["status"] for c in n.get("status", {}).get("conditions") or []}
            pressure = [t for t in ("MemoryPressure", "DiskPressure", "PIDPressure") if conds.get(t) == "True"]
            rows.append({"name": n["metadata"]["name"], "ready": conds.get("Ready", "Unknown"),
                         "pressure": ",".join(pressure) or "-",
                         "unschedulable": bool(n.get("spec", {}).get("unschedulable"))})
        return rows

    def object_now(self, ns, kind, name):
        """Is the object an event is about healthy now? ok / NOT OK / gone / ?"""
        if kind == "Pod":
            rows = [p for p in self.pods() if p["namespace"] == ns and p["name"] == name]
            return "gone" if not rows else ("ok" if rows[0]["ok"] else "NOT OK")
        if kind in ("Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job"):
            rows = [w for w in self.workloads() if w["namespace"] == ns and w["kind"] == kind and w["name"] == name]
            return "gone" if not rows else ("ok" if rows[0]["ok"] else "NOT OK")
        if kind == "HorizontalPodAutoscaler" and name.startswith("keda-hpa-"):
            target = name[len("keda-hpa-"):]
            rows = [k for k in self.keda() if k["namespace"] == ns and k["name"] == target]
            return "gone" if not rows else ("ok" if rows[0]["ready"] == "True" else "NOT OK")
        if kind == "Node":
            rows = [n for n in self.nodes() if n["name"] == name]
            return "gone" if not rows else ("ok" if rows[0]["ready"] == "True" else "NOT OK")
        return "?"

    def events(self, include_resolved=False):
        seen = {}
        events = self.src.items("events")
        # A failure resolved by a later success on the same object (RESOLVED_BY):
        # 11/25, a CronJob's Jobs rejected and RKE2's local-path-storage addon not
        # applied while Kyverno and the Zarf registry were still starting after a
        # VM boot; both succeeded seconds later and were reported as faults.
        succeeded = {}
        for e in events:
            if e.get("type") == "Normal" and e.get("reason") in RESOLVED_BY.values():
                io = e.get("involvedObject", {})
                k = (io.get("namespace") or e["metadata"]["namespace"], io.get("kind"), io.get("name"), e.get("reason"))
                ts = e.get("lastTimestamp") or e.get("eventTime") or e["metadata"].get("creationTimestamp") or ""
                succeeded[k] = max(succeeded.get(k, ""), ts)
        for e in events:
            if e.get("type") != "Warning":
                continue
            io = e.get("involvedObject", {})
            ns, kind, name = io.get("namespace") or e["metadata"]["namespace"], io.get("kind"), io.get("name")
            message = " ".join((e.get("message") or "").split())
            m = _POLICY_TARGET.match(message) if e.get("reason") == "PolicyViolation" else None
            if m:
                # Locate the finding at the object Kyverno checked, not at the policy.
                ns, kind, name = m.group(2), m.group(1), m.group(4)
                rest = message[m.end():]
                # Say it plainly: without the policy as the object, an image policy's
                # "GET .../manifests/..." reads as a pull error (Week 3 eval, f06).
                message = (f"blocked at admission by {io.get('kind')}/{io.get('name')}: {rest}" if "(blocked)" in rest
                           else f"{io.get('kind')}/{io.get('name')}: {rest}")
                now = self.object_now(ns, kind, name)
                if ns not in self.namespaces():
                    now = "gone"                    # its namespace was deleted: resolved
                elif now == "gone" and "(blocked)" in message:
                    now = "blocked at admission"    # rejected, never created: still the current state
            else:
                now = self.object_now(ns, kind, name)
            key = (ns, kind, name, e.get("reason"))
            ts = e.get("lastTimestamp") or e.get("eventTime") or e["metadata"].get("creationTimestamp") or ""
            ok_reason = RESOLVED_BY.get(e.get("reason"))
            if ok_reason and succeeded.get((ns, kind, name, ok_reason), "") > ts:
                now = "ok"                          # succeeded since: the failure is over
            if key not in seen or ts > seen[key]["ts"]:
                seen[key] = {"namespace": ns, "object": f"{kind}/{name}", "reason": e.get("reason"),
                             "count": e.get("count") or 1, "ts": ts, "age": _age(self.now, ts),
                             "now": now, "message": message[:200]}
        rows = sorted(seen.values(), key=lambda r: r["ts"], reverse=True)
        shown = rows if include_resolved else [r for r in rows if r["now"] not in ("ok", "gone")]
        return shown, len(rows) - len(shown)


def _render(header, rows, cols, footer=""):
    lines = ["\t".join(cols)] + ["\t".join(str(r.get(c, "")) for c in cols) for r in rows]
    out, n = [], 0
    for line in lines:
        if n + len(line) + 1 > MAX_RESULT_CHARS - 120:
            out.append(f"... {len(lines) - len(out)} more rows omitted; narrow by namespace")
            break
        out.append(line)
        n += len(line) + 1
    return header + "\n" + "\n".join(out) + (("\n" + footer) if footer else "")


def _ns(rows, ns):
    return [r for r in rows if r.get("namespace") == ns] if ns else rows


_NS = {"namespace": {"type": "string", "description": "Namespace; omit for all namespaces"}}
SPECS = [
    ("overview", "Start here: everything that is NOT healthy now (nodes, pods, workloads, warning events, PVCs, Argo CD apps) in one result, plus counts of what is healthy.", _NS, []),
    ("list_namespaces", "List namespaces and their phase.", {}, []),
    ("list_nodes", "List nodes: Ready, pressure conditions, unschedulable.", {}, []),
    ("list_pods", "List pods: phase, ready, restarts, waiting reason, last termination. Not-ready pods first.", _NS, []),
    ("list_workloads", "List Deployments, StatefulSets, DaemonSets, ReplicaSets and Jobs: desired/ready, conditions that are not True, and whether KEDA scales them. Unhealthy first.", _NS, []),
    ("list_events", "List Warning events whose object is NOT healthy now (resolved ones are hidden and counted), newest first.", _NS, []),
    ("list_keda_objects", "List KEDA ScaledObjects and HTTPScaledObjects: target, min/max replicas, Ready, Active, Paused.", _NS, []),
    ("list_pvcs", "List PersistentVolumeClaims: phase, storage class and whether that class exists, capacity.", _NS, []),
    ("list_argocd_apps", "List Argo CD Applications: sync status, health, health message.", {}, []),
    ("pod_metrics", "Memory and CPU use per container in one namespace, with the memory limit.",
     {"namespace": {"type": "string", "description": "Namespace"}}, ["namespace"]),
    ("get_status", "Status of one object.",
     {"kind": {"type": "string", "enum": KINDS}, "namespace": {"type": "string", "description": "Namespace (empty for a Node)"},
      "name": {"type": "string"}}, ["kind", "name"]),
]
NAMES = [s[0] for s in SPECS]


def openai_tools():
    return [{"type": "function", "function": {"name": n, "description": d, "parameters": {
        "type": "object", "properties": p, "required": r, "additionalProperties": False}}} for n, d, p, r in SPECS]


def validate_args(name, args):
    spec = next((s for s in SPECS if s[0] == name), None)
    if spec is None:
        return f"unknown tool {name}"
    if not isinstance(args, dict):
        return "arguments must be a JSON object"
    props, req = spec[2], spec[3]
    for k in req:
        if not args.get(k):
            return f"missing {k}"
    for k, v in args.items():
        if k not in props:
            return f"unknown argument {k}"
        if not isinstance(v, str):
            return f"{k} must be a string"
        if "enum" in props[k] and v not in props[k]["enum"]:
            return f"{k} must be one of {props[k]['enum']}"
    return None


def _overview(cluster, ns):
    parts, healthy = [], []

    def section(title, rows, cols, total):
        healthy.append(f"{title} {total - len(rows)}/{total} healthy")
        if rows:
            parts.append(title + "\n" + "\n".join(["\t".join(cols)] + ["\t".join(str(r.get(c, "")) for c in cols) for r in rows]))

    if not ns:
        nodes = cluster.nodes()
        section("nodes", [n for n in nodes if n["ready"] != "True" or n["pressure"] != "-"],
                ["name", "ready", "pressure"], len(nodes))
    pods = _ns(cluster.pods(), ns)
    section("pods", [p for p in pods if not p["ok"]],
            ["namespace", "name", "phase", "ready", "restarts", "waiting", "last_terminated", "owner"], len(pods))
    wl = _ns(cluster.workloads(), ns)
    section("workloads", [w for w in wl if not w["ok"]],
            ["namespace", "kind", "name", "desired", "ready", "conditions", "autoscaler"], len(wl))
    ev, hidden = cluster.events()
    ev = _ns(ev, ns)
    section("warning events (object not healthy now)", ev, ["namespace", "object", "reason", "count", "age", "message"],
            len(ev) + hidden)
    pv = _ns(cluster.pvcs(), ns)
    section("pvcs", [c for c in pv if c["phase"] != "Bound" or c["class_exists"] != "yes"],
            ["namespace", "name", "phase", "storage_class", "class_exists"], len(pv))
    if not ns:
        apps = cluster.argocd_apps()
        section("argo cd apps", [a for a in apps if a["sync"] != "Synced" or a["health"] != "Healthy"],
                ["name", "sync", "health", "message"], len(apps))
    text = "overview" + (f" of namespace {ns}" if ns else "") + ": " + "; ".join(healthy)
    text += ("\n\n" + "\n\n".join(parts)) if parts else "\nNothing unhealthy found."
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS - 80] + "\n... truncated; use the list_* tools with a namespace"
    return text


def call(cluster, name, args):
    err = validate_args(name, args)
    if err:
        return f"error: {err}"
    ns = args.get("namespace") or None
    if name == "overview":
        return _overview(cluster, ns)
    if name == "list_namespaces":
        return _render("namespaces", [{"name": n["metadata"]["name"], "phase": n["status"]["phase"]}
                                      for n in cluster.src.items("namespaces")], ["name", "phase"])
    if name == "list_nodes":
        return _render("nodes", cluster.nodes(), ["name", "ready", "pressure", "unschedulable"])
    if name == "list_pods":
        rows = sorted(_ns(cluster.pods(), ns), key=lambda r: (r["ok"], r["namespace"], r["name"]))
        return _render("pods", rows, ["namespace", "name", "phase", "ready", "restarts", "waiting", "last_terminated", "owner"])
    if name == "list_workloads":
        rows = sorted(_ns(cluster.workloads(), ns), key=lambda r: (r["ok"], r["namespace"], r["kind"], r["name"]))
        return _render("workloads", rows, ["namespace", "kind", "name", "desired", "ready", "conditions", "autoscaler"])
    if name == "list_events":
        rows, hidden = cluster.events()
        rows = _ns(rows, ns)
        return _render("warning events about objects that are not healthy now", rows,
                       ["namespace", "object", "reason", "count", "age", "now", "message"],
                       f"({hidden} warning events about objects that are healthy now or gone were hidden)")
    if name == "list_keda_objects":
        return _render("keda objects", _ns(cluster.keda(), ns),
                       ["namespace", "kind", "name", "target", "min", "max", "ready", "active", "paused"])
    if name == "list_pvcs":
        return _render("persistent volume claims", _ns(cluster.pvcs(), ns),
                       ["namespace", "name", "phase", "storage_class", "class_exists", "capacity"])
    if name == "list_argocd_apps":
        return _render("argo cd applications", cluster.argocd_apps(), ["namespace", "name", "sync", "health", "message"])
    if name == "pod_metrics":
        return _render(f"pod metrics in {ns}", cluster.pod_metrics(ns),
                       ["pod", "container", "cpu", "memory", "memory_limit"])
    if name == "get_status":
        kind, nm = args["kind"], args["name"]
        if kind == "CronJob":
            hit = [c for c in cluster.src.items("cronjobs.batch")
                   if c["metadata"]["name"] == nm and c["metadata"]["namespace"] == ns]
            if not hit:
                return f"not found: CronJob/{ns or ''}/{nm}"
            sp, st = hit[0].get("spec") or {}, hit[0].get("status") or {}
            return json.dumps({"schedule": sp.get("schedule"), "suspend": sp.get("suspend", False),
                               "active_jobs": len(st.get("active") or []), "last_schedule": st.get("lastScheduleTime"),
                               "last_success": st.get("lastSuccessfulTime")})
        pool = {"Pod": cluster.pods(), "ScaledObject": cluster.keda(), "Node": cluster.nodes()}.get(kind) or \
            [w for w in cluster.workloads() if w["kind"] == kind]
        hit = [r for r in pool if r["name"] == nm and (kind == "Node" or r.get("namespace") == ns)]
        return json.dumps(hit[0])[:MAX_RESULT_CHARS] if hit else f"not found: {kind}/{ns or ''}/{nm}"
    return "error: unknown tool"
