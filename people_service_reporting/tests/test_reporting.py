import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline import aggregate,ALLOWED_FIELDS

def cases(n,r):
    return [dict(final_group='A',opened_at='2024-01-01T00:00:00',closed_at='2024-01-02T00:00:00',
            reassignments=int(i<r),invalid_closed_interval=0,caller_id='must_not_export') for i in range(n)]

class ReleaseBoundaries(unittest.TestCase):
    def test_small_cell(self):
        r=aggregate(cases(9,3),10)[0]
        self.assertIsNone(r['case_count']);self.assertIsNone(r['median_elapsed_close_hours'])
    def test_small_complement(self):
        r=aggregate(cases(25,20),10)[0]
        self.assertEqual(r['case_count'],25);self.assertIsNone(r['reassignment_share'])
    def test_exact_threshold(self):
        r=aggregate(cases(20,10),10)[0]
        self.assertEqual(r['reassignment_share'],.5)
        self.assertEqual(r['median_elapsed_close_hours'],24)
    def test_allowlist(self):
        r=aggregate(cases(20,10),10)[0]
        self.assertEqual(list(r),ALLOWED_FIELDS)
        self.assertNotIn('caller_id',r)
    def test_negative_duration_excluded(self):
        rows=cases(10,5);rows[0]['invalid_closed_interval']=1
        r=aggregate(rows,10)[0]
        self.assertIsNone(r['valid_closed_cases']);self.assertIsNone(r['median_elapsed_close_hours'])
    def test_invalid_threshold(self):
        with self.assertRaises(ValueError):aggregate(cases(5,2),1)

if __name__=='__main__':unittest.main()
