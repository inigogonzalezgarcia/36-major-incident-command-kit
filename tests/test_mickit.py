import csv
import hashlib
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from mickit import cli
from mickit.checks import CRITICAL, INFO, ORDER, WARNING, comms_gaps, facts, incident_rows, metrics, run_all
from mickit.model import (Action, Alert, Change, Data, Event, Incident, Problem, Update, add_business_days, load, load_incidents, load_timeline,
                          parse_dt, priority_of, settings_from_dict)

AS_OF = datetime(2026, 10, 5, 9, 0)
DAY = datetime(2026, 9, 29)


def write(path: Path, header: list[str], rows: list[list], delimiter: str = ",") -> Path:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=delimiter)
        w.writerow(header)
        w.writerows(rows)
    return path


def at(hm: str, day: datetime = DAY) -> datetime:
    h, m = hm.split(":")
    return day + timedelta(hours=int(h), minutes=int(m))


def inc(number="INC1", priority="P1", **kw) -> Incident:
    base = dict(started=at("10:00"), detected=at("10:03"), acknowledged=at("10:10"), mitigated=at("11:00"), resolved=at("12:00"),
                service="Online banking", ci="ob-idp", major=True, commander="IC", comms_lead="Comms", tech_lead="Tech", review=date(2026, 9, 30))
    base.update(kw)
    opened = base.pop("opened", at("10:05"))
    return Incident(number, priority, opened, **base)


def good_comms(i: Incident, every: int = 30) -> list[Update]:
    t, out = i.opened + timedelta(minutes=10), []
    while t < i.resolved:
        out.append(Update(i.number, t, kind="Update"))
        t += timedelta(minutes=every)
    out.append(Update(i.number, i.resolved + timedelta(minutes=2), kind="Resolved"))
    return out


def data(incidents=None, alerts=None, comms=None, changes=None, problems=None, actions=None, timeline=None, **raw) -> Data:
    s = settings_from_dict(raw)
    incidents = incidents or [inc()]
    if comms is None:
        comms = [u for i in incidents if i.resolved for u in good_comms(i)]
    if alerts is None:
        alerts = [Alert(i.started + timedelta(minutes=1), "Dynatrace", i.service, i.ci) for i in incidents if i.started]
    if problems is None:
        problems = [Problem(f"PRB-{i.number}", [i.number], "root cause") for i in incidents]
    if actions is None:
        actions = [Action(f"A-{i.number}", "fix", f"PRB-{i.number}", owner="Owner", due=date(2026, 11, 30), status="Open") for i in incidents]
    return Data(s, AS_OF, incidents, timeline or [], alerts, comms, changes or [], problems, actions)


def issues(d: Data, number: str = "INC1") -> tuple[dict, dict]:
    r = next(x for x in incident_rows(d) if x["incident"].number == number)
    out = {}
    for i in r["issues"]:
        out.setdefault(i.code, []).append(i)
    return out, r


class TestLoading(unittest.TestCase):
    def test_servicenow_export_with_display_values(self):
        with tempfile.TemporaryDirectory() as t:
            p = write(Path(t) / "i.csv", ["number", "priority", "opened_at", "resolved_at", "business_service", "cmdb_ci", "major_incident_state",
                                          "caused_by", "contact_type", "short_description"],
                      [["INC0010001", "1 - Critical", "2026-07-14 08:10:00", "2026-07-14 10:40:00", "Card payments", "auth-switch-01", "",
                        "", "Monitoring", "Card authorisations failing"],
                       ["INC0010002", "2 - High", "2026-07-15 09:00:00", "", "Payments hub", "swift-mq-01", "accepted", "CHG0031102",
                        "Phone", "Queue"],
                       ["INC0010003", "3 - Moderate", "2026-07-16 09:00:00", "", "Email", "", "", "", "", ""]])
            rows = load_incidents(p, settings_from_dict({}))
        self.assertEqual([(i.priority, i.major) for i in rows], [("P1", True), ("P2", True), ("P3", False)])
        self.assertEqual((rows[1].change, rows[1].detection, rows[0].service, rows[0].ci), ("CHG0031102", "Phone", "Card payments", "auth-switch-01"))
        self.assertEqual(rows[0].resolved, datetime(2026, 7, 14, 10, 40))

    def test_jira_names_semicolons_and_jsonl_timeline(self):
        with tempfile.TemporaryDirectory() as t:
            p = write(Path(t) / "i.csv", ["Key", "Priority", "Created", "Resolutiondate", "Components", "Summary"],
                      [["ITOPS-12", "Highest", "2026-08-04T08:55:00.000+0200", "2026-08-04T11:05:00.000+0200", "ob-idp-cluster", "Logins"]],
                      delimiter=";")
            rows = load_incidents(p)
            j = Path(t) / "timeline.jsonl"
            j.write_text(json.dumps({"incident": "ITOPS-12", "time": "2026-08-04T08:12:00Z", "source": "Service desk", "actor": "Desk",
                                     "text": "first call"}) + "\n", encoding="utf-8")
            ev = load_timeline(j)
        self.assertEqual((rows[0].number, rows[0].priority, rows[0].ci, rows[0].opened), ("ITOPS-12", "P1", "ob-idp-cluster", datetime(2026, 8, 4, 8, 55)))
        self.assertEqual((ev[0].time, ev[0].source), (datetime(2026, 8, 4, 8, 12), "Service desk"))
        self.assertEqual([priority_of(x) for x in ("Sev2", "P4", "Medium", "1 - Critical", "")], ["P2", "P4", "P3", "P1", ""])
        self.assertEqual(parse_dt("14/07/2026 08:10"), datetime(2026, 7, 14, 8, 10))

    def test_settings_and_business_days(self):
        s = settings_from_dict({"targets": {"1": {"ack": 10}}, "comms_interval_min": {"P1": 20}, "owners": {"comms": "Comms desk"},
                                "major_priorities": ["1 - Critical", "P2"], "holidays": ["2026-10-12"]})
        self.assertEqual((s.target("P1", "ack"), s.target("P1", "resolve"), s.comms_interval_min, s.owner("comms"), s.owner("change")),
                         (10, 240, {"P1": 20, "P2": 60}, "Comms desk", "Change manager"))
        self.assertEqual(s.major_priorities, ["P1", "P2"])
        self.assertEqual(add_business_days(date(2026, 10, 9), 2, s), date(2026, 10, 14))       # Fri + 2, over a weekend and a holiday
        with tempfile.TemporaryDirectory() as t, self.assertRaises(FileNotFoundError):
            load(Path(t))


class TestDetection(unittest.TestCase):
    def test_clean_incident(self):
        iss, r = issues(data())
        self.assertEqual((iss, r["verdict"]), ({}, "clean"))
        self.assertEqual((r["facts"]["ttd"], r["facts"]["tta"], r["facts"]["ttr"]), (3, 5, 115))

    def test_blind_spot_and_slow_detection(self):
        i = inc(started=at("08:05"), detected=at("08:52"), opened=at("08:55"), acknowledged=at("09:00"), mitigated=at("10:00"),
                resolved=at("10:30"), detection="Service desk")
        late_alert = [Alert(at("09:31"), "Grafana", "Online banking", "ob-idp")]
        users = [Event("INC1", at("08:12"), "Service desk", "Contact centre", "first calls")]
        iss, r = issues(data([i], alerts=late_alert, timeline=users))
        self.assertEqual(iss["DET-01"][0].severity, CRITICAL)
        self.assertIn("first alert 39 min after detection", iss["DET-01"][0].text)
        self.assertIn("detected 47 min after the first signal (impact started 08:05", iss["DET-02"][0].text)
        self.assertEqual(r["facts"]["users"], at("08:12"))
        # P2: a warning; an alert on another service does not count
        i.priority = "P2"
        iss, _ = issues(data([i], alerts=[Alert(at("08:06"), "Grafana", "Email", "exo")]))
        self.assertEqual(iss["DET-01"][0].severity, WARNING)

    def test_alert_ignored_and_ticket_late(self):
        i = inc(started=None, detected=at("02:58"), opened=at("03:20"), acknowledged=at("03:30"), mitigated=at("04:00"), resolved=at("05:00"))
        iss, _ = issues(data([i], alerts=[Alert(at("02:10"), "Grafana", "", "ob-idp")]))
        self.assertNotIn("DET-01", iss)
        self.assertIn("first alert 02:10", iss["DET-02"][0].text)
        self.assertIn("ticket opened 22 min after detection", iss["DET-03"][0].text)


class TestResponse(unittest.TestCase):
    def test_targets_by_priority(self):
        p1 = inc(acknowledged=at("10:25"), mitigated=at("15:00"), resolved=at("15:30"))
        iss, r = issues(data([p1]))
        self.assertEqual([(c, iss[c][0].severity) for c in ("RSP-01", "RSP-02", "RSP-03")], [("RSP-01", WARNING), ("RSP-02", CRITICAL),
                                                                                           ("RSP-03", WARNING)])
        self.assertEqual(r["verdict"], "action needed")
        p2 = inc(priority="P2", acknowledged=at("10:25"), mitigated=at("14:00"), resolved=at("15:30"))
        self.assertEqual(issues(data([p2]))[0], {})                                           # inside the P2 targets

    def test_roles(self):
        iss, _ = issues(data([inc(commander="", comms_lead="")]))
        self.assertEqual((iss["CMD-01"][0].severity, iss["CMD-01"][0].text), (CRITICAL, "no incident commander, comms lead recorded"))
        iss, _ = issues(data([inc(priority="P2", tech_lead="")]))
        self.assertEqual(iss["CMD-01"][0].severity, WARNING)

    def test_comms_cadence(self):
        i = inc(opened=at("07:48"), resolved=at("12:30"))
        ups = [Update("INC1", at(t), kind="Update") for t in ("08:05", "08:30", "10:05")]
        d = data([i], comms=ups)
        kinds = [(g["kind"], round(g["gap"])) for g in comms_gaps(d, i)]
        self.assertEqual(kinds, [("first update late", 17), ("gap", 95), ("no update before resolution", 145), ("no resolution update", 0)])
        sev = [x.severity for x in issues(d)[0]["COM-01"]]
        self.assertEqual(sev, [WARNING, CRITICAL, CRITICAL, WARNING])
        self.assertEqual(comms_gaps(data([i], comms=good_comms(i)), i), [])
        self.assertEqual(comms_gaps(data([i], comms=[]), i)[0]["kind"], "no updates")


class TestChangeReviewActions(unittest.TestCase):
    def test_change_in_the_72_hours_before(self):
        chs = [Change("CHG1", at("22:00") - timedelta(days=1), at("23:30") - timedelta(days=1), "Online banking", "", summary="LB profile"),
               Change("CHG2", at("09:30"), at("10:30"), "", "ob-idp", summary="Patch"),                        # running at the start
               Change("CHG3", DAY - timedelta(days=5), DAY - timedelta(days=5) + timedelta(hours=1), "Online banking", "ob-idp"),  # too old
               Change("CHG4", at("09:00"), at("09:30"), "Email", "exo")]                                      # other service
        iss, r = issues(data([inc(change="CHG2")], changes=chs))
        self.assertEqual([c.number for c in r["facts"]["changes"]], ["CHG1", "CHG2"])
        self.assertIn("not linked to the incident", iss["CHG-01"][0].text)
        self.assertIn("in progress when the impact started; linked as cause", iss["CHG-01"][1].text)

    def test_review_rca_and_actions(self):
        late = inc(review=None, problem="")
        d = data([late], problems=[], actions=[])
        iss, r = issues(d)
        self.assertEqual(r["facts"]["pir_due"], date(2026, 10, 6))
        self.assertEqual(iss["PIR-01"][0].severity, INFO)                                    # not due yet: no RCA/action checks
        self.assertNotIn("PIR-02", iss)
        old = inc(opened=at("10:05", datetime(2026, 8, 3)), started=None, detected=None, acknowledged=None, mitigated=None,
                  resolved=at("12:00", datetime(2026, 8, 3)), review=None)
        acts = [Action("A1", "Synthetic check", "PRB-INC1", owner="Mon", due=date(2026, 8, 31), status="Open"),
                Action("A2", "Disk alert", "PRB-INC1", due=date(2026, 9, 20), status="In progress"),
                Action("A3", "Done", "PRB-INC1", due=date(2026, 8, 20), status="Closed")]
        iss, _ = issues(data([old], problems=[Problem("PRB-INC1", ["INC1"], "")], actions=acts))
        self.assertEqual(iss["PIR-01"][0].severity, CRITICAL)
        self.assertEqual(iss["PIR-02"][0].text, "PRB-INC1 has no root cause recorded")
        self.assertEqual([(x.severity, x.text.split(" ")[0]) for x in iss["ACT-01"]], [(CRITICAL, "A1"), (WARNING, "A2")])
        held_late = inc(opened=at("10:05", datetime(2026, 8, 3)), resolved=at("12:00", datetime(2026, 8, 3)), started=None, detected=None,
                        acknowledged=None, mitigated=None, review=date(2026, 8, 20))
        iss, _ = issues(data([held_late], actions=[]))
        self.assertIn("after the due date 10 Aug", iss["PIR-01"][0].text)
        self.assertEqual(iss["ACT-02"][0].severity, WARNING)

    def test_repeats_and_metrics(self):
        mi = inc("INC9", priority="P2", opened=at("13:20"), started=at("13:10"), detected=at("13:15"), acknowledged=at("13:40"),
                 mitigated=at("14:30"), resolved=at("15:15"))
        before = [Incident("INC7", "P3", at("10:15") - timedelta(days=9), ci="ob-idp", service="Online banking", resolved=at("12:00") - timedelta(days=9)),
                  Incident("INC8", "P2", at("16:40") - timedelta(days=40), ci="ob-idp", resolved=at("18:00") - timedelta(days=40)),  # too old
                  Incident("INC6", "P3", at("09:00") - timedelta(days=3), ci="other-ci", service="Online banking")]                   # other CI
        d = data([mi] + before)
        iss, r = issues(d, "INC9")
        self.assertEqual([x["incident"].number for x in r["facts"]["repeats"]], ["INC7"])
        self.assertIn("repeat: INC7 P3 on 20 Sep on the same CI", iss["REP-01"][0].text)
        m = {(x["month"], x["priority"]): x for x in metrics(d)}
        self.assertEqual((m[("2026-09", "P2")]["incidents"], m[("2026-09", "P2")]["major"], m[("2026-09", "P2")]["mttr"]), (1, 1, 115.0))
        self.assertEqual(m[("2026-09", "P3")]["incidents"], 2)


class TestCommands(unittest.TestCase):
    def test_start_prints_role_card_and_first_update(self):
        text = cli.start_text("1 - Critical", "Trader voice", "No external lines", "Lucía Prieto", at=datetime(2026, 10, 9, 7, 48))
        self.assertIn("# Major incident started · P1 · Trader voice", text)
        self.assertIn("| Incident commander | Lucía Prieto |", text)
        self.assertIn("First stakeholder update sent by **08:03**", text)
        self.assertIn("**Next update:** 08:33", text)
        self.assertIn("review booked by **Fri 16 Oct**", text)
        self.assertNotIn("$", text)
        self.assertEqual(cli.main(["start", "--service", "Payments hub", "--priority", "P2", "--at", "2026-10-05 03:00"]), 0)

    def test_demo_end_to_end_is_deterministic(self):
        hashes = []
        with tempfile.TemporaryDirectory() as t:
            for k in range(2):
                out = Path(t) / f"out{k}"
                self.assertEqual(cli.main(["demo", "--data", str(Path(t) / f"data{k}"), "--out", str(out)]), 0)
                self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(cli.OUTPUTS))
                files = sorted(p for p in out.rglob("*") if p.is_file())
                hashes.append({p.relative_to(out).as_posix(): hashlib.sha1(p.read_bytes()).hexdigest() for p in files})
            self.assertEqual(hashes[0], hashes[1])
            self.assertEqual(len([k for k in hashes[0] if k.startswith("reviews/")]), 6)
            d = load(Path(t) / "data0")
        f = run_all(d)
        self.assertEqual([x.severity for x in f], sorted((x.severity for x in f), key=ORDER.get))
        for c in ("DET-01", "DET-02", "RSP-01", "RSP-03", "CMD-01", "COM-01", "CHG-01", "PIR-01", "PIR-02", "ACT-01", "ACT-02", "REP-01", "MET-01"):
            self.assertIn(c, {x.code for x in f})
        verdicts = {r["incident"].service: r["verdict"] for r in incident_rows(d)}
        self.assertEqual(verdicts, {"Card payments": "follow up", "Online banking": "action needed", "Trader voice": "action needed",
                                    "Mobile banking API": "follow up", "Payments hub": "follow up", "Market data": "clean"})
        self.assertEqual((len(d.incidents), d.settings.organisation), (54, "Woodgrove Bank · IT operations"))
        mi1 = next(r for r in incident_rows(d) if r["incident"].service == "Card payments")
        self.assertEqual([c.number for c in facts(d, mi1["incident"])["changes"]], ["CHG0031102"])

    def test_review_reports_a_missing_incident_export(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o")]), 2)
            self.assertEqual(cli.main(["review", "--data", t, "--out", str(Path(t) / "o")]), 2)


if __name__ == "__main__":
    unittest.main()
