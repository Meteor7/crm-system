"""Quotation warning rules, independent of Frappe and of the chosen reference date."""
import unittest
from datetime import datetime, timedelta

from rayher_crm.services.cockpit_metrics import quotation_expiry


REFERENCE = datetime(2026, 9, 22, 12)


def fixture(offset=7):
    return {
        "customers": [{"name": "customer", "customer_name": "Customer", "custom_crm_region": "East China", "custom_crm_segment": "Frontend"}],
        "opportunities": [{"name": "opp", "stage": "quotation_sent"}],
        "quotes": [{"name": "quote", "account": "customer", "quotation_owner": "alice", "opportunity": "opp",
                    "ref_no": "Q-1", "status": "Published", "current_version": "v1", "current_published_version": "v1"}],
        "versions": [{"name": "v1", "quotation": "quote", "version_no": 1, "status": "Published",
                      "published_at": "2026-09-01T00:00:00+08:00", "valid_until": (REFERENCE + timedelta(days=offset)).date().isoformat()}],
    }


class TestQuotationExpiry(unittest.TestCase):
    def test_inclusive_business_date_boundaries_and_configurable_horizon(self):
        for offset, expected in ((-1, 0), (0, 1), (1, 1), (14, 1), (15, 0)):
            with self.subTest(offset=offset):
                result = quotation_expiry(fixture(offset), {}, REFERENCE)
                self.assertEqual(result["count"]["value"], expected)
                self.assertEqual(len(result["items"]), expected)
                if expected:
                    self.assertEqual(result["items"][0]["daysToExpiry"], offset)
        self.assertEqual(quotation_expiry(fixture(15), {}, REFERENCE, 30)["count"]["value"], 1)
        self.assertEqual(quotation_expiry(fixture(0), {}, REFERENCE, 0)["count"]["value"], 1)
        self.assertEqual(quotation_expiry(fixture(1), {}, REFERENCE, 0)["count"]["value"], 0)

    def test_closed_linked_opportunity_outside_customer_scope_is_still_excluded(self):
        data = fixture()
        data["opportunities"] = []
        data["quotation_opportunities"] = [{"name": "opp", "stage": "lost"}]
        self.assertEqual(quotation_expiry(data, {"market": "Frontend"}, REFERENCE)["count"]["value"], 0)
        data["quotation_opportunities"] = []
        self.assertEqual(quotation_expiry(data, {}, REFERENCE)["count"]["state"], "insufficient")

    def test_draft_does_not_hide_formal_version_and_replacement_moves_warning(self):
        data = fixture()
        data["quotes"][0].update(status="Draft", current_version="v2")
        data["versions"].append({**data["versions"][0], "name": "v2", "status": "Draft", "version_no": 2})
        result = quotation_expiry(data, {}, REFERENCE)
        self.assertEqual(result["count"]["value"], 1)
        self.assertEqual(result["items"][0]["quotationVersionId"], "v1")
        data["versions"][0]["status"] = "Superseded"
        data["versions"][1].update(status="Published", valid_until="2026-12-01")
        data["quotes"][0].update(status="Published", current_published_version="v2")
        self.assertEqual(quotation_expiry(data, {}, REFERENCE)["count"]["value"], 0)

    def test_decisions_expiry_and_closed_opportunities_remove_warning(self):
        for status in ("Draft", "Accepted", "Rejected", "Expired", "Superseded"):
            data = fixture()
            data["versions"][0]["status"] = status
            self.assertEqual(quotation_expiry(data, {}, REFERENCE)["count"]["value"], 0)
        for stage in ("lost", "po_received"):
            data = fixture()
            data["opportunities"][0]["stage"] = stage
            self.assertEqual(quotation_expiry(data, {}, REFERENCE)["count"]["value"], 0)

    def test_current_owner_customer_filters_and_service_quotes(self):
        data = fixture()
        data["quotes"][0].update(quotation_owner="bob", opportunity=None)
        data["versions"][0]["quotation_owner"] = "alice"
        self.assertEqual(quotation_expiry(data, {"sales": "alice"}, REFERENCE)["count"]["value"], 0)
        result = quotation_expiry(data, {"sales": "bob", "region": "East China", "market": "Frontend"}, REFERENCE)
        self.assertEqual(result["items"][0]["owner"], "bob")
        for query in ({"market": "Other"}, {"region": "Other"}):
            self.assertEqual(quotation_expiry(data, query, REFERENCE)["count"]["value"], 0)
        data["customers"] = []
        self.assertEqual(quotation_expiry(data, {}, REFERENCE)["items"], [])

    def test_missing_or_malformed_formal_data_is_not_a_zero_count(self):
        for field, value in (("valid_until", None), ("valid_until", "bad"), ("published_at", None), ("published_at", "bad"), ("quotation", "other")):
            data = fixture()
            data["versions"][0][field] = value
            result = quotation_expiry(data, {}, REFERENCE)
            self.assertEqual(result["count"]["state"], "insufficient")
            self.assertIsNone(result["count"]["value"])
        data = fixture()
        data["versions"] = []
        self.assertEqual(quotation_expiry(data, {}, REFERENCE)["count"]["state"], "insufficient")
        data["quotes"][0].update(status="Draft", current_published_version=None)
        self.assertEqual(quotation_expiry(data, {}, REFERENCE)["count"]["value"], 0)

    def test_publication_after_reference_is_not_backdated_and_timezone_is_shanghai(self):
        data = fixture()
        data["versions"][0]["published_at"] = "2026-09-22T04:00:01Z"
        self.assertEqual(quotation_expiry(data, {}, REFERENCE)["count"]["value"], 0)
        data["versions"][0]["published_at"] = "2026-09-22T04:00:00Z"
        self.assertEqual(quotation_expiry(data, {}, REFERENCE)["count"]["value"], 1)

    def test_sort_is_nearest_expiry_first_then_stable_id(self):
        data = fixture(14)
        data["quotes"].append({**data["quotes"][0], "name": "soon", "current_published_version": "soon-v"})
        data["versions"].append({**data["versions"][0], "name": "soon-v", "quotation": "soon", "valid_until": "2026-09-22"})
        self.assertEqual([r["id"] for r in quotation_expiry(data, {}, REFERENCE)["items"]], ["soon", "quote"])

    def test_stale_expiry_job_cannot_keep_a_currently_expired_quote_in_a_past_review(self):
        data = fixture(7)
        self.assertEqual(quotation_expiry(data, {}, REFERENCE, now=datetime(2026, 9, 29, 23, 59))["count"]["value"], 1)
        self.assertEqual(quotation_expiry(data, {}, REFERENCE, now=datetime(2026, 9, 30))["count"]["value"], 0)


if __name__ == "__main__":
    unittest.main()
