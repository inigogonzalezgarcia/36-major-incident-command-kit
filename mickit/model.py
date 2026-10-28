"""Loading: the incident export, the timeline of each incident, the monitoring alerts, the stakeholder updates, the changes, the problems
and their actions, and settings.json, with forgiving column names (ServiceNow and Jira Service Management names included), into plain
dataclasses."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

INCIDENT_ALIASES = {
    "number": ["number", "incident", "ticket", "id", "key", "issue key", "incidencia"],
    "priority": ["priority", "prioridad", "severity", "sev"],
    "opened": ["opened", "opened at", "opened_at", "created", "sys created on", "apertura"],
    "started": ["started", "impact start", "outage start", "u impact start", "inicio impacto"],
    "detected": ["detected", "detected at", "u detected", "deteccion", "detectado"],
    "acknowledged": ["acknowledged", "acknowledged at", "ack", "first response", "u acknowledged", "asignado"],
    "mitigated": ["mitigated", "restored", "service restored", "workaround", "u mitigated", "mitigado", "restablecido"],
    "resolved": ["resolved", "resolved at", "resolved_at", "resolution date", "resolutiondate", "resuelto"],
    "service": ["service", "business service", "business_service", "affected service", "servicio"],
    "ci": ["ci", "cmdb ci", "cmdb_ci", "configuration item", "component", "components", "elemento"],
    "group": ["assignment group", "assignment_group", "group", "team", "grupo"],
    "major": ["major", "major incident", "major incident state", "major_incident_state", "major flag", "mayor"],
    "impact": ["customer impact", "business impact", "impact", "impacto"],
    "problem": ["problem", "problem id", "problem_id", "linked problem", "problema"],
    "change": ["change", "caused by", "caused_by", "caused by change", "linked change", "rfc", "cambio"],
    "commander": ["incident commander", "commander", "major incident manager", "incident manager", "ic"],
    "comms_lead": ["comms lead", "communications lead", "communications manager", "comms"],
    "tech_lead": ["tech lead", "technical lead", "resolver lead", "lead engineer"],
    "review": ["review date", "pir date", "post incident review", "pir", "review", "revision"],
    "detection": ["detection source", "detected by", "contact type", "contact_type", "channel", "origen"],
    "summary": ["short description", "short_description", "summary", "title", "descripcion"],
}
TIMELINE_ALIASES = {
    "incident": ["incident", "number", "ticket", "key"],
    "time": ["time", "timestamp", "at", "when", "hora"],
    "source": ["source", "origin", "tool", "origen"],
    "actor": ["actor", "who", "author", "user", "quien"],
    "text": ["text", "message", "event", "note", "texto"],
}
ALERT_ALIASES = {
    "alert_id": ["alert id", "id", "alert", "event id"],
    "source": ["source", "tool", "monitor", "origen"],
    "fired": ["first fired", "fired", "triggered", "first seen", "start", "raised", "disparada"],
    "service": ["service", "business service", "application", "servicio"],
    "ci": ["ci", "host", "entity", "node", "resource", "object"],
    "severity": ["severity", "level", "priority", "severidad"],
    "message": ["message", "name", "title", "summary", "mensaje"],
}
COMMS_ALIASES = {
    "incident": ["incident", "number", "ticket", "key"],
    "time": ["time", "sent", "sent at", "timestamp", "hora"],
    "audience": ["audience", "to", "recipients", "stakeholders", "destinatarios"],
    "channel": ["channel", "via", "medium", "canal"],
    "kind": ["type", "kind", "update type", "tipo"],
    "summary": ["summary", "text", "message", "subject", "resumen"],
}
CHANGE_ALIASES = {
    "number": ["number", "change", "id", "key", "cambio"],
    "service": ["service", "business service", "business_service", "servicio"],
    "ci": ["ci", "cmdb ci", "cmdb_ci", "configuration item", "component"],
    "start": ["start", "planned start", "start date", "start_date", "work start", "work_start", "implementation start", "inicio"],
    "end": ["end", "planned end", "end date", "end_date", "work end", "work_end", "implementation end", "fin"],
    "kind": ["type", "kind", "category", "tipo"],
    "state": ["state", "status", "estado"],
    "summary": ["short description", "short_description", "summary", "title", "descripcion"],
}
PROBLEM_ALIASES = {
    "number": ["number", "problem", "id", "key", "problema"],
    "incidents": ["incidents", "incident", "related incidents", "first reported by", "incidencias"],
    "root_cause": ["root cause", "cause notes", "cause_notes", "rca", "cause", "causa raiz"],
    "rca_date": ["rca date", "rca recorded", "cause recorded", "fecha rca"],
    "state": ["state", "status", "estado"],
}
ACTION_ALIASES = {
    "action_id": ["action id", "id", "number", "task", "key", "accion id"],
    "problem": ["problem", "problem id", "parent", "problema"],
    "incident": ["incident", "related incident", "incidencia"],
    "action": ["action", "short description", "short_description", "summary", "title", "accion"],
    "owner": ["owner", "assigned to", "assigned_to", "assignee", "responsable"],
    "due": ["due", "due date", "due_date", "duedate", "fecha limite"],
    "status": ["status", "state", "estado"],
    "closed": ["closed", "closed at", "closed_at", "done", "resolutiondate", "cerrada"],
}
YES = {"yes", "y", "true", "1", "si", "x", "accepted", "major"}
DONE = {"closed", "done", "complete", "completed", "resolved", "cancelled", "canceled", "closed complete", "closed skipped", "cerrada",
        "hecha", "completada"}
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d %b %Y %H:%M", "%d %b %Y")
PRIORITY_WORDS = {"critical": "P1", "highest": "P1", "urgent": "P1", "high": "P2", "major": "P2", "medium": "P3", "moderate": "P3",
                  "low": "P4", "minor": "P4", "lowest": "P5", "planning": "P5", "critica": "P1", "alta": "P2", "media": "P3", "baja": "P4"}


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(ch for ch in s if not unicodedata.combining(ch))).strip()


def parse_dt(v) -> datetime | None:
    s = str(v or "").strip()
    if not s or _norm(s) in {"never", "n a", "na", "none", "null"}:
        return None
    s = re.sub(r"(\.\d+)?(Z|[+-]\d{2}:?\d{2})$", "", s)      # ISO with offset: kept as the local time written in the export
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def parse_date(v) -> date | None:
    d = parse_dt(v)
    return d.date() if d else None


def priority_of(v) -> str:
    n = _norm(v)
    m = re.match(r"^(?:p|sev|s)?\s*([1-5])\b", n)
    if m:
        return f"P{m.group(1)}"
    for w in n.split():
        if w in PRIORITY_WORDS:
            return PRIORITY_WORDS[w]
    return "P3" if n else ""


def yes(v) -> bool:
    return _norm(v) in YES


def done(v) -> bool:
    return _norm(v) in DONE


def split_refs(v) -> list[str]:
    return [x.strip() for x in re.split(r"[;,|\s]+", str(v or "")) if x.strip()]


def _read(path: Path) -> tuple[list[str], list[dict]]:
    if path.suffix.lower() in (".jsonl", ".ndjson"):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        heads = []
        for r in rows:
            heads += [k for k in r if k not in heads]
        return heads, [{k: "" if v is None else str(v) for k, v in r.items()} for r in rows]
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        return list(reader.fieldnames or []), list(reader)


def _rows(path: Path, aliases: dict[str, list[str]]) -> list[dict]:
    fields, raw = _read(path)
    heads = {_norm(h): h for h in fields}
    cols = {}
    for key, names in aliases.items():
        for n in [key.replace("_", " ")] + names:
            if _norm(n) in heads and heads[_norm(n)] not in cols.values():
                cols[key] = heads[_norm(n)]
                break
    return [{k: (r.get(c) or "").strip() for k, c in cols.items()} for r in raw]


@dataclass
class Incident:
    number: str
    priority: str
    opened: datetime
    started: datetime | None = None
    detected: datetime | None = None
    acknowledged: datetime | None = None
    mitigated: datetime | None = None
    resolved: datetime | None = None
    service: str = ""
    ci: str = ""
    group: str = ""
    major: bool = False
    impact: str = ""
    problem: str = ""
    change: str = ""
    commander: str = ""
    comms_lead: str = ""
    tech_lead: str = ""
    review: date | None = None
    detection: str = ""
    summary: str = ""

    @property
    def detected_at(self) -> datetime:
        return self.detected or self.opened

    @property
    def start_ref(self) -> datetime:
        return self.started or self.detected_at


@dataclass
class Event:
    incident: str
    time: datetime
    source: str = ""
    actor: str = ""
    text: str = ""


@dataclass
class Alert:
    fired: datetime
    source: str = ""
    service: str = ""
    ci: str = ""
    severity: str = ""
    message: str = ""
    alert_id: str = ""


@dataclass
class Update:
    incident: str
    time: datetime
    audience: str = ""
    channel: str = ""
    kind: str = ""
    summary: str = ""

    @property
    def final(self) -> bool:
        n = _norm(f"{self.kind} {self.summary}")
        return any(w in n.split() for w in ("resolved", "resolution", "final", "closed", "resuelto"))


@dataclass
class Change:
    number: str
    start: datetime
    end: datetime
    service: str = ""
    ci: str = ""
    kind: str = ""
    state: str = ""
    summary: str = ""


@dataclass
class Problem:
    number: str
    incidents: list[str] = field(default_factory=list)
    root_cause: str = ""
    rca_date: date | None = None
    state: str = ""


@dataclass
class Action:
    action_id: str
    action: str = ""
    problem: str = ""
    incident: str = ""
    owner: str = ""
    due: date | None = None
    status: str = ""
    closed: date | None = None

    @property
    def is_open(self) -> bool:
        return not done(self.status) and self.closed is None


DEFAULT_TARGETS = {"P1": {"ack": 15, "mitigate": 120, "resolve": 240}, "P2": {"ack": 30, "mitigate": 240, "resolve": 480},
                   "P3": {"ack": 60, "mitigate": 480, "resolve": 1440}, "P4": {"ack": 240, "mitigate": 1440, "resolve": 4320}}


@dataclass
class Settings:
    organisation: str = "IT operations"
    as_of: datetime | None = None
    major_priorities: list = field(default_factory=lambda: ["P1"])
    targets: dict = field(default_factory=lambda: {k: dict(v) for k, v in DEFAULT_TARGETS.items()})
    comms_interval_min: dict = field(default_factory=lambda: {"P1": 30, "P2": 60})
    first_update_min: dict = field(default_factory=lambda: {"P1": 15, "P2": 30})
    detect_gap_min: int = 15
    open_lag_min: int = 15
    alert_lookback_min: int = 120
    change_lookback_hours: int = 72
    pir_business_days: int = 5
    holidays: list = field(default_factory=list)
    repeat_days: int = 30
    required_roles: list = field(default_factory=lambda: ["commander", "comms_lead", "tech_lead"])
    action_critical_days: int = 30
    owners: dict = field(default_factory=lambda: {"detection": "Monitoring lead", "response": "Major incident manager",
                                                  "comms": "Major incident manager", "change": "Change manager",
                                                  "review": "Problem manager", "actions": "Problem manager"})

    def owner(self, key: str) -> str:
        return self.owners.get(key, "")

    def target(self, priority: str, key: str) -> float | None:
        return (self.targets.get(priority) or {}).get(key)

    def is_holiday(self, d: date) -> bool:
        return d.weekday() >= 5 or d.isoformat() in {str(x) for x in self.holidays}


def settings_from_dict(raw: dict) -> Settings:
    s = Settings()
    for k, v in raw.items():
        if not hasattr(s, k):
            continue
        cur = getattr(s, k)
        if k == "as_of":
            v = parse_dt(v)
        elif k in ("owners", "comms_interval_min", "first_update_min"):
            v = {**cur, **{(priority_of(a) if k != "owners" else a): b for a, b in v.items()}}
        elif k == "targets":
            v = {**cur, **{priority_of(a): {**cur.get(priority_of(a), {}), **b} for a, b in v.items()}}
        elif k == "major_priorities":
            v = [priority_of(x) for x in v]
        elif isinstance(cur, bool):
            v = bool(v)
        elif isinstance(cur, int):
            v = int(v)
        setattr(s, k, v)
    return s


def load_incidents(path: Path, s: Settings | None = None) -> list[Incident]:
    s = s or Settings()
    out = []
    for r in _rows(path, INCIDENT_ALIASES):
        t = parse_dt(r.get("opened"))
        if not r.get("number") or not t:
            continue
        p = priority_of(r.get("priority"))
        major = yes(r.get("major")) or p in s.major_priorities
        out.append(Incident(r["number"], p, t, parse_dt(r.get("started")), parse_dt(r.get("detected")), parse_dt(r.get("acknowledged")),
                            parse_dt(r.get("mitigated")), parse_dt(r.get("resolved")), r.get("service", ""), r.get("ci", ""),
                            r.get("group", ""), major, r.get("impact", ""), r.get("problem", ""), r.get("change", ""),
                            r.get("commander", ""), r.get("comms_lead", ""), r.get("tech_lead", ""), parse_date(r.get("review")),
                            r.get("detection", ""), r.get("summary", "")))
    return sorted(out, key=lambda i: (i.opened, i.number))


def load_timeline(path: Path) -> list[Event]:
    out = [Event(r.get("incident", ""), t, r.get("source", ""), r.get("actor", ""), r.get("text", ""))
           for r in _rows(path, TIMELINE_ALIASES) for t in [parse_dt(r.get("time"))] if t]
    return sorted(out, key=lambda e: (e.incident, e.time))


def load_alerts(path: Path) -> list[Alert]:
    out = [Alert(t, r.get("source", ""), r.get("service", ""), r.get("ci", ""), r.get("severity", ""), r.get("message", ""), r.get("alert_id", ""))
           for r in _rows(path, ALERT_ALIASES) for t in [parse_dt(r.get("fired"))] if t]
    return sorted(out, key=lambda a: (a.fired, a.alert_id))


def load_comms(path: Path) -> list[Update]:
    out = [Update(r.get("incident", ""), t, r.get("audience", ""), r.get("channel", ""), r.get("kind", ""), r.get("summary", ""))
           for r in _rows(path, COMMS_ALIASES) for t in [parse_dt(r.get("time"))] if t]
    return sorted(out, key=lambda u: (u.incident, u.time))


def load_changes(path: Path) -> list[Change]:
    out = []
    for r in _rows(path, CHANGE_ALIASES):
        st = parse_dt(r.get("start"))
        if not st:
            continue
        en = parse_dt(r.get("end")) or st + timedelta(hours=1)
        out.append(Change(r.get("number", ""), st, en, r.get("service", ""), r.get("ci", ""), r.get("kind", ""), r.get("state", ""),
                          r.get("summary", "")))
    return sorted(out, key=lambda c: (c.start, c.number))


def load_problems(path: Path) -> list[Problem]:
    return [Problem(r["number"], split_refs(r.get("incidents")), r.get("root_cause", ""), parse_date(r.get("rca_date")), r.get("state", ""))
            for r in _rows(path, PROBLEM_ALIASES) if r.get("number")]


def load_actions(path: Path) -> list[Action]:
    return [Action(r.get("action_id") or f"A{k + 1:03d}", r.get("action", ""), r.get("problem", ""), r.get("incident", ""), r.get("owner", ""),
                   parse_date(r.get("due")), r.get("status", ""), parse_date(r.get("closed")))
            for k, r in enumerate(_rows(path, ACTION_ALIASES)) if r.get("action") or r.get("action_id")]


def same(a: str, b: str) -> bool:
    return bool(_norm(a)) and _norm(a) == _norm(b)


@dataclass
class Data:
    settings: Settings
    as_of: datetime
    incidents: list[Incident]
    timeline: list[Event] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    comms: list[Update] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)

    @property
    def today(self) -> date:
        return self.as_of.date()

    def majors(self) -> list[Incident]:
        return [i for i in self.incidents if i.major and i.opened <= self.as_of]

    def events_of(self, inc: Incident) -> list[Event]:
        return [e for e in self.timeline if same(e.incident, inc.number)]

    def updates_of(self, inc: Incident) -> list[Update]:
        return [u for u in self.comms if same(u.incident, inc.number)]

    def problem_of(self, inc: Incident) -> Problem | None:
        if inc.problem:
            p = next((x for x in self.problems if same(x.number, inc.problem)), None)
            if p:
                return p
        return next((x for x in self.problems if any(same(r, inc.number) for r in x.incidents)), None)

    def actions_of(self, inc: Incident) -> list[Action]:
        p = self.problem_of(inc)
        return [a for a in self.actions if same(a.incident, inc.number) or (p and same(a.problem, p.number))]


def _opt(folder: Path, names: tuple[str, ...], fn):
    for n in names:
        if (folder / n).exists():
            return fn(folder / n)
    return []


def load(folder: Path, as_of: datetime | date | None = None) -> Data:
    folder = Path(folder)
    if not (folder / "incidents.csv").exists():
        raise FileNotFoundError(f"{folder / 'incidents.csv'} not found: the incident export is required")
    sp = folder / "settings.json"
    s = settings_from_dict(json.loads(sp.read_text(encoding="utf-8"))) if sp.exists() else Settings()
    inc = load_incidents(folder / "incidents.csv", s)
    if not inc:
        raise ValueError("incidents.csv has no rows with a number and an opened time")
    if isinstance(as_of, date) and not isinstance(as_of, datetime):
        as_of = datetime.combine(as_of, datetime.min.time()) + timedelta(hours=9)
    when = as_of or s.as_of or datetime.now().replace(second=0, microsecond=0)
    return Data(s, when, inc, _opt(folder, ("timeline.jsonl", "timeline.csv"), load_timeline), _opt(folder, ("alerts.csv",), load_alerts),
                _opt(folder, ("comms.csv",), load_comms), _opt(folder, ("changes.csv",), load_changes),
                _opt(folder, ("problems.csv",), load_problems), _opt(folder, ("problem-actions.csv",), load_actions))


def add_business_days(d: date, n: int, s: Settings) -> date:
    k = 0
    while k < n:
        d += timedelta(days=1)
        if not s.is_holiday(d):
            k += 1
    return d


def business_days_between(a: date, b: date, s: Settings) -> int:
    """Business days after a up to and including b (0 when b <= a)."""
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if not s.is_holiday(d):
            n += 1
    return n


def minutes(a: datetime | None, b: datetime | None) -> float | None:
    return None if a is None or b is None else (b - a).total_seconds() / 60
