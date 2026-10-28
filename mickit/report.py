"""Outputs: report.html (with a timeline per major incident as inline SVG), one draft post-incident review per major incident, and the
CSVs (major incidents, metrics, comms gaps, overdue actions, repeats, actions, findings)."""
from __future__ import annotations

import csv
import html
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean

from .checks import (AREAS, CRITICAL, INFO, WARNING, Finding, area_status, fmt_min, incident_rows, metrics, now_label)
from .model import Data, minutes

e = html.escape


def build(d: Data) -> dict:
    return dict(rows=incident_rows(d), metrics=metrics(d))


def _avg(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return mean(xs) if xs else None


def summary(d: Data, findings: list[Finding], b: dict) -> dict:
    rows = b["rows"]
    f = [r["facts"] for r in rows]
    codes = lambda c: sum(any(i.code == c and i.severity != INFO for i in r["issues"]) for r in rows)  # noqa: E731
    return dict(incidents=sum(i.opened <= d.as_of for i in d.incidents), majors=len(rows),
                p1=sum(r["incident"].priority == "P1" for r in rows), p2=sum(r["incident"].priority == "P2" for r in rows),
                action_needed=sum(r["verdict"] == "action needed" for r in rows), follow_up=sum(r["verdict"] == "follow up" for r in rows),
                clean=sum(r["verdict"] == "clean" for r in rows),
                mttd=_avg([x["ttd"] for x in f]), mtta=_avg([x["tta"] for x in f]), mttr=_avg([x["ttr"] for x in f]),
                blind=codes("DET-01"), slow_detect=codes("DET-02"), comms=codes("COM-01"),
                gaps=sum(g["kind"] != "no resolution update" for x in f for g in x["gaps"]), change=codes("CHG-01"),
                pir_late=codes("PIR-01"), overdue=sum(1 for r in rows for i in r["issues"] if i.code == "ACT-01"), repeats=codes("REP-01"),
                critical=sum(x.severity == CRITICAL for x in findings), warning=sum(x.severity == WARNING for x in findings),
                info=sum(x.severity == INFO for x in findings))


# ---------------------------------------------------------------- csv

def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _t(v, f="%Y-%m-%d %H:%M") -> str:
    return v.strftime(f) if v else ""


def _m(v) -> str:
    return "" if v is None else f"{v:g}" if isinstance(v, int) else f"{round(v, 1):g}"


def write_findings(findings: list[Finding], path: Path) -> None:
    _w(path, ["severity", "area", "code", "subject", "detail", "next_step", "owner", "items"],
       [[f.severity, f.area, f.code, f.subject, f.detail, f.fix, f.owner, "; ".join(f.items)] for f in findings])


def write_actions(findings: list[Finding], path: Path) -> None:
    _w(path, ["ref", "action", "next_step", "owner", "severity", "due", "done"],
       [[f.code, f.subject, f.fix, f.owner, f.severity, "", ""] for f in findings if f.severity != INFO])


def write_majors(b: dict, path: Path) -> None:
    out = []
    for r in b["rows"]:
        i, f = r["incident"], r["facts"]
        acts = f["actions"]
        out.append([i.number, i.priority, i.service, i.ci, i.group, _t(i.opened), _t(i.started), _t(f["first_alert"]), _t(f["users"]),
                    _t(i.detected), _t(i.acknowledged), _t(i.mitigated), _t(i.resolved), _m(f["ttd"]), _m(f["tta"]), _m(f["ttm"]), _m(f["ttr"]),
                    _m(f["impact_min"]), i.commander, i.comms_lead, i.tech_lead, len(f["updates"]),
                    sum(g["kind"] != "no resolution update" for g in f["gaps"]), "; ".join(c.number for c in f["changes"]),
                    f["problem"].number if f["problem"] else "", "yes" if f["problem"] and f["problem"].root_cause else "no",
                    _t(i.review, "%Y-%m-%d"), _t(f["pir_due"], "%Y-%m-%d"), len(acts), sum(a.is_open for a in acts),
                    sum(1 for x in r["issues"] if x.code == "ACT-01"), "; ".join(x["incident"].number for x in f["repeats"]), r["verdict"],
                    " | ".join(f"{x.code} {x.text}" for x in r["issues"])])
    _w(path, ["number", "priority", "service", "ci", "assignment_group", "opened", "impact_start", "first_alert", "first_user_report", "detected",
              "acknowledged", "mitigated", "resolved", "ttd_min", "tta_min", "ttm_min", "ttr_min", "impact_min", "commander", "comms_lead",
              "tech_lead", "updates_sent", "comms_gaps", "changes_72h", "problem", "root_cause_recorded", "review_date", "review_due",
              "actions", "actions_open", "actions_overdue", "repeats", "verdict", "issues"], out)


def write_metrics(b: dict, path: Path) -> None:
    _w(path, ["month", "priority", "incidents", "major", "mttd_min", "mtta_min", "mttm_min", "mttr_min", "ack_within_target_pct",
              "resolve_within_target_pct"],
       [[m["month"], m["priority"], m["incidents"], m["major"], _m(m["mttd"]), _m(m["mtta"]), _m(m["mttm"]), _m(m["mttr"]),
         _m(m["ack_ok"]), _m(m["resolve_ok"])] for m in b["metrics"]])


def write_gaps(b: dict, path: Path) -> None:
    _w(path, ["incident", "priority", "service", "kind", "from", "to", "gap_min", "policy_min"],
       [[r["incident"].number, r["incident"].priority, r["incident"].service, g["kind"], _t(g["start"]), _t(g["end"]), _m(g["gap"]),
         g["allowed"]] for r in b["rows"] for g in r["facts"]["gaps"]])


def overdue_actions(d: Data, b: dict) -> list[dict]:
    out = []
    for r in b["rows"]:
        for a in r["facts"]["actions"]:
            if a.is_open and a.due and a.due < d.today:
                out.append(dict(incident=r["incident"], action=a, days=(d.today - a.due).days))
    return sorted(out, key=lambda x: (-x["days"], x["action"].action_id))


def write_overdue(d: Data, b: dict, path: Path) -> None:
    _w(path, ["action_id", "incident", "problem", "action", "owner", "due", "days_overdue", "status"],
       [[x["action"].action_id, x["incident"].number, x["action"].problem, x["action"].action, x["action"].owner,
         _t(x["action"].due, "%Y-%m-%d"), x["days"], x["action"].status] for x in overdue_actions(d, b)])


def write_repeats(b: dict, path: Path) -> None:
    _w(path, ["incident", "priority", "service", "ci", "opened", "related_incident", "related_priority", "related_opened", "days_apart", "match",
              "related_summary"],
       [[i.number, i.priority, i.service, i.ci, _t(i.opened), o.number, o.priority, _t(o.opened), f"{x['days']:.1f}", x["by"], o.summary]
        for r in b["rows"] for i in [r["incident"]] for x in sorted(r["facts"]["repeats"], key=lambda x: x["days"]) for o in [x["incident"]]])


# ---------------------------------------------------------------- timeline (shared by the SVG and the review)

def timeline_of(d: Data, r: dict) -> list[tuple[datetime, str, str, str]]:
    """Every point of the incident in time order: alerts, user reports, bridge, ITSM milestones and stakeholder updates."""
    i, f = r["incident"], r["facts"]
    out = [(ev.time, ev.source, ev.actor, ev.text) for ev in d.events_of(i)]
    for a in f["alerts"]:
        if not any(t == a.fired and a.source in s for t, s, _, _ in out):
            out.append((a.fired, f"Monitoring ({a.source})", a.source, a.message))
    for t, label in ((i.started, "Impact started"), (i.detected, "Detected"), (i.opened, "Ticket opened"), (i.acknowledged, "Acknowledged"),
                     (i.mitigated, "Mitigated"), (i.resolved, "Resolved")):
        if t and not any(x == t and s == "ITSM" for x, s, _, _ in out):
            out.append((t, "ITSM", "", label))
    for u in f["updates"]:
        if not any(x == u.time and s.startswith("Stakeholder") for x, s, _, _ in out):
            out.append((u.time, "Stakeholder update", u.audience, f"{u.kind or 'Update'}: {u.summary}"))
    return sorted(out, key=lambda x: (x[0], x[1], x[3]))


LANES = [("Monitoring", "alert"), ("Users / desk", "user"), ("ITSM", "itsm"), ("Bridge", "bridge"), ("Comms", "comms")]


def _lane(source: str) -> str:
    s = source.lower()
    if s.startswith("monitoring"):
        return "alert"
    if s.startswith("itsm"):
        return "itsm"
    if s.startswith("stakeholder") or s.startswith("status page"):
        return "comms"
    if s.startswith("chat") or s.startswith("bridge"):
        return "bridge"
    return "user"


def timeline_svg(d: Data, r: dict) -> str:
    i, f = r["incident"], r["facts"]
    pts = timeline_of(d, r)
    times = [t for t, *_ in pts] + [i.start_ref, i.opened]
    t0 = min(times) - timedelta(minutes=5)
    t1 = max(times + [i.resolved or d.as_of]) + timedelta(minutes=5)
    span = max(minutes(t0, t1), 30)
    W, L, R, top = 1000, 112, 16, 34
    lane_h = 26
    H = top + lane_h * len(LANES) + 26
    x = lambda t: L + (W - L - R) * minutes(t0, t) / span  # noqa: E731
    y = {k: top + lane_h * n + lane_h / 2 for n, (_, k) in enumerate(LANES)}
    g = [f"<svg class='tl' viewBox='0 0 {W} {H}' role='img' aria-label='Timeline of {e(i.number)}'>"]
    # phases
    if i.mitigated or i.resolved:
        a, b_ = x(i.start_ref), x(i.mitigated or i.resolved)
        g.append(f"<rect class='ph-impact' x='{a:.1f}' y='8' width='{max(b_ - a, 2):.1f}' height='12' rx='3'><title>Impact {fmt_min(minutes(i.start_ref, i.mitigated or i.resolved))}"
                 f"</title></rect><text class='tl-l' x='{a + 4:.1f}' y='18'>impact</text>")
        if i.mitigated and i.resolved and i.resolved > i.mitigated:
            c = x(i.resolved)
            g.append(f"<rect class='ph-fix' x='{b_ + 2:.1f}' y='8' width='{max(c - b_ - 2, 2):.1f}' height='12' rx='3'><title>Mitigated, resolving "
                     f"{fmt_min(minutes(i.mitigated, i.resolved))}</title></rect>")
            if c - b_ > 70:
                g.append(f"<text class='tl-l' x='{b_ + 6:.1f}' y='18'>mitigated → resolved</text>")
    # lanes and grid
    step = next(s for s in (5, 10, 15, 30, 60, 120, 240, 480, 1440) if span / s <= 10)
    first = t0.replace(minute=0, second=0)
    while first < t0:
        first += timedelta(minutes=step)
    t = first
    while t <= t1:
        xx = x(t)
        g.append(f"<line class='tl-grid' x1='{xx:.1f}' x2='{xx:.1f}' y1='{top - 4}' y2='{H - 22}'/>"
                 f"<text class='tl-ax' x='{xx:.1f}' y='{H - 8}' text-anchor='middle'>{t:%H:%M}</text>")
        t += timedelta(minutes=step)
    for label, k in LANES:
        g.append(f"<line class='tl-lane' x1='{L}' x2='{W - R}' y1='{y[k]:.1f}' y2='{y[k]:.1f}'/>"
                 f"<text class='tl-lab' x='{L - 10}' y='{y[k] + 4:.1f}' text-anchor='end'>{e(label)}</text>")
    for gp in f["gaps"]:
        if gp["gap"] <= 0:
            continue
        a, b_ = x(gp["start"]), x(gp["end"])
        g.append(f"<rect class='tl-gap' x='{a:.1f}' y='{y['comms'] - 10:.1f}' width='{b_ - a:.1f}' height='20' rx='3'><title>{e(gp['kind'])}: "
                 f"{fmt_min(gp['gap'])} without an update (policy {gp['allowed']} min)</title></rect>")
    # points
    for t, src, who, text in pts:
        k = _lane(src)
        tip = e(f"{t:%H:%M} · {src}{' · ' + who if who else ''}: {text}")
        xx = x(t)
        if k == "itsm":
            g.append(f"<g class='tl-itsm'><rect x='{xx - 5:.1f}' y='{y[k] - 5:.1f}' width='10' height='10' transform='rotate(45 {xx:.1f} {y[k]:.1f})'/>"
                     f"<title>{tip}</title></g>")
        else:
            g.append(f"<circle class='tl-{k}' cx='{xx:.1f}' cy='{y[k]:.1f}' r='5.5'><title>{tip}</title></circle>")
    for t, label in ((i.opened, "opened"), (i.mitigated, "mitigated"), (i.resolved, "resolved")):
        if t:
            g.append(f"<text class='tl-l' x='{x(t):.1f}' y='{y['itsm'] - 9:.1f}' text-anchor='middle'>{label}</text>")
    g.append("</svg>")
    return "".join(g)


# ---------------------------------------------------------------- post-incident review draft

TODO = "**[TO COMPLETE IN THE REVIEW]**"


def review_md(d: Data, r: dict) -> str:
    s, i, f = d.settings, r["incident"], r["facts"]
    tg = lambda k: s.target(i.priority, k)  # noqa: E731
    vs = lambda v, k: (f"{fmt_min(v)}" + (f" (target {fmt_min(tg(k))}, {'met' if v <= tg(k) else '**missed**'})" if v is not None and tg(k) else ""))  # noqa: E731
    due_txt = f" · due {f['pir_due']:%Y-%m-%d}" if f["pir_due"] else ""
    out = [f"# Post-incident review · {i.number} · {i.summary}", "",
           f"> DRAFT generated by mickit on {now_label(d.as_of)} from the ITSM export, the timeline, the alerts and the stakeholder updates. "
           f"Everything marked {TODO} is for the people who ran the incident; check every time and figure before it is shared.", "",
           "| | |", "|---|---|",
           f"| Priority | {i.priority}{' · major incident' if i.major else ''} |",
           f"| Service · CI | {i.service or '–'} · {i.ci or '–'} |",
           f"| Assignment group | {i.group or '–'} |",
           f"| Incident commander · comms lead · tech lead | {i.commander or '**none recorded**'} · {i.comms_lead or '**none recorded**'} · "
           f"{i.tech_lead or '**none recorded**'} |",
           f"| Opened · resolved | {_t(i.opened)} · {_t(i.resolved) or 'open'} |",
           f"| Review | {('held ' + _t(i.review, '%Y-%m-%d')) if i.review else 'not held yet'}"
           f"{due_txt} |",
           f"| Automated verdict | {r['verdict']} |", "",
           "## Impact", "",
           f"- Recorded in the ticket: {i.impact or TODO}",
           f"- Impact duration: {fmt_min(f['impact_min'])} from {_t(i.start_ref, '%H:%M')} to {_t(i.mitigated or i.resolved, '%H:%M') or '–'}.",
           f"- Customers, transactions, desks or branches affected, and any regulatory or contractual reporting: {TODO}", "",
           "## Metrics", "",
           "| Measure | Value |", "|---|---|",
           f"| First signal → detected (TTD) | {fmt_min(f['ttd'])}"
           f"{' (first alert ' + _t(f['first_alert'], '%H:%M') + ')' if f['first_alert'] else ' (no alert)'} |",
           f"| Detected → ticket opened | {fmt_min(f['open_lag'])} |",
           f"| Opened → acknowledged (TTA) | {vs(f['tta'], 'ack')} |",
           f"| Opened → mitigated (TTM) | {vs(f['ttm'], 'mitigate')} |",
           f"| Opened → resolved (TTR) | {vs(f['ttr'], 'resolve')} |",
           f"| Stakeholder updates | {len(f['updates'])} sent, {sum(g['kind'] != 'no resolution update' for g in f['gaps'])} gaps over the "
           f"{s.comms_interval_min.get(i.priority, '–')} min policy |", "",
           "## Timeline", "", "| Time | Source | Who | What |", "|---|---|---|---|"]
    out += [f"| {t:%d %b %H:%M} | {src} | {who or ''} | {text.replace('|', '/')} |" for t, src, who, text in timeline_of(d, r)]
    out += ["", f"Times come from the exports. Add what only people know (decisions, calls, who was paged when): {TODO}", "",
            "## What the automated review found", ""]
    out += [f"- **{x.code}** ({x.severity}): {x.text}" for x in r["issues"]] or ["- Nothing flagged."]
    out += ["", "## Detection", "",
            f"- First alert: {_t(f['first_alert']) or 'none on this service or CI'}"
            + (f" ({', '.join(sorted({a.source for a in f['alerts']}))})" if f["alerts"] else "") + ".",
            f"- First user report: {_t(f['users']) or 'none recorded'}.",
            f"- Would monitoring have caught it earlier, and with which alert? {TODO}", "",
            "## Changes in the previous " + f"{s.change_lookback_hours} hours", ""]
    out += [f"- {c.number} · {c.summary or c.kind} · {_t(c.start)}–{_t(c.end, '%H:%M')} · {c.state}"
            + (" · linked as cause in the ticket" if i.change and c.number.lower() == i.change.lower() else " · **not linked in the ticket**")
            for c in f["changes"]] or ["- None on this service or CI."]
    out += [f"- Related to the incident? {TODO}" if f["changes"] else "", "",
            "## Root cause", ""]
    pr = f["problem"]
    out.append(f"- {pr.number}: {pr.root_cause or TODO}" if pr else f"- No problem record linked. {TODO}")
    out += ["", "## Contributing factors", "", f"{TODO} — for example: detection, runbook, change process, capacity, supplier, knowledge.", "",
            "- People and process:", "- Technology:", "- Suppliers:", "",
            "## What went well", "", f"{TODO}", "",
            "## Actions", "", "| Action | Owner | Due | Status |", "|---|---|---|---|"]
    out += [f"| {a.action_id} {a.action} | {a.owner or '–'} | {_t(a.due, '%Y-%m-%d') or '–'} | {a.status or '–'}"
            f"{' · **overdue**' if a.is_open and a.due and a.due < d.today else ''} |" for a in f["actions"]] or [f"| {TODO} | | | |"]
    out += ["", "## Repeats", ""]
    out += [f"- {x['incident'].number} {x['incident'].priority} · {x['incident'].opened:%d %b} · same {x['by']} · {x['incident'].summary}"
            for x in sorted(f["repeats"], key=lambda x: x["days"])] or [f"- None within {s.repeat_days} days."]
    out += ["", "## Sign-off", "", f"- Reviewed with: {TODO}", f"- Approved by the problem manager: {TODO}", ""]
    return "\n".join(x for x in out if x is not None)


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#f6f7f8;--card:#fff;--ink:#1b2128;--muted:#66717c;--line:#e2e5e9;--ok:#1e7a4c;--warn:#a46200;--bad:#b42318;--info:#0b6bcb}
@media (prefers-color-scheme:dark){:root{--bg:#13171b;--card:#1b2127;--ink:#e7eaee;--muted:#9aa5b0;--line:#2b333b;--ok:#4cc38a;--warn:#f0a83a;--bad:#f2685c;--info:#5aa9f0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 12px}h3{font-size:16px;margin:0 0 4px}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:10px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile b{display:block;font-size:26px}
.areas{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.area{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--ok);border-radius:10px;padding:10px 14px}
.area.critical{border-left-color:var(--bad)}.area.warning{border-left-color:var(--warn)}
.area .lbl{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:4px}.area .cnt{display:block;font-size:13px;color:var(--muted);margin-top:4px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;white-space:nowrap;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.critical{color:var(--bad)}.warning{color:var(--warn)}.info{color:var(--info)}.ok{color:var(--ok)}
.area.critical,.area.warning,.area.ok{color:inherit}
.pill.clean{color:var(--ok)}.pill.follow-up{color:var(--warn)}.pill.action-needed{color:var(--bad)}
td.nw{white-space:nowrap}td.fix{font-size:13px;color:var(--muted);max-width:380px}
.mi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:14px}
.mi .head{display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex-wrap:wrap}
.facts{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;color:var(--muted);margin:6px 0 4px}.facts b{color:var(--ink);font-weight:600}
.mi ul{margin:8px 0 0;padding-left:18px;font-size:14px}
svg.tl{width:100%;height:auto;display:block;margin-top:8px;font:11px system-ui,-apple-system,Segoe UI,sans-serif}
.tl-grid{stroke:var(--line)}.tl-lane{stroke:var(--line);stroke-dasharray:2 3}.tl-ax,.tl-lab,.tl-l{fill:var(--muted)}.tl-lab{font-size:12px}
.ph-impact{fill:var(--bad);opacity:.28}.ph-fix{fill:var(--warn);opacity:.28}.tl-gap{fill:var(--bad);opacity:.16}
.tl-alert{fill:var(--warn);stroke:var(--card);stroke-width:2}.tl-user{fill:var(--bad);stroke:var(--card);stroke-width:2}
.tl-bridge{fill:var(--muted);stroke:var(--card);stroke-width:2}.tl-comms{fill:var(--ok);stroke:var(--card);stroke-width:2}
.tl-itsm rect{fill:var(--info);stroke:var(--card);stroke-width:2}
footer{margin-top:40px;font-size:13px}
"""


def _pill(cls: str, text: str) -> str:
    return f"<span class='pill {cls}'>{e(text)}</span>"


def _vpill(v: str) -> str:
    return _pill(v.replace(" ", "-"), v.upper())


def render_html(d: Data, findings: list[Finding], title: str, b: dict) -> str:
    s, sm, st = d.settings, summary(d, findings, b), area_status(findings)
    rows = b["rows"]
    first = min((i.opened for i in d.incidents), default=d.as_of)
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>Detection, response, command, comms, changes, reviews and actions of every major incident · "
         f"incidents from {first:%d %b %Y} · as of {now_label(d.as_of)}</p><div class='tiles'>"]
    tiles = [("Major incidents", str(sm["majors"]), f"{sm['p1']} P1 · {sm['p2']} P2 · of {sm['incidents']}"),
             ("Action needed", str(sm["action_needed"]), f"{sm['follow_up']} follow up · {sm['clean']} clean"),
             ("MTTD", fmt_min(sm["mttd"]), "major incidents"), ("MTTA", fmt_min(sm["mtta"]), "major incidents"),
             ("MTTR", fmt_min(sm["mttr"]), "major incidents"),
             ("Blind spots", str(sm["blind"]), "no alert before detection"),
             ("Comms gaps", str(sm["gaps"]), f"in {sm['comms']} incidents"),
             ("Change in 72 h", str(sm["change"]), "before the impact"),
             ("Reviews late", str(sm["pir_late"]), f"{s.pir_business_days} business days"),
             ("Actions overdue", str(sm["overdue"]), f"{sm['repeats']} repeat incidents")]
    h += [f"<div class='tile'><span class='muted'>{e(a)}</span><b>{e(x)}</b><span class='muted'>{e(y)}</span></div>" for a, x, y in tiles]
    h.append("</div><h2>Status by area</h2><div class='areas'>")
    for a in AREAS:
        n = sum(f.area == a and f.severity != INFO for f in findings)
        h.append(f"<div class='area {st[a]}'><span class='lbl'>{e(a)}</span>{_pill(st[a], 'OK' if st[a] == 'ok' else st[a].upper())}"
                 f"<span class='cnt'>{n} to act on</span></div>")
    h.append("</div>")
    h.append("<h2>Major incidents</h2><div class='wrap'><table><tr><th>Incident</th><th>Service</th><th>Opened</th><th class='num'>TTD</th>"
             "<th class='num'>TTA</th><th class='num'>TTM</th><th class='num'>TTR</th><th>Review</th><th>Status</th></tr>")
    for r in rows:
        i, f = r["incident"], r["facts"]
        cls = lambda k, v: " warning" if v is not None and s.target(i.priority, k) and v > s.target(i.priority, k) else ""  # noqa: E731
        rv = f"held {i.review:%d %b}" if i.review else (f"due {f['pir_due']:%d %b}" if f["pir_due"] else "–")
        h.append(f"<tr><td class='nw'><b>{e(i.number)}</b> {_pill('info', i.priority)}</td><td>{e(i.service)}<br><span class='muted'>"
                 f"{e(i.summary)}</span></td><td class='nw'>{i.opened:%a %d %b %H:%M}</td>"
                 f"<td class='num{' warning' if f['ttd'] and f['ttd'] > s.detect_gap_min else ''}'>{fmt_min(f['ttd'])}</td>"
                 f"<td class='num{cls('ack', f['tta'])}'>{fmt_min(f['tta'])}</td><td class='num{cls('mitigate', f['ttm'])}'>{fmt_min(f['ttm'])}</td>"
                 f"<td class='num{cls('resolve', f['ttr'])}'>{fmt_min(f['ttr'])}</td><td class='nw'>{e(rv)}</td><td>{_vpill(r['verdict'])}</td></tr>")
    h.append("</table></div>")
    crit = [f for f in findings if f.severity == CRITICAL]
    if crit:
        h.append("<h2>Fix first</h2><div class='wrap'><table><tr><th>Subject</th><th>What</th><th>Next step</th><th>Owner</th></tr>")
        h += [f"<tr><td><b>{e(f.subject)}</b><br><span class='muted'>{e(f.area)} · {e(f.code)}</span></td><td>{e(f.detail)}</td>"
              f"<td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in crit]
        h.append("</table></div>")
    h.append("<h2>Timelines</h2><p class='muted'>Bar: impact (red) and mitigated → resolved (amber). Dots: monitoring alerts, user reports, "
             "bridge notes and stakeholder updates; diamonds: ticket milestones; shaded: stretches without a stakeholder update. "
             "Hover a mark for the detail.</p>")
    for r in rows:
        i, f = r["incident"], r["facts"]
        roles = " · ".join(f"{lab}: {e(v) if v else '<span class=critical>none</span>'}" for lab, v in
                           (("IC", i.commander), ("comms", i.comms_lead), ("tech", i.tech_lead)))
        h.append(f"<div class='mi'><div class='head'><h3>{e(i.number)} · {e(i.service)} · {e(i.summary)}</h3>{_vpill(r['verdict'])}</div>"
                 f"<div class='facts'><span>{e(i.priority)} · {i.opened:%a %d %b %Y}</span><span>{roles}</span>"
                 f"<span>impact <b>{fmt_min(f['impact_min'])}</b></span><span>updates <b>{len(f['updates'])}</b></span>"
                 f"<span>alerts <b>{len(f['alerts'])}</b></span></div>"
                 f"{('<div class=muted style=font-size:13px>' + e(i.impact) + '</div>') if i.impact else ''}{timeline_svg(d, r)}")
        iss = [x for x in sorted(r["issues"], key=lambda x: (x.severity != CRITICAL, x.severity == INFO))]
        if iss:
            h.append("<ul>" + "".join(f"<li><span class='{x.severity}'>●</span> <b>{e(x.code)}</b> {e(x.text)}</li>" for x in iss) + "</ul>")
        h.append("</div>")
    # metrics
    h.append("<h2>Metrics by month and priority</h2><div class='wrap'><table><tr><th>Month</th><th>Priority</th><th class='num'>Incidents</th>"
             "<th class='num'>Major</th><th class='num'>MTTD</th><th class='num'>MTTA</th><th class='num'>MTTM</th><th class='num'>MTTR</th>"
             "<th class='num'>Ack in target</th><th class='num'>Resolved in target</th></tr>")
    pc = lambda v: "–" if v is None else f"{v:g}%"  # noqa: E731
    h += [f"<tr><td class='nw'>{e(m['month'])}</td><td>{e(m['priority'])}</td><td class='num'>{m['incidents']}</td><td class='num'>{m['major']}</td>"
          f"<td class='num'>{fmt_min(m['mttd'])}</td><td class='num'>{fmt_min(m['mtta'])}</td><td class='num'>{fmt_min(m['mttm'])}</td>"
          f"<td class='num'>{fmt_min(m['mttr'])}</td><td class='num'>{pc(m['ack_ok'])}</td><td class='num'>{pc(m['resolve_ok'])}</td></tr>"
          for m in b["metrics"]]
    h.append("</table></div>")
    od = overdue_actions(d, b)
    if od:
        h.append("<h2>Post-incident actions overdue</h2><div class='wrap'><table><tr><th>Action</th><th>Incident</th><th>Owner</th><th>Due</th>"
                 "<th class='num'>Days late</th><th>Status</th></tr>")
        h += [f"<tr><td><b>{e(x['action'].action_id)}</b> {e(x['action'].action)}</td><td class='nw'>{e(x['incident'].number)}</td>"
              f"<td class='nw'>{e(x['action'].owner)}</td><td class='nw'>{x['action'].due:%d %b}</td>"
              f"<td class='num {'critical' if x['days'] > s.action_critical_days else 'warning'}'>{x['days']}</td><td>{e(x['action'].status)}</td></tr>"
              for x in od]
        h.append("</table></div>")
    h.append("<h2>All findings</h2><div class='wrap'><table><tr><th>Severity</th><th>Area</th><th>Subject</th><th>Detail</th><th>Next step</th><th>Owner</th></tr>")
    h += [f"<tr><td>{_pill(f.severity, f.severity.upper())}</td><td class='nw'>{e(f.area)}</td><td>{e(f.subject)}</td>"
          f"<td>{e(f.detail)}</td><td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in findings]
    h.append("</table></div><footer class='muted'>Generated by mickit. Fictional demo data unless you ran it on your own exports. "
             "Draft post-incident reviews are in reviews/.</footer></main></body></html>")
    return "".join(h)
