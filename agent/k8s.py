"""Read-only access to the Kubernetes API (stdlib only, GET only).

Sources, chosen by `source()`:
- in-cluster: https://kubernetes.default.svc with the pod's ServiceAccount
  token and CA (the agent's own identity, read-only RBAC: step 3);
- KUBE_API=http://127.0.0.1:8001: a local `kubectl proxy` (development);
- KUBE_RECORDED=<dir>: raw `kubectl get <resource> -A -o json` files
  (raw-<resource>.json), for offline runs and tests.
Every source returns the same raw list JSON; agent/tools.py summarises it.
"""
import json
import os
import pathlib
import ssl
import urllib.request

SA = pathlib.Path("/var/run/secrets/kubernetes.io/serviceaccount")

# resource -> API path (cluster-wide lists)
PATHS = {
    "namespaces": "/api/v1/namespaces",
    "nodes": "/api/v1/nodes",
    "pods": "/api/v1/pods",
    "events": "/api/v1/events",
    "deployments.apps": "/apis/apps/v1/deployments",
    "statefulsets.apps": "/apis/apps/v1/statefulsets",
    "daemonsets.apps": "/apis/apps/v1/daemonsets",
    "replicasets.apps": "/apis/apps/v1/replicasets",
    "jobs.batch": "/apis/batch/v1/jobs",
    "scaledobjects.keda.sh": "/apis/keda.sh/v1alpha1/scaledobjects",
    "httpscaledobjects.http.keda.sh": "/apis/http.keda.sh/v1alpha1/httpscaledobjects",
}


class Source:
    def __init__(self):
        self.cache = {}

    def items(self, resource):
        if resource not in self.cache:
            self.cache[resource] = self._load(resource).get("items") or []
        return self.cache[resource]


class Api(Source):
    def __init__(self, base, token=None, ca=None):
        super().__init__()
        self.base, self.token = base.rstrip("/"), token
        self.ctx = ssl.create_default_context(cafile=ca) if ca else None

    def _load(self, resource):
        req = urllib.request.Request(self.base + PATHS[resource] + "?limit=500")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=30, context=self.ctx) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):   # not allowed or CRD absent: an empty list, said so
                return {"items": [], "error": f"{resource}: HTTP {e.code}"}
            raise


class Recorded(Source):
    def __init__(self, path):
        super().__init__()
        self.path = pathlib.Path(path)

    def _load(self, resource):
        f = self.path / f"raw-{resource}.json"
        return json.loads(f.read_text()) if f.exists() else {"items": []}


def source():
    if os.environ.get("KUBE_RECORDED"):
        return Recorded(os.environ["KUBE_RECORDED"])
    if os.environ.get("KUBE_API"):
        return Api(os.environ["KUBE_API"])
    return Api("https://kubernetes.default.svc", (SA / "token").read_text().strip(), str(SA / "ca.crt"))
