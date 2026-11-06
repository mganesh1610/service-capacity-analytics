#!/usr/bin/env python3
"""Public service-event consolidation, weekly metrics and capacity scenarios."""
import argparse
import csv
import hashlib
import io
import json
import math
import sqlite3
import statistics
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

URL = 'https://archive.ics.uci.edu/static/public/498/incident+management+process+enriched+event+log.zip'
SOURCE = 'https://archive.ics.uci.edu/dataset/498/incident+management+process+enriched+event+log'
EXPECTED_ZIP_SHA256 = '6294e29a311647306bfdfc85783f7df66517c197b9cd49aa5ee36ba9c525d1d6'
ROOT = Path(__file__).resolve().parents[1]


def timestamp(value):
    if value in ('', '?', None):
        return None
    return datetime.strptime(value, '%d/%m/%Y %H:%M')


def monday(value):
    return value.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=value.weekday())


def capacity(volume, minutes, hours, utilization):
    if volume < 0 or minutes <= 0 or hours <= 0 or not 0 < utilization <= 1:
        raise ValueError('Nonnegative volume, positive effort/hours and 0 < utilization <= 1 required')
    return math.ceil(volume * minutes / 60 / (hours * utilization))


def consolidate(rows):
    """Retain all raw records; use update timestamp, mod count, row order for latest state."""
    latest, earliest, snapshots = {}, {}, Counter()
    max_update = None
    for i, row in enumerate(rows, 1):
        key = row['number']
        if not key:
            raise ValueError('Missing incident identifier')
        opened = timestamp(row['opened_at'])
        updated = timestamp(row['sys_updated_at'])
        if opened is None or updated is None:
            raise ValueError('Missing opening/update time')
        earliest[key] = min(earliest.get(key, opened), opened)
        max_update = max(max_update or updated, updated)
        snapshots[key] += 1
        rank = (updated, int(row['sys_mod_count']), i)
        if key not in latest or rank > latest[key][0]:
            latest[key] = (rank, row)
    cases = []
    for key, (_, r) in sorted(latest.items()):
        opened = earliest[key]
        closed, resolved = timestamp(r['closed_at']), timestamp(r['resolved_at'])
        negative = int(closed is not None and closed < opened)
        cases.append(dict(case_id=key, opened_at=opened, closed_at=closed,
            resolved_at=resolved, final_group=r['assignment_group'], priority=r['priority'],
            reassignments=int(r['reassignment_count']), reopens=int(r['reopen_count']),
            source_made_sla=r['made_sla'] if r['made_sla'] in ('true', 'false') else None,
            snapshots=snapshots[key], invalid_closed_interval=negative))
    return cases, max_update


def weekly(cases, max_update):
    if not cases:
        raise ValueError('No cases')
    start = monday(min(c['opened_at'] for c in cases))
    # Exclude the final partial calendar week from forecasting and reporting.
    stop = monday(max_update)
    result = []
    while start < stop:
        end = start + timedelta(days=7)
        opened = [c for c in cases if start <= c['opened_at'] < end]
        closed = [c for c in cases if c['closed_at'] and not c['invalid_closed_interval']
                  and start <= c['closed_at'] < end]
        backlog = sum(c['opened_at'] < end and (c['closed_at'] is None or c['closed_at'] >= end
                      or c['invalid_closed_interval']) for c in cases)
        durations = [(c['closed_at'] - c['opened_at']).total_seconds() / 3600 for c in closed]
        known = [c for c in closed if c['source_made_sla'] is not None]
        result.append(dict(week_start=start.date().isoformat(), arrivals=len(opened),
            closed_cases=len(closed), backlog_at_end=backlog,
            median_elapsed_close_hours=statistics.median(durations) if durations else None,
            reassigned_closures=sum(c['reassignments'] > 0 for c in closed),
            source_sla_known=len(known), source_sla_true=sum(c['source_made_sla']=='true' for c in known),
            partial_first_week=(start == monday(min(c['opened_at'] for c in cases)))))
        start = end
    return result


def forecast(weeks):
    # Only arrivals are predictors. No resolution fields or future snapshots enter the model.
    counts = [w['arrivals'] for w in weeks if not w['partial_first_week']]
    evaluation = []
    for i in range(4, len(counts)):
        pred = statistics.mean(counts[i-4:i])
        evaluation.append(dict(index=i, actual=counts[i], mean4=pred, last_week=counts[i-1]))
    return dict(complete_weeks=len(counts), evaluation_weeks=len(evaluation),
        mean4_mae=statistics.mean(abs(r['actual']-r['mean4']) for r in evaluation) if evaluation else None,
        last_week_mae=statistics.mean(abs(r['actual']-r['last_week']) for r in evaluation) if evaluation else None,
        next_week_mean4=statistics.mean(counts[-4:]) if len(counts)>=4 else None,
        backtest=evaluation)


def write_csv(path, rows):
    if not rows:
        return
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def run(data_zip, output, minutes=30, hours=30, utilization=.8):
    capacity(0, minutes, hours, utilization)
    output.mkdir(parents=True, exist_ok=True)
    if not data_zip.exists():
        urllib.request.urlretrieve(URL, data_zip)
    raw = data_zip.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ZIP_SHA256:
        raise ValueError('Source ZIP hash changed; inspect provenance before proceeding')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        csv_bytes = z.read('incident_event_log.csv')
    reader = csv.DictReader(io.StringIO(csv_bytes.decode('utf-8-sig')))
    fields = reader.fieldnames
    raw_rows = list(reader)
    cases, max_update = consolidate(raw_rows)
    weeks = weekly(cases, max_update)
    # Closure follow-up may extend beyond observed intake. Do not train on that empty tail.
    intake_stop = monday(max(c['opened_at'] for c in cases)).date().isoformat()
    pred = forecast([w for w in weeks if w['week_start'] < intake_stop])
    scenario = dict(handling_minutes_per_case=minutes, productive_hours_per_week=hours,
        planned_utilization=utilization, volume=pred['next_week_mean4'],
        scenario_fte=capacity(pred['next_week_mean4'], minutes, hours, utilization)
                     if pred['next_week_mean4'] is not None else None)
    db = sqlite3.connect(output/'service.sqlite')
    db.execute('DROP TABLE IF EXISTS cases')
    db.execute('''CREATE TABLE cases(case_id TEXT PRIMARY KEY, opened_at TEXT NOT NULL,
      closed_at TEXT, resolved_at TEXT, final_group TEXT, priority TEXT, reassignments INTEGER,
      reopens INTEGER, source_made_sla TEXT, snapshots INTEGER, invalid_closed_interval INTEGER)''')
    serial = [{k:(v.isoformat() if isinstance(v,datetime) else v) for k,v in c.items()} for c in cases]
    db.executemany('INSERT INTO cases VALUES(?,?,?,?,?,?,?,?,?,?,?)', (tuple(c.values()) for c in serial))
    db.execute('DROP TABLE IF EXISTS weekly')
    db.execute('''CREATE TABLE weekly(week_start TEXT PRIMARY KEY, arrivals INTEGER,
      closed_cases INTEGER, backlog_at_end INTEGER, median_elapsed_close_hours REAL,
      reassigned_closures INTEGER, source_sla_known INTEGER, source_sla_true INTEGER,
      partial_first_week INTEGER)''')
    db.executemany('INSERT INTO weekly VALUES(?,?,?,?,?,?,?,?,?)', (tuple(w.values()) for w in weeks))
    integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
    groups = [dict(final_group=g,cases=n,reassigned_cases=r) for g,n,r in db.execute(
        'SELECT final_group,COUNT(*),SUM(reassignments>0) FROM cases GROUP BY final_group ORDER BY COUNT(*) DESC')]
    db.commit()
    db.close()
    write_csv(output/'weekly_metrics.csv', weeks)
    write_csv(output/'group_workload.csv', groups)
    write_csv(output/'forecast_backtest.csv', pred.pop('backtest'))
    write_csv(output/'capacity_scenario.csv', [scenario])
    summary = dict(source=SOURCE,download_url=URL,zip_sha256=hashlib.sha256(raw).hexdigest(),
        csv_sha256=hashlib.sha256(csv_bytes).hexdigest(),event_rows=len(raw_rows),columns=len(fields),
        unique_incidents=len(cases),snapshot_to_case_reduction_pct=round((1-len(cases)/len(raw_rows))*100,4),
        snapshot_sum=sum(c['snapshots'] for c in cases),groups=len(groups),weeks=len(weeks),
        missing_closed=sum(c['closed_at'] is None for c in cases),
        invalid_closed_intervals=sum(c['invalid_closed_interval'] for c in cases),
        sqlite_integrity=integrity,forecast=pred,capacity_scenario=scenario,
        limits=['Public IT support data, not DSP customers or employer records.',
            'Event snapshots are not independent cases. Equal snapshots are retained in input counts.',
            'Elapsed calendar close time is not staff handling effort. Local timezone is unspecified.',
            'Source made_sla semantics are preserved verbatim, not relabeled as measured compliance.',
            'Historical backlog uses eventual closing timestamps and is retrospective, not an online reconstruction.',
            'Capacity inputs are user-set assumptions; FTE is an illustrative scenario, not measured staffing need.',
            'Final group is descriptive case attribution, not the historical owner at each week.',
        'First and final intake weeks excluded from forecasting, as is closure-only follow-up. No hiring or customer outcome claimed.'])
    assert summary['snapshot_sum']==summary['event_rows']
    assert summary['unique_incidents']==len({c['case_id'] for c in cases})
    assert integrity=='ok'
    (output/'validation_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (output/'schema.json').write_text(json.dumps(dict(raw_columns=fields,case_columns=list(serial[0]),weekly_columns=list(weeks[0])),indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-zip',type=Path,default=ROOT/'incident-log.zip')
    parser.add_argument('--output',type=Path,default=ROOT/'results')
    parser.add_argument('--handling-minutes',type=float,default=30)
    parser.add_argument('--productive-hours',type=float,default=30)
    parser.add_argument('--utilization',type=float,default=.8)
    args=parser.parse_args()
    run(args.data_zip,args.output,args.handling_minutes,args.productive_hours,args.utilization)
