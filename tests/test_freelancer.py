import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import freelancer_source as f


class ReadOnlyTests(unittest.TestCase):
    def test_token_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "token"
            p.write_text("x" * 40)
            p.chmod(0o600)
            self.assertEqual(f.read_token(p), "x" * 40)
            p.chmod(0o644)
            with self.assertRaises(f.ConnectionError):
                f.read_token(p)

    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "token"
            p.write_text("x" * 40)
            p.chmod(0o600)
            link = Path(tmp) / "link"
            link.symlink_to(p)
            with self.assertRaises(OSError):
                f.read_token(link)

    def test_only_get_to_fixed_endpoint(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.headers.get_content_type.return_value = "application/json"
        response.read.return_value = b'{"status":"success","result":{"projects":[]}}'
        opener = Mock()
        opener.open.return_value = response
        with (
            patch.object(f, "read_token", return_value="SECRET"),
            patch.object(f, "build_opener", return_value=opener),
        ):
            self.assertEqual(f.search("Excel"), [])
        req = opener.open.call_args.args[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertIsNone(req.data)
        self.assertTrue(req.full_url.startswith(f.ENDPOINT + "?"))
        self.assertNotIn("SECRET", req.full_url)

    def test_redirect_refused(self):
        with self.assertRaises(f.ConnectionError):
            f.NoRedirect().redirect_request(
                None, None, 302, "", {}, "https://evil.test"
            )

    def test_error_redaction(self):
        with (
            patch.object(f, "read_token", return_value="SECRET"),
            patch.object(f, "build_opener", side_effect=RuntimeError("SECRET")),
        ):
            with self.assertRaises(f.ConnectionError) as ctx:
                f.search("Excel")
            self.assertNotIn("SECRET", str(ctx.exception))

    def test_invalid_query(self):
        with self.assertRaises(f.ConnectionError):
            f.search("x", 100)
