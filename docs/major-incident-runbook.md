# Major incident runbook

Two moments: **during** the incident, the first fifteen minutes decide most of what the review will say; **after** it, a weekly 20-minute review of every major incident closed or still open in actions. The tool only reads exports; tickets, problems and actions are changed in the ITSM tool.

## During: the first fifteen minutes

1. Print the role card and the first update for the bridge:
   ```bash
   python -m mickit start --priority P1 --service "Trader voice" --summary "No external lines on the rates desk" --commander "Name" --settings data/settings.json
   ```
   The template is `mickit/templates/start.md`; copy it and pass `--template` to use your own wording.
2. Name the incident commander, the tech lead, the comms lead and a scribe, and write them in the ticket.
3. Write the impact in one line and send the first update before the time printed on the card.
4. Check the changes on the service and its CIs in the last 72 hours. If one fits, roll back first and investigate after.
5. Write down which alert fired first, or that users told you first: it is the first question of the review.

## During: every interval

- Send the stakeholder update on time even if nothing changed: "still investigating, next update at 10:30" is an update; silence is not.
- The commander asks three things: what do we know, what are we trying, when is the next decision.
- Restore first (rollback, failover, workaround), root cause later.
- Send a resolution notice to everyone who got the first update.

## After: the weekly review (20 minutes)

Before it:

1. Export the period from the ITSM tool (read-only):
   ```powershell
   .\scripts\Export-MajorIncidentData.ps1 -Platform ServiceNow -InstanceUrl https://contoso.service-now.com -Credential $cred -From 2026-07-01 -To 2026-09-30 -IncludeWorkNotes -OutputFolder .\data
   ```
2. Add `alerts.csv` from the monitoring tools and `comms.csv` from the communication log, and check `settings.json`.
3. Build the outputs:
   ```bash
   python -m mickit review data/ --title "Major incidents · Q3"
   ```

| Minutes | Topic | Output |
|---|---|---|
| 5 | Incidents marked "action needed": what is critical and who fixes it | `report.html` → Fix first |
| 5 | Detection: blind spots and alerts nobody acted on | `major-incidents.csv` (TTD, first alert, first user report) |
| 4 | Comms and roles: gaps, missing resolution notices, missing commander | `comms-gaps.csv` |
| 3 | Overdue actions: new date or close with a reason | `actions-overdue.csv` |
| 3 | Repeats and change-related incidents for the problem and change managers | `repeats.csv`, CHG-01 findings |

## The post-incident review

- Start from `output/reviews/PIR-<number>.md`: the timeline, the metrics, the changes, the comms and the actions are already there.
- Fill every **[TO COMPLETE IN THE REVIEW]**: impact in business terms, contributing factors, what went well, the decisions only people remember.
- Blameless: the question is what made the wrong action look right at the time, not who did it.
- Every review leaves at least one action with an owner and a date, and the root cause (or "not found yet" and the next step) goes into the problem record.
- Hold it within the business days in `pir_business_days`, with the people who were on the bridge.

## How to read it

- **The first signal is the honest start.** TTD runs from the earliest of impact start, first alert and first user report, not from the ticket.
- **Users first means a blind spot.** If the service desk heard it before any alert, the review owes the alert that would have caught it.
- **An alert nobody acted on is a routing problem.** Check who received it, at what severity, and at what hour.
- **A change in the last 72 hours is a suspect, not a culprit.** Rule it in or out in the review and link it in the ticket if it was the cause.
- **A repeat is one problem.** Two incidents on the same CI within a month share a root cause until proven otherwise.
