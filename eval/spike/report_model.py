"""The report schema of common.py as a pydantic model (for pydantic-ai and
langgraph, which take a model class for structured output)."""
from typing import Literal

from pydantic import BaseModel, ConfigDict

import common

Category = Literal[tuple(common.CATEGORIES)]


class Fault(BaseModel):
    model_config = ConfigDict(extra="forbid")
    namespace: str
    kind: str
    name: str
    category: Category
    evidence: list[str]


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")
    faults: list[Fault]
    summary: str


def capped(fx):
    """The fixture's tools as Python functions with the same caps as the plain loops."""
    def call(name, args):
        if len(fx.calls) >= common.MAX_TOOL_CALLS:
            return "error: tool-call limit reached; give your final answer now"
        return fx.call(name, {k: v for k, v in args.items() if v is not None})

    def list_namespaces() -> str:
        """List namespaces and their phase."""
        return call("list_namespaces", {})

    def list_pods(namespace: str | None = None) -> str:
        """List pods: phase, ready, restarts, waiting reason, last termination. Not-ready pods first.

        Args:
            namespace: Namespace; omit for all namespaces
        """
        return call("list_pods", {"namespace": namespace})

    def list_workloads(namespace: str | None = None) -> str:
        """List Deployments, StatefulSets, DaemonSets, ReplicaSets and Jobs: desired/ready/available and conditions that are not True.

        Args:
            namespace: Namespace; omit for all namespaces
        """
        return call("list_workloads", {"namespace": namespace})

    def list_events(namespace: str | None = None) -> str:
        """List Warning events, newest first, deduplicated by object and reason.

        Args:
            namespace: Namespace; omit for all namespaces
        """
        return call("list_events", {"namespace": namespace})

    def list_keda_objects(namespace: str | None = None) -> str:
        """List KEDA ScaledObjects and HTTPScaledObjects: target, min/max replicas, Ready, Active, Paused.

        Args:
            namespace: Namespace; omit for all namespaces
        """
        return call("list_keda_objects", {"namespace": namespace})

    def get_status(kind: Literal["Pod", "Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "ScaledObject"],
                   namespace: str, name: str) -> str:
        """Status and conditions of one object.

        Args:
            kind: Object kind
            namespace: Namespace
            name: Object name
        """
        return call("get_status", {"kind": kind, "namespace": namespace, "name": name})

    return [list_namespaces, list_pods, list_workloads, list_events, list_keda_objects, get_status]
