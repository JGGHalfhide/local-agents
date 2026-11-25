"""Read-only web view (ADR 0005, docs/interface.md "Web view"), standard
library only.

GET /                 recent runs (as GET /v1/runs)
GET /runs/{run_id}    one run: status, findings with evidence linked to
                      their tool calls, ungrounded findings, the tool-call
                      trace, model settings, timings
GET /static/view.css  the only asset (kept here: the image ships .py files)

Rendered on the server, no JavaScript, no forms, no write actions; nothing
loaded from outside the pod (airgap). Model output and tool output are
untrusted: every value goes through html.escape, nothing is rendered as
markdown or HTML, tool output is shown as escaped text in <pre>. Demo mode
(AGENT_DEMO_RUNS) puts a fixed DEMO banner on every page.
"""
from html import escape

HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; "
                               "form-action 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

CSS = """
:root { --bg: #f7f7f5; --fg: #1d1d1b; --muted: #66665f; --line: #d9d9d2; --card: #ffffff;
        --ok: #1f7a3a; --fault: #b3261e; --unknown: #8a6100; --code: #f0f0ea; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #161615; --fg: #ecece6; --muted: #a3a39b; --line: #34342f; --card: #1f1f1d;
          --ok: #5cc27a; --fault: #ff7a70; --unknown: #e0b04a; --code: #262623; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
       font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 16px; }
header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap;
         border-bottom: 1px solid var(--line); padding-bottom: 8px; margin-bottom: 16px; }
header h1 { font-size: 20px; margin: 0; }
header .sub { color: var(--muted); }
a { color: inherit; }
h2 { font-size: 16px; margin: 24px 0 8px; }
.demo { position: sticky; top: 0; z-index: 1; background: #b3261e; color: #fff; font-weight: 700;
        text-align: center; padding: 8px 16px; letter-spacing: .02em; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; background: var(--card); }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 13px; }
td.num { font-variant-numeric: tabular-nums; text-align: right; }
.status { font-weight: 700; text-transform: uppercase; font-size: 13px; }
.status.healthy { color: var(--ok); } .status.fault { color: var(--fault); } .status.unknown { color: var(--unknown); }
.kv { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; background: var(--card);
      border: 1px solid var(--line); padding: 10px 12px; }
.kv dt { color: var(--muted); } .kv dd { margin: 0; overflow-wrap: anywhere; }
.finding { background: var(--card); border: 1px solid var(--line); border-left: 4px solid var(--fault);
           padding: 10px 12px; margin: 8px 0; }
.finding.ungrounded { border-left-color: var(--unknown); }
.finding .head { font-weight: 600; overflow-wrap: anywhere; }
.muted { color: var(--muted); }
pre { background: var(--code); padding: 10px; overflow-x: auto; white-space: pre; margin: 6px 0 0; font-size: 13px; }
details { background: var(--card); border: 1px solid var(--line); margin: 6px 0; padding: 6px 10px; }
summary { cursor: pointer; overflow-wrap: anywhere; }
code { font-size: 13px; }
"""


def _e(v):
    return escape("" if v is None else str(v), quote=True)


def _status(s):
    s = s if s in ("healthy", "fault", "unknown") else "unknown"
    return f'<span class="status {s}">{_e(s)}</span>'


def _page(title, body, demo):
    banner = '<div class="demo">DEMO: recorded run, not the live cluster</div>' if demo else ""
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{_e(title)}</title><link rel=\"stylesheet\" href=\"/static/view.css\"></head>"
            f"<body>{banner}<main><header><h1><a href=\"/\">Status reporter</a></h1>"
            f"<span class=\"sub\">local-agents, read-only</span></header>{body}</main></body></html>")


def index(runs, demo, version):
    rows = "".join(
        f"<tr><td><a href=\"/runs/{_e(r['run_id'])}\"><code>{_e(r['run_id'])}</code></a></td>"
        f"<td>{_e(r['started'])}</td><td>{_status(r['status'])}</td><td>{_e(r['namespace'] or 'whole cluster')}</td>"
        f"<td class=\"num\">{_e(r['findings'])}</td><td class=\"num\">{_e(r['seconds'])}</td></tr>"
        for r in runs)
    body = (f"<p class=\"muted\">Last {len(runs)} runs, newest first. Runs start only through "
            f"<code>agentctl status</code> (POST /v1/status); this page cannot start or change anything. "
            f"Version {_e(version)}.</p>"
            "<div class=\"table-wrap\"><table><thead><tr><th>Run</th><th>Started (UTC)</th><th>Status</th>"
            "<th>Scope</th><th>Findings</th><th>Seconds</th></tr></thead>"
            f"<tbody>{rows or '<tr><td colspan=6 class=muted>No runs yet.</td></tr>'}</tbody></table></div>")
    return _page("Status reporter: runs", body, demo)


def _finding(f, ungrounded=False):
    ev = "".join(
        f"<li><a href=\"#{_e(x['tool_call_id'])}\">{_e(x['tool_call_id'])}</a>: <code>{_e(x['excerpt'])}</code></li>"
        for x in f.get("evidence") or [])
    reason = f"<div class=\"muted\">Moved to ungrounded: {_e(f.get('reason'))}</div>" if ungrounded else ""
    if f.get("corrected_from"):
        reason += f"<div class=\"muted\">Name corrected from <code>{_e(f['corrected_from'])}</code> (1-2 characters off)</div>"
    return (f"<div class=\"finding{' ungrounded' if ungrounded else ''}\">"
            f"<div class=\"head\">{_e(f.get('category'))}: {_e(f.get('namespace'))}/{_e(f.get('object'))}</div>"
            f"<div>{_e(f.get('summary'))}</div>{reason}"
            f"{'<ul>' + ev + '</ul>' if ev else ''}</div>")


def run_page(r, demo):
    t, m = r.get("timings") or {}, r.get("model") or {}
    kv = "".join(f"<dt>{_e(k)}</dt><dd>{v}</dd>" for k, v in [
        ("Status", _status(r.get("status"))),
        ("Scope", _e(r.get("namespace") or "whole cluster")),
        ("Started / finished", f"{_e(t.get('started'))} / {_e(t.get('finished'))}"),
        ("Time", f"{_e(t.get('total_s'))} s (model {_e(t.get('model_s'))} s, tools {_e(t.get('tools_s'))} s, "
                 f"{_e(t.get('turns'))} turns)"),
        ("Model", f"{_e(m.get('name'))}, temperature {_e(m.get('temperature'))}, thinking {_e(m.get('thinking'))}"),
        ("Prompts and limits", f"<code>config_sha256 {_e((m.get('config_sha256') or '')[:12])}</code>"),
        ("Trace", f"<code>{_e(r.get('trace_id'))}</code> (Grafana, datasource Tempo)"),
        ("Error", _e(r.get("error") or "none")),
    ])
    findings = "".join(_finding(f) for f in r.get("findings") or []) or "<p class=\"muted\">No findings.</p>"
    ungrounded = "".join(_finding(f, True) for f in r.get("ungrounded") or [])
    calls = "".join(
        f"<details id=\"{_e(c['id'])}\"><summary><code>{_e(c['id'])}</code> {_e(c['tool'])} "
        f"<code>{_e(c.get('arguments'))}</code>: {_e(c.get('result_chars'))} chars, {_e(c.get('duration_ms'))} ms"
        f"{', error' if c.get('error') else ''}{', truncated' if c.get('truncated') else ''}</summary>"
        f"<pre>{_e(c.get('result'))}</pre></details>"
        for c in r.get("tool_calls") or [])
    body = (f"<h2>Run <code>{_e(r.get('run_id'))}</code></h2><dl class=\"kv\">{kv}</dl>"
            f"<h2>Summary</h2><p>{_e(r.get('summary'))}</p>"
            f"<h2>Findings</h2>{findings}"
            + (f"<h2>Ungrounded (not reported)</h2>{ungrounded}" if ungrounded else "")
            + f"<h2>Tool calls</h2>{calls or '<p class=muted>None.</p>'}")
    return _page(f"Status reporter: {r.get('run_id')}", body, demo)
