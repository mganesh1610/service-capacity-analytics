-- Each case appears exactly once. Raw events must not be counted as tickets.
SELECT week_start,arrivals,closed_cases,backlog_at_end,
       median_elapsed_close_hours,
       1.0 * reassigned_closures / NULLIF(closed_cases,0) AS reassignment_share,
       1.0 * source_sla_true / NULLIF(source_sla_known,0) AS source_made_sla_true_share
FROM weekly ORDER BY week_start;

SELECT final_group,COUNT(*) AS distinct_cases,
       SUM(reassignments > 0) AS reassigned_cases,
       SUM(reopens > 0) AS reopened_cases
FROM cases GROUP BY final_group ORDER BY distinct_cases DESC;
