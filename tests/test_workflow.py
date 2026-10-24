import json
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

import workflow as w
from ollama_local import validate

PROFILE = {
    "skills": ["excel", "dashboard creation", "sales-to-inventory reconciliation"],
    "preferred_hourly_usd": 50,
    "unconfirmed_tools": ["SQL"],
}


def row():
    return {
        "id": 1,
        "title": "Excel inventory dashboard",
        "description": "Build an Excel inventory dashboard. SQL required.",
        "status": "active",
        "language": "en",
        "time_submitted": time.time(),
        "type": "fixed",
        "currency": {"code": "USD"},
        "budget": {"minimum": 500, "maximum": 1000},
    }


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = w.connect(self.root)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_fixed_pay_needs_effort(self):
        r = w.rank([row()], PROFILE, self.db, time.time())[0][0]
        self.assertIsNone(r["effective_hourly"])
        self.db.execute("INSERT INTO effort VALUES (?,?)", ("freelancer:1", 10))
        self.assertEqual(
            w.rank([row()], PROFILE, self.db, time.time())[0][0]["effective_hourly"], 50
        )

    def test_currency_not_assumed_usd(self):
        p = row()
        p["type"] = "hourly"
        p["currency"]["code"] = "INR"
        self.assertIsNone(
            w.rank([p], PROFILE, self.db, time.time())[0][0]["effective_hourly"]
        )

    def test_reviews_persist_and_changed_not_reset(self):
        p = row()
        w.rank([p], PROFILE, self.db, time.time())
        self.db.execute('UPDATE items SET status="dismissed"')
        self.db.commit()
        p["description"] += " Changed scope."
        result = w.rank([p], PROFILE, self.db, time.time())[0][0]
        self.assertEqual(result["status"], "dismissed")
        self.assertTrue(result["changed_since_last_run"])

    def test_duplicate_suppression(self):
        self.assertEqual(
            len(w.rank([row(), row()], PROFILE, self.db, time.time())[0]), 1
        )

    def test_inactive_language_and_location(self):
        for edit in (
            {"status": "closed"},
            {"language": "es"},
            {"local": True},
            {"time_submitted": 1},
        ):
            self.assertEqual(
                w.rank([dict(row(), **edit)], PROFILE, self.db, time.time())[0], []
            )

    def test_html_escaped(self):
        self.assertNotIn(
            "<script>alert",
            w.render(
                {
                    "top_three": [],
                    "excluded": [
                        {"title": "<script>alert(1)</script>", "reasons": ["x"]}
                    ],
                    "ranked": [],
                    "source_fetched": "now",
                    "freshness": "saved",
                }
            ),
        )

    def test_model_unsupported_quotes_rejected(self):
        with self.assertRaises(ValueError):
            validate({"requirements": ["invented pay"]}, "Excel needed")
        self.assertEqual(
            validate({"requirements": ["Excel needed"]}, "Excel needed")[
                "requirements"
            ],
            ["Excel needed"],
        )

    def test_stale_snapshot_and_reviews_end_to_end(self):
        (self.root / "user-profile.json").write_text(json.dumps(PROFILE))
        source = {"projects": [row()], "fetched_at_epoch": time.time()}
        (self.root / "freelancer-results.json").write_text(json.dumps(source))
        self.assertEqual(len(w.build(self.root)["top_three"]), 1)
        with closing(w.connect(self.root)) as db, db:
            db.execute('UPDATE items SET status="reviewed"')
        self.assertEqual(w.build(self.root)["top_three"], [])
        with closing(w.connect(self.root)) as db, db:
            db.execute('UPDATE items SET status="new"')
        source["fetched_at_epoch"] = time.time() - 90000
        (self.root / "freelancer-results.json").write_text(json.dumps(source))
        self.assertEqual(w.build(self.root)["top_three"], [])


class ModelBoundaryTests(unittest.TestCase):
    def test_loopback_only_no_tools(self):
        from unittest.mock import Mock, patch

        import ollama_local as o

        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(
            {
                "done": True,
                "message": {"content": json.dumps({"requirements": ["Excel needed"]})},
            }
        ).encode()
        opener = Mock()
        opener.open.return_value = response
        with patch.object(o, "build_opener", return_value=opener):
            self.assertEqual(
                o.extract("Excel needed")["requirements"], ["Excel needed"]
            )
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, "http://127.0.0.1:11434/api/chat")
        data = json.loads(req.data)
        self.assertNotIn("tools", data)
        self.assertEqual(data["model"], "qwen3.5:4b")
        self.assertNotIn("Freelancer-oauth-v1", req.headers)

    def test_timeout_keeps_report(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "user-profile.json").write_text(json.dumps(PROFILE))
            (root / "freelancer-results.json").write_text(
                json.dumps({"projects": [row()], "fetched_at_epoch": time.time()})
            )
            with patch("ollama_local.extract", side_effect=TimeoutError):
                r = w.build(root, True)
            self.assertEqual(len(r["top_three"]), 1)
            self.assertIn("unavailable", r["top_three"][0]["model"]["status"])

    def test_stream_validates_quotes(self):
        from unittest.mock import Mock, patch

        import ollama_local as o

        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.__iter__ = Mock(
            return_value=iter(
                [
                    json.dumps(
                        {"message": {"content": '{"requirements": ['}, "done": False}
                    ).encode(),
                    json.dumps(
                        {"message": {"content": '"Excel needed"]}'}, "done": True}
                    ).encode(),
                ]
            )
        )
        opener = Mock()
        opener.open.return_value = response
        chunks = []
        with patch.object(o, "build_opener", return_value=opener):
            result = o.extract("Excel needed", chunks.append)
        self.assertEqual(result, {"requirements": ["Excel needed"]})
        self.assertEqual(len(chunks), 2)
        self.assertTrue(json.loads(opener.open.call_args.args[0].data)["stream"])
