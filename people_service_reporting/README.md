# People Service Reporting

Codex-created extension for trusted recurring reporting in a comparable service environment. It uses the parent repository's original, hash-checked UCI incident consolidation, without changing its methods or the unrelated triage module.

```sh
python3 src/pipeline.py
python3 people_service_reporting/pipeline.py
python3 -m unittest discover -s people_service_reporting/tests -v
```

The pipeline reads SQLite in read-only mode, groups cases by final assignment group and intake month, and writes an allowlisted aggregate CSV. No employee, caller, agent, salary or case identifiers enter the export. Counts under 10 are blank. Reassignment shares additionally require at least 10 cases in both the numerator and complement. Duration medians require 10 valid closures. No all-group totals are exported. These are local release rules, not proof of anonymisation or BI identity enforcement.

## Schema and metric definitions

| Column | Definition |
| --- | --- |
| final_group | Latest observed assignment group; no historical ownership inference |
| intake_month | Month of earliest observed case opening |
| reporting_status | released or small_cohort |
| case_count | Distinct cases in the cell, subject to threshold |
| reassigned_cases | Cases with reassignment_count > 0, with numerator/complement suppression |
| reassignment_share | reassigned_cases / case_count; no averaging of subgroup percentages |
| valid_closed_cases | Nonmissing nonnegative closure intervals, subject to threshold |
| median_elapsed_close_hours | Median (closed_at - opened_at) in calendar hours; not handling time |

## Stakeholder handoff

Service owners approve measures and reporting cadence. Source-system owners investigate invalid or missing timestamps. BI administrators configure approved workspaces, viewer permissions, row-level access if needed, export restrictions and refresh credentials. Analysts document exceptions and escalate access issues without changing production source systems. The CSV is an approved-input example, not an authentication service.

Power BI: import the CSV and preserve blanks. Sum counts only across disjoint released cells. Compute a weighted reassignment share using only cells where both numerator and denominator are disclosed; label its coverage. Never average medians or construct an overall median from subgroup medians. Exclude small_cohort cells from counts of released reporting populations. Partial intake months and changing capture coverage require review before trend narratives.

## Sources

Primary: [UCI Incident management process enriched event log](https://archive.ics.uci.edu/dataset/498/incident+management+process+enriched+event+log), CC BY 4.0. Backup, located but not executed: [Mendeley Helpdesk v1](https://data.mendeley.com/datasets/39bp3vv62t/1), MIT, 3,804 cases and 13,710 events. Public IT-support events demonstrate a service-reporting method; they do not establish historical employer, employee experience or staffing outcomes.
