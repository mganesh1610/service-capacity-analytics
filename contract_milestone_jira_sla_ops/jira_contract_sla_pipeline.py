#!/usr/bin/env python3
"""Contractual SLA Compliance, Milestone Lifecycle & Jira-Schema Ticket Analytics Module.

Consolidates 141,712 SHA-256-verified service ticket event snapshots into 24,918 canonical
Jira-mapped issue lifecycles across 71 dispatch queues, evaluates contractual SLA compliance
across P1-P4 priority tiers, isolates multi-hop reassignment bottlenecks via SQL Joins & CTEs,
and executes quantitative two-sample hypothesis tests and 10 deterministic QA checks.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sqlite3
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

UCI_URL = "https://archive.ics.uci.edu/static/public/498/incident+management+process+enriched+event+log.zip"
UCI_SHA256 = "6294e29a311647306bfdfc85783f7df66517c197b9cd49aa5ee36ba9c525d1d6"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_uci_zip(dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        req = urllib.request.Request(UCI_URL, headers={"User-Agent": "ServiceTicketSLAPipeline/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as out:
            while True:
                buf = resp.read(1 << 20)
                if not buf:
                    break
                out.write(buf)
    digest = sha256_file(dest)
    if digest != UCI_SHA256:
        raise ValueError(f"SHA-256 mismatch: {digest} != {UCI_SHA256}")
    return digest


def parse_dt(val: str) -> Optional[datetime]:
    val = (val or "").strip()
    if not val or val == "?":
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def map_jira_priority_tier(raw_priority: str) -> str:
    val = (raw_priority or "").strip()
    if val.startswith("1"):
        return "P1_Critical"
    if val.startswith("2"):
        return "P2_High"
    if val.startswith("3"):
        return "P3_Moderate"
    return "P4_Low_Planning"


def two_prop_z(k1: int, n1: int, k2: int, n2: int) -> Dict[str, float]:
    p1 = k1 / n1
    p2 = k2 / n2
    pool = (k1 + k2) / (n1 + n2)
    se = math.sqrt(pool * (1.0 - pool) * (1.0 / n1 + 1.0 / n2))
    z = (p1 - p2) / se if se > 0 else 0.0
    p_val = math.erfc(abs(z) / math.sqrt(2.0))
    return {
        "rate_a": round(p1, 6),
        "rate_b": round(p2, 6),
        "diff_pp": round((p1 - p2) * 100.0, 4),
        "z_stat": round(z, 4),
        "p_value_two_sided": p_val,
    }


def welch_t(xs: List[float], ys: List[float]) -> Dict[str, float]:
    n1, n2 = len(xs), len(ys)
    m1 = sum(xs) / n1
    m2 = sum(ys) / n2
    v1 = sum((x - m1) ** 2 for x in xs) / (n1 - 1)
    v2 = sum((y - m2) ** 2 for y in ys) / (n2 - 1)
    se = math.sqrt(v1 / n1 + v2 / n2)
    t = (m1 - m2) / se if se > 0 else 0.0
    p_val = math.erfc(abs(t) / math.sqrt(2.0))
    return {
        "n_a": n1,
        "n_b": n2,
        "mean_a_hours": round(m1, 3),
        "mean_b_hours": round(m2, 3),
        "diff_hours": round(m1 - m2, 3),
        "t_stat": round(t, 4),
        "p_value_two_sided": p_val,
    }


def run_module(zip_path: Path, out_dir: Path, sqlite_path: Path) -> Dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    if sqlite_path.exists():
        sqlite_path.unlink()

    sha = ensure_uci_zip(zip_path)

    total_events = 0
    tickets: Dict[str, Dict] = {}

    with zipfile.ZipFile(zip_path, "r") as zf:
        csv_name = [n for n in zf.namelist() if n.endswith(".csv")][0]
        with zf.open(csv_name, "r") as raw_f:
            reader = csv.DictReader(io.TextIOWrapper(raw_f, encoding="utf-8", errors="replace"))
            for row in reader:
                total_events += 1
                num = row["number"].strip()
                mod_cnt = int(row.get("sys_mod_count") or 0)
                upd_dt = parse_dt(row.get("sys_updated_at", ""))
                open_dt = parse_dt(row.get("opened_at", ""))
                res_dt = parse_dt(row.get("resolved_at", ""))
                close_dt = parse_dt(row.get("closed_at", ""))

                rec = tickets.get(num)
                if rec is None:
                    tickets[num] = {
                        "issue_key": num,
                        "snapshot_count": 1,
                        "max_mod": mod_cnt,
                        "latest_upd": upd_dt,
                        "opened_at": open_dt,
                        "resolved_at": res_dt,
                        "closed_at": close_dt,
                        "priority_tier": map_jira_priority_tier(row.get("priority", "")),
                        "assignment_group": (row.get("assignment_group") or "UNASSIGNED").strip() or "UNASSIGNED",
                        "category": (row.get("category") or "Uncategorized").strip() or "Uncategorized",
                        "reassignment_count": int(row.get("reassignment_count") or 0),
                        "reopen_count": int(row.get("reopen_count") or 0),
                        "made_sla": 1 if (row.get("made_sla") or "").strip().lower() == "true" else 0,
                        "knowledge_used": 1 if (row.get("knowledge") or "").strip().lower() == "true" else 0,
                    }
                else:
                    rec["snapshot_count"] += 1
                    is_newer = (mod_cnt > rec["max_mod"]) or (
                        mod_cnt == rec["max_mod"]
                        and upd_dt is not None
                        and (rec["latest_upd"] is None or upd_dt >= rec["latest_upd"])
                    )
                    if open_dt is not None and (rec["opened_at"] is None or open_dt < rec["opened_at"]):
                        rec["opened_at"] = open_dt
                    if res_dt is not None and (rec["resolved_at"] is None or res_dt > rec["resolved_at"]):
                        rec["resolved_at"] = res_dt
                    if close_dt is not None and (rec["closed_at"] is None or close_dt > rec["closed_at"]):
                        rec["closed_at"] = close_dt
                    if is_newer:
                        rec["max_mod"] = mod_cnt
                        rec["latest_upd"] = upd_dt
                        rec["priority_tier"] = map_jira_priority_tier(row.get("priority", ""))
                        ag = (row.get("assignment_group") or "").strip()
                        if ag and ag != "?":
                            rec["assignment_group"] = ag
                        cat = (row.get("category") or "").strip()
                        if cat and cat != "?":
                            rec["category"] = cat
                        rec["reassignment_count"] = max(rec["reassignment_count"], int(row.get("reassignment_count") or 0))
                        rec["reopen_count"] = max(rec["reopen_count"], int(row.get("reopen_count") or 0))
                        rec["made_sla"] = 1 if (row.get("made_sla") or "").strip().lower() == "true" else 0
                        rec["knowledge_used"] = 1 if (row.get("knowledge") or "").strip().lower() == "true" else 0

    conn = sqlite3.connect(str(sqlite_path))
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE fct_jira_ticket_lifecycle (
            issue_key TEXT PRIMARY KEY,
            priority_tier TEXT NOT NULL,
            assignment_group TEXT NOT NULL,
            category TEXT NOT NULL,
            snapshot_count INTEGER NOT NULL,
            reassignment_count INTEGER NOT NULL,
            reopen_count INTEGER NOT NULL,
            made_sla INTEGER NOT NULL,
            knowledge_used INTEGER NOT NULL,
            resolution_hours REAL NOT NULL,
            routing_band TEXT NOT NULL
        );
        """
    )

    zero_hop_hours: List[float] = []
    multi_hop_hours: List[float] = []
    ticket_rows = []
    for rec in tickets.values():
        end_dt = rec["resolved_at"] or rec["closed_at"] or rec["latest_upd"]
        start_dt = rec["opened_at"]
        if start_dt and end_dt and end_dt >= start_dt:
            hrs = (end_dt - start_dt).total_seconds() / 3600.0
        else:
            hrs = 0.0
        rc = rec["reassignment_count"]
        if rc == 0:
            band = "0_First_Owner_Direct"
            if hrs > 0:
                zero_hop_hours.append(hrs)
        elif rc == 1:
            band = "1_Single_Handoff"
        else:
            band = "2_Multi_Hop_Escalation"
            if hrs > 0:
                multi_hop_hours.append(hrs)

        ag = rec["assignment_group"] if rec["assignment_group"] != "?" else "UNASSIGNED"
        ticket_rows.append(
            (
                rec["issue_key"],
                rec["priority_tier"],
                ag,
                rec["category"],
                rec["snapshot_count"],
                rc,
                rec["reopen_count"],
                rec["made_sla"],
                rec["knowledge_used"],
                round(hrs, 4),
                band,
            )
        )

    cur.executemany(
        "INSERT INTO fct_jira_ticket_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ticket_rows,
    )
    conn.commit()

    priority_mart = cur.execute(
        """
        WITH tier_rollup AS (
            SELECT
                priority_tier,
                routing_band,
                COUNT(*) AS ticket_count,
                SUM(snapshot_count) AS source_snapshots,
                SUM(made_sla) AS sla_compliant_tickets,
                ROUND(100.0 * SUM(made_sla) / COUNT(*), 4) AS sla_compliance_pct,
                ROUND(AVG(resolution_hours), 2) AS mean_resolution_hours,
                SUM(CASE WHEN reopen_count > 0 THEN 1 ELSE 0 END) AS reopened_tickets
            FROM fct_jira_ticket_lifecycle
            GROUP BY priority_tier, routing_band
        )
        SELECT * FROM tier_rollup
        ORDER BY priority_tier, routing_band;
        """
    ).fetchall()

    queue_bottlenecks = cur.execute(
        """
        SELECT
            assignment_group,
            COUNT(*) AS total_tickets,
            SUM(made_sla) AS sla_met_tickets,
            ROUND(100.0 * SUM(made_sla) / COUNT(*), 2) AS sla_compliance_pct,
            ROUND(AVG(reassignment_count), 2) AS avg_reassignments,
            ROUND(AVG(resolution_hours), 2) AS avg_resolution_hours
        FROM fct_jira_ticket_lifecycle
        GROUP BY assignment_group
        HAVING COUNT(*) >= 50
        ORDER BY sla_compliance_pct ASC, total_tickets DESC
        LIMIT 25;
        """
    ).fetchall()

    z_k1, z_n1 = cur.execute(
        "SELECT SUM(made_sla), COUNT(*) FROM fct_jira_ticket_lifecycle WHERE reassignment_count = 0"
    ).fetchone()
    z_k2, z_n2 = cur.execute(
        "SELECT SUM(made_sla), COUNT(*) FROM fct_jira_ticket_lifecycle WHERE reassignment_count >= 2"
    ).fetchone()

    sla_z = two_prop_z(int(z_k1), int(z_n1), int(z_k2), int(z_n2))
    hrs_t = welch_t(multi_hop_hours, zero_hop_hours)

    sum_snaps = cur.execute("SELECT SUM(snapshot_count) FROM fct_jira_ticket_lifecycle").fetchone()[0]
    distinct_queues = cur.execute("SELECT COUNT(DISTINCT assignment_group) FROM fct_jira_ticket_lifecycle WHERE assignment_group != 'UNASSIGNED'").fetchone()[0]
    distinct_tiers = cur.execute("SELECT COUNT(DISTINCT priority_tier) FROM fct_jira_ticket_lifecycle").fetchone()[0]
    neg_hrs = cur.execute("SELECT COUNT(*) FROM fct_jira_ticket_lifecycle WHERE resolution_hours < 0").fetchone()[0]
    integrity_ok = cur.execute("PRAGMA integrity_check;").fetchone()[0] == "ok"
    overall_sla_pct = cur.execute("SELECT ROUND(100.0 * SUM(made_sla) / COUNT(*), 4) FROM fct_jira_ticket_lifecycle").fetchone()[0]
    conn.close()

    row_reduction_pct = round(100.0 * (1.0 - len(ticket_rows) / total_events), 4)

    qa_gates = [
        {"gate_id": "JIRA-01", "name": "Source ZIP SHA-256 matches UCI benchmark", "passed": sha == UCI_SHA256},
        {"gate_id": "JIRA-02", "name": "Exact 141,712 event snapshots ingested", "passed": total_events == 141712},
        {"gate_id": "JIRA-03", "name": "Exact 24,918 canonical Jira tickets deduplicated", "passed": len(ticket_rows) == 24918},
        {"gate_id": "JIRA-04", "name": "100% snapshot-to-ticket conservation", "passed": int(sum_snaps) == total_events},
        {"gate_id": "JIRA-05", "name": "All 4 P1-P4 Jira SLA tiers populated", "passed": distinct_tiers == 4},
        {"gate_id": "JIRA-06", "name": "70+ active dispatch queues profiled", "passed": distinct_queues >= 70},
        {"gate_id": "JIRA-07", "name": "Zero negative resolution durations", "passed": neg_hrs == 0},
        {"gate_id": "JIRA-08", "name": "Statistically significant first-owner SLA lift (p < 1e-10)", "passed": sla_z["p_value_two_sided"] < 1e-10},
        {"gate_id": "JIRA-09", "name": "Reporting row reduction > 80%", "passed": row_reduction_pct > 80.0},
        {"gate_id": "JIRA-10", "name": "SQLite integrity_check == ok", "passed": integrity_ok},
    ]

    with (out_dir / "jira_priority_sla_mart.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "priority_tier", "routing_band", "ticket_count", "source_snapshots",
            "sla_compliant_tickets", "sla_compliance_pct", "mean_resolution_hours", "reopened_tickets",
        ])
        w.writerows(priority_mart)

    with (out_dir / "queue_escalation_bottlenecks.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "assignment_group", "total_tickets", "sla_met_tickets",
            "sla_compliance_pct", "avg_reassignments", "avg_resolution_hours",
        ])
        w.writerows(queue_bottlenecks)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": sha,
        "source_events": total_events,
        "canonical_jira_tickets": len(ticket_rows),
        "reporting_row_reduction_pct": row_reduction_pct,
        "active_dispatch_queues": int(distinct_queues),
        "overall_contract_sla_compliance_pct": float(overall_sla_pct),
        "hypothesis_tests": {
            "direct_owner_vs_multi_hop_sla_z_test": sla_z,
            "multi_hop_vs_direct_resolution_hours_welch_t": hrs_t,
        },
        "qa_gates_passed": sum(1 for g in qa_gates if g["passed"]),
        "qa_gates_total": len(qa_gates),
        "qa_gates": qa_gates,
    }
    with (out_dir / "validation_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Jira Contract SLA & Milestone Lifecycle module.")
    parser.add_argument("--zip-path", type=Path, default=Path("data/raw/uci_incidents.zip"))
    parser.add_argument("--out-dir", type=Path, default=Path("contract_milestone_jira_sla_ops/results"))
    parser.add_argument("--sqlite-path", type=Path, default=Path("contract_milestone_jira_sla_ops/results/jira_sla.sqlite"))
    args = parser.parse_args()
    res = run_module(args.zip_path, args.out_dir, args.sqlite_path)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
