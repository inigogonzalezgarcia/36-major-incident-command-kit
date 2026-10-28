# Major incident started · $priority · $service

Declared $opened · ticket $number · $summary

## Roles (name them in the first 10 minutes and write them in the ticket)

| Role | Who | Owns |
|---|---|---|
| Incident commander | $commander | Runs the bridge, decides, keeps time. Does not fix. |
| Tech lead | ______________ | Leads the diagnosis and the fix with the resolver groups; tells the commander the options and the risk of each. |
| Comms lead | ______________ | Sends every stakeholder update on time and keeps the status page in line. |
| Scribe | ______________ | Writes the timeline on the bridge: time, who, what was seen, what was decided. |

## First 15 minutes

- [ ] Ticket opened as $priority with the major incident flag, service and CI filled in.
- [ ] Bridge open (call + chat channel) and the resolver groups paged; on-call acknowledged within $ack_target.
- [ ] Impact written in one line: who cannot do what, since when, how many.
- [ ] Changes on the service and its CIs in the last 72 hours checked (CAB calendar, change records): roll back first if one fits.
- [ ] Monitoring checked: which alert fired first, or "users told us first" written down.
- [ ] First stakeholder update sent by **$first_update_due**.

## Every $interval minutes until resolved

- [ ] Stakeholder update sent, even if nothing changed. Next one due at **$next_update**, then every $interval minutes.
- [ ] Commander asks: what do we know, what are we trying, what is the next decision and when.
- [ ] Options to restore service first (rollback, failover, workaround), root cause later.

## Targets for $priority

- Acknowledge: $ack_target · mitigate: $mitigate_target · resolve: $resolve_target (from the ticket opening).

## Closing

- [ ] Service confirmed with the business, not only with monitoring.
- [ ] Resolution update sent to everyone who received the first one.
- [ ] Problem record opened or linked; post-incident review booked by **$review_due**.

---

## First stakeholder update (copy, fill, send)

**Subject:** [$priority] $service · $summary · update 1

**Status:** Investigating
**Started:** $opened (impact may have started earlier)
**Impact:** ______________ (who is affected, what they cannot do, how many)
**What we are doing:** The incident team is on a bridge with ______________. We are checking ______________.
**Workaround:** ______________ / none yet
**Next update:** $next_update or earlier if anything changes.

Incident commander: $commander · Ticket: $number
