#!/usr/bin/env python3
"""
P1 Module: AI-Assisted Request Triage, Contact-Center SLA & dbt Operations Mart
Executes across 141,712 event snapshots (24,918 unique cases, 71 assignment queues)
from UCI Incident Management Process Enriched Event Log.
"""
import csv
import hashlib
import io
import json
import math
import sqlite3
import statistics
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

URL = "https://archive.ics.uci.edu/static/public/498/incident+management+process+enriched+event+log.zip"
EXPECTED_ZIP_SHA256 = "6294e29a311647306bfdfc85783f7df66517c197b9cd49aa5ee36ba9c525d1d6"
MODULE_DIR = Path(__file__).resolve().parent
ROOT_DIR = MODULE_DIR.parent
RESULTS_DIR = MODULE_DIR / "results"


def parse_ts(val: str):
    if val in ("", "?", None):
        return None
    return datetime.strptime(val, "%d/%m/%Y %H:%M")


def two_prop_z(k1: int, n1: int, k2: int, n2: int):
    p1 = k1 / n1
    p2 = k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n1 + 1.0 / n2))
    z = (p1 - p2) / se if se > 0 else 0.0
    p_val = math.erfc(abs(z) / math.sqrt(2.0))
    return {
        "first_touch_rate_pct": round(100.0 * p1, 2),
        "reassigned_rate_pct": round(100.0 * p2, 2),
        "abs_diff_pp": round(100.0 * (p1 - p2), 2),
        "rel_improvement_pct": round(100.0 * (p1 - p2) / p2, 2) if p2 > 0 else 0.0,
        "z_stat": round(z, 4),
        "p_value": float(f"{p_val:.6e}"),
    }


def run_triage_mart():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = ROOT_DIR / "incident-log.zip"
    if not zip_path.exists():
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=45) as r:
            zip_path.write_bytes(r.read())
    raw = zip_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != EXPECTED_ZIP_SHA256:
        raise ValueError(f"SHA256 mismatch: {sha}")

    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        csv_bytes = z.read("incident_event_log.csv")
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
    raw_rows = list(reader)

    latest, earliest, snapshots = {}, {}, Counter()
    for i, row in enumerate(raw_rows, 1):
        key = row["number"]
        opened = parse_ts(row["opened_at"])
        updated = parse_ts(row["sys_updated_at"])
        earliest[key] = min(earliest.get(key, opened), opened)
        snapshots[key] += 1
        rank = (updated, int(row["sys_mod_count"]), i)
        if key not in latest or rank > latest[key][0]:
            latest[key] = (rank, row)

    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE stg_contact_center_cases (
            case_id TEXT PRIMARY KEY,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            final_group TEXT,
            priority TEXT,
            contact_type TEXT,
            category TEXT,
            reassignments INTEGER,
            reopens INTEGER,
            snapshots INTEGER,
            elapsed_hours REAL,
            made_sla_flag INTEGER,
            invalid_closed_interval INTEGER
        )
    """)

    batch = []
    first_touch_hours, reassigned_hours = [], []
    ft_sla_ok, ft_total = 0, 0
    re_sla_ok, re_total = 0, 0

    for key, (_, r) in sorted(latest.items()):
        opened = earliest[key]
        closed = parse_ts(r["closed_at"])
        invalid = int(closed is not None and closed < opened)
        elapsed = ((closed - opened).total_seconds() / 3600.0) if (closed and not invalid) else None
        reass = int(r["reassignment_count"])
        reop = int(r["reopen_count"])
        sla_flag = 1 if r["made_sla"] == "true" else 0

        if elapsed is not None:
            if reass == 0:
                first_touch_hours.append(elapsed)
                ft_total += 1
                ft_sla_ok += sla_flag
            else:
                reassigned_hours.append(elapsed)
                re_total += 1
                re_sla_ok += sla_flag

        batch.append((
            key,
            opened.isoformat(),
            closed.isoformat() if closed else None,
            r["assignment_group"] or "UNASSIGNED",
            r["priority"],
            r["contact_type"],
            r["category"],
            reass,
            reop,
            snapshots[key],
            elapsed,
            sla_flag,
            invalid,
        ))

    cur.executemany("INSERT INTO stg_contact_center_cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
    mart_sql = (MODULE_DIR / "models" / "fct_contact_center_sla_mart.sql").read_text()
    cur.execute(f"CREATE TABLE fct_contact_center_sla_mart AS {mart_sql}")
    conn.commit()

    cur.execute("SELECT * FROM fct_contact_center_sla_mart")
    cols = [d[0] for d in cur.description]
    mart_rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    with (RESULTS_DIR / "queue_sla_mart.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(mart_rows)

    sla_test = two_prop_z(ft_sla_ok, ft_total, re_sla_ok, re_total)
    med_ft = statistics.median(first_touch_hours)
    med_re = statistics.median(reassigned_hours)
    cycle_reduction_pct = round(100.0 * (med_re - med_ft) / med_re, 2)

    summary = {
        "zip_sha256": sha,
        "raw_event_snapshots": len(raw_rows),
        "unique_cases": len(batch),
        "distinct_queues": len(mart_rows),
        "first_touch_triage_cases": ft_total,
        "reassigned_multi_hop_cases": re_total,
        "first_touch_median_close_hours": round(med_ft, 2),
        "reassigned_median_close_hours": round(med_re, 2),
        "median_resolution_time_reduction_pct": cycle_reduction_pct,
        "sla_compliance_comparison": sla_test,
    }
    (RESULTS_DIR / "triage_sla_validation.json").write_text(json.dumps(summary, indent=2) + "\n")
    conn.close()
    return summary


if __name__ == "__main__":
    print(json.dumps(run_triage_mart(), indent=2))
