"""OpenTelemetry tracing of a status run (ADR 0008): one span per run, per
model call and per tool call, sent as OTLP/HTTP to Tempo (platform-lab,
namespace monitoring).

Names and attributes follow the OpenTelemetry GenAI semantic conventions
(invoke_agent / chat / execute_tool). Spans carry metadata only: model
settings, token counts, finish reasons, tool names and arguments' keys,
result sizes, errors, timings, the prompt's SHA-256. No prompt, model
output, tool argument values or tool result text: the run object
(GET /v1/runs/{id}) keeps those, as before. Same rule as local-airgap-LLM's
"no prompt or response content in Loki" (docs/observability.md there).

Off unless OTEL_EXPORTER_OTLP_ENDPOINT is set (the SDK reads it and the
other OTEL_* variables itself); without it every span is a no-op.
"""
import os

from opentelemetry import trace

SERVICE = "status-reporter"
_provider = None


def setup():
    """Install the SDK tracer provider if an OTLP endpoint is configured."""
    global _provider
    if _provider is not None or not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _provider = TracerProvider(resource=Resource.create({"service.name": SERVICE}))
    _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(timeout=5)))
    trace.set_tracer_provider(_provider)


def flush():
    """Send the run's spans now (a run is minutes apart from the next)."""
    if _provider is not None:
        _provider.force_flush(timeout_millis=5000)


def tracer():
    return trace.get_tracer("agent")


def trace_id(span):
    ctx = span.get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None
