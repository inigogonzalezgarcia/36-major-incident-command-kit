# Data format

Put the files in one folder and run `python -m mickit review <folder>`. Only `incidents.csv` is required; every other file adds its checks when present. Comma, semicolon or tab separated, UTF-8. Column names are matched loosely (case, accents and punctuation are ignored), and the common alternatives below, including the ServiceNow and Jira Service Management field names, are accepted. `scripts/Export-MajorIncidentData.ps1` writes `incidents.csv`, `changes.csv`, `problems.csv`, `problem-actions.csv` and, optionally, `timeline.csv` from either tool.

Dates: `YYYY-MM-DD HH:MM[:SS]`, ISO (`2026-08-04T08:55:00.000+0200`: the offset is dropped and the written time kept) or `DD/MM/YYYY HH:MM`. Keep every file in the same time zone.

## incidents.csv (required)

All incidents of the period, not only the major ones: the everyday ones feed the metrics and the repeat check.

| Column | Also accepted | Notes |
|---|---|---|
| Number | incident, key, issue key | |
| Priority | severity | `1 - Critical`, `P1`, `Sev1`, `Highest`, `Critical` → P1; `High` → P2; `Medium`/`Moderate` → P3; `Low` → P4 |
| Opened | opened_at, created | Every target (acknowledge, mitigate, resolve) is measured from here |
| Impact start | started, outage start | When customers were first affected, often filled in at the review. Optional |
| Detected | u_detected | When someone in IT knew. If empty, Opened |
| Acknowledged | first response | When the resolver group took it |
| Mitigated | restored, service restored, workaround | Service back for users, root cause not necessarily fixed |
| Resolved | resolved_at, resolutiondate | |
| Business service | service, business_service | Matched with alerts and changes |
| Configuration item | cmdb_ci, CI, components | Matched with alerts and changes, and used for repeats |
| Assignment group | assignment_group, team | |
| Major incident state | major, major_incident_state | `accepted`, `yes`, `true` mark a major incident. Priorities in `major_priorities` are always major |
| Customer impact | business impact, impact | One line, copied to the review |
| Problem | problem_id | Linked problem record |
| Caused by change | caused_by, change, rfc | Linked change, to tell "linked" from "not linked" |
| Incident commander, Comms lead, Tech lead | major incident manager, communications lead, technical lead | The roles in `required_roles` |
| Review date | PIR date | Date of the post-incident review |
| Detection source | contact_type, detected by | `Monitoring`, `Service desk`, `Phone`… A user-facing source with no alert counts as "users told us first" |
| Short description | summary, title | |

## timeline.jsonl or timeline.csv

One line per event of a major incident, from the bridge chat, the ITSM work notes, the status page and the user reports. JSON lines (`{"incident": ..., "time": ..., "source": ..., "actor": ..., "text": ...}`) or a CSV with the same columns.

| Column | Also accepted | Notes |
|---|---|---|
| Incident | number, key | |
| Time | timestamp | |
| Source | origin, tool | `Service desk`, `Phone`, `Users`, `Trading desk`, `Branch`… count as user reports (DET-01 and the first signal). `Monitoring (...)`, `Chat bridge`, `ITSM`, `Status page`, `Stakeholder update` place the event on the timeline lane |
| Actor, Text | who, message | |

## alerts.csv

First-fired time of the alerts from the monitoring tools (SolarWinds, Grafana, Dynatrace, Datadog, Azure Monitor…), at least for the services and CIs of the major incidents.

| Column | Also accepted | Notes |
|---|---|---|
| Alert ID | id | |
| Source | tool, monitor | Name of the tool |
| First fired | fired, triggered, first seen | |
| Service, CI | host, entity, node | An alert counts for an incident when its service or CI matches and it fired between `alert_lookback_min` before the impact and the resolution |
| Severity, Message | level, name | |

## comms.csv

Every stakeholder update sent: from the communication plan, the status page history or the sent folder of the incident mailbox.

| Column | Also accepted | Notes |
|---|---|---|
| Incident | number | |
| Time | sent | |
| Audience, Channel | to, via | |
| Type | kind | `Resolved`, `Resolution` or `Final` (in Type or Summary) marks the resolution notice |
| Summary | text, subject | |

## changes.csv

| Column | Also accepted | Notes |
|---|---|---|
| Number | change | |
| Business service, Configuration item | business_service, cmdb_ci | |
| Planned start, Planned end | start_date, end_date, work_start, work_end | Use actual times when you have them. A change whose window ends within `change_lookback_hours` before the impact (or is still running) is flagged |
| Type, State, Short description | | |

## problems.csv

| Column | Also accepted | Notes |
|---|---|---|
| Number | problem | |
| Incidents | related incidents, first_reported_by_task | Separated by `;`; the incident's Problem column also links them |
| Root cause | cause_notes, rca | Empty means no root cause recorded (PIR-02) |
| RCA date, State | | |

## problem-actions.csv

The post-incident actions (problem tasks, Jira sub-tasks or a tracker).

| Column | Also accepted | Notes |
|---|---|---|
| Action ID | number, task, key | |
| Problem, Incident | parent | Linked by either |
| Action | short description, summary | |
| Owner | assigned_to, assignee | |
| Due date | due_date, duedate | |
| Status, Closed | state, closed_at | `Closed`, `Done`, `Complete`, `Resolved`, `Cancelled` or a closed date count as done |

## settings.json

| Key | Default | What |
|---|---|---|
| `organisation`, `as_of` | | Name for the reports; review time (otherwise now) |
| `major_priorities` | `["P1"]` | Priorities that are always major; others need the major flag |
| `targets` | P1 15/120/240, P2 30/240/480, P3 60/480/1440, P4 240/1440/4320 | Minutes to acknowledge, mitigate and resolve, from the ticket opening |
| `comms_interval_min`, `first_update_min` | P1 30 · 15, P2 60 · 30 | Stakeholder update every N minutes; the first one within M minutes of opening |
| `detect_gap_min`, `open_lag_min` | 15, 15 | First signal → detected; detected → ticket opened |
| `alert_lookback_min` | 120 | How far before the impact an alert still counts |
| `change_lookback_hours` | 72 | Changes before the impact that are flagged |
| `pir_business_days`, `holidays` | 5, [] | Review due this many business days after the resolution; weekends and these dates are skipped |
| `repeat_days` | 30 | Incidents on the same CI (or service, when there is no CI) within this window |
| `required_roles` | commander, comms_lead, tech_lead | Roles every major incident must record |
| `action_critical_days` | 30 | Actions overdue longer than this are critical |
| `owners` | | Owner per area: detection, response, comms, change, review, actions |

## Measures

- **TTD** (time to detect): first signal → detected. The first signal is the earliest of impact start, first related alert and first user report.
- **TTA**, **TTM**, **TTR**: ticket opened → acknowledged, mitigated, resolved. `metrics.csv` gives their means (MTTD, MTTA, MTTM, MTTR) by month and priority, over every incident, with the share inside the targets.
