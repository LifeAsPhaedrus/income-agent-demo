import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bids


class BidTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        self.request = {
            "id": "freelancer:1",
            "version": 2,
            "confirm": True,
            "milestone_percentage": 100,
            "fingerprint": "abc",
        }
        self.ready = {
            "fingerprint": "abc",
            "version": 2,
            "payload": {
                "project_id": 1,
                "bidder_id": 2,
                "amount": 250,
                "period": 7,
                "description": "approved",
                "milestone_percentage": 100,
            },
            "status": {},
        }

    def tearDown(self):
        self.tmp.cleanup()

    def run_submit(self, side_effect):
        with (
            patch.object(bids, "prepare", return_value=self.ready),
            patch.object(bids, "api", side_effect=side_effect) as api,
            patch.object(bids, "record") as record,
        ):
            result = bids.submit(self.root, self.request)
            return result, api.call_args_list, record.call_args_list

    def test_success_once(self):
        r, calls, records = self.run_submit([{"bids": []}, {"id": 99}])
        self.assertEqual(r["submission"]["state"], "submitted")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(records), 2)

    def test_timeout_blocks_retry(self):
        r, calls, _ = self.run_submit([{"bids": []}, TimeoutError()])
        self.assertEqual(r["submission"]["state"], "unknown")
        self.ready["status"] = r["submission"]
        r, calls, _ = self.run_submit([])
        self.assertEqual(calls, [])

    def test_existing_bid_no_write(self):
        r, calls, _ = self.run_submit([{"bids": [{"id": 88, "bidder_id": 2}]}])
        self.assertEqual(r["submission"]["state"], "existing")
        self.assertEqual(len(calls), 1)

    def test_changed_payload_refused(self):
        self.request["fingerprint"] = "changed"
        with self.assertRaises(ValueError):
            self.run_submit([])

    def test_unconfirmed_refused(self):
        self.request["confirm"] = False
        with self.assertRaises(ValueError):
            self.run_submit([])

    def test_database_failure_prevents_send(self):
        with (
            patch.object(bids, "prepare", return_value=self.ready),
            patch.object(bids, "api", return_value={"bids": []}) as api,
            patch.object(bids, "record", side_effect=RuntimeError("offline")),
        ):
            with self.assertRaises(RuntimeError):
                bids.submit(self.root, self.request)
            self.assertEqual(api.call_count, 1)

    def test_explicit_rejected_retry(self):
        self.ready["status"] = {"state": "rejected", "message": "balance required"}
        self.request["retry_rejected"] = True
        r, calls, _ = self.run_submit([{"bids": []}, {"id": 101}])
        self.assertEqual(r["submission"]["state"], "submitted")

    def test_unknown_never_retried(self):
        self.ready["status"] = {"state": "unknown"}
        self.request["retry_rejected"] = True
        r, calls, _ = self.run_submit([])
        self.assertEqual(calls, [])

    def test_api_write_allowlist(self):
        with self.assertRaises(ValueError):
            bids.api("users/0.1/self/", {"bad": 1})

    def test_rejected_recorded(self):
        r, _, _ = self.run_submit([{"bids": []}, bids.Rejected("Freelancer HTTP 403")])
        self.assertEqual(r["submission"]["state"], "rejected")


if __name__ == "__main__":
    unittest.main()
