"""The checks: for every major incident, how it was detected (first alert, user reports, the ticket), how fast it was acknowledged,
mitigated and resolved against the targets of its priority, who ran it, how often stakeholders heard from it, the changes made to the
service in the days before, the post-incident review, the root cause and the actions, and the incidents that came back. Each finding says
what to do and who owns it."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean

from .model import Alert, Change, Data, Incident, _norm, add_business_days, minutes, same

CRITICAL, WARNING, INFO = "critical", "warning", "info"
ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}
AREAS = ("Detection", "Response", "Command & comms", "Change", "Review & actions", "Repeats")
VERDICT = {CRITICAL: "action needed", WARNING: "follow up", None: "clean"}
ROLE_LABEL = {"commander": "incident commander", "comms_lead": "comms lead", "tech_lead": "tech lead"}
USER_SOURCES = ("user", "users", "service desk", "servicedesk", "phone", "call", "email", "customer", "branch", "trader", "desk", "self service",
                "walk in", "social")


@dataclass
class Finding:
    severity: str
    area: str
    code: str
    subject: str
    detail: str
    fix: str
    owner: str = ""
    items: list[str] = field(default_factory=list)


@dataclass
class Issue:
    severity: str
    code: str
    text: str


def _n(k: int, word: str, plural: str | None = None) -> str:
    return f"{k} {word if k == 1 else (plural or word + 's')}"


def _top(items: list[str], k: int = 6) -> str:
    return ", ".join(items[:k]) + (f" and {len(items) - k} more" if len(items) > k else "")


def fmt_min(m: float | None) -> str:
    if m is None:
        return "–"
    m = round(m)
    return f"{m} min" if abs(m) < 120 else f"{m // 60} h {m % 60:02d}"


# ---------------------------------------------------------------- per incident facts

def related_alerts(d: Data, inc: Incident) -> list[Alert]:
    """Alerts on the incident's service or CI from `alert_lookback_min` before the impact started until it was resolved."""
    lo = inc.start_ref - timedelta(minutes=d.settings.alert_lookback_min)
    hi = inc.resolved or inc.mitigated or inc.detected_at + timedelta(hours=4)
    return [a for a in d.alerts if lo <= a.fired <= hi and (same(a.service, inc.service) or same(a.ci, inc.ci))]


def user_reported(d: Data, inc: Incident) -> datetime | None:
    """First time users told us: a timeline event from the service desk or users, or the detection source of the ticket."""
    hits = [e.time for e in d.events_of(inc) if any(w in _norm(e.source).split() or _norm(e.source).startswith(w) for w in USER_SOURCES)]
    if hits:
        return min(hits)
    n = _norm(inc.detection)
    return inc.detected_at if n and any(n.startswith(w) for w in USER_SOURCES) else None


def changes_before(d: Data, inc: Incident) -> list[Change]:
    """Changes on the service or CI whose window was within `change_lookback_hours` before the impact started (or still running)."""
    lo = inc.start_ref - timedelta(hours=d.settings.change_lookback_hours)
    return [c for c in d.changes if c.start <= inc.start_ref and c.end >= lo and (same(c.service, inc.service) or same(c.ci, inc.ci))]


def comms_gaps(d: Data, inc: Incident) -> list[dict]:
    """Every stretch longer than the policy without a stakeholder update, from the ticket opening until the resolution notice."""
    s = d.settings
    every = s.comms_interval_min.get(inc.priority)
    if not every:
        return []
    first = s.first_update_min.get(inc.priority, every)
    end = inc.resolved or inc.mitigated or d.as_of
    ups = sorted({u.time for u in d.updates_of(inc) if inc.opened <= u.time <= end + timedelta(minutes=every)})
    out = []
    prev, allowed = inc.opened, first
    for t in ups:
        if t > end:
            break
        gap = minutes(prev, t)
        if gap > allowed:
            out.append(dict(start=prev, end=t, gap=gap, allowed=allowed, kind="first update late" if prev == inc.opened else "gap"))
        prev, allowed = t, every
    gap = minutes(prev, end)
    if gap > allowed:
        out.append(dict(start=prev, end=end, gap=gap, allowed=allowed, kind="no update before resolution" if prev != inc.opened else "no updates"))
    if inc.resolved and not any(u.final for u in d.updates_of(inc) if u.time >= (inc.mitigated or inc.opened)):
        out.append(dict(start=inc.resolved, end=inc.resolved, gap=0.0, allowed=0, kind="no resolution update"))
    return out


def repeats_of(d: Data, inc: Incident) -> list[dict]:
    """Other incidents on the same CI (or, without CI, the same service) within `repeat_days` before or after this one."""
    w = timedelta(days=d.settings.repeat_days)
    out = []
    for o in d.incidents:
        if o is inc or abs(o.opened - inc.opened) > w or o.opened > d.as_of:
            continue
        by = "CI" if same(o.ci, inc.ci) else "service" if same(o.service, inc.service) and not (o.ci and inc.ci) else ""
        if by:
            out.append(dict(incident=o, by=by, days=(o.opened - inc.opened).total_seconds() / 86400))
    return out


def facts(d: Data, inc: Incident) -> dict:
    s = d.settings
    al = related_alerts(d, inc)
    first_alert = min((a.fired for a in al), default=None)
    users = user_reported(d, inc)
    signals = [t for t in (inc.started, first_alert, users) if t]
    first_signal = min(signals) if signals else None
    pir_due = add_business_days((inc.resolved or inc.mitigated or inc.opened).date(), s.pir_business_days, s) if inc.resolved else None
    return dict(alerts=al, first_alert=first_alert, users=users, first_signal=first_signal,
                alert_before=bool(first_alert and first_alert <= inc.detected_at),
                ttd=minutes(first_signal, inc.detected_at) if first_signal and first_signal <= inc.detected_at else None,
                alert_to_detect=minutes(first_alert, inc.detected_at) if first_alert and first_alert <= inc.detected_at else None,
                open_lag=minutes(inc.detected_at, inc.opened), tta=minutes(inc.opened, inc.acknowledged), ttm=minutes(inc.opened, inc.mitigated),
                ttr=minutes(inc.opened, inc.resolved), impact_min=minutes(inc.start_ref, inc.mitigated or inc.resolved),
                changes=changes_before(d, inc), gaps=comms_gaps(d, inc), updates=d.updates_of(inc), problem=d.problem_of(inc),
                actions=d.actions_of(inc), pir_due=pir_due, repeats=repeats_of(d, inc))


# ---------------------------------------------------------------- per major incident

def incident_rows(d: Data) -> list[dict]:
    s = d.settings
    rows = []
    for inc in d.majors():
        f = facts(d, inc)
        iss: list[Issue] = []
        add = lambda sev, code, text: iss.append(Issue(sev, code, text))  # noqa: E731
        p1 = inc.priority == "P1"
        # detection
        if not f["alert_before"]:
            how = f"reported by {inc.detection or 'users'}" if f["users"] else f"detected via {inc.detection or 'the ticket'}"
            late = f"; first alert {fmt_min(minutes(inc.detected_at, f['first_alert']))} after detection" if f["first_alert"] else "; no alert at all"
            add(CRITICAL if p1 else WARNING, "DET-01", f"monitoring blind spot: no alert on {inc.ci or inc.service} before detection, {how}{late}")
        if f["ttd"] is not None and f["ttd"] > s.detect_gap_min:
            src = "first alert" if f["first_signal"] == f["first_alert"] else "users reported" if f["first_signal"] == f["users"] else "impact started"
            add(WARNING, "DET-02", f"detected {fmt_min(f['ttd'])} after the first signal ({src} {f['first_signal']:%H:%M}, detected "
                                   f"{inc.detected_at:%H:%M}; limit {s.detect_gap_min} min)")
        if f["open_lag"] is not None and f["open_lag"] > s.open_lag_min:
            add(WARNING, "DET-03", f"ticket opened {fmt_min(f['open_lag'])} after detection (limit {s.open_lag_min} min)")
        # response against targets
        for code, key, label, val, ts in (("RSP-01", "ack", "acknowledged", f["tta"], inc.acknowledged),
                                          ("RSP-02", "mitigate", "mitigated", f["ttm"], inc.mitigated),
                                          ("RSP-03", "resolve", "resolved", f["ttr"], inc.resolved)):
            tgt = s.target(inc.priority, key)
            if tgt is None:
                continue
            if ts is None and code != "RSP-01" and minutes(inc.opened, d.as_of) > tgt:
                add(WARNING, code, f"not {label} yet, {fmt_min(minutes(inc.opened, d.as_of))} after opening (target {fmt_min(tgt)})")
            elif val is not None and val > tgt:
                add(CRITICAL if p1 and val > 2 * tgt else WARNING, code, f"{label} in {fmt_min(val)} (target {fmt_min(tgt)} for {inc.priority})")
        # command and comms
        missing = [ROLE_LABEL.get(r, r) for r in s.required_roles if not getattr(inc, r, "")]
        if missing:
            sev = CRITICAL if "incident commander" in missing and p1 else WARNING
            add(sev, "CMD-01", f"no {', '.join(missing)} recorded")
        every = s.comms_interval_min.get(inc.priority)
        for g in f["gaps"]:
            if g["kind"] == "no resolution update":
                add(WARNING, "COM-01", "no resolution update sent to stakeholders")
            else:
                sev = CRITICAL if p1 and (g["gap"] > 2 * (every or g["allowed"]) or g["kind"] == "no updates") else WARNING
                add(sev, "COM-01", f"{g['kind']}: {fmt_min(g['gap'])} without a stakeholder update from {g['start']:%H:%M} to {g['end']:%H:%M} "
                                   f"(policy {g['allowed']} min)")
        # change
        for c in f["changes"]:
            linked = same(c.number, inc.change)
            when = "in progress when the impact started" if c.end >= inc.start_ref else \
                f"ended {fmt_min(minutes(c.end, inc.start_ref))} before the impact"
            add(WARNING, "CHG-01", f"{c.number} on {c.ci or c.service} ({c.summary or c.kind}) {when}"
                                   + ("; linked as cause" if linked else "; not linked to the incident"))
        # review, RCA, actions
        if f["pir_due"]:
            due = f["pir_due"]
            if inc.review:
                if inc.review > due:
                    add(WARNING, "PIR-01", f"review held {inc.review:%d %b}, after the due date {due:%d %b} ({s.pir_business_days} business days)")
            elif d.today > due:
                add(CRITICAL if p1 else WARNING, "PIR-01", f"no post-incident review recorded; due {due:%a %d %b}")
            else:
                add(INFO, "PIR-01", f"post-incident review due by {due:%a %d %b}")
            if d.today > due:
                pr = f["problem"]
                if not pr:
                    add(WARNING, "PIR-02", "no problem record linked: the root cause has nowhere to live")
                elif not pr.root_cause:
                    add(WARNING, "PIR-02", f"{pr.number} has no root cause recorded")
                if not f["actions"]:
                    add(WARNING, "ACT-02", "no post-incident actions recorded")
        for a in f["actions"]:
            if a.is_open and a.due and a.due < d.today:
                late = (d.today - a.due).days
                add(CRITICAL if late > s.action_critical_days else WARNING, "ACT-01",
                    f"{a.action_id} \"{a.action}\" ({a.owner or 'no owner'}) overdue {late} days")
        # repeats
        before = [r for r in f["repeats"] if r["days"] < 0]
        after = [r for r in f["repeats"] if r["days"] > 0]
        ref = lambda rs: _top([f"{x.number} {x.priority} on {x.opened:%d %b}" for x in (r["incident"] for r in rs)], 4)  # noqa: E731
        if before:
            add(WARNING, "REP-01", f"repeat: {ref(before)} on the same {before[0]['by']} in the {s.repeat_days} days before")
        if after:
            add(WARNING, "REP-01", f"came back: {ref(after)} on the same {after[0]['by']} within {s.repeat_days} days")
        sev = CRITICAL if any(i.severity == CRITICAL for i in iss) else WARNING if any(i.severity == WARNING for i in iss) else None
        rows.append(dict(incident=inc, facts=f, issues=iss, severity=sev, verdict=VERDICT[sev]))
    return rows


# ---------------------------------------------------------------- metrics

def metrics(d: Data) -> list[dict]:
    """MTTD, MTTA, MTTM and MTTR by month and priority, over every incident opened up to the review date."""
    by = defaultdict(list)
    for i in d.incidents:
        if i.opened <= d.as_of:
            by[(f"{i.opened:%Y-%m}", i.priority)].append(i)
    out = []
    for (month, p), xs in sorted(by.items()):
        fs = [(i, facts(d, i)) for i in xs]
        avg = lambda vals: round(mean(vals), 1) if vals else None  # noqa: E731
        within = lambda key, k: [v <= d.settings.target(p, key) for _, f in fs for v in [f[k]] if v is not None  # noqa: E731
                                 and d.settings.target(p, key) is not None]
        pct = lambda xs_: round(100 * sum(xs_) / len(xs_)) if xs_ else None  # noqa: E731
        out.append(dict(month=month, priority=p, incidents=len(xs), major=sum(i.major for i in xs),
                        mttd=avg([f["ttd"] for _, f in fs if f["ttd"] is not None]), mtta=avg([f["tta"] for _, f in fs if f["tta"] is not None]),
                        mttm=avg([f["ttm"] for _, f in fs if f["ttm"] is not None]), mttr=avg([f["ttr"] for _, f in fs if f["ttr"] is not None]),
                        ack_ok=pct(within("ack", "tta")), resolve_ok=pct(within("resolve", "ttr"))))
    return out


# ---------------------------------------------------------------- findings

def _collect(rows: list[dict], code: str) -> list[tuple[dict, Issue]]:
    return [(r, i) for r in rows for i in r["issues"] if i.code == code]


def run_all(d: Data, rows: list[dict] | None = None) -> list[Finding]:
    s = d.settings
    rows = rows if rows is not None else incident_rows(d)
    o = s.owner
    out: list[Finding] = []

    def per_incident(code, area, owner, word, fix, sevs=(CRITICAL, WARNING)):
        hits = _collect(rows, code)
        for sev in sevs:
            hs = [(r, i) for r, i in hits if i.severity == sev]
            if not hs:
                continue
            ids = sorted({r["incident"].number for r, _ in hs})
            det = [f"{r['incident'].number} {r['incident'].priority} {r['incident'].service} ({r['incident'].opened:%d %b}): {i.text}" for r, i in hs]
            out.append(Finding(sev, area, code, f"{_n(len(ids), 'major incident')} {word}", _top(det, 8), fix, owner, ids))

    per_incident("DET-01", "Detection", o("detection"), "with no monitoring alert before detection",
                 "Add the synthetic check or the alert that would have caught it (login journey, API error rate, queue depth) and route it to "
                 "the on-call rota; record the new alert as a post-incident action.")
    per_incident("DET-02", "Detection", o("detection"), "detected long after the first signal",
                 "Review who received the first alert and why it was not acted on: routing, severity, noise on the console, overnight cover.")
    per_incident("DET-03", "Detection", o("response"), "with the ticket opened late",
                 "Open the ticket when the bridge opens, not after: the ticket time is what every SLA and report is measured from.")
    per_incident("RSP-01", "Response", o("response"), "acknowledged over target",
                 "Check the paging path for the assignment group (on-call rota, escalation after no answer) and test it.")
    per_incident("RSP-02", "Response", o("response"), "mitigated over target",
                 "Look for the faster way back in the review: a rollback, a failover or a documented workaround in the runbook.")
    per_incident("RSP-03", "Response", o("response"), "resolved over target",
                 "Agree in the review whether the target or the fix path is wrong, and record it.")
    per_incident("CMD-01", "Command & comms", o("response"), "with incident roles missing",
                 "Name an incident commander, a comms lead and a tech lead in the first ten minutes (`python -m mickit start`), and record them "
                 "in the ticket.")
    per_incident("COM-01", "Command & comms", o("comms"), "with gaps in stakeholder updates",
                 "Send an update every interval even when nothing changed (\"still investigating, next update at ...\"), and a resolution notice.")
    per_incident("CHG-01", "Change", o("change"), "with a change on the service in the days before",
                 "Confirm or rule out the change in the review; link it as the cause in the ticket if confirmed and bring it to the next CAB.",
                 (WARNING,))
    per_incident("PIR-01", "Review & actions", o("review"), "without a timely post-incident review",
                 f"Hold the review within {s.pir_business_days} business days with the people on the bridge; start from the draft in reviews/.")
    per_incident("PIR-01", "Review & actions", o("review"), "with the review still due", "Book the review now.", (INFO,))
    per_incident("PIR-02", "Review & actions", o("review"), "without a root cause recorded",
                 "Open or link a problem record and write the root cause in it, even when it is 'not found yet' with the next step.")
    per_incident("ACT-01", "Review & actions", o("actions"), "with post-incident actions overdue",
                 "Chase the owners with a new date, or close the action with the reason; bring the list to the weekly problem review.")
    per_incident("ACT-02", "Review & actions", o("actions"), "with no post-incident actions",
                 "Every major incident should leave at least one action: an alert, a runbook step, a fix or a test.")
    per_incident("REP-01", "Repeats", o("review"), "on a service or CI that failed again within the window",
                 "Treat the group as one problem: one root cause, one owner, and a check that the fix holds.", (WARNING,))
    open_major = [i for i in d.majors() if not i.resolved]
    if open_major:
        out.append(Finding(INFO, "Response", "RSP-04", f"{_n(len(open_major), 'major incident')} still open",
                           _top([f"{i.number} {i.service}" for i in open_major]), "Follow up on the bridge.", o("response"),
                           [i.number for i in open_major]))
    m = metrics(d)
    tot = defaultdict(lambda: [0, [], []])
    for r in m:
        t = tot[r["priority"]]
        t[0] += r["incidents"]
        if r["mtta"] is not None:
            t[1].append((r["mtta"], r["incidents"]))
        if r["mttr"] is not None:
            t[2].append((r["mttr"], r["incidents"]))
    wavg = lambda xs: sum(a * n for a, n in xs) / sum(n for _, n in xs) if xs else None  # noqa: E731
    if tot:
        out.append(Finding(INFO, "Response", "MET-01", f"{_n(sum(t[0] for t in tot.values()), 'incident')} in the period",
                           "; ".join(f"{p}: {t[0]}, MTTA {fmt_min(wavg(t[1]))}, MTTR {fmt_min(wavg(t[2]))}" for p, t in sorted(tot.items())),
                           "Watch the monthly trend in metrics.csv.", o("response")))
    out.sort(key=lambda f: (ORDER[f.severity], AREAS.index(f.area), f.code))
    return out


def area_status(findings: list[Finding]) -> dict[str, str]:
    st = {}
    for a in AREAS:
        sev = [f.severity for f in findings if f.area == a and f.severity != INFO]
        st[a] = CRITICAL if CRITICAL in sev else WARNING if sev else "ok"
    return st


def now_label(when: datetime) -> str:
    return f"{when:%a %d %b %Y %H:%M}"
