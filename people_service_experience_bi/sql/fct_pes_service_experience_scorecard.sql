-- Governed PES Service Delivery, Solution Adoption & Employee Experience Scorecard
WITH group_benchmarks AS (
    SELECT
        final_group,
        COUNT(*) AS total_cases,
        SUM(snapshots) AS total_event_snapshots,
        SUM(knowledge_adopted_flag) AS kb_adopted_cases,
        ROUND(AVG(knowledge_adopted_flag) * 100.0, 2) AS kb_solution_adoption_pct,
        ROUND(AVG(made_sla_flag) * 100.0, 2) AS sla_compliance_pct,
        ROUND(AVG(CASE WHEN reassignments = 0 THEN 1.0 ELSE 0.0 END) * 100.0, 2) AS first_touch_resolution_pct,
        ROUND(AVG(CASE WHEN reopens > 0 THEN 1.0 ELSE 0.0 END) * 100.0, 2) AS reopen_exception_pct,
        ROUND(AVG(elapsed_hours), 2) AS avg_resolution_hours,
        SUM(invalid_closed_interval) AS timestamp_discrepancy_count
    FROM stg_pes_service_cases
    GROUP BY final_group
)
SELECT
    final_group,
    total_cases,
    total_event_snapshots,
    kb_adopted_cases,
    kb_solution_adoption_pct,
    sla_compliance_pct,
    first_touch_resolution_pct,
    reopen_exception_pct,
    avg_resolution_hours,
    timestamp_discrepancy_count,
    CASE
        WHEN total_cases < 5 THEN 'SUPPRESSED_K_ANONYMITY'
        WHEN sla_compliance_pct < 55.0 OR reopen_exception_pct > 5.0 THEN 'ESCALATE_TO_PES_OWNER'
        ELSE 'HEALTHY_SELF_SERVICE'
    END AS governance_status
FROM group_benchmarks
ORDER BY total_cases DESC, final_group ASC
