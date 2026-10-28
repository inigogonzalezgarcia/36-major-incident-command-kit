"""Command line: `demo` builds everything from the fictional bank, `review` runs on your own exports, `start` prints the role card,
the checklist and the first stakeholder update for a new major incident."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from string import Template

from . import report, simulate
from .checks import fmt_min, run_all
from .model import Settings, add_business_days, load, parse_dt, priority_of, settings_from_dict

OUTPUTS = ("report.html", "reviews", "major-incidents.csv", "metrics.csv", "comms-gaps.csv", "actions-overdue.csv", "repeats.csv",
           "actions.csv", "findings.csv")
TEMPLATE = Path(__file__).parent / "templates" / "start.md"


def run(data: Path, out: Path, title: str, as_of: datetime | None = None) -> dict:
    d = load(data, as_of)
    b = report.build(d)
    findings = run_all(d, b["rows"])
    out.mkdir(parents=True, exist_ok=True)
    rv = out / "reviews"
    rv.mkdir(exist_ok=True)
    for old in rv.glob("PIR-*.md"):
        old.unlink()
    for r in b["rows"]:
        (rv / f"PIR-{r['incident'].number}.md").write_text(report.review_md(d, r), encoding="utf-8")
    (out / "report.html").write_text(report.render_html(d, findings, title, b), encoding="utf-8")
    report.write_majors(b, out / "major-incidents.csv")
    report.write_metrics(b, out / "metrics.csv")
    report.write_gaps(b, out / "comms-gaps.csv")
    report.write_overdue(d, b, out / "actions-overdue.csv")
    report.write_repeats(b, out / "repeats.csv")
    report.write_actions(findings, out / "actions.csv")
    report.write_findings(findings, out / "findings.csv")
    return report.summary(d, findings, b)


def start_text(priority: str, service: str, summary: str = "", commander: str = "", number: str = "", at: datetime | None = None,
               settings: Settings | None = None, template: Path = TEMPLATE) -> str:
    s = settings or Settings()
    p = priority_of(priority) or "P1"
    at = at or datetime.now().replace(second=0, microsecond=0)
    every = s.comms_interval_min.get(p, 60)
    first = s.first_update_min.get(p, every)
    tg = lambda k: fmt_min(s.target(p, k)) if s.target(p, k) is not None else "–"  # noqa: E731
    return Template(Path(template).read_text(encoding="utf-8")).safe_substitute(
        priority=p, service=service, summary=summary or "summary to be written", commander=commander or "______________",
        number=number or "(to be opened)", opened=f"{at:%a %d %b %Y %H:%M}", first_update_due=f"{at + timedelta(minutes=first):%H:%M}",
        interval=every, next_update=f"{at + timedelta(minutes=first + every):%H:%M}", ack_target=tg("ack"), mitigate_target=tg("mitigate"),
        resolve_target=tg("resolve"), review_due=f"{add_business_days(at.date(), s.pir_business_days, s):%a %d %b}")


def _when(value: str) -> datetime:
    d = parse_dt(value)
    if not d:
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD or 'YYYY-MM-DD HH:MM'): {value}")
    return d


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mickit", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    dm = sub.add_parser("demo", help="write the fictional bank to sample_data/ and build the outputs")
    dm.add_argument("--data", type=Path, default=Path("sample_data"))
    dm.add_argument("--out", type=Path, default=Path("output"))
    rv = sub.add_parser("review", help="build the outputs from your own exports")
    rv.add_argument("data", type=Path, nargs="?", help="folder with incidents.csv (required) and the optional files")
    rv.add_argument("--data", dest="data_opt", type=Path, help="same as the positional folder")
    rv.add_argument("--out", type=Path, default=Path("output"))
    rv.add_argument("--title", default="Major incident review")
    rv.add_argument("--as-of", type=_when, help="review time (default: settings.json, or now)")
    st = sub.add_parser("start", help="print the role card, checklist and first stakeholder update for a new major incident")
    st.add_argument("--priority", default="P1")
    st.add_argument("--service", required=True)
    st.add_argument("--summary", default="")
    st.add_argument("--commander", default="")
    st.add_argument("--number", default="", help="ticket number, if already opened")
    st.add_argument("--at", type=_when, help="declared time (default: now)")
    st.add_argument("--settings", type=Path, help="settings.json with targets and comms intervals")
    st.add_argument("--template", type=Path, default=TEMPLATE)
    st.add_argument("--out", type=Path, help="also write it to this file")
    a = p.parse_args(argv)
    if a.cmd == "start":
        s = settings_from_dict(json.loads(a.settings.read_text(encoding="utf-8"))) if a.settings else Settings()
        text = start_text(a.priority, a.service, a.summary, a.commander, a.number, a.at, s, a.template)
        if a.out:
            a.out.write_text(text, encoding="utf-8")
        print(text)
        return 0
    if a.cmd == "demo":
        simulate.write(a.data)
        sm = run(a.data, a.out, f"{simulate.ORG} · Major incident review, Q3 2026")
    else:
        folder = a.data or a.data_opt
        if not folder:
            print("error: give the folder with the exports", file=sys.stderr)
            return 2
        try:
            sm = run(folder, a.out, a.title, a.as_of)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    print(f"{sm['majors']} major incidents of {sm['incidents']} ({sm['action_needed']} action needed, {sm['follow_up']} follow up, "
          f"{sm['clean']} clean) · MTTD {fmt_min(sm['mttd'])} · MTTA {fmt_min(sm['mtta'])} · MTTR {fmt_min(sm['mttr'])} · "
          f"blind spots {sm['blind']} · comms gaps {sm['gaps']} · change-related {sm['change']} · reviews late {sm['pir_late']} · "
          f"actions overdue {sm['overdue']} · repeats {sm['repeats']} · {sm['critical']} critical, {sm['warning']} warnings")
    print(f"outputs in {a.out}/: {', '.join(OUTPUTS)}")
    return 0
