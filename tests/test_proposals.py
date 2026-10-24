import json
import tempfile
import unittest
from pathlib import Path

import proposals


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "PERSONALIZED-RESULTS.json").write_text(
            json.dumps(
                {
                    "ranked": [
                        {
                            "id": "freelancer:1",
                            "title": "Excel",
                            "url": "https://www.freelancer.com/projects/1",
                            "description": "Listing",
                            "budget": {"maximum": 250, "currency": "USD"},
                        }
                    ]
                }
            )
        )
        (self.root / "user-profile.json").write_text(
            json.dumps(
                {"skills": ["excel"], "token": "NEVER EXPORT", "weekly_hours": None}
            )
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_max_default_no_submission(self):
        d = proposals.get(self.root, "freelancer:1")
        self.assertEqual(d["draft"]["amount"], 250)
        self.assertFalse(d["submission_enabled"])
        self.assertIn("Pending", d["delivery"])

    def test_versions_and_conflict(self):
        r = {"id": "freelancer:1", "body": "First", "amount": 250, "version": 0}
        proposals.save(self.root, r)
        with self.assertRaises(ValueError):
            proposals.save(self.root, r)
        r.update(version=1, body="Edited")
        d = proposals.save(self.root, r)
        self.assertEqual(len(d["versions"]), 2)
        self.assertEqual(d["versions"][1]["body"], "First")

    def test_export_professional_only(self):
        text = proposals.export(self.root, "freelancer:1")["text"]
        self.assertNotIn("NEVER EXPORT", text)
        self.assertIn("pending scope", text.lower())

    def test_unknown_listing_and_invalid_amount(self):
        with self.assertRaises(ValueError):
            proposals.get(self.root, "freelancer:2")
        with self.assertRaises(ValueError):
            proposals.save(
                self.root,
                {
                    "id": "freelancer:1",
                    "body": "Draft",
                    "amount": float("nan"),
                    "version": 0,
                },
            )

    def test_qwen_runner_saves_new_version_without_marketplace(self):
        import io
        from unittest.mock import MagicMock, patch

        import proposal_draft

        response = MagicMock()
        response.__enter__.return_value = [
            json.dumps(
                {
                    "message": {"content": "A draft for $250, delivery pending scope."},
                    "done": True,
                }
            ).encode()
        ]
        opener = MagicMock()
        opener.open.return_value = response
        with (
            patch.object(proposal_draft, "root", self.root),
            patch.object(
                proposal_draft.sys,
                "stdin",
                io.StringIO('{"id":"freelancer:1","version":0}'),
            ),
            patch.object(proposal_draft.sys, "stdout", io.StringIO()),
            patch.object(proposal_draft, "build_opener", return_value=opener),
        ):
            proposal_draft.main()
        self.assertEqual(
            opener.open.call_args.args[0].full_url, "http://127.0.0.1:11434/api/chat"
        )
        self.assertEqual(
            proposals.get(self.root, "freelancer:1")["draft"]["origin"], "Qwen draft"
        )

    def test_delivery_terms_saved_inherited_and_exported(self):
        r = {
            "id": "freelancer:1",
            "body": "Agreed wording",
            "amount": 250,
            "version": 0,
            "terms": {"days": 7, "revision_rounds": 1},
        }
        d = proposals.save(self.root, r)
        self.assertIn("7 days after receiving", d["delivery"])
        r.pop("terms")
        r.update(version=1, body="Revised wording")
        d = proposals.save(self.root, r)
        self.assertEqual(d["draft"]["terms"], {"days": 7, "revision_rounds": 1})
        self.assertIn(
            "1 revision round", proposals.export(self.root, "freelancer:1")["text"]
        )
        self.assertFalse(d["submission_enabled"])
