import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import contra_source as c
from earnings import estimate


class ContraTests(unittest.TestCase):
    def job(self):
        return {
            "jobId": "opaque-job",
            "publicUrl": "https://contra.com/opportunity/test",
            "title": "Excel dashboard",
            "status": "POSTED",
            "createdAt": "2026-10-24T00:00:00Z",
            "budget": {
                "type": "MonthlyRateJobBudget",
                "feeMin": "USD:400",
                "feeMax": "USD:800",
            },
            "blocknoteDescription": [
                {
                    "id": "secret-metadata",
                    "content": [{"text": "Build an Excel dashboard."}],
                }
            ],
        }

    def test_writes_denied_before_credentials_or_network(self):
        with (
            patch.object(c, "access_token") as token,
            patch.object(c, "request") as request,
        ):
            for name in (
                "apply_to_job_prepare",
                "apply_to_job_confirm",
                "bookmark_job",
                "send_chat_message_confirm",
            ):
                with self.assertRaises(ValueError):
                    c.call_tool(name, {})
            token.assert_not_called()
            request.assert_not_called()

    def test_private_account_feeds_denied(self):
        with self.assertRaises(ValueError):
            c.call_tool("list_job_feed", {"preset": "APPLIED"})

    def test_normalization_preserves_units_and_visible_text(self):
        row = c.normalize([self.job()])[0]
        self.assertEqual(row["type"], "monthly")
        self.assertEqual(row["budget"]["maximum"], 800)
        self.assertEqual(row["description"], "Build an Excel dashboard.")
        self.assertEqual(row["id"], c.normalize([self.job()])[0]["id"])
        e = estimate(
            {
                "source": "Contra",
                "budget": {"maximum": 800, "currency": "USD", "type": "monthly"},
            }
        )
        self.assertEqual(e["unit"], "month")
        self.assertIsNone(e["net_amount"])

    def test_untrusted_listing_links_rejected(self):
        for url in (
            "https://contra.com.evil.test/opportunity/x",
            "http://contra.com/opportunity/x",
            "https://user@contra.com/opportunity/x",
        ):
            self.assertEqual(c.normalize([{**self.job(), "publicUrl": url}]), [])

    def test_cached_queries_do_not_mix(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.object(
                c, "call_tool", return_value={"entries": [], "accessLimitedFeed": True}
            ) as call,
        ):
            root = Path(d)
            c.fetch(root, "Excel")
            c.fetch(root, "Excel")
            self.assertEqual(call.call_count, 1)
            c.fetch(root, "inventory")
            self.assertEqual(call.call_count, 2)

    def test_refresh_rotates_private_token(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "token.json"
            path.write_text(
                json.dumps(
                    {
                        "refresh_token": "old",
                        "client_id": "client",
                        "expires_in": 1,
                        "received_at": 0,
                    }
                )
            )
            with patch.object(
                c,
                "request",
                return_value={
                    "access_token": "new",
                    "refresh_token": "rotated",
                    "expires_in": 3600,
                },
            ):
                self.assertEqual(c.access_token(path), "new")
            self.assertEqual(json.loads(path.read_text())["refresh_token"], "rotated")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_contra_ranking_preserves_review_and_public_link(self):
        import time

        from test_workflow import PROFILE

        import workflow

        with tempfile.TemporaryDirectory() as d:
            db = workflow.connect(Path(d))
            try:
                rows = c.normalize([self.job()])
                rows[0]["time_submitted"] = time.time()
                ranked, _ = workflow.rank(rows, PROFILE, db, time.time())
                self.assertEqual(len(ranked), 1)
                ident = ranked[0]["id"]
                self.assertTrue(ident.startswith("contra:"))
                db.execute("UPDATE items SET status='saved' WHERE id=?", (ident,))
                ranked, _ = workflow.rank(rows, PROFILE, db, time.time())
                self.assertEqual(ranked[0]["status"], "saved")
                self.assertEqual(ranked[0]["url"], self.job()["publicUrl"])
                self.assertIsNone(ranked[0]["effective_hourly"])
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
