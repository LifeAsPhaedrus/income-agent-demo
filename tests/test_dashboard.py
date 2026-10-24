import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mac_dashboard
import ui_bridge
import workflow


class DashboardTests(unittest.TestCase):
    def test_reject_invalid_search(self):
        for query in ("x", "x\ncommand", "x" * 101):
            with self.assertRaises(ValueError):
                mac_dashboard.local_action({"action": "start", "query": query})

    def test_duplicate_search(self):
        with patch.dict(mac_dashboard.JOB, running=True):
            with self.assertRaises(ValueError):
                mac_dashboard.local_action({"action": "start", "query": "Excel"})

    def test_database_failure_keeps_review(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            db = workflow.connect(root)
            db.execute("INSERT INTO items(id,title) VALUES ('freelancer:1','Test')")
            db.commit()
            db.close()
            (root / "PERSONALIZED-RESULTS.json").write_text(
                json.dumps({"ranked": [{"id": "freelancer:1"}]})
            )
            (root / "postgres-enabled").touch()
            with patch("postgres_store.sync", side_effect=RuntimeError):
                report = ui_bridge.dispatch(
                    {"action": "review", "id": "freelancer:1", "status": "saved"}, root
                )
                self.assertEqual(report["history"][0]["status"], "saved")
                self.assertIn("pending", report["database_status"])
                with self.assertRaises(ValueError):
                    ui_bridge.dispatch({"action": "export"}, root)

    def test_evidence_survives_next_batch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            db = workflow.connect(root)
            db.execute(
                "INSERT INTO items(id,title,status) VALUES ('freelancer:1','Test','saved')"
            )
            db.commit()
            db.close()
            path = root / "PERSONALIZED-RESULTS.json"
            path.write_text(
                json.dumps(
                    {
                        "ranked": [
                            {"id": "freelancer:1", "description": "Original scope"}
                        ]
                    }
                )
            )
            ui_bridge.dispatch({"action": "snapshot"}, root)
            path.write_text('{"ranked":[]}')
            self.assertEqual(
                ui_bridge.dispatch({"action": "snapshot"}, root)["history"][0][
                    "description"
                ],
                "Original scope",
            )
