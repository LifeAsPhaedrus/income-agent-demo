import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_workflow import PROFILE, row

import earnings
import remotive_source
import workflow


class MultiSourceTests(unittest.TestCase):
    def test_fee_minimum_and_bid(self):
        p = {
            "source": "Freelancer",
            "budget": {"maximum": 30, "currency": "USD", "type": "fixed"},
        }
        self.assertEqual(earnings.estimate(p)["net_amount"], 25)
        self.assertEqual(earnings.estimate(p, 250)["net_amount"], 225)

    def test_foreign_minimum_not_invented(self):
        p = {"budget": {"maximum": 250, "currency": "INR", "type": "fixed"}}
        self.assertIsNone(earnings.estimate(p)["net_amount"])

    def test_unknown_remotive_takehome(self):
        self.assertIsNone(
            earnings.estimate({"source": "Remotive", "budget": {}})["net_amount"]
        )

    def remote(self):
        return {
            "id": 1,
            "title": "Excel reporting analyst",
            "description": "<p>Excel inventory dashboards</p>",
            "url": "https://remotive.com/remote-jobs/data/analyst-1",
            "publication_date": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "candidate_required_location": "USA",
            "job_type": "contract",
            "salary": "$70,000 - $90,000",
        }

    def test_normalize_source_and_text(self):
        p = remotive_source.normalize([self.remote()], "Excel")[0]
        self.assertEqual(p["description"], "Excel inventory dashboards")
        self.assertEqual(p["currency"]["code"], "unknown")

    def test_offsite_url_refused(self):
        p = self.remote()
        p["url"] = "https://evil.test/job"
        self.assertEqual(remotive_source.normalize([p]), [])

    def test_same_numeric_id_reviews_isolated(self):
        with tempfile.TemporaryDirectory() as t:
            db = workflow.connect(Path(t))
            rows = [row()] + remotive_source.normalize([self.remote()])
            ranked, _ = workflow.rank(rows, PROFILE, db, time.time())
            self.assertEqual({p["id"] for p in ranked}, {"freelancer:1", "remotive:1"})
            db.execute("UPDATE items SET status='saved' WHERE id='remotive:1'")
            ranked, _ = workflow.rank(rows, PROFILE, db, time.time())
            self.assertEqual(
                {p["id"]: p["status"] for p in ranked},
                {"freelancer:1": "new", "remotive:1": "saved"},
            )
            db.close()

    def test_wrong_geography_excluded(self):
        p = self.remote()
        p["candidate_required_location"] = "Germany"
        with tempfile.TemporaryDirectory() as t:
            db = workflow.connect(Path(t))
            self.assertEqual(
                workflow.rank(remotive_source.normalize([p]), PROFILE, db, time.time())[
                    0
                ],
                [],
            )
            db.close()

    def test_cache_no_network(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "data").mkdir()
            (root / "data/remotive-last-attempt.json").write_text(
                json.dumps({"time": time.time()})
            )
            (root / "remotive-results.json").write_text(
                json.dumps({"jobs": [], "fetched_at_epoch": time.time()})
            )
            with patch.object(remotive_source, "build_opener") as op:
                remotive_source.fetch(root)
                op.assert_not_called()


if __name__ == "__main__":
    unittest.main()
