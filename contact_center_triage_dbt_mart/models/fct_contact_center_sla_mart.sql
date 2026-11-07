-- contact_center_triage_dbt_mart/models/fct_contact_center_sla_mart.sql
-- Contact-Center Queue SLA, First-Contact Resolution (FCR) & AI Request Triage dbt Mart
WITH case_metrics AS (
    SELECT
        case_id,
        final_group AS queue_id,
        priority,
        contact_type,
        category,
        reassignments,
        reopens,
        snapshots,
        elapsed_hours,
        CASE WHEN reassignments = 0 AND reopens = 0 THEN 1 ELSE 0 END AS fcr_flag,
        CASE WHEN reassignments = 0 THEN 1 ELSE 0 END AS first_touch_triage_flag,
        made_sla_flag
    FROM stg_contact_center_cases
    WHERE invalid_closed_interval = 0 AND elapsed_hours IS NOT NULL
)
SELECT
    queue_id,
    COUNT(*) AS total_cases,
    SUM(snapshots) AS total_event_logs,
    ROUND(100.0 * SUM(first_touch_triage_flag) / COUNT(*), 2) AS first_touch_triage_rate_pct,
    ROUND(100.0 * SUM(fcr_flag) / COUNT(*), 2) AS fcr_rate_pct,
    ROUND(100.0 * SUM(made_sla_flag) / COUNT(*), 2) AS sla_compliance_rate_pct,
    ROUND(AVG(reassignments), 2) AS avg_reassignments,
    ROUND(AVG(elapsed_hours), 2) AS avg_resolution_hours
FROM case_metrics
GROUP BY queue_id
ORDER BY total_cases DESC;
