"""Approved aggregate service reporting with small-cell suppression."""
import argparse
import csv
import json
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ALLOWED_FIELDS=['final_group','intake_month','reporting_status','case_count',
                'reassigned_cases','reassignment_share','valid_closed_cases','median_elapsed_close_hours']


def aggregate(rows, minimum=10):
    if minimum<2:
        raise ValueError('Small-cell threshold must be at least 2')
    grouped=defaultdict(list)
    for row in rows:
        group=row['final_group']
        month=row['opened_at'][:7]
        grouped[(group,month)].append(row)
    result=[]
    for (group,month), cases in sorted(grouped.items()):
        n=len(cases)
        r=sum(c['reassignments']>0 for c in cases)
        durations=[(datetime.fromisoformat(c['closed_at'])-datetime.fromisoformat(c['opened_at'])).total_seconds()/3600
                   for c in cases if c['closed_at'] and not c['invalid_closed_interval']]
        # Numerator and complement both meet the threshold before a rate is exposed.
        safe_count=n>=minimum
        safe_rate=safe_count and r>=minimum and n-r>=minimum
        safe_duration=safe_count and len(durations)>=minimum
        result.append(dict(final_group=group,intake_month=month,
            reporting_status='released' if safe_count else 'small_cohort',
            case_count=n if safe_count else None,
            reassigned_cases=r if safe_rate else None,
            reassignment_share=round(r/n,6) if safe_rate else None,
            valid_closed_cases=len(durations) if safe_duration else None,
            median_elapsed_close_hours=round(statistics.median(durations),6) if safe_duration else None))
    return result


def run(db_path,output,minimum=10):
    if not db_path.exists():
        raise FileNotFoundError('Run python3 src/pipeline.py first')
    db=sqlite3.connect('file:'+str(db_path)+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    rows=[dict(r) for r in db.execute('SELECT final_group,opened_at,closed_at,reassignments,invalid_closed_interval FROM cases')]
    source_events=db.execute('SELECT SUM(snapshots) FROM cases').fetchone()[0]
    db.close()
    report=aggregate(rows,minimum)
    output.mkdir(parents=True,exist_ok=True)
    with (output/'approved_group_month.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=ALLOWED_FIELDS,lineterminator='\n')
        w.writeheader();w.writerows(report)
    checks={
      'one_row_per_group_month':len(report)==len({(r['final_group'],r['intake_month']) for r in report}),
      'allowlisted_fields_only':all(list(r)==ALLOWED_FIELDS for r in report),
      'small_counts_withheld':all(r['case_count'] is None for r in report if r['reporting_status']=='small_cohort'),
      'released_counts_meet_threshold':all(r['case_count']>=minimum for r in report if r['case_count'] is not None),
      'rate_numerator_and_complement':all(r['reassigned_cases']>=minimum and r['case_count']-r['reassigned_cases']>=minimum for r in report if r['reassignment_share'] is not None),
      'duration_sample_meets_threshold':all(r['valid_closed_cases']>=minimum for r in report if r['median_elapsed_close_hours'] is not None),
      'source_case_count':len(rows)==24918,
      'source_event_conservation':source_events==141712,
    }
    if not all(checks.values()):raise ValueError(str(checks))
    summary=dict(source_events=source_events,unique_cases=len(rows),minimum_cohort=minimum,
        group_month_cells=len(report),released_count_cells=sum(r['case_count'] is not None for r in report),
        suppressed_count_cells=sum(r['case_count'] is None for r in report),
        released_rate_cells=sum(r['reassignment_share'] is not None for r in report),
        row_reduction_pct=round((1-len(rows)/source_events)*100,4),
        checks=checks,checks_passed=sum(checks.values()),
        limits=['Public IT-support cases provide a comparable service reporting implementation; they are not HR or employer records.',
          'Final assignment group is not the historical owner at opening.',
          'Calendar elapsed closure time is not employee effort or handling time.',
          'Reassignment share is not measured escalation or first-contact resolution.',
          'Suppression is a local release rule, not differential privacy. Do not combine extracts to reconstruct cells.',
          'No all-group totals are released. CSV filtering is not identity-based access control; access must be configured in the BI tenant.'])
    (output/'validation.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',type=Path,default=ROOT.parent/'results/service.sqlite')
    p.add_argument('--output',type=Path,default=ROOT/'results')
    p.add_argument('--minimum-cohort',type=int,default=10)
    a=p.parse_args();print(json.dumps(run(a.database,a.output,a.minimum_cohort),indent=2))
