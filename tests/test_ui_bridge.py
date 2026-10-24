import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import ui_bridge
import workflow


class ReviewBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        with closing(workflow.connect(self.root)) as db, db:
            db.execute(
                "INSERT INTO items(id,title,hash) VALUES (?,?,?)",
                ("freelancer:1", "Example", "hash"),
            )
        self.report = {
            "ranked": [
                {
                    "id": "freelancer:1",
                    "status": "new",
                    "model": {"requirements": ["Original quote"]},
                }
            ]
        }
        (self.root / "PERSONALIZED-RESULTS.json").write_text(json.dumps(self.report))

    def tearDown(self):
        self.tmp.cleanup()

    def test_pursue_and_restore_persist(self):
        r = ui_bridge.dispatch(
            {
                "action": "review",
                "id": "freelancer:1",
                "status": "saved",
                "note": "Ask about hours",
            },
            self.root,
        )
        self.assertEqual(r["ranked"][0]["status"], "saved")
        self.assertEqual(r["history"][0]["note"], "Ask about hours")
        self.assertEqual(r["ranked"][0]["model"]["requirements"], ["Original quote"])
        self.assertEqual(
            ui_bridge.dispatch({"action": "snapshot"}, self.root)["ranked"][0][
                "status"
            ],
            "saved",
        )
        self.assertEqual(
            ui_bridge.dispatch(
                {"action": "review", "id": "freelancer:1", "status": "new"}, self.root
            )["ranked"][0]["status"],
            "new",
        )

    def test_no_marketplace_actions(self):
        for action in ("bid", "message", "pay", "exec"):
            with self.assertRaises(ValueError):
                ui_bridge.dispatch({"action": action}, self.root)

    def test_unknown_or_injected_id_rejected(self):
        for ident in ("freelancer:2", "freelancer:1; rm -rf /"):
            with self.assertRaises(ValueError):
                ui_bridge.dispatch(
                    {"action": "review", "id": ident, "status": "saved"}, self.root
                )

    def test_does_not_modify_model_report(self):
        ui_bridge.dispatch(
            {"action": "review", "id": "freelancer:1", "status": "dismissed"}, self.root
        )
        self.assertEqual(
            json.loads((self.root / "PERSONALIZED-RESULTS.json").read_text()),
            self.report,
        )
