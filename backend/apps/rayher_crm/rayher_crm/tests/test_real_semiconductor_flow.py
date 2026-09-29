from __future__ import annotations

from io import BytesIO

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfWriter

from rayher_crm.services.accounts import create_account, get_account_360
from rayher_crm.services.bookings import get_booking, list_bookings
from rayher_crm.services.contact_files import list_contact_files, upload_contact_files
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.controlled_documents import render_controlled_document
from rayher_crm.services.dashboard import get_dashboard
from rayher_crm.services.demo_reports import release_demo_test_report
from rayher_crm.services.demo_requests import create_demo_request, transition_demo_request
from rayher_crm.services.document_access import create_request, decide_request, version_id
from rayher_crm.services.evaluations import (
    add_evaluation_run,
    get_demo_workflow,
    get_evaluation,
    update_evaluation_status,
)
from rayher_crm.services.installed_tools import (
    add_installed_tool_service_record,
    add_installed_tool_version_record,
    convert_booking_to_installed_tool,
    list_installed_tools,
    transition_installed_tool,
)
from rayher_crm.services.leads import create_lead, convert_lead
from rayher_crm.services.opportunities import (
    confirm_budget_approved,
    confirm_po,
    get_strategy_opportunity,
    update_strategy_opportunity,
)
from rayher_crm.services.opportunity_stages import (
    CUSTOMER_BUDGET_APPROVED,
    DEMO_DONE,
    PO_RECEIVED,
    QUALIFIED_OPPORTUNITY,
    QUOTATION_SENT,
    RFQ_VALIDATED,
)
from rayher_crm.services.quotations import create_quotation, record_decision, review_approval, submit_for_approval
from rayher_crm.services.rfqs import create_rfq, review_rfq, submit_engineer_comment
from rayher_crm.services.sites import create_site
from rayher_crm.services.visits import create_visit, list_visits, update_visit
from rayher_crm.setup.controlled_documents import ACONCA_DOCUMENT_ID
from rayher_crm.tests._controlled_document_fixtures import install_test_controlled_documents


class CleanScanner:
    def scan(self, content: bytes) -> bool:
        return True


def rfq_pdf_part() -> dict:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    return {"file_name": "cis-inspector-rfq.pdf", "mime_type": "application/pdf", "content": output.getvalue()}


class TestRealSemiconductorFlow(FrappeTestCase):
    """One non-Stage, non-Mock vertical slice using real semiconductor semantics."""

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        install_test_controlled_documents()
        self.files_before = set(frappe.get_all("File", pluck="name"))
        self.run_id = f"cis-{frappe.generate_hash(length=10)}"
        self.sales = self._user(f"sales-{self.run_id}@example.invalid", "CRM Sales", "设备采购客户经理")
        self.engineer = self._user(f"engineer-{self.run_id}@example.invalid", "CRM Engineer", "良率应用工程师")
        self.manager = self._user(f"manager-{self.run_id}@example.invalid", "CRM Manager", "业务审批经理")

    def tearDown(self):
        frappe.set_user("Administrator")
        new_files = set(frappe.get_all("File", pluck="name")) - self.files_before
        for file_name in new_files:
            if frappe.db.exists("File", file_name):
                frappe.delete_doc("File", file_name, ignore_permissions=True, force=True)
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, email: str, role: str, name: str) -> str:
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": name,
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _contact(self, account_id: str, site_id: str, name: str, title: str, department: str, index: int):
        return create_contact({
            "accountId": account_id, "siteId": site_id, "name": name,
            "title": title, "department": department, "phone": f"13900000{index:03d}",
            "email": f"contact-{index}-{self.run_id}@example.invalid",
            "relationship": "Strong" if index == 1 else "Developing",
            "status": "Active", "owner": self.sales,
        })

    def test_hanxin_cis_opportunity_to_warranty_and_controlled_knowledge(self):
        frappe.set_user(self.sales)
        account = create_account({
            "name": "示例企业035有限公司", "shortName": f"瀚芯-{self.run_id}",
            "segment": "Frontend", "tier": "S", "city": "苏州", "region": "华东",
            "owner": self.sales,
        })
        site = create_site(account["id"], {
            "name": "苏州 12 英寸特色工艺厂", "city": "苏州", "type": "Fab",
            "process": "300mm CIS", "status": "量产",
        })
        procurement = self._contact(account["id"], site["id"], "陈玮", "设备采购负责人", "采购部", 1)
        self._contact(account["id"], site["id"], "顾敏", "良率工程经理", "良率工程部", 2)
        self._contact(account["id"], site["id"], "陆行", "工艺整合工程师", "工艺整合部", 3)

        lead = create_lead({
            "name": "陈玮", "company": "示例企业035有限公司", "title": "设备采购负责人",
            "phone": "13800000005", "email": f"lead-{self.run_id}@example.invalid",
            "source": "Customer Referral", "status": "Qualified", "owner": self.sales,
            "interest": f"300mm CIS 晶圆缺陷检测需求 | runId={self.run_id} | dataOrigin=test-acceptance",
            "firstContactNote": "客户需要验证表面颗粒、划伤与 Pattern 缺陷分类",
            "nextAction": "安排现场需求澄清", "nextActionDue": "2026-08-01", "activities": [],
        })
        converted = convert_lead(lead["id"], {
            "accountId": account["id"], "contactId": procurement["id"], "siteId": site["id"],
            "opportunityTitle": "CIS 缺陷检测设备项目", "opportunityAmount": "4860000.00", "opportunityAmountCny": "4860000.00",
            "opportunityCloseDate": "2026-12-31", "opportunityOwner": self.sales,
            "toolType": "CIS Wafer Defect Inspection", "qualificationConfirmed": True,
            "opportunityProbabilityLevel": "pipeline",
        })
        opportunity_id = converted["opportunityId"]
        opportunity = get_strategy_opportunity(opportunity_id)
        self.assertEqual((opportunity["stage"], opportunity["amount"]), (QUALIFIED_OPPORTUNITY, "4860000.00"))

        visit = create_visit({
            "accountId": account["id"], "primaryContactId": procurement["id"],
            "opportunityId": opportunity_id, "subject": "现场需求澄清",
            "date": "2026-08-01", "type": "On-site", "owner": self.sales,
            "objective": "确认 300mm CIS 缺陷类型、验收指标和样片计划",
        })
        visit = update_visit(visit["id"], {
            "type": "advance", "status": "Visited", "outcome": "确认 12 片 CIS 测试晶圆及验收标准",
        }, visit["modified"])
        frappe.get_doc({
            "doctype": "CRM Visit Meeting Record", "visit": visit["id"],
            "purpose": "确认 CIS Demo 验收范围", "attendees": "客户采购负责人\n客户良率工程师\n销售负责人",
            "agenda": "确认样片、缺陷类型与验收指标", "summary": "客户确认 12 片测试晶圆和验收标准",
            "conclusion": "进入 Demo 测试方案准备", "followup": "提交 Demo 测试方案",
            "parse_status": "Parsed", "parse_message": "Acceptance flow record", "manually_corrected": 1,
        }).insert(ignore_permissions=True)
        visit = update_visit(visit["id"], {
            "type": "advance", "status": "Minutes Submitted", "nextAction": "准备 Demo 测试方案",
            "actionOwner": self.sales, "due": "2026-08-03",
        }, visit["modified"])
        visit = update_visit(visit["id"], {"type": "complete_action"}, visit["modified"])
        frappe.set_user(self.manager)
        visit = update_visit(visit["id"], {"type": "advance", "status": "Manager Reviewed"}, visit["modified"])
        self.assertEqual(visit["status"], "Manager Reviewed")

        frappe.set_user(self.sales)
        uploaded = upload_contact_files(procurement["id"], [{
            "file_name": "瀚芯-CIS-采购技术需求.txt", "mime_type": "text/plain",
            "content": b"300mm CIS wafer defect inspection requirement",
        }], scanner=CleanScanner())
        self.assertEqual(list_contact_files(procurement["id"])[0]["id"], uploaded[0]["id"])

        request = create_demo_request({
            "accountId": account["id"], "primaryContactId": procurement["id"],
            "opportunityId": opportunity_id, "requirementId": f"REQ-{self.run_id}",
            "customerExpectedDate": "2026-08-10", "submit": True,
            "formData": {
                "contactPerson": "server derives this", "industry": "300mm CIS Fab",
                "salesContact": self.sales, "demoOwner": self.engineer,
                "sizeShape": "300 mm", "material": "CIS Si(100)",
                "specificRequest": "12 片 CIS 晶圆表面颗粒、划伤与 Pattern 缺陷分类",
                "detectMeasure": "Capture / False Positive / WPH", "expectedResults": "Wafer map + defect review",
                "otherTools": "Customer reference AOI", "primaryTool": "CIS Defect Inspector X8",
                "complementaryTool": "Review SEM", "timing": "2026-08-10",
                "keySuccessFactors": "Capture ≥ 95%; False Positive ≤ 2%; WPH ≥ 18",
                "internalQuestions": "确认 recipe 与 edge exclusion", "customerQuestions": "确认 Golden Sample",
                "wafers": [{
                    "slotId": str(index), "wid": f"CIS-{self.run_id}-W{index:02d}",
                    "waferSpecificity": "300mm CIS test wafer", "notchFlat": "Notch up",
                    "doiMetrologyItems": "Particle/Scratch/Pattern", "resultFileProvided": "Wafer map",
                } for index in range(1, 13)],
            },
        })
        # Requesting and approving the Demo does not move the Opportunity.
        self.assertEqual(get_strategy_opportunity(opportunity_id)["stage"], QUALIFIED_OPPORTUNITY)

        frappe.set_user(self.engineer)
        engineering = transition_demo_request(request["id"], {
            "type": "engineer_approve", "engineerOwner": self.engineer,
            "testPlan": "12-wafer CIS recipe and Golden Sample comparison",
            "assignedEquipment": "CIS Defect Inspector X8", "resourceWindow": "2026-08-04 ~ 2026-08-10",
            "estimatedCompletionDate": "2026-08-10", "technicalRisk": "Golden Sample alignment",
            "comment": "技术方案与资源已确认",
        }, request["modified"])
        frappe.set_user(self.manager)
        approved = transition_demo_request(request["id"], {
            "type": "manager_approve", "comment": "批准进入 Demo Test",
        }, engineering["request"]["modified"])
        evaluation = approved["evaluation"]
        self.assertEqual(get_strategy_opportunity(opportunity_id)["stage"], QUALIFIED_OPPORTUNITY)

        frappe.set_user(self.engineer)
        for status in ("Scope Confirmed", "Sample Received", "Scheduled", "Testing"):
            evaluation = update_evaluation_status(evaluation["id"], {"status": status}, evaluation["modified"])
        report = release_demo_test_report(
            evaluation["id"],
            {"file_name": "瀚芯-CIS-Demo-Test-Report.txt", "mime_type": "text/plain", "content": b"Capture=96.8%; False Positive=1.1%; WPH=18.5; Result=Accepted"},
            {"file_name": "瀚芯-CIS-Customer-Test-Report.txt", "mime_type": "text/plain", "content": b"Capture=96.8%; False Positive=1.1%; WPH=18.5; Result=Accepted"},
            scanner=CleanScanner(),
            expected_round=1,
        )
        evaluation = get_evaluation(evaluation["id"])
        evaluation = add_evaluation_run(evaluation["id"], {
            "date": "2026-08-10", "lot": f"CIS-{self.run_id}", "wafers": 12,
            "capture": 96.8, "falsePositive": 1.1, "wph": 18.5,
            "summary": "12 片 CIS 晶圆达到客户验收指标",
            "expectedModified": evaluation["modified"],
        })
        for status in ("Internal Review", "Customer Review", "Accepted"):
            command = {"status": status}
            if status == "Accepted":
                command["customerComment"] = "客户确认 12 片 CIS 晶圆达到验收指标"
            evaluation = update_evaluation_status(evaluation["id"], command, evaluation["modified"])
        frappe.set_user(self.sales)
        # Entering Customer Review marked the demo as done; the acceptance itself moves nothing.
        self.assertEqual(get_strategy_opportunity(opportunity_id)["stage"], DEMO_DONE)
        workflow = get_demo_workflow(request["id"])
        self.assertEqual((workflow["evaluation"]["status"], workflow["testRuns"][0]["capture"]), ("Accepted", 96.8))
        report_ids = {item["id"] for item in workflow["artifacts"] if item["type"] == "Test Report"}
        self.assertEqual(report_ids, {
            report["internalReportArtifact"]["id"], report["externalReportArtifact"]["id"],
        })

        frappe.set_user(self.sales)
        opportunity = get_strategy_opportunity(opportunity_id)
        opportunity = update_strategy_opportunity(
            opportunity_id, {"probabilityLevel": "upside"}, opportunity["modified"],
        )
        opportunity = confirm_budget_approved(opportunity_id, {"approvedOn": "2026-08-11"}, opportunity["modified"])
        self.assertEqual(
            (opportunity["stage"], opportunity["budgetApprovedOn"]), (CUSTOMER_BUDGET_APPROVED, "2026-08-11"),
        )
        rfq = create_rfq(
            {"opportunityId": opportunity_id, "engineerId": self.engineer},
            rfq_pdf_part(), CleanScanner(),
        )
        frappe.set_user(self.engineer)
        rfq = submit_engineer_comment(
            rfq["id"], "设备规格满足 CIS 缺陷检测要求。", rfq["modified"],
        )
        frappe.set_user(self.manager)
        review_rfq(rfq["id"], "Approved", "技术规格确认通过。", rfq["modified"])
        frappe.set_user(self.sales)
        self.assertEqual(get_strategy_opportunity(opportunity_id)["stage"], RFQ_VALIDATED)
        quotation = create_quotation({
            "quotationType": "Device", "opportunityId": opportunity_id,
            "primaryContactId": procurement["id"],
            "addressId": site["id"], "quoteDate": "2026-08-10",
            "paymentTerms": [
                {"percentage": "30"}, {"percentage": "30"},
                {"percentage": "30"}, {"percentage": "10"},
            ],
            "items": [{
                "lineKey": "cis-inspector-x8", "lineType": "Device", "name": "CIS Defect Inspector X8",
                "quantity": 1, "unitPrice": "4860000.00",
            }],
        })
        quotation = submit_for_approval(quotation["quotation"]["id"], quotation["version"]["modified"])
        self.assertEqual(quotation["version"]["approvalStatus"], "Pending")
        frappe.set_user(self.manager)
        quotation = review_approval(
            quotation["quotation"]["id"], "Approved", "商务条款和价格审批通过",
            quotation["version"]["modified"],
        )
        frappe.set_user(self.sales)
        quotation = record_decision(
            quotation["quotation"]["id"], "Accepted", "2026-08-11",
            "客户确认技术指标、交期及商务条款", quotation["version"]["modified"],
        )
        self.assertEqual(quotation["version"]["status"], "Accepted")
        opportunity = get_strategy_opportunity(opportunity_id)
        self.assertEqual(opportunity["stage"], QUOTATION_SENT)
        opportunity = confirm_po(opportunity_id, {"booking": {
            "primaryContactId": procurement["id"],
            "equipment": "CIS Defect Inspector X8", "quantity": 1, "ddl": "2026-12-20",
            "amount": "4860000.00", "currency": "CNY",
            "owner": self.sales, "note": f"runId={self.run_id}; dataOrigin=test-acceptance",
        }, "actualPoDate": frappe.utils.today()}, opportunity["modified"])
        self.assertEqual(opportunity["stage"], PO_RECEIVED)

        booking = get_booking(opportunity["liveBooking"]["id"])
        self.assertEqual((booking["status"], booking["sourceOpportunityId"]), ("Confirmed", opportunity_id))
        converted_tool = convert_booking_to_installed_tool(booking["id"], {
            "siteId": site["id"], "engineerOwner": self.engineer,
            "serial": f"HX-CIS-X8-{self.run_id}", "model": "CIS Defect Inspector X8",
            "location": "CIS Fab / Bay 12", "salesOrder": f"SO-{self.run_id}",
            "contract": f"CT-{self.run_id}", "software": "CIS-Recipe 1.0",
            "firmware": "FW 3.2", "configuration": "300mm CIS / Front+Back Surface",
        }, booking["modified"])
        tool = converted_tool["installedTool"]
        frappe.set_user(self.engineer)
        for index, stage in enumerate(("FAT", "Shipment", "Installation", "SAT", "Warranty"), start=8):
            self.assertEqual(tool["lifecycleStage"], stage)
            tool = transition_installed_tool(tool["id"], {
                "completedAt": f"2026-08-{index:02d}", "result": f"{stage} passed",
                "openIssues": "None", "customerSignoff": "瀚芯项目组确认",
                "comment": f"{stage} acceptance completed", "evidence": [f"{stage.lower()}-{self.run_id}.pdf"],
            }, tool["modified"])
        self.assertTrue(tool["lifecycleCompleted"])
        tool = add_installed_tool_version_record(tool["id"], {
            "changeDate": "2026-08-13", "changeType": "Software", "toValue": "CIS-Recipe 1.1",
            "reason": "Golden Sample recipe tuning", "comment": "客户确认升级",
        }, tool["modified"])
        tool = add_installed_tool_service_record(tool["id"], {
            "serviceDate": "2026-08-14", "serviceType": "Warranty Activation",
            "result": "Warranty activated", "openIssues": "None", "nextAction": "首月健康检查",
            "actionOwner": self.engineer, "due": "2026-09-14", "comment": "设备进入质保服务",
            "warrantyStart": "2026-08-14", "warrantyEnd": "2027-08-13",
            "serviceContract": f"SC-{self.run_id}", "pmCycle": "6 months",
        }, tool["modified"])
        self.assertEqual((tool["lastService"], tool["software"]), ("2026-08-14", "CIS-Recipe 1.1"))

        frappe.set_user(self.sales)
        document = frappe.get_doc("CRM Controlled Document", ACONCA_DOCUMENT_ID)
        access = create_request(version_id(document), f"瀚芯 CIS 技术评审 | {self.run_id}")
        frappe.set_user(self.manager)
        access = decide_request(access["id"], "approve-watermarked")
        frappe.set_user(self.sales)
        controlled = render_controlled_document(ACONCA_DOCUMENT_ID, "download")
        self.assertEqual((access["status"], controlled["mime_type"]), ("Approved", "application/pdf"))

        account_360 = get_account_360(account["id"])
        self.assertIn(opportunity_id, {item["id"] for item in account_360["opportunities"]})
        self.assertIn(tool["id"], {item["id"] for item in list_installed_tools({"accountId": account["id"]})[0]})
        self.assertIn(visit["id"], {item["id"] for item in list_visits({"accountId": account["id"]})[0]})
        self.assertIn(booking["id"], {item["id"] for item in list_bookings({"accountId": account["id"]})[0]})
        frappe.set_user(self.manager)
        dashboard = get_dashboard({"range": "quarter"})
        self.assertIn("CNY", {item["currency"] for item in dashboard["kpis"]["moneyByCurrency"]})
        self.assertGreater(frappe.db.count("CRM Notification Event", {"source_name": ["in", [request["id"], evaluation["id"], visit["id"]]]}), 0)
