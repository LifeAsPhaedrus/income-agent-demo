import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import demo


class DemoTests(unittest.TestCase):
    def test_offline_demo_and_review_need_no_connections(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("network forbidden"),
            ),
            patch("ssh_transport.command", side_effect=AssertionError("SSH forbidden")),
            patch(
                "postgres_store.sql", side_effect=AssertionError("database forbidden")
            ),
        ):
            root = Path(folder)
            report = demo.prepare(root)
            self.assertEqual(len(report["top_three"]), 3)
            self.assertTrue(
                all(
                    p["url"].startswith("https://example.org/demo/")
                    for p in report["ranked"]
                )
            )
            demo.dispatch(
                {
                    "action": "review",
                    "id": "demo:101",
                    "status": "saved",
                    "note": "Sample note",
                },
                root,
            )
            self.assertEqual(len(demo.dispatch({"action": "export"}, root)["rows"]), 1)
            demo.prepare(root)
            self.assertEqual(len(demo.dispatch({"action": "export"}, root)["rows"]), 1)

    def test_live_actions_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for action in (
                "bid_submit",
                "bid_prepare",
                "proposal_start",
                "excel",
                "exec",
            ):
                with self.assertRaises(ValueError):
                    demo.dispatch({"action": action}, root)

    def test_existing_directory_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "private.json"
            path.write_text('{"keep":true}')
            with self.assertRaises(ValueError):
                demo.prepare(root)
            self.assertEqual(json.loads(path.read_text()), {"keep": True})

    def test_private_database_marker_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            demo.prepare(root)
            (root / "postgres-enabled").touch()
            with self.assertRaises(ValueError):
                demo.dispatch({"action": "snapshot"}, root)
            with self.assertRaises(ValueError):
                demo.prepare(root)
