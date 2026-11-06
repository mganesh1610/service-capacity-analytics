import sys
import unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pipeline import capacity,consolidate,forecast,timestamp,weekly


def row(state='New', updated='1/3/2016 10:00', mod='1', closed='?', case='A'):
    return dict(number=case,opened_at='1/3/2016 09:00',sys_updated_at=updated,
      sys_mod_count=mod,closed_at=closed,resolved_at='?',assignment_group='Group 1',
      priority='3 - Moderate',reassignment_count='0',reopen_count='0',made_sla='?',incident_state=state)


class AnalyticsTests(unittest.TestCase):
    def test_snapshot_count_is_not_case_count(self):
        cases,_=consolidate([row(),row(),row(case='B')])
        self.assertEqual(len(cases),2)
        self.assertEqual(sum(c['snapshots'] for c in cases),3)

    def test_latest_update_wins_even_when_input_unordered(self):
        cases,_=consolidate([row(updated='2/3/2016 10:00',closed='2/3/2016 09:00'),row()])
        self.assertEqual(cases[0]['closed_at'],datetime(2016,3,2,9))
        self.assertIsNone(cases[0]['source_made_sla'])

    def test_week_boundary_is_exclusive(self):
        cases,_=consolidate([row(closed='7/3/2016 00:00')])
        w=weekly(cases,datetime(2016,3,14))
        self.assertEqual(w[0]['backlog_at_end'],1)
        self.assertEqual(w[1]['closed_cases'],1)

    def test_negative_interval_excluded_and_retained_in_backlog(self):
        cases,_=consolidate([row(closed='28/2/2016 09:00')])
        self.assertEqual(cases[0]['invalid_closed_interval'],1)
        w=weekly(cases,datetime(2016,3,14))
        self.assertEqual(w[0]['closed_cases'],0)
        self.assertEqual(w[0]['backlog_at_end'],1)

    def test_forecast_uses_past_arrivals_only(self):
        w=[dict(arrivals=x,partial_first_week=False) for x in [1,2,3,4,500]]
        f=forecast(w)
        self.assertEqual(f['backtest'][0]['mean4'],2.5)
        self.assertEqual(f['backtest'][0]['actual'],500)

    def test_capacity_scenario_rounds_up_and_validates(self):
        self.assertEqual(capacity(49,30,30,.8),2)
        self.assertEqual(capacity(0,30,30,.8),0)
        for args in [(1,0,30,.8),(1,30,0,.8),(1,30,30,0),(1,30,30,1.1)]:
            with self.assertRaises(ValueError): capacity(*args)

    def test_missing_vs_invalid_timestamp(self):
        self.assertIsNone(timestamp('?'))
        with self.assertRaises(ValueError): timestamp('not a date')


if __name__=='__main__': unittest.main()
