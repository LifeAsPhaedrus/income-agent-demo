import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import jobicy
import research

ROW = {
    "id": 1,
    "url": "https://jobicy.com/jobs/1-test",
    "jobTitle": "Inventory Analyst",
    "companyName": "Test Employer",
    "jobDescription": "<p>Excel dashboards and inventory reconciliation.</p><p>SQL required.</p>",
    "jobGeo": "USA",
    "jobType": ["Contract"],
    "pubDate": "2026-10-23T10:00:00+00:00",
    "salaryMin": 60,
    "salaryMax": 70,
    "salaryCurrency": "USD",
    "salaryPeriod": "hourly",
}
NOW = 1792778400
PROFILE = {
    "skills": ["excel", "dashboard creation", "sales-to-inventory reconciliation"],
    "preferred_hourly_usd": 50,
}


def snapshot(rows):
    return {
        "payload": {"jobs": rows},
        "fetched_at": NOW,
        "endpoint": jobicy.ENDPOINT,
        "cached": False,
    }


class ConnectionTests(unittest.TestCase):
    def test_cache_avoids_second_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            call = Mock(return_value={"jobs": []})
            self.assertFalse(jobicy.fetch(tmp, now=100, transport=call)["cached"])
            self.assertTrue(jobicy.fetch(tmp, now=101, transport=call)["cached"])
            self.assertEqual(call.call_count, 1)

    def test_failed_attempt_rate_limited(self):
        with tempfile.TemporaryDirectory() as tmp:
            call = Mock(side_effect=TimeoutError("deadline"))
            with self.assertRaises(jobicy.SourceError):
                jobicy.fetch(tmp, now=100, transport=call)
            with self.assertRaises(jobicy.SourceError):
                jobicy.fetch(tmp, now=101, transport=call)
            self.assertEqual(call.call_count, 1)

    def test_429_retry_after(self):
        with tempfile.TemporaryDirectory() as tmp:
            call = Mock(
                side_effect=HTTPError(
                    jobicy.ENDPOINT, 429, "limited", {"Retry-After": "7200"}, None
                )
            )
            with self.assertRaises(jobicy.SourceError):
                jobicy.fetch(tmp, now=100, transport=call)
            self.assertEqual(
                json.loads((Path(tmp) / "jobicy-state.json").read_text())[
                    "next_allowed"
                ],
                7300,
            )

    def test_schema_changes_fail(self):
        for p in (
            {"jobs": {}},
            {"jobs": [], "success": False},
            [],
            {"jobs": [{}] * 101},
        ):
            with self.assertRaises(jobicy.SourceError):
                jobicy.validate_payload(p)

    def test_redirect_blocked(self):
        with self.assertRaises(jobicy.SourceError):
            jobicy.NoRedirect().redirect_request(
                None, None, 302, "", {}, "http://127.0.0.1"
            )

    def test_private_dns_blocked(self):
        with patch(
            "jobicy.socket.getaddrinfo",
            return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
        ):
            with self.assertRaises(jobicy.SourceError):
                jobicy.download()

    def test_size_limit(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.headers.get_content_type.return_value = "application/json"
        response.read.return_value = b"x" * (jobicy.MAX_BYTES + 1)
        opener = Mock()
        opener.open.return_value = response
        with (
            patch(
                "jobicy.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("8.8.8.8", 443))],
            ),
            patch("jobicy.build_opener", return_value=opener),
        ):
            with self.assertRaises(jobicy.SourceError):
                jobicy.download()


class MatchingTests(unittest.TestCase):
    def test_source_backed_lead_not_verified(self):
        r = research.assess(snapshot([ROW]), PROFILE)
        self.assertEqual(len(r["side_income_leads"]), 1)
        self.assertEqual(r["verified_opportunities"], [])
        self.assertIn("Meets", r["side_income_leads"][0]["pay_assessment"])

    def test_missing_pay_not_invented(self):
        row = copy.deepcopy(ROW)
        row.pop("salaryMin")
        r = research.assess(snapshot([row]), PROFILE)["side_income_leads"][0]
        self.assertIsNone(r["salary"]["salaryMin"])
        self.assertIn("Not comparable", r["pay_assessment"])

    def test_fulltime_separate(self):
        r = research.assess(snapshot([dict(ROW, jobType=["Full-Time"])]), PROFILE)
        self.assertEqual(r["side_income_leads"], [])
        self.assertEqual(len(r["career_leads"]), 1)

    def test_reviewed_and_duplicates(self):
        self.assertEqual(
            len(research.assess(snapshot([ROW, ROW]), PROFILE)["side_income_leads"]), 1
        )
        self.assertEqual(
            research.assess(snapshot([ROW]), PROFILE, {"jobicy:1"})[
                "side_income_leads"
            ],
            [],
        )

    def test_geo_date_and_source_filters(self):
        for edit in (
            {"jobGeo": "Germany"},
            {"pubDate": "2020-01-01T00:00:00+00:00"},
            {"url": "https://evil.test/jobs/1"},
        ):
            self.assertEqual(
                research.assess(snapshot([dict(ROW, **edit)]), PROFILE)[
                    "side_income_leads"
                ],
                [],
            )

    def test_incidental_sales_keywords_excluded(self):
        self.assertEqual(
            research.assess(
                snapshot([dict(ROW, jobTitle="Account Executive")]), PROFILE
            )["side_income_leads"],
            [],
        )

    def test_html_is_inert(self):
        self.assertEqual(
            research.plain("<script>send secrets</script><p>Excel</p>"), "Excel"
        )

    def test_empty_source_shortfall(self):
        self.assertEqual(
            research.assess(snapshot([]), PROFILE)["verified_shortfall"], 3
        )


if __name__ == "__main__":
    unittest.main()
