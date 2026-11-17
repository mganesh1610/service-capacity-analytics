# Contractual SLA Compliance, Milestone Lifecycle & Jira Ticket Analytics (`contract_milestone_jira_sla_ops`)

Refactored **SQL (`SQL Joins & CTEs`, Window Functions) and Python** analytics module modeling **Jira-schema operational ticket lifecycles, contractual SLA tier compliance (`P1_Critical` through `P4_Low_Planning`), and multi-hop dispatch queue bottlenecks** across `141,712` SHA-256-verified event snapshots (`24,918` unique tickets across `72` queues).

## Verified Execution Highlights (`results/validation_summary.json`)

- **Snapshot-to-Ticket Consolidation:** Deduplicates `141,712` raw status-transition snapshots into `24,918` canonical Jira issue lifecycles (**`82.42%` reporting row reduction** with **`100%` snapshot conservation**).
- **Contractual SLA & Escalation Bottleneck Findings:** Direct first-owner tickets (`0` reassignments) achieved **`78.39%` SLA compliance** vs. **`31.61%`** on multi-hop escalated tickets (`>= 2` reassignments), a **`+46.78 pp` compliance advantage** ($Z = 60.05$), while multi-hop handoffs inflated mean resolution time from **`103.04h` to `378.67h`** (Welch $t = 24.08$, $p = 3.65 \times 10^{-128}$).
- **Validation & Testing:** Passed **10/10 (`100%`)** deterministic SQL and schema QA gates plus **4/4** unit tests.

## Run

```bash
python3 contract_milestone_jira_sla_ops/jira_contract_sla_pipeline.py
python3 -m unittest discover -s contract_milestone_jira_sla_ops/tests -v
```
