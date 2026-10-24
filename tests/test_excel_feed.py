import unittest
from unittest.mock import Mock
from xml.etree import ElementTree

import excel_feed


class ExcelFeedTests(unittest.TestCase):
    def test_no_access_with_wrong_key(self):
        remote = Mock()
        self.assertEqual(
            excel_feed.route("/excel/wrong/odata/Pursue", "correct", remote)[0], 404
        )
        remote.assert_not_called()

    def test_metadata_and_empty_rows(self):
        remote = Mock(return_value={"rows": []})
        code, xml, kind = excel_feed.route("/excel/key/odata/$metadata", "key", remote)
        ElementTree.fromstring(xml)
        self.assertEqual(code, 200)
        remote.assert_not_called()
        code, body, kind = excel_feed.route("/excel/key/odata/Pursue", "key", remote)
        self.assertEqual(body["value"], [])
        remote.assert_called_once_with({"action": "excel"})

    def test_paging_and_projection(self):
        remote = Mock(
            return_value={
                "rows": [
                    {"listing_id": "freelancer:1", "title": "One"},
                    {"listing_id": "freelancer:2", "title": "Two"},
                ]
            }
        )
        code, body, kind = excel_feed.route(
            "/excel/key/odata/Pursue?$skip=1&$top=1&$select=title&$count=true",
            "key",
            remote,
        )
        self.assertEqual(body["value"], [{"title": "Two"}])
        self.assertEqual(body["@odata.count"], 2)

    def test_query_rejected_before_database(self):
        remote = Mock()
        self.assertEqual(
            excel_feed.route(
                "/excel/key/odata/Pursue?$filter=malicious", "key", remote
            )[0],
            400,
        )
        remote.assert_not_called()

    def test_database_error_not_empty_success(self):
        with self.assertRaises(RuntimeError):
            excel_feed.route(
                "/excel/key/odata/Pursue", "key", Mock(side_effect=RuntimeError)
            )

    def test_bid_fields_keep_rejection_and_null_id(self):
        row = {
            "listing_id": "freelancer:101",
            "proposed_bid_amount": 250.0,
            "bid_status": "Not submitted - rejected by Freelancer",
            "freelancer_bid_id": None,
            "bid_status_detail": "Account balance requires $19 USD",
        }
        remote = Mock(return_value={"rows": [row]})
        _, body, _ = excel_feed.route(
            "/excel/key/odata/Pursue?$select=proposed_bid_amount,bid_status,freelancer_bid_id,bid_status_detail",
            "key",
            remote,
        )
        self.assertEqual(body["value"][0]["proposed_bid_amount"], 250.0)
        self.assertIsNone(body["value"][0]["freelancer_bid_id"])
        self.assertEqual(body["value"][0]["bid_status"], row["bid_status"])
        _, xml, _ = excel_feed.route("/excel/key/odata/$metadata", "key", remote)
        ns = {"e": "http://docs.oasis-open.org/odata/ns/edm"}
        props = {
            p.attrib["Name"]: p.attrib["Type"]
            for p in ElementTree.fromstring(xml).findall(".//e:Property", ns)
        }
        self.assertEqual(props["delivery_days"], "Edm.Int32")
        self.assertEqual(props["bid_status_updated_at"], "Edm.DateTimeOffset")
