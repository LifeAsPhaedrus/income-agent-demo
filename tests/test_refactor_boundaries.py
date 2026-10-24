"""Regression coverage for persistence, source isolation and transport boundaries."""

import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import search_watch
from file_store import write_json_atomic
from source_snapshots import load_candidates
from ssh_transport import command


class RefactorTests(unittest.TestCase):
    def test_failed_atomic_write_preserves_previous_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            write_json_atomic(path, {"complete": True})
            with self.assertRaises(TypeError):
                write_json_atomic(path, {"bad": object()})
            self.assertEqual(json.loads(path.read_text()), {"complete": True})
            self.assertEqual(list(path.parent.iterdir()), [path])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_ssh_entrypoint_injection_is_refused(self):
        for script in ("ui_bridge.py; echo injected", "../ui_bridge.py", "bids.py"):
            with self.assertRaises(ValueError):
                command(script)
        args = command("search_watch.py")
        self.assertIn("StrictHostKeyChecking=yes", args)
        self.assertTrue(args[-1].endswith("python3 -u search_watch.py"))

    def test_old_freelancer_query_not_relabelled_as_new_search(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json_atomic(
                root / "freelancer-results.json",
                {
                    "query": "graphic design",
                    "projects": [{"id": 1}],
                    "fetched_at_epoch": time.time(),
                },
            )
            self.assertEqual(load_candidates(root, "Excel", time.time())[1], [])
            self.assertEqual(
                len(load_candidates(root, "graphic design", time.time())[1]), 1
            )

    def test_stale_or_different_contra_query_is_not_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for query, age in (("different", 0), ("Excel", 90000)):
                write_json_atomic(
                    root / "contra-results.json",
                    {
                        "query": query,
                        "jobs": [{}],
                        "fetched_at_epoch": time.time() - age,
                    },
                )
                with patch("source_snapshots.normalize_contra") as normalize:
                    load_candidates(root, "Excel", time.time())
                    normalize.assert_not_called()

    def test_freelancer_timeout_does_not_stop_other_sources(self):
        from io import StringIO

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(search_watch, "ROOT", root),
                patch("sys.stdin", StringIO('{"query":"Excel"}')),
                patch("sys.stdout", StringIO()),
                patch(
                    "search_watch.subprocess.run",
                    side_effect=subprocess.TimeoutExpired("search", 40),
                ),
                patch(
                    "remotive_source.fetch", return_value=({}, "Connected")
                ) as remotive,
                patch("contra_source.fetch", return_value=({}, "Connected")) as contra,
                patch("workflow.build", return_value={"top_three": []}) as build,
            ):
                self.assertEqual(search_watch.main(), 0)
                remotive.assert_called_once()
                contra.assert_called_once()
                build.assert_called_once()
            status = json.loads((root / "source-status.json").read_text())
            self.assertIn("failed", status["Freelancer"])
            self.assertEqual(status["Contra"], "Connected")
