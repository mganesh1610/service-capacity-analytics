# Service Capacity & Workload Analytics

An independent, public-data project for reviewing support workload, handoffs and staffing assumptions. Built with Codex using Python's standard library and SQLite. It demonstrates service-management analytics, not a live consulting operation.

## Run

```sh
python3 src/pipeline.py
python3 -m unittest discover -s tests -v
sqlite3 results/service.sqlite < sql/weekly_business_review.sql
```

The pipeline downloads the public ZIP when absent. No account, secret or paid service is needed. It verifies the source SHA-256 before parsing. Raw data and the generated SQLite database stay local; compact result CSVs, schemas and validation evidence are committed.

## Architecture

UCI ZIP → hash verification → 36-column event validation → latest-state incident table → weekly arrival/closure/backlog scorecard → walk-forward arrival baseline comparison → configurable capacity scenario → CSV/SQLite evidence.

The executed dataset has **141,712 event snapshots and 24,918 unique incidents**. Counting snapshots as tickets would inflate the workload denominator. The case table reduces the reporting row count by **82.4165%** while accounting for every source snapshot. It contains 71 final assignment groups. Seven boundary tests cover count inflation, unordered events, weekly cutoffs, negative intervals, forecast leakage, missing dates and capacity inputs.

The executed 45-week backtest gives a four-week-mean MAE of 130.79 cases versus 82.44 for the last-week benchmark. The moving average did not improve forecasting. The capacity CSV deliberately remains a configurable example, and is not a promoted operational staffing plan.

## Decision workflow

1. Reconcile incident counts before setting team goals.
2. Compare arrivals, closures, backlog and elapsed close time by complete week.
3. Inspect final-group handoffs and reopened cases before changing triage guidance.
4. Compare a four-week mean arrival forecast with a last-week baseline on past-only walk-forward folds. Review the actual errors in `results/validation_summary.json`; do not assume the more complex baseline wins.
5. Change effort, productive hours and utilization assumptions, then rerun the capacity scenario.
6. Use the review/runbook to turn the analysis into a concrete service question and an evidence-gathering plan.

```sh
python3 src/pipeline.py --handling-minutes 45 --productive-hours 28 --utilization 0.75
```

These are scenario inputs, not measured labor time or actual staffing recommendations. The staffing formula is `ceil(forecast_cases × assumed_minutes / 60 / (productive_hours × utilization))`.

## Data and provenance

Primary: Amaral, C., Fantinato, M. and Peres, S. (2018), [Incident management process enriched event log](https://archive.ics.uci.edu/dataset/498/incident+management+process+enriched+event+log), DOI [10.24432/C57S4H](https://doi.org/10.24432/C57S4H), CC BY 4.0. The source describes anonymized ServiceNow incident events from an IT company. ZIP SHA-256: `6294e29a311647306bfdfc85783f7df66517c197b9cd49aa5ee36ba9c525d1d6`.

Backup located, not executed: Ilya Verenich, [Helpdesk, Mendeley Data v1](https://data.mendeley.com/datasets/39bp3vv62t/1), DOI `10.17632/39bp3vv62t.1`, MIT license. It has 3,804 cases and 13,710 events from an Italian software company's help desk. It needs a separate case/activity/timestamp adapter and does not supply the UCI SLA, priority or group fields. Never silently substitute it into this schema.

## Limits

- Public IT support events are not advertising clients, consultants, HR records or historical employer evidence.
- Closure duration is elapsed calendar time, not staff handling time. Timezone is unspecified.
- Raw equal snapshots are retained in event counts. Latest state uses update time, modification count and source row order.
- `made_sla` is exposed as the original true/false flag. Its ambiguity is not converted into a measured compliance claim.
- Historical backlog uses eventual closing timestamps. Final group is not a historical owner-at-time record.
- The first and final intake weeks and closure-only follow-up are excluded from arrival forecasting. Dataset capture completeness remains unknown.
- Reassignment is a handoff proxy, not proof of escalation. No hiring, coaching, adoption, customer satisfaction or realized business improvement is inferred.

See [schema and methods](docs/SCHEMA_AND_METHODS.md), [review runbook](docs/SERVICE_REVIEW_RUNBOOK.md) and [executed validation](results/validation_summary.json).
