from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def functions(path: Path) -> set[str]:
    return {node.name for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


class TestQuotationBackendContract(unittest.TestCase):
    def test_service_exposes_complete_lifecycle(self):
        names = functions(ROOT / "services" / "quotations.py")
        self.assertTrue({
            "list_quotations", "list_catalog", "get_quotation", "create_quotation", "link_quotation_opportunity", "save_draft",
            "create_version", "discard_draft", "submit_for_approval", "review_approval", "publish_version", "record_decision",
            "expire_quotations", "get_pdf_file",
        }.issubset(names))

    def test_api_exposes_list_detail_draft_version_publish_decision_and_pdf(self):
        names = functions(ROOT / "api" / "v1" / "quotations.py")
        self.assertTrue({
            "list_quotations", "list_catalog", "get_quotation", "create_quotation", "link_opportunity", "save_draft",
            "create_version", "discard_draft", "submit_for_approval", "review_approval", "publish_version", "record_decision", "download_pdf",
        }.issubset(names))

    def test_catalog_is_registered_only_when_draft_leaves_editable_state(self):
        source = (ROOT / "services" / "quotations.py").read_text(encoding="utf-8")
        save_source = source.split("def save_draft", 1)[1].split("def create_version", 1)[0]
        submit_source = source.split("def submit_for_approval", 1)[1].split("def _lock_approval", 1)[0]
        publish_source = source.split("def _publish_locked", 1)[1].split("def _manager_users", 1)[0]
        self.assertNotIn("_register_version_catalog", save_source)
        self.assertIn("_register_version_catalog(version)", submit_source)
        self.assertIn("_register_version_catalog(version)", publish_source)
        self.assertIn("seed_quotation_catalog", functions(ROOT / "services" / "quotations.py"))
    def test_opportunity_title_uses_real_doctype_field(self):
        source = (ROOT / "services" / "quotations.py").read_text(encoding="utf-8")
        self.assertNotIn('"opportunity_title"', source)
        self.assertGreaterEqual(source.count('"CRM Opportunity", master.opportunity, "title"'), 2)

    def test_list_supports_exact_opportunity_filter_without_keyword_search(self):
        source = (ROOT / "services" / "quotations.py").read_text(encoding="utf-8")
        self.assertIn('opportunity_id = _text(query, "opportunityId")', source)
        self.assertNotIn('_text(query, "search")', source)
        list_source = source.split("def list_quotations", 1)[1].split("def get_quotation", 1)[0]
        self.assertNotIn("LIKE %s", list_source)

    def test_item_names_remain_required_by_the_database_schema(self):
        source = (ROOT / "services" / "quotations.py").read_text(encoding="utf-8")
        self.assertIn("def _item_rows(payload_items: Any)", source)
        self.assertIn('required_text(item, "name")', source)

    def test_versions_use_the_shared_optimistic_lock_contract(self):
        service = (ROOT / "services" / "quotations.py").read_text(encoding="utf-8")
        concurrency = (ROOT / "services" / "concurrency.py").read_text(encoding="utf-8")
        self.assertIn('"CRM Quotation Version"', concurrency)
        self.assertEqual(service.count('lock_document("CRM Quotation Version", master.current_version, expected_modified, "NOT_FOUND")'), 5)

    def test_database_money_is_normalized_before_public_serialization(self):
        source = (ROOT / "services" / "quotations.py").read_text(encoding="utf-8")
        self.assertIn("def _db_decimal(value: Any)", source)
        for field in ("row.unit_price", "row.line_amount", "doc.subtotal", "doc.discount_value", "doc.discount_amount", "doc.total", "row.percentage"):
            self.assertIn(f"_db_decimal({field})", source)

    def test_ref_number_is_generated_from_initial_quote_date(self):
        source = (ROOT / "services" / "quotations.py").read_text(encoding="utf-8")
        self.assertIn("def _next_ref_no(quote_date: str)", source)
        self.assertIn('f"PK{date_key}-A', source)
        self.assertNotIn('required_text(payload, "refNo")', source)

    def test_unexpected_api_errors_roll_back_partial_writes(self):
        source = (ROOT / "api" / "v1" / "errors.py").read_text(encoding="utf-8")
        generic_handler = source.split("        except Exception as failure:", 1)[1]
        # The rollback comes first: before the failure is looked at, logged or answered.
        self.assertTrue(generic_handler.lstrip().startswith("frappe.db.rollback()"))

    def test_new_formal_version_supersedes_every_previous_formal_outcome(self):
        source = (ROOT / "services" / "quotations.py").read_text(encoding="utf-8")
        self.assertIn('{"Published", "Expired", "Accepted", "Rejected"}', source)

    def test_pdf_template_contains_repeating_header_and_word_sections(self):
        template = (ROOT / "templates" / "quotation" / "quotation.html").read_text(encoding="utf-8")
        for token in (
            "page-header", "Ref. No.:", "ATTN", "items", "deviceGroups",
            "Payment Terms:", "FOB上海", "Installation &amp; Training",
            "栖衡科技（演示）",
        ):
            self.assertIn(token, template)
        self.assertIn("position: absolute; right: 0;", template)
        self.assertIn(".page-header { position: relative; width: 176mm !important;", template)
        self.assertIn("text-align: right !important;", template)
        self.assertNotIn("margin-top:-15mm", template)



    def test_pdf_template_matches_retained_word_contract(self):
        template = (ROOT / "templates" / "quotation" / "quotation.html").read_text(encoding="utf-8")
        for token in (
            "quotation-qiheng-logo.png", "Ref. No.: {{ refNo | e }}", "Items", "Description",
            "QTY", "Unit price", "单台配置价（含税）（RMB）", "总价（折扣后）（RMB）",
        ):
            self.assertIn(token, template)
        self.assertIn("position: absolute; right: 0;", template)
        self.assertIn(".page-header { position: relative; width: 176mm !important;", template)
        self.assertIn("text-align: right !important;", template)
        self.assertNotIn("Amount（RMB）", template)
        self.assertIn("报价小计", template)
        self.assertIn("整单折扣", template)

    def test_pdf_renderer_stamps_the_template_header_on_every_page(self):
        service = (ROOT / "services" / "quotations.py").read_text(encoding="utf-8")
        self.assertIn('header = soup.find(id="header-html")', service)
        self.assertIn("header.extract()", service)
        self.assertIn("page.merge_page(header_page, over=True)", service)
    def test_preview_and_publish_share_one_pdf_renderer(self):
        service = (ROOT / "services" / "quotations.py").read_text(encoding="utf-8")
        api = (ROOT / "api" / "v1" / "quotations.py").read_text(encoding="utf-8")
        names = functions(ROOT / "services" / "quotations.py")
        self.assertIn("render_quotation_pdf", names)
        self.assertIn("get_preview_pdf", names)
        self.assertGreaterEqual(service.count("render_quotation_pdf(master, version)"), 2)
        self.assertIn("def preview_pdf", api)
        self.assertIn('"margin-top": "35mm"', service)
if __name__ == "__main__":
    unittest.main()
