-- SQL Joins & CTEs Mart: Contractual SLA Compliance & Multi-Hop Reassignment Bottlenecks

WITH queue_sla_metrics AS (
    SELECT
        assignment_group,
        priority_tier,
        COUNT(*) AS ticket_volume,
        SUM(made_sla) AS compliant_tickets,
        ROUND(100.0 * SUM(made_sla) / COUNT(*), 2) AS sla_compliance_pct,
        ROUND(AVG(reassignment_count), 2) AS avg_handoffs,
        ROUND(AVG(resolution_hours), 2) AS avg_resolution_hours
    FROM fct_jira_ticket_lifecycle
    GROUP BY assignment_group, priority_tier
)
SELECT
    assignment_group,
    priority_tier,
    ticket_volume,
    compliant_tickets,
    sla_compliance_pct,
    avg_handoffs,
    avg_resolution_hours,
    RANK() OVER (PARTITION BY priority_tier ORDER BY sla_compliance_pct ASC) AS breach_severity_rank
FROM queue_sla_metrics
WHERE ticket_volume >= 25
ORDER BY priority_tier, breach_severity_rank;
