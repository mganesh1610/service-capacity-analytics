# Schema and methods

## Raw → case mapping

| Source field | Derived field | Treatment |
| --- | --- | --- |
| number | case_id | Incident primary key, never event count |
| opened_at | opened_at | Earliest recorded opening per case, day-first parsing |
| sys_updated_at, sys_mod_count | latest-state selector | Descending timestamp, modification count, source row index |
| closed_at, resolved_at | closed_at, resolved_at | Latest-state values; `?` is unknown |
| assignment_group | final_group | Latest-state group, not owner at opening |
| reassignment_count, reopen_count | reassignments, reopens | Latest-state integer counts |
| made_sla | source_made_sla | Preserve source flag; unknown remains NULL |
| priority | priority | Preserve source category |
| all snapshots | snapshots | Count and reconcile every event to one incident |

The complete raw and derived column lists are in `results/schema.json`. SQLite primary keys prevent duplicate cases and weeks. The CSV uses `closed_code`; the source prose calls it `close_code`. The implementation uses the observed schema, not the prose spelling.

## Weekly definitions

Weeks are half-open Monday intervals `[start, next_start)`. Arrivals count incident openings, closures count valid closing timestamps. End backlog is the number opened before the interval end and not closed strictly before that end. Invalid negative closing intervals are excluded from elapsed-time/closure metrics and retained in backlog. Closure median is measured in elapsed hours; missing values remain blank. Source SLA true share uses only cases with known source flags. It is not a newly validated SLA.

Weekly historical reporting continues through the last complete update week. Arrival forecasting separately stops before the final intake week, so a closure-only tail is not mistaken for demand disappearing. The first capture week is excluded as potentially partial. Remaining capture gaps are not known.

## Forecast and capacity

For each eligible week `t`, compare `mean(arrivals[t-4:t])` and `arrivals[t-1]` against arrivals in week `t`. MAE is `sum(abs(actual - predicted))/N`. Inputs contain only past arrivals; future resolution fields never enter either predictor. There is no tuned or production-promoted model.

Scenario FTE is `ceil(next_week_mean4 × assumed_handling_minutes / (60 × productive_hours × planned_utilization))`. Those inputs are assumptions. Validate all positive effort/capacity inputs and `0 < utilization <= 1`. A live staffing plan also needs measured work effort, skills, leave, concurrent client commitments, service targets and capture-complete arrivals.
