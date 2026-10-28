"""Fictional demo: Woodgrove Bank IT operations, one quarter (July to September 2026) of incidents, with six major incidents placed on
purpose among the everyday ones, their timelines, the monitoring alerts, the stakeholder updates, the changes, the problems and the
post-incident actions. Every name is made up."""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

ORG = "Woodgrove Bank · IT operations"
AS_OF = datetime(2026, 10, 5, 9, 0)
SEED = 36
PRIO = {"P1": "1 - Critical", "P2": "2 - High", "P3": "3 - Moderate", "P4": "4 - Low"}


def _t(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M")


def _s(t: datetime | None) -> str:
    return t.strftime("%Y-%m-%d %H:%M") if t else ""


# The six major incidents. Times are on the day of the incident; the problems are placed on purpose.
MAJORS = [
    dict(key="MI1", prio="P1", day="2026-07-14", started="08:02", detected="08:07", opened="08:10", ack="08:14", mitigated="09:35",
         resolved="10:40", service="Card payments", ci="auth-switch-01", group="Payments platform", detection="Monitoring",
         impact="Card authorisations failing for about 38% of transactions (POS and e-commerce) for 93 minutes",
         commander="Marta Ibarra", comms_lead="Sara Lindqvist", tech="Ravi Menon", review="2026-07-16", problem="PRB0007012", change="",
         summary="Card authorisations failing after load balancer change",
         alerts=[("08:04", "Dynatrace", "critical", "Failure rate increase on authorisation service")],
         users=[], comms=["08:20", "08:48", "09:15", "09:40", "10:05", "10:30", "R10:42"],
         bridge=[("08:12", "Ravi Menon", "Bridge open. TLS handshake errors to the acquirer from the auth pool since 08:02"),
                 ("08:41", "Ravi Menon", "Last change on the pool: SSL profile update last night (CHG0031102)"),
                 ("09:05", "Marta Ibarra", "Decision: roll back the SSL profile on the auth pool"),
                 ("09:35", "Ravi Menon", "Rollback done, authorisation success rate back to 99.6%")]),
    dict(key="MI2", prio="P1", day="2026-08-04", started="08:05", detected="08:52", opened="08:55", ack="09:02", mitigated="10:20",
         resolved="11:05", service="Online banking", ci="ob-idp-cluster", group="Digital channels", detection="Service desk",
         impact="Customers unable to log in to online banking and the mobile app for 2 h 15 min; 1,900 calls to the contact centre",
         commander="Daniel Okafor", comms_lead="Tom Becker", tech="Elena Ruiz", review="2026-08-07", problem="PRB0007040", change="",
         summary="Online banking logins failing",
         alerts=[("09:31", "Grafana", "critical", "Login success rate below 90% (synthetic check added during the incident)")],
         users=[("08:12", "Service desk", "Contact centre", "First customer calls: login page spins and times out"),
                ("08:20", "Service desk", "Social media team", "Customers posting that online banking is down"),
                ("08:38", "Service desk", "Service desk lead", "34 calls in 25 minutes, escalating to the major incident manager")],
         comms=["09:05", "09:35", "10:00", "10:25", "10:55", "R11:08"],
         bridge=[("09:00", "Elena Ruiz", "Bridge open. Identity provider answering, session store not accepting writes"),
                 ("09:40", "Elena Ruiz", "Session store volume at 100%; no disk alert configured on these nodes"),
                 ("10:20", "Elena Ruiz", "Old sessions purged, volume extended, logins working")]),
    dict(key="MI3", prio="P1", day="2026-08-21", started="07:40", detected="07:45", opened="07:48", ack="07:52", mitigated="09:10",
         resolved="12:30", service="Trader voice", ci="turret-gw-02", group="Voice & trading floor", detection="Trading desk",
         impact="Rates desk without external voice lines on 18 turrets from market open; orders moved to mobiles and the backup desk",
         commander="Lucía Prieto", comms_lead="", tech="Pablo Serrano", review="2026-08-27", problem="PRB0007066", change="",
         summary="Trading turrets without external lines on the rates desk",
         alerts=[("07:41", "SolarWinds", "critical", "Node down: SIP trunk interface on turret-gw-02")],
         users=[("07:43", "Trading desk (phone)", "Rates desk head", "No dial tone on external lines, internal calls work")],
         comms=["08:05", "08:30", "10:05"],
         bridge=[("07:55", "Pablo Serrano", "Bridge open. Carrier SIP trunk down on gateway 2; gateway 1 healthy"),
                 ("08:40", "Pablo Serrano", "Gateway 1 is not in the automatic failover group for the rates desk lines"),
                 ("09:10", "Pablo Serrano", "Lines re-homed to gateway 1 manually, dial tone back on all turrets"),
                 ("12:30", "Pablo Serrano", "Carrier restored the trunk; lines moved back and tested")]),
    dict(key="MI4", prio="P2", major=True, day="2026-09-02", started="13:10", detected="13:15", opened="13:20", ack="13:41", mitigated="15:05",
         resolved="17:50", service="Mobile banking API", ci="api-gw-mob-01", group="Digital channels", detection="Monitoring",
         impact="One in five mobile app requests failing with errors for 1 h 55 min; transfers retried by customers",
         commander="Daniel Okafor", comms_lead="Tom Becker", tech="Hannah Cole", review="", problem="", change="",
         summary="Mobile app requests failing with 502 errors",
         alerts=[("13:12", "Datadog", "critical", "5xx error rate above 5% on api-gw-mob-01")],
         users=[], comms=["13:45", "14:40", "15:30", "16:25", "17:20", "R17:55"],
         bridge=[("13:30", "Hannah Cole", "Bridge open. Gateway workers restarting under load, same pattern as last week"),
                 ("15:05", "Hannah Cole", "Worker pool doubled, errors back under 0.5%")]),
    dict(key="MI5", prio="P2", major=True, day="2026-09-18", started="02:10", detected="02:58", opened="03:02", ack="03:40", mitigated="05:10",
         resolved="07:30", service="Payments hub", ci="swift-mq-01", group="Payments platform", detection="Operations bridge",
         impact="Outbound SWIFT payments queued for 3 hours; cut-off met after the backlog cleared",
         commander="Marta Ibarra", comms_lead="Sara Lindqvist", tech="Jon Etxeberria", review="2026-09-23", problem="PRB0007101", change="",
         summary="SWIFT outbound queue not draining overnight",
         alerts=[("02:10", "Grafana", "warning", "MQ queue depth above 5,000 on swift-mq-01"),
                 ("02:40", "Grafana", "critical", "MQ queue depth above 20,000 on swift-mq-01")],
         users=[], comms=["03:30", "04:25", "05:15", "06:15", "07:05", "R07:35"],
         bridge=[("03:45", "Jon Etxeberria", "Bridge open. Sender channel to the SWIFT interface stopped after a certificate reload"),
                 ("05:10", "Jon Etxeberria", "Channel restarted, queue draining at 900 messages a minute")]),
    dict(key="MI6", prio="P1", day="2026-09-29", started="14:30", detected="14:33", opened="14:36", ack="14:40", mitigated="15:20",
         resolved="16:05", service="Market data", ci="mdfeed-ldn-01", group="Trading systems", detection="Monitoring",
         impact="Stale prices on the FX and rates pricing screens for 50 minutes; desks switched to the backup feed",
         commander="Lucía Prieto", comms_lead="Sara Lindqvist", tech="Nora Haddad", review="", problem="", change="",
         summary="Market data feed stale on pricing screens",
         alerts=[("14:31", "Dynatrace", "critical", "Response time degradation on market data handler")],
         users=[], comms=["14:45", "15:12", "15:35", "R16:08"],
         bridge=[("14:38", "Nora Haddad", "Bridge open. Feed handler stuck on a malformed message from the vendor"),
                 ("15:20", "Nora Haddad", "Desks on the backup feed; handler restarted with the message skipped")]),
]

# everyday incidents placed on purpose: the repeats before the mobile API outage
PLACED = [
    dict(when="2026-08-24 10:15", prio="P3", service="Mobile banking API", ci="api-gw-mob-01", group="Digital channels",
         summary="Intermittent 502 errors from the mobile API gateway", dur=95),
    dict(when="2026-08-27 16:40", prio="P2", service="Mobile banking API", ci="api-gw-mob-01", group="Digital channels",
         summary="Mobile API gateway workers restarting under load", dur=140),
]
FILLER = [  # service, CI, group, monitoring tool, summary
    ("Email & collaboration", "exo-hybrid-01", "Workplace", "Azure Monitor", "Mail flow delayed to external recipients"),
    ("Core banking batch", "cb-batch-01", "Core banking", "Dynatrace", "End-of-day batch job running late"),
    ("Branch network", "sdwan-hub-01", "Network", "SolarWinds", "Branch site on backup 4G link"),
    ("Treasury apps", "trs-app-02", "Trading systems", "Dynatrace", "Treasury blotter slow to load"),
    ("Branch network", "sdwan-hub-02", "Network", "SolarWinds", "High latency to branch sites in the north region"),
    ("HR portal", "hr-web-01", "Corporate apps", "Datadog", "HR portal login loop for some users"),
    ("Printing", "print-q-01", "Workplace", "SolarWinds", "Print queue stuck on head office floor 3"),
    ("Data warehouse", "dwh-etl-01", "Data platform", "Grafana", "Overnight ETL load failed and was rerun"),
    ("Virtual desktops", "vdi-pool-01", "Workplace", "Azure Monitor", "Virtual desktop sessions disconnecting"),
]
CHANGES = [  # number, service, CI, start, end, type, state, summary
    ("CHG0031102", "Card payments", "auth-switch-01", "2026-07-13 22:00", "2026-07-13 23:30", "Normal", "Closed",
     "Load balancer SSL profile update on the authorisation pool"),
    ("CHG0031890", "Online banking", "ob-idp-cluster", "2026-07-30 21:00", "2026-07-30 22:00", "Standard", "Closed",
     "Identity provider monthly patching"),
    ("CHG0032250", "Market data", "mdfeed-ldn-01", "2026-09-20 08:00", "2026-09-20 10:00", "Standard", "Closed",
     "Feed handler configuration backup"),
]
FILLER_CHANGES = [("Email & collaboration", "exo-hybrid-01", "Connector certificate renewal"),
                  ("Core banking batch", "cb-batch-01", "Batch scheduler patching"),
                  ("Branch network", "sdwan-hub-01", "SD-WAN firmware update"),
                  ("Virtual desktops", "vdi-pool-01", "Golden image monthly update"),
                  ("Data warehouse", "dwh-etl-01", "ETL job dependency change"),
                  ("Treasury apps", "trs-app-02", "Application server patching")]
PROBLEMS = [  # number, incident key, root cause, rca date, state
    ("PRB0007012", "MI1", "The SSL profile change removed a TLS 1.2 cipher suite still used by the acquirer link; the pre-production pool "
                          "does not connect to the acquirer, so the test did not catch it", "2026-07-17", "Resolved"),
    ("PRB0007040", "MI2", "Session store volume filled up after session expiry stopped running; no disk usage alert was configured on the "
                          "identity nodes and no synthetic login check existed", "2026-08-10", "Fix in progress"),
    ("PRB0007066", "MI3", "Carrier SIP trunk failure on gateway 2; gateway 1 was not in the automatic failover group for the rates desk lines",
     "2026-08-28", "Fix in progress"),
    ("PRB0007101", "MI5", "The sender channel stopped after a certificate reload and the queue depth alert only reached the console, which "
                          "nobody watches between 01:00 and 03:00", "2026-09-25", "Fix in progress"),
]
ACTIONS = [  # id, problem, incident key, action, owner, due, status, closed
    ("PIA-101", "PRB0007012", "MI1", "Add an acquirer handshake test to the load balancer pre-change checklist", "Ravi Menon", "2026-07-31",
     "Closed", "2026-07-29"),
    ("PIA-102", "PRB0007012", "MI1", "CAB: rollback plan and test evidence required for changes on payment pools", "Change manager", "2026-07-24",
     "Closed", "2026-07-22"),
    ("PIA-103", "PRB0007040", "MI2", "Synthetic login journey every 2 minutes from two locations, paging the on-call", "Monitoring lead",
     "2026-08-31", "Open", ""),
    ("PIA-104", "PRB0007040", "MI2", "Disk usage alert at 80% on the identity session store nodes", "Elena Ruiz", "2026-08-14", "Closed",
     "2026-08-12"),
    ("PIA-105", "PRB0007066", "MI3", "Add gateway 1 to the automatic failover group for all trading desk lines and test it", "Pablo Serrano",
     "2026-09-15", "In progress", ""),
    ("PIA-106", "PRB0007066", "MI3", "Quarterly failover test of the turret gateways with the carrier", "Voice & trading floor", "2026-10-30",
     "Open", ""),
    ("PIA-107", "PRB0007101", "MI5", "Route MQ queue depth alerts to the overnight on-call phone, not only the console", "Monitoring lead",
     "2026-09-30", "Open", ""),
    ("PIA-108", "PRB0007101", "MI5", "Runbook: restart the SWIFT sender channel after a certificate reload", "Jon Etxeberria", "2026-10-15",
     "Open", ""),
]


def _rows() -> dict[str, list]:
    rnd = random.Random(SEED)
    inc, alerts, timeline, comms = [], [], [], []
    # everyday incidents across the quarter
    day0 = datetime(2026, 7, 1)
    for k in range(46):
        svc, ci, grp, tool, text = FILLER[k % len(FILLER)]
        t = day0 + timedelta(days=rnd.randint(0, 91), hours=rnd.randint(7, 19), minutes=rnd.choice([0, 10, 20, 30, 40, 50]))
        prio = rnd.choice(["P2", "P3", "P3", "P3", "P4", "P4"])
        lag = rnd.choice([3, 5, 8, 12, 20])
        det = t - timedelta(minutes=lag)
        ack = t + timedelta(minutes=rnd.choice([5, 10, 15, 25, 40, 70]))
        res = t + timedelta(minutes=rnd.choice([45, 90, 150, 240, 420, 900]))
        mon = rnd.random() < 0.65
        if mon:
            alerts.append([t - timedelta(minutes=lag + rnd.choice([1, 2, 4, 9])), tool, rnd.choice(["warning", "critical"]), svc, ci, text])
        inc.append(dict(opened=t, prio=prio, started=None, detected=det, ack=ack, mitigated=None, resolved=res, service=svc, ci=ci, group=grp,
                        major="", impact="", problem="", change="", commander="", comms="", tech="", review="",
                        detection="Monitoring" if mon else "Service desk", summary=text, key=""))
    for p in PLACED:
        t = _t(p["when"])
        inc.append(dict(opened=t, prio=p["prio"], started=None, detected=t - timedelta(minutes=4), ack=t + timedelta(minutes=12), mitigated=None,
                        resolved=t + timedelta(minutes=p["dur"]), service=p["service"], ci=p["ci"], group=p["group"], major="", impact="",
                        problem="", change="", commander="", comms="", tech="", review="", detection="Monitoring", summary=p["summary"], key=""))
        alerts.append([t - timedelta(minutes=6), "Datadog", "warning", p["service"], p["ci"], "5xx error rate above 2% on api-gw-mob-01"])
    # the major incidents
    for m in MAJORS:
        at = lambda hm: _t(f"{m['day']} {hm}") if hm else None  # noqa: E731
        inc.append(dict(opened=at(m["opened"]), prio=m["prio"], started=at(m["started"]), detected=at(m["detected"]), ack=at(m["ack"]),
                        mitigated=at(m["mitigated"]), resolved=at(m["resolved"]), service=m["service"], ci=m["ci"], group=m["group"],
                        major="Accepted" if m.get("major") or m["prio"] == "P1" else "", impact=m["impact"], problem=m["problem"],
                        change=m["change"], commander=m["commander"], comms=m["comms_lead"], tech=m["tech"], review=m["review"],
                        detection=m["detection"], summary=m["summary"], key=m["key"]))
        for hm, tool, sev, msg in m["alerts"]:
            alerts.append([at(hm), tool, sev, m["service"], m["ci"], msg])
    # some noise on the major services, far from any incident
    for svc, ci, tool, when, msg in (("Card payments", "auth-switch-01", "Dynatrace", "2026-08-10 03:12", "Response time degradation (self-cleared)"),
                                     ("Trader voice", "turret-gw-02", "SolarWinds", "2026-07-08 06:55", "Interface utilisation above 80%"),
                                     ("Market data", "mdfeed-ldn-01", "Dynatrace", "2026-07-22 13:05", "Process restart detected"),
                                     ("Payments hub", "swift-mq-01", "Grafana", "2026-08-12 01:40", "MQ queue depth above 5,000 (cleared in 4 min)")):
        alerts.append([_t(when), tool, "warning", svc, ci, msg])
    inc.sort(key=lambda x: x["opened"])
    numbers = {}
    for i, x in enumerate(inc):
        x["number"] = f"INC00{41000 + i * 83}"
        if x["key"]:
            numbers[x["key"]] = x["number"]
    incidents = [[x["number"], PRIO[x["prio"]], _s(x["opened"]), _s(x["started"]), _s(x["detected"]), _s(x["ack"]), _s(x["mitigated"]),
                  _s(x["resolved"]), x["service"], x["ci"], x["group"], x["major"], x["impact"], x["problem"], x["change"], x["commander"],
                  x["comms"], x["tech"], x["review"], x["detection"], x["summary"]] for x in inc]
    alerts.sort(key=lambda a: (a[0], a[4]))
    alerts = [[f"ALR-{20000 + i}", tool, _s(t), svc, ci, sev, msg] for i, (t, tool, sev, svc, ci, msg) in enumerate(alerts)]
    # timelines and stakeholder updates of the major incidents
    for m in MAJORS:
        n = numbers[m["key"]]
        at = lambda hm: _t(f"{m['day']} {hm}")  # noqa: E731
        ev = [(at(hm), f"Monitoring ({tool})", tool, msg) for hm, tool, _, msg in m["alerts"]]
        ev += [(at(hm), src, who, text) for hm, src, who, text in m["users"]]
        ev += [(at(hm), "Chat bridge", who, text) for hm, who, text in m["bridge"]]
        ev += [(at(m["opened"]), "ITSM", "Service desk" if m["detection"] == "Service desk" else m["commander"],
                f"{n} opened as {m['prio']}: {m['summary']}"),
               (at(m["ack"]), "ITSM", m["tech"], f"Acknowledged by {m['group']}"),
               (at(m["mitigated"]), "ITSM", m["tech"], "Service restored (mitigated)"),
               (at(m["resolved"]), "ITSM", m["tech"], "Resolved")]
        external = m["service"] in ("Card payments", "Online banking", "Mobile banking API")
        audience = "Executive committee, branches, contact centre" if external else "Business owners, desk heads"
        for k, hm in enumerate(m["comms"]):
            final = hm.startswith("R")
            t = at(hm.lstrip("R"))
            kind = "Resolved" if final else "Initial" if k == 0 else "Update"
            text = (f"Resolved: {m['service']} working normally since {m['resolved']}; review to follow" if final else
                    f"{m['service']}: {m['summary'].lower()}; next update in {30 if m['prio'] == 'P1' else 60} minutes")
            comms.append([n, _s(t), audience, "Email + Teams", kind, text])
            ev.append((t, "Stakeholder update", m["comms_lead"] or m["commander"], f"{dict(Initial='Initial update', Update='Update', Resolved='Resolution notice')[kind]} sent to {audience.lower()}"))
            if external and k == 0:
                ev.append((t + timedelta(minutes=3), "Status page", m["commander"], f"Status page: {m['service']} degraded"))
        for t, src, who, text in sorted(ev, key=lambda e: (e[0], e[1], e[3])):
            timeline.append(dict(incident=n, time=t.strftime("%Y-%m-%dT%H:%M:00"), source=src, actor=who, text=text))
    # changes
    changes = [list(c) for c in CHANGES]
    for k in range(24):
        svc, ci, text = FILLER_CHANGES[k % len(FILLER_CHANGES)]
        st = day0 + timedelta(days=rnd.randint(0, 91), hours=rnd.choice([20, 21, 22]))
        changes.append([f"CHG00{32300 + k * 7}", svc, ci, _s(st), _s(st + timedelta(hours=rnd.choice([1, 2, 3]))),
                        rnd.choice(["Standard", "Standard", "Normal"]), "Closed", text])
    changes.sort(key=lambda c: (c[3], c[0]))
    problems = [[p, numbers[k], rc, d, st] for p, k, rc, d, st in PROBLEMS]
    actions = [[a, p, numbers[k], text, own, due, st, cl] for a, p, k, text, own, due, st, cl in ACTIONS]
    comms.sort(key=lambda c: (c[0], c[1]))
    return dict(incidents=incidents, alerts=alerts, comms=comms, changes=changes, problems=problems, actions=actions, timeline=timeline)


HEADERS = {
    "incidents": ["Number", "Priority", "Opened", "Impact start", "Detected", "Acknowledged", "Mitigated", "Resolved", "Business service",
                  "Configuration item", "Assignment group", "Major incident state", "Customer impact", "Problem", "Caused by change",
                  "Incident commander", "Comms lead", "Tech lead", "Review date", "Detection source", "Short description"],
    "alerts": ["Alert ID", "Source", "First fired", "Service", "CI", "Severity", "Message"],
    "comms": ["Incident", "Time", "Audience", "Channel", "Type", "Summary"],
    "changes": ["Number", "Business service", "Configuration item", "Planned start", "Planned end", "Type", "State", "Short description"],
    "problems": ["Number", "Incidents", "Root cause", "RCA date", "State"],
    "problem-actions": ["Action ID", "Problem", "Incident", "Action", "Owner", "Due date", "Status", "Closed"],
}

SETTINGS = {
    "organisation": ORG,
    "as_of": AS_OF.strftime("%Y-%m-%d %H:%M"),
    "major_priorities": ["P1"],
    "targets": {"P1": {"ack": 15, "mitigate": 120, "resolve": 240}, "P2": {"ack": 30, "mitigate": 240, "resolve": 480},
                "P3": {"ack": 60, "mitigate": 480, "resolve": 1440}, "P4": {"ack": 240, "mitigate": 1440, "resolve": 4320}},
    "comms_interval_min": {"P1": 30, "P2": 60},
    "first_update_min": {"P1": 15, "P2": 30},
    "detect_gap_min": 15,
    "open_lag_min": 15,
    "alert_lookback_min": 120,
    "change_lookback_hours": 72,
    "pir_business_days": 5,
    "holidays": ["2026-08-15", "2026-10-12"],
    "repeat_days": 30,
    "required_roles": ["commander", "comms_lead", "tech_lead"],
    "action_critical_days": 30,
    "owners": {"detection": "Monitoring lead", "response": "Major incident manager", "comms": "Major incident manager",
               "change": "Change manager", "review": "Problem manager", "actions": "Problem manager"},
}


def write(folder: Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rows = _rows()
    for name in HEADERS:
        with open(folder / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(HEADERS[name])
            w.writerows(rows[name.replace("problem-actions", "actions")])
    with open(folder / "timeline.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for e in rows["timeline"]:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    (folder / "settings.json").write_text(json.dumps(SETTINGS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return folder
