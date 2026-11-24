#!/usr/bin/env python3
"""Build the spike's fixtures (docs/adr/0002).

  make_fixtures.py <raw-dir> <out-dir>

<raw-dir> holds `kubectl get <resource> -A -o json` output recorded
read-only from the build cluster (raw-<resource>.json, recorded-at.txt;
kept in build/, never committed: pod specs can carry env values). Writes:

- healthy.json: RECORDED. The live cluster, summarised into the tool rows.
- f04-crash-loop.json, f06-admission-denied.json, k1-keda-zero.json:
  CONSTRUCTED. healthy.json plus one namespace with hand-written rows that
  mimic the fault or control of docs/eval-status.md. No fault was injected
  (inject.sh is a stub); field values follow what the API reports for these
  states, the event messages are representative, not captured.
"""
import copy
import datetime as dt
import json
import pathlib
import sys

RAW, OUT = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
NOW = dt.datetime.fromisoformat((RAW / "recorded-at.txt").read_text().strip().replace("Z", "+00:00"))


def items(res):
    return json.loads((RAW / f"raw-{res}.json").read_text())["items"]


def age(ts):
    if not ts:
        return ""
    s = (NOW - dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds()
    return f"{int(s // 3600)}h" if s >= 3600 else f"{int(s // 60)}m"


def bad_conditions(conds):
    return ",".join(f"{c['type']}={c['status']}" + (f"({c.get('reason')})" if c.get("reason") else "")
                    for c in conds or [] if c.get("status") != "True"
                    and c["type"] not in ("Progressing",)) or "-"


def pod_row(p):
    st = p.get("status", {})
    cs = st.get("containerStatuses") or []
    ready = sum(bool(c.get("ready")) for c in cs)
    waiting = ",".join(c["state"]["waiting"].get("reason", "") for c in cs if "waiting" in c.get("state", {})) or "-"
    last = ",".join(f"{c['lastState']['terminated'].get('reason')}({c['lastState']['terminated'].get('exitCode')})"
                    for c in cs if "terminated" in c.get("lastState", {})) or "-"
    phase = st.get("phase", "")
    ok = phase == "Succeeded" or (phase == "Running" and ready == len(cs) and waiting == "-")
    owner = ",".join(f"{o['kind']}/{o['name']}" for o in p["metadata"].get("ownerReferences", [])) or "-"
    return {"namespace": p["metadata"]["namespace"], "name": p["metadata"]["name"], "phase": phase,
            "ready": f"{ready}/{len(cs)}", "restarts": sum(c.get("restartCount", 0) for c in cs),
            "waiting": waiting, "last_terminated": last, "owner": owner, "ok": ok}


def workload_rows():
    rows = []
    for kind, res in (("Deployment", "deployments.apps"), ("StatefulSet", "statefulsets.apps"),
                      ("DaemonSet", "daemonsets.apps"), ("ReplicaSet", "replicasets.apps"), ("Job", "jobs.batch")):
        for o in items(res):
            s, sp = o.get("status", {}), o.get("spec", {})
            if kind == "DaemonSet":
                desired, ready, avail = s.get("desiredNumberScheduled", 0), s.get("numberReady", 0), s.get("numberAvailable", 0)
            elif kind == "Job":
                desired, ready, avail = sp.get("completions", 1), s.get("succeeded", 0), s.get("active", 0)
            else:
                desired, ready, avail = sp.get("replicas", 0), s.get("readyReplicas", 0), s.get("availableReplicas", 0)
            if kind == "ReplicaSet" and desired == 0 and not s.get("replicas"):
                continue        # old ReplicaSets of a Deployment: noise
            rows.append({"namespace": o["metadata"]["namespace"], "kind": kind, "name": o["metadata"]["name"],
                         "desired": desired, "ready": ready, "available": avail,
                         "conditions": bad_conditions(s.get("conditions"))})
    return rows


def event_rows():
    seen = {}
    for e in items("events"):
        if e.get("type") != "Warning":
            continue
        io = e.get("involvedObject", {})
        k = (io.get("namespace") or e["metadata"]["namespace"], f"{io.get('kind')}/{io.get('name')}", e.get("reason"))
        ts = e.get("lastTimestamp") or e.get("eventTime") or e["metadata"].get("creationTimestamp")
        if k not in seen or ts > seen[k]["ts"]:
            seen[k] = {"namespace": k[0], "object": k[1], "reason": k[2], "count": e.get("count") or 1,
                       "ts": ts, "age": age(ts), "message": " ".join((e.get("message") or "").split())[:200]}
    rows = sorted(seen.values(), key=lambda r: r["ts"], reverse=True)
    for r in rows:
        r.pop("ts")
    return rows


def keda_rows():
    rows = []
    for kind, res in (("ScaledObject", "scaledobjects.keda.sh"), ("HTTPScaledObject", "httpscaledobjects.http.keda.sh")):
        for o in items(res):
            sp, conds = o.get("spec", {}), {c["type"]: c["status"] for c in o.get("status", {}).get("conditions") or []}
            tgt = sp.get("scaleTargetRef", {})
            rows.append({"namespace": o["metadata"]["namespace"], "kind": kind, "name": o["metadata"]["name"],
                         "target": f"{tgt.get('kind', 'Deployment')}/{tgt.get('name')}",
                         "min": sp.get("minReplicaCount", sp.get("replicas", {}).get("min", "")),
                         "max": sp.get("maxReplicaCount", sp.get("replicas", {}).get("max", "")),
                         "ready": conds.get("Ready", "-"), "active": conds.get("Active", "-"),
                         "paused": conds.get("Paused", "-")})
    return rows


def status_map(pods, workloads):
    st = {}
    for p in pods:
        st[f"Pod/{p['namespace']}/{p['name']}"] = {k: p[k] for k in ("phase", "ready", "restarts", "waiting", "last_terminated", "owner")}
    for w in workloads:
        st[f"{w['kind']}/{w['namespace']}/{w['name']}"] = {k: w[k] for k in ("desired", "ready", "available", "conditions")}
    return st


pods = [pod_row(p) for p in items("pods")]
wl = workload_rows()
healthy = {
    "provenance": f"recorded read-only from build-node-01 at {NOW.isoformat()}",
    "namespaces": [{"name": n["metadata"]["name"], "phase": n["status"]["phase"]} for n in items("namespaces")],
    "pods": pods, "workloads": wl, "events": event_rows(), "keda": keda_rows(),
    "status": status_map(pods, wl),
    "expected": {"faults": []},
}


def construct(name, ns, pods_add, wl_add, events_add, keda_add, expected, note):
    f = copy.deepcopy(healthy)
    f["provenance"] = f"CONSTRUCTED from healthy.json: {note}"
    f["namespaces"].append({"name": ns, "phase": "Active"})
    f["pods"] += pods_add
    f["workloads"] += wl_add
    f["events"] = events_add + f["events"]
    f["keda"] += keda_add
    f["status"].update(status_map(pods_add, wl_add))
    f["expected"] = expected
    (OUT / f"{name}.json").write_text(json.dumps(f, indent=1) + "\n")


OUT.mkdir(parents=True, exist_ok=True)
(OUT / "healthy.json").write_text(json.dumps(healthy, indent=1) + "\n")

ns = "agent-eval-f04"
construct("f04-crash-loop", ns,
          [{"namespace": ns, "name": "crashy-6d8f9c7b5-x2kqp", "phase": "Running", "ready": "0/1", "restarts": 6,
            "waiting": "CrashLoopBackOff", "last_terminated": "Error(127)", "owner": "ReplicaSet/crashy-6d8f9c7b5", "ok": False}],
          [{"namespace": ns, "kind": "Deployment", "name": "crashy", "desired": 1, "ready": 0, "available": 0,
            "conditions": "Available=False(MinimumReplicasUnavailable)"},
           {"namespace": ns, "kind": "ReplicaSet", "name": "crashy-6d8f9c7b5", "desired": 1, "ready": 0, "available": 0, "conditions": "-"}],
          [{"namespace": ns, "object": "Pod/crashy-6d8f9c7b5-x2kqp", "reason": "BackOff", "count": 24, "age": "1m",
            "message": "Back-off restarting failed container crashy in pod crashy-6d8f9c7b5-x2kqp_agent-eval-f04(...)"}],
          [], {"faults": [{"namespace": ns, "category": "crash-loop",
                           "objects": ["Pod/crashy-6d8f9c7b5-x2kqp", "Deployment/crashy", "ReplicaSet/crashy-6d8f9c7b5"]}]},
          "f04, Deployment crashy whose container exits 127 (bad args)")

ns = "agent-eval-f06"
construct("f06-admission-denied", ns, [],
          [{"namespace": ns, "kind": "Deployment", "name": "unsigned", "desired": 1, "ready": 0, "available": 0,
            "conditions": "Available=False(MinimumReplicasUnavailable),ReplicaFailure=True(FailedCreate)"},
           {"namespace": ns, "kind": "ReplicaSet", "name": "unsigned-5c7d8b9f4", "desired": 1, "ready": 0, "available": 0,
            "conditions": "ReplicaFailure=True(FailedCreate)"}],
          [{"namespace": ns, "object": "ReplicaSet/unsigned-5c7d8b9f4", "reason": "FailedCreate", "count": 9, "age": "2m",
            "message": "Error creating: admission webhook \"ivpol.validate.kyverno.svc-fail\" denied the request: Policy verify-platform-images failed: failed to verify image 127.0.0.1:30500/library/alpine@sha256:0000...: no signatures found"}],
          [], {"faults": [{"namespace": ns, "category": "admission-denied",
                           "objects": ["Deployment/unsigned", "ReplicaSet/unsigned-5c7d8b9f4"]}]},
          "f06, Deployment unsigned whose pods Kyverno denies (event message representative)")

ns = "agent-eval-k1"
construct("k1-keda-zero", ns, [],
          [{"namespace": ns, "kind": "Deployment", "name": "idle", "desired": 0, "ready": 0, "available": 0, "conditions": "-"}],
          [], [{"namespace": ns, "kind": "ScaledObject", "name": "idle", "target": "Deployment/idle", "min": 0, "max": 1,
                "ready": "True", "active": "False", "paused": "False"}],
          {"faults": []}, "k1, Deployment idle scaled to zero by its KEDA ScaledObject (healthy control)")
print("fixtures:", sorted(p.name for p in OUT.glob("*.json")))
print("healthy: pods", len(pods), "not ok", sum(not p["ok"] for p in pods), "workloads", len(wl),
      "warning events", len(healthy["events"]), "keda", len(healthy["keda"]))
for p in pods:
    if not p["ok"]:
        print("  not ok:", p["namespace"], p["name"], p["phase"], p["waiting"], p["ready"])
