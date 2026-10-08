"""Wipe a staging site's CRM business data and seed a realistic dataset for the Sales Cockpit.

Both entry points refuse to run unless ``confirm`` is the site name and the site is one of
``ALLOWED_SITES``; nothing here may touch operational data.

- ``wipe(confirm)`` removes every CRM business row (customers, sites, contacts, leads,
  opportunities with all their history, bookings, visits, demo work, quotations, RFQs,
  installed tools, targets, notifications) and the uploaded files, and resets the region options
  to the five presets and the business areas to their defaults, since nothing uses the ones Sales
  added any more. Users, roles, custom fields, the quotation catalog and site config stay.
- ``seed(confirm)`` writes about two years of activity for the CRM staff on the site through
  the app's own service layer, with the clock backdated so history, stage dates and
  actual PO dates fall where a real team would have produced them. A few read-side records
  (demo requests, evaluations, test runs, RFQs, quotations) are inserted directly because
  their services need uploaded reports and rendered PDFs.
- ``counts()`` prints how many rows each business table holds.

Run inside the site::

    bench --site <site> execute rayher_crm.setup.staging_dataset.counts
    bench --site <site> execute rayher_crm.setup.staging_dataset.wipe --kwargs '{"confirm": "<site>"}'
    bench --site <site> execute rayher_crm.setup.staging_dataset.seed --kwargs '{"confirm": "<site>"}'
"""

from __future__ import annotations

import json
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable

import frappe

from rayher_crm.services import (  # noqa: F401  (imported so the clock can patch their time helpers)
    accounts, bookings, cockpit, contacts, demo_reports, installed_tools, leads, notifications,
    opportunities, opportunity_bookings, quotations, rfqs, sites, visit_meetings, visits,
)
from rayher_crm.services.common import to_iso_timestamp
from rayher_crm.services.regions import REGION_FIELD, REGION_PRESETS, options_text
from rayher_crm.setup.custom_fields import ACCOUNT_SEGMENT_FIELD, CRM_CUSTOM_FIELDS


ALLOWED_SITES = {"rayher-crm.test", "203.0.113.58"}

# Deleted with raw SQL, dependents first. Child tables and immutable history rows included.
WIPE_ORDER = (
    "CRM Query Recipient", "CRM Plan Commitment",
    "CRM Demo Resource Impact", "CRM Demo Unavailability", "CRM Demo Resource",
    "CRM Quotation Item", "CRM Quotation Payment Term",
    "CRM Notification Event", "CRM File Access Audit",
    "CRM Warning Handling Revision", "CRM Warning Handling",
    "CRM Probability Recovery Revision", "CRM Probability Recovery",
    # Loss reviews link to their marked_lost stage-history row, so they go first.
    "CRM Opportunity Loss Review Revision", "CRM Opportunity Loss Review",
    "CRM Opportunity History", "CRM Opportunity Stage History", "CRM Opportunity Probability History",
    "CRM Opportunity Action", "CRM Opportunity Stakeholder", "CRM Opportunity Internal Validation",
    "CRM Demo Request History", "CRM Evaluation History", "CRM Evaluation Customer Review", "CRM Demo Comment",
    "CRM Test Run", "CRM Installed Tool Lifecycle History", "CRM Installed Tool Version History",
    "CRM Installed Tool Service History", "CRM Visit Meeting Record",
    "CRM Quotation Approval", "CRM Quotation Version", "CRM Quotation", "CRM RFQ Version", "CRM RFQ",
    "CRM Demo Artifact", "CRM Contact File", "CRM Document Access Request", "CRM Document Upload Request",
    "CRM Controlled Document",
    "CRM Demo Request", "CRM Evaluation",
    "CRM Status Attachment", "CRM Opportunity Status",
    "CRM Visit", "CRM Installed Tool", "CRM Booking", "CRM Opportunity",
    "CRM Cockpit Target", "CRM Opportunity Saved Query", "CRM Equipment Type", "CRM Account Engineer Assignment",
    "Contact", "Address", "Customer", "Lead",
)
FILE_OWNERS = (
    "CRM Contact File", "CRM Demo Artifact", "CRM Controlled Document", "CRM Document Upload Request",
    "CRM Quotation Version", "CRM RFQ Version", "CRM Visit", "CRM RFQ", "CRM Evaluation", "CRM Demo Request",
    "CRM Status Attachment",
    "Contact", "Customer", "Address", "Lead",
)


def _guard(confirm: Any) -> str:
    site = str(frappe.local.site or "")
    if site not in ALLOWED_SITES or confirm != site:
        raise RuntimeError(f"Refusing: pass confirm='{site}' and run only on {sorted(ALLOWED_SITES)}.")
    return site


def counts() -> dict[str, int]:
    result = {doctype: frappe.db.count(doctype) for doctype in WIPE_ORDER}
    result["File (CRM)"] = frappe.db.count("File", {"attached_to_doctype": ["in", list(FILE_OWNERS)]})
    print(json.dumps({k: v for k, v in result.items() if v}, ensure_ascii=False, indent=2))
    return result


# ----------------------------------------------------------------------------------------- wipe


def wipe(confirm: str = "") -> dict[str, Any]:
    _guard(confirm)
    before = {doctype: frappe.db.count(doctype) for doctype in WIPE_ORDER}
    files = frappe.get_all("File", filters={"attached_to_doctype": ["in", list(FILE_OWNERS)]}, pluck="name")
    for name in files:
        frappe.delete_doc("File", name, ignore_permissions=True, force=True, delete_permanently=True)
    for doctype in WIPE_ORDER:
        frappe.db.delete(doctype)
    frappe.db.delete("Dynamic Link", {"parenttype": ["in", ["Address", "Contact"]]})
    frappe.db.delete("Version", {"ref_doctype": ["in", list(WIPE_ORDER)]})
    frappe.db.delete("Comment", {"reference_doctype": ["in", list(WIPE_ORDER)]})
    # With no Customer or Opportunity left, no custom region or business area is in use.
    frappe.db.set_value("Custom Field", REGION_FIELD, "options", options_text(list(REGION_PRESETS)), update_modified=False)
    segments = next(field["options"] for field in CRM_CUSTOM_FIELDS["Customer"] if field["fieldname"] == "custom_crm_segment")
    frappe.db.set_value("Custom Field", ACCOUNT_SEGMENT_FIELD, "options", segments, update_modified=False)
    frappe.clear_cache(doctype="Customer")
    orphans = _sweep_private_files()
    frappe.db.commit()
    after = {doctype: frappe.db.count(doctype) for doctype in WIPE_ORDER}
    summary = {
        "deleted": {k: v for k, v in before.items() if v},
        "files": len(files),
        "orphanFilesRemoved": orphans,
        "leftover": {k: v for k, v in after.items() if v},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def _sweep_private_files() -> int:
    """Remove regular files under private/files that no File row references any more."""

    root = Path(frappe.get_site_path("private", "files")).resolve()
    if not root.is_dir():
        return 0
    referenced = {str(url).rsplit("/", 1)[-1] for url in frappe.get_all("File", pluck="file_url") if url}
    removed = 0
    for candidate in root.iterdir():
        if candidate.is_symlink() or not candidate.is_file() or candidate.name in referenced:
            continue
        if candidate.resolve().parent != root:
            continue
        candidate.unlink()
        removed += 1
    return removed


# ----------------------------------------------------------------------------------------- clock


class Clock:
    """Backdates every time helper the services and Frappe's document layer use."""

    PREFIXES = ("frappe.utils", "frappe.model", "frappe.database", "rayher_crm.")

    def __init__(self) -> None:
        self.current = datetime.now()
        self.patched: list[tuple[Any, str, Any]] = []

    def install(self) -> None:
        originals = {
            "now_datetime": frappe.utils.now_datetime, "today": frappe.utils.today,
            "nowdate": frappe.utils.nowdate, "now": frappe.utils.now,
        }
        replacements = {
            "now_datetime": lambda: self.current,
            "today": lambda: self.current.strftime("%Y-%m-%d"),
            "nowdate": lambda: self.current.strftime("%Y-%m-%d"),
            "now": lambda: self.current.strftime("%Y-%m-%d %H:%M:%S.%f"),
        }
        for name, module in list(sys.modules.items()):
            if module is None or not name.startswith(self.PREFIXES):
                continue
            for attr, original in originals.items():
                if getattr(module, attr, None) is original:
                    setattr(module, attr, replacements[attr])
                    self.patched.append((module, attr, original))

    def restore(self) -> None:
        for module, attr, original in self.patched:
            setattr(module, attr, original)
        self.patched = []


# ----------------------------------------------------------------------------------------- staff


STAFF = {
    "sales": [("person063@staff.example.invalid", "演示员工155"), ("person064@staff.example.invalid", "演示员工201")],
    "managers": [("person060@staff.example.invalid", "演示员工29"), ("person046@staff.example.invalid", "演示员工21")],
    "engineers": [("person027@staff.example.invalid", "演示员工224"), ("person057@staff.example.invalid", "演示员工158")],
}
ROLE_BY_GROUP = {"sales": "CRM Sales", "managers": "CRM Manager", "engineers": "CRM Engineer"}


def _ensure_users() -> None:
    for group, people in STAFF.items():
        for email, full_name in people:
            if frappe.db.exists("User", email):
                continue
            frappe.get_doc({
                "doctype": "User", "email": email, "first_name": full_name, "enabled": 1,
                "send_welcome_email": 0, "roles": [{"role": ROLE_BY_GROUP[group]}],
            }).insert(ignore_permissions=True)


# ----------------------------------------------------------------------------------------- data


CUSTOMERS = [
    # name, short, segment, tier, city, region, site process, mail domain
    ("示例企业012有限公司", "华芯微", "Frontend", "S", "无锡", "East China", "28nm Logic", "huaxin"),
    ("示例企业034有限公司", "瀚海集成", "Frontend", "S", "上海", "East China", "14nm FinFET", "hanhai"),
    ("示例企业023有限公司", "晶元封装", "Advanced Packaging", "A", "苏州", "East China", "2.5D / CoWoS", "jingyuan"),
    ("示例企业042有限公司", "鑫辰存储", "Memory", "S", "合肥", "Central China", "DRAM 1x", "xinchen"),
    ("示例企业043有限公司", "示例企业044光电", "Frontend", "A", "武汉", "Central China", "3D NAND", "cjguangdian"),
    ("示例企业013有限公司", "南方硅谷", "Power", "A", "深圳", "South China", "SiC MOSFET", "southsv"),
    ("示例企业007有限公司", "示例企业007", "Advanced Packaging", "B", "厦门", "South China", "Fan-out WLP", "donghai"),
    ("示例企业020有限公司", "星晨功率", "Power", "B", "西安", "West China", "IGBT", "xingchen"),
    ("示例企业017有限公司", "天工微", "Frontend", "A", "成都", "West China", "55nm BCD", "tiangong"),
    ("示例企业011有限公司", "北极光", "Frontend", "B", "北京", "North China", "40nm Logic", "beijiguang"),
    ("示例企业036有限公司", "示例企业036", "Frontend", "B", "杭州", "East China", "CIS 65nm", "ruixin"),
    ("示例企业008有限公司", "中原微纳", "Advanced Packaging", "B", "郑州", "Central China", "SiP", "zhongyuan"),
    ("示例企业029有限公司", "润和晶圆", "Frontend", "A", "南京", "East China", "22nm ULP", "runhe"),
    ("示例企业009有限公司", "凌云材料", "Frontend", "B", "宁波", "East China", "SOI 300mm", "lingyun"),
]
CONTACT_TITLES = [
    ("设备工程经理", "设备部"), ("工艺整合总监", "工艺部"), ("采购经理", "采购部"), ("厂长", "制造部"),
    ("良率提升负责人", "良率部"), ("量测工程师", "量测部"), ("技术副总", "管理层"), ("设备采购专员", "采购部"),
]
SURNAMES = "王李张刘陈杨黄赵周吴徐孙马朱胡郭何林罗高"
GIVEN = ["伟", "芳", "娜", "敏", "静", "磊", "军", "洋", "勇", "艳", "杰", "涛", "明", "超", "秀英", "华", "平", "刚", "桂英", "志强", "海燕", "文博", "思远", "嘉怡"]
TOOLS = [("Aconca", "Defect Inspection"), ("Nansi", "Macro Inspection"), ("Veymont", "CD Metrology"), ("Kibo 4895C", "Package Inspection"), ("Drakens", "Wafer Edge Inspection")]
SEGMENT_LEADS = ["先进封装检测", "前道缺陷检测", "功率器件外观检测", "存储晶圆量测", "CIS 晶圆缺陷检测"]
LOST_REASONS = [
    "客户预算延后到明年，本轮采购取消",
    "竞争对手报价低约 15%，客户选择价格优先",
    "客户产线扩产计划暂停",
    "技术指标未达到客户对最小缺陷尺寸的要求",
    "客户选择沿用现有供应商，减少切换成本",
    "客户内部立项未通过",
    "交期无法满足客户搬入窗口",
]
DOWNGRADE_REASONS = [
    "客户预算审批推迟到下季度",
    "竞争对手进入最终评估，客户态度转为观望",
    "客户技术负责人换人，需要重新验证",
    "客户要求追加降价，商务谈判陷入僵持",
]
ACTIONS = [
    "安排设备副总拜访", "提交最终报价与商务条款", "确认客户预算审批进度", "协调 Demo 样片物流",
    "发送测试报告并约定评审会", "确认 FAT 时间与验收标准", "跟进采购流程与合同条款", "补充竞争对手对比材料",
    "确认厂务接口与搬入条件", "与工艺团队复核 recipe 要求", "邀请客户参观演示中心", "更新交付计划并确认交期",
]
VISIT_SUBJECTS = ["需求澄清与现场勘查", "技术方案交流", "Demo 结果评审", "商务条款沟通", "季度业务回顾", "新机台选型交流", "装机前准备会议", "售后与升级需求沟通"]
VISIT_TYPES = ["On-site", "On-site", "On-site", "Video", "Phone"]
STAGES = ("qualified_opportunity", "demo_done", "customer_budget_approved", "rfq_validated", "quotation_sent", "internal_validation", "po_received")


class Seeder:
    def __init__(self) -> None:
        self.rng = random.Random(20260918)
        self.today = date.today()
        self.clock = Clock()
        self.sales = [email for email, _ in STAFF["sales"]]
        self.managers = [email for email, _ in STAFF["managers"]]
        self.engineers = [email for email, _ in STAFF["engineers"]]
        self.accounts: list[dict[str, Any]] = []
        self.log: dict[str, int] = {}
        self.used_names: set[str] = set()

    # -- helpers ------------------------------------------------------------------------

    def at(self, when: date | datetime, user: str, fn: Callable[[], Any]) -> Any:
        if isinstance(when, date) and not isinstance(when, datetime):
            when = datetime.combine(when, time(9, 30)) + timedelta(minutes=self.rng.randint(0, 8 * 60))
        # Frappe compares modified as text; a zero microsecond part would not round-trip through the DB.
        self.clock.current = when.replace(microsecond=self.rng.randint(1000, 998000))
        frappe.set_user(user)
        try:
            return fn()
        finally:
            frappe.set_user("Administrator")

    def count(self, key: str) -> None:
        self.log[key] = self.log.get(key, 0) + 1

    def modified_of(self, doctype: str, name: str) -> str:
        return to_iso_timestamp(frappe.db.get_value(doctype, name, "modified"))

    def person(self) -> str:
        for _ in range(100):
            name = self.rng.choice(SURNAMES) + self.rng.choice(GIVEN)
            if name not in self.used_names:
                self.used_names.add(name)
                return name
        return self.rng.choice(SURNAMES) + self.rng.choice(GIVEN) + str(len(self.used_names))

    def money(self, low: int, high: int) -> str:
        return f"{self.rng.randint(low // 10000, high // 10000) * 10000}.00"

    def days_ago(self, low: int, high: int) -> date:
        return self.today - timedelta(days=self.rng.randint(low, high))

    def insert(self, doctype: str, **fields: Any):
        return frappe.get_doc({"doctype": doctype, **fields}).insert(ignore_permissions=True)

    # -- customers ----------------------------------------------------------------------

    def seed_customers(self) -> None:
        for index, (name, short, segment, tier, city, region, process, domain) in enumerate(CUSTOMERS):
            owner = self.sales[index % 2] if index % 5 else self.sales[(index + 1) % 2]
            created = self.today - timedelta(days=self.rng.randint(280, 640))
            account = self.at(created, owner, lambda: accounts.create_account({
                "name": name, "shortName": short, "segment": segment, "tier": tier, "city": city,
                "region": region, "owner": owner,
            }))
            site_rows = []
            for site_index in range(1 if tier == "B" else 2):
                site = self.at(created + timedelta(days=site_index), owner, lambda: sites.create_site(account["id"], {
                    "name": f"{short}{'一' if site_index == 0 else '二'}厂", "city": city, "type": "Fab" if segment != "Advanced Packaging" else "OSAT",
                    "process": process if site_index == 0 else f"{process} (Phase 2)", "status": "量产" if site_index == 0 else "建设中",
                }))
                site_rows.append(site)
            contact_rows = []
            for contact_index in range(self.rng.randint(2, 4)):
                title, department = CONTACT_TITLES[(index + contact_index) % len(CONTACT_TITLES)]
                person = self.person()
                contact = self.at(created + timedelta(days=2 + contact_index), owner, lambda: contacts.create_contact({
                    "accountId": account["id"], "siteId": site_rows[0]["id"], "name": person, "title": title,
                    "department": department, "phone": f"13{self.rng.randint(100000000, 999999999)}",
                    "email": f"contact{index + 1}{chr(97 + contact_index)}@{domain}.example.cn",
                    "relationship": self.rng.choice(["Strong", "Developing", "Developing", "Weak"]), "status": "Active", "owner": owner,
                }))
                contact_rows.append(contact)
            self.accounts.append({
                "id": account["id"], "name": name, "short": short, "segment": segment, "region": region,
                "owner": owner, "sites": site_rows, "contacts": contact_rows, "created": created, "process": process, "domain": domain,
            })
            self.count("customers")

    # -- leads --------------------------------------------------------------------------

    def lead_payload(self, account: dict[str, Any], owner: str, index: int, status: str, created: date) -> dict[str, Any]:
        person = self.person()
        title, _ = CONTACT_TITLES[index % len(CONTACT_TITLES)]
        interest = SEGMENT_LEADS[index % len(SEGMENT_LEADS)]
        return {
            "name": person, "company": account["name"] if index % 3 else f"{account['short']}（{['嘉兴', '南通', '东莞', '珠海'][index % 4]}）新厂",
            "title": title, "phone": f"13{self.rng.randint(100000000, 999999999)}", "email": f"lead{index + 1}@{account['domain']}-new.example.cn",
            "source": self.rng.choice(["Trade Show", "Website", "Partner Referral", "Outbound", "Customer Referral"]),
            "status": status, "owner": owner, "interest": interest,
            "firstContactNote": f"{['SEMICON China 现场沟通', '官网留资后电话联系', '合作伙伴介绍', '主动拜访'][index % 4]}，关注{interest}。",
            "nextAction": "安排技术交流", "nextActionDue": (created + timedelta(days=10)).isoformat(),
        }

    def seed_leads(self, specs: list[dict[str, Any]]) -> None:
        to_convert = [spec for spec in specs if spec["convert"]]
        plans = (
            [("converted", len(to_convert)), ("Working", 7), ("Qualified", 5), ("Nurturing", 3), ("Disqualified", 4)]
        )
        index = 0
        for outcome, count in plans:
            for slot in range(count):
                spec = to_convert[slot] if outcome == "converted" else None
                account = spec["account"] if spec else self.accounts[index % len(self.accounts)]
                owner = account["owner"]
                # A converted Lead was worked for a few weeks before its deal was opened.
                created = spec["created"] - timedelta(days=self.rng.randint(12, 30)) if spec else self.days_ago(5, 420)
                payload = self.lead_payload(account, owner, index, "New", created)
                lead = self.at(created, owner, lambda: leads.create_lead(dict(payload)))
                if outcome == "Working" and self.rng.random() < 0.5:
                    index += 1
                    self.count("leads")
                    continue
                working = created + timedelta(days=self.rng.randint(2, 5))
                lead = self.at(working, owner, lambda: leads.update_lead(lead["id"], {**payload, "status": "Working"}, lead["modified"]))
                if outcome in ("Qualified", "converted"):
                    qualified = working + timedelta(days=self.rng.randint(2, 6))
                    lead = self.at(qualified, owner, lambda: leads.update_lead(lead["id"], {**payload, "status": "Qualified"}, lead["modified"]))
                    if spec:
                        spec["conversion"] = {"lead": lead, "when": spec["created"]}
                elif outcome in ("Nurturing", "Disqualified"):
                    later = working + timedelta(days=self.rng.randint(5, 30))
                    self.at(later, owner, lambda: leads.update_lead(lead["id"], {**payload, "status": outcome}, lead["modified"]))
                index += 1
                self.count("leads")

    # -- opportunities ------------------------------------------------------------------

    def opportunity_specs(self) -> list[dict[str, Any]]:
        """Each spec: how far the deal went and when. Dates are chosen backwards from today."""

        specs: list[dict[str, Any]] = []
        # final stage, how many, days-ago range of creation
        buckets = [
            ("po_2026", 6), ("po_2025", 3), ("po_missing", 1), ("lost", 7),
            ("internal_validation", 2), ("quotation_sent", 5), ("rfq_validated", 4),
            ("customer_budget_approved", 4), ("demo_done", 5), ("qualified_opportunity", 6),
        ]
        n = 0
        for kind, count in buckets:
            for _ in range(count):
                account = self.accounts[(n * 5 + n // len(self.accounts)) % len(self.accounts)]
                tool, tool_type = TOOLS[n % len(TOOLS)]
                currency = "USD" if n % 9 == 4 else ("EUR" if n % 13 == 7 else "CNY")
                amount_cny = self.money(3_000_000, 36_000_000)
                amount = amount_cny if currency == "CNY" else f"{int(float(amount_cny) / (7.1 if currency == 'USD' else 7.8) // 1000 * 1000)}.00"
                spec = {
                    "kind": kind, "account": account, "owner": account["owner"], "tool": tool, "tool_type": tool_type,
                    "currency": currency, "amount": amount, "amount_cny": amount_cny, "conversion": None,
                    "title": f"{account['short']} {account['process'].split(' ')[0]} {tool} {'检测' if 'Inspection' in tool_type else '量测'}项目",
                    "level": self.rng.choice(["pipeline", "pipeline", "upside", "low_probability"]),
                }
                spec["created"], spec["dates"], spec["ending"] = self.stage_dates(spec)
                specs.append(spec)
                n += 1
        early = [spec for spec in specs if spec["kind"] in ("qualified_opportunity", "demo_done", "customer_budget_approved")]
        for spec in specs:
            spec["convert"] = spec in early[:12]
        return specs

    def stage_dates(self, spec: dict[str, Any]) -> tuple[date, list[tuple[str, date]], dict[str, Any]]:
        """Creation date, the stages reached with their dates, and the ending (open / lost / po)."""

        kind = spec["kind"]
        rng = self.rng
        gap = lambda low, high: timedelta(days=rng.randint(low, high))  # noqa: E731
        ending: dict[str, Any] = {"type": "open"}
        if kind.startswith("po"):
            if kind == "po_2026":
                po_day = date(self.today.year, 1, 1) + timedelta(days=rng.randint(3, max(4, (self.today - date(self.today.year, 1, 1)).days - 2)))
            else:
                po_day = date(self.today.year - 1, 1, 1) + timedelta(days=rng.randint(30, 340))
            reached = ["demo_done", "customer_budget_approved", "rfq_validated", "quotation_sent"]
            if rng.random() < 0.3:
                reached.append("internal_validation")
            dates = []
            cursor = po_day
            for stage in reversed(reached):
                cursor = cursor - gap(12, 40)
                dates.append((stage, cursor))
            dates.reverse()
            created = dates[0][1] - gap(10, 30)
            ending = {"type": "po", "date": po_day, "missing": kind == "po_missing"}
            return created, dates, ending
        if kind == "lost":
            lost_stage = rng.choice(STAGES[:5])
            reached = list(STAGES[1: STAGES.index(lost_stage) + 1])
            recent = rng.random() < 0.45
            lost_day = self.days_ago(2, 26) if recent else self.days_ago(30, 330)
            dates = []
            cursor = lost_day
            for stage in reversed(reached):
                cursor = cursor - gap(10, 35)
                dates.append((stage, cursor))
            dates.reverse()
            created = (dates[0][1] if dates else lost_day) - gap(10, 40)
            ending = {"type": "lost", "date": lost_day, "reason": rng.choice(LOST_REASONS)}
            return created, dates, ending
        reached = list(STAGES[1: STAGES.index(kind) + 1])
        last = self.days_ago(2, 40) if kind in ("qualified_opportunity", "demo_done") else self.days_ago(3, 70)
        dates = []
        cursor = last
        for stage in reversed(reached):
            dates.append((stage, cursor))
            cursor = cursor - gap(12, 45)
        dates.reverse()
        created = (dates[0][1] - gap(8, 40)) if dates else self.days_ago(2, 45)
        return created, dates, ending

    def create_opportunity(self, spec: dict[str, Any], created: date) -> dict[str, Any]:
        account, owner = spec["account"], spec["owner"]
        conversion = spec["conversion"]
        expected_po = created + timedelta(days=self.rng.randint(120, 300))
        if conversion:
            when = created
            result = self.at(when, owner, lambda: leads.convert_lead(conversion["lead"]["id"], {
                "accountId": account["id"], "siteId": account["sites"][0]["id"], "contactId": account["contacts"][0]["id"],
                "opportunityTitle": spec["title"], "opportunityAmount": spec["amount"], "opportunityAmountCny": spec["amount_cny"],
                "opportunityCloseDate": expected_po.isoformat(), "opportunityOwner": owner, "toolType": spec["tool"],
                "currency": spec["currency"], "opportunityProbabilityLevel": spec["level"], "qualificationConfirmed": True,
            }))
            self.count("leads converted")
            return self.at(when, owner, lambda: opportunities.get_strategy_opportunity(result["opportunityId"]))
        return self.at(created, owner, lambda: opportunities.create_strategy_opportunity({
            "accountId": account["id"], "siteId": account["sites"][-1]["id"], "title": spec["title"], "owner": owner,
            "amount": spec["amount"], "amountCny": spec["amount_cny"], "originalAmount": spec["amount"], "currency": spec["currency"],
            "poDate": expected_po.isoformat(), "toolType": spec["tool"], "saleType": self.rng.choice(["New Equipment", "New Equipment", "Repeat Order"]),
            "subRegion": account["region"], "probabilityLevel": spec["level"], "intentScore": self.rng.randint(35, 85),
            "qualificationConfirmed": True, "competition": self.rng.choice(["KLA · 最终候选", "Onto Innovation · 对标中", "本土 AOI 厂商 · 价格压力", ""]),
            "strengths": ["本地服务响应快", "样片测试指标领先"], "redFlags": ["预算尚未最终批复"] if self.rng.random() < 0.5 else [],
            "informationNeeded": ["客户 FAT 验收标准"], "paymentMilestones": ["30% PO", "60% 发货", "10% SAT"],
        }))

    def demo_records(self, spec: dict[str, Any], opp: dict[str, Any], when: date, in_progress: bool = False) -> str:
        account, owner = spec["account"], spec["owner"]
        engineer = self.rng.choice(self.engineers)
        contact = account["contacts"][0]
        requested = when - timedelta(days=self.rng.randint(25, 45))
        if in_progress:
            requested = max(requested, spec["created"] + timedelta(days=1))
        form = {
            "companyName": account["name"], "industry": account["segment"], "salesContact": owner, "demoOwner": engineer,
            "sizeShape": "300 mm 圆片", "material": "Si", "specificRequest": f"{spec['tool_type']} 缺陷捕获率与误报率评估",
            "detectMeasure": "已知缺陷样片 + 盲测样片", "expectedResults": "捕获率 ≥ 95%，误报 ≤ 5%", "otherTools": "KLA 2935",
            "primaryTool": spec["tool"], "timing": (requested + timedelta(days=20)).isoformat(),
            "keySuccessFactors": "最小缺陷尺寸、吞吐量", "internalQuestions": "是否需要定制 recipe", "customerQuestions": "交期与培训",
            "wafers": [{"slotId": "1", "wid": f"W{self.rng.randint(1000, 9999)}", "waferSpecificity": "300 mm 已知缺陷片", "notchFlat": "Notch up",
                        "doiMetrologyItems": "颗粒、划伤", "resultFileProvided": "KLARF + PDF"}],
        }
        request = self.at(requested, owner, lambda: self.insert(
            "CRM Demo Request", account=account["id"], primary_contact=contact["id"], request_mode="Opportunity", opportunity=opp["id"],
            sales_owner=owner, created_by_user=owner, title=f"{account['short']} {spec['tool']} Demo", objective=form["specificRequest"],
            requested_equipment=spec["tool"], sample_type=form["sizeShape"], sample_quantity=self.rng.randint(2, 6),
            target_date=form["timing"], customer_expected_date=form["timing"], priority=self.rng.choice(["High", "Medium"]),
            acceptance_criteria=form["expectedResults"], status="Converted", engineer_owner=engineer, feasibility="Feasible",
            estimated_completion_date=(requested + timedelta(days=24)).isoformat(), manager_decision="Approved",
            form_data=json.dumps(form, ensure_ascii=False), prepared_by=engineer, prepared_date=(requested + timedelta(days=2)).isoformat(),
            approved_by=self.managers[0], approved_date=(requested + timedelta(days=3)).isoformat(),
        ))
        # Submitted the day after: an Engineer reads a request from its submission for Engineer Review on.
        self.at(requested + timedelta(days=1), owner, lambda: self.insert(
            "CRM Demo Request History", demo_request=request.name, at=self.clock.current, actor=owner,
            from_status="Draft", to_status="Engineer Review", comment="Sales submitted for Engineer Review",
        ))
        evaluation = self.at(requested + timedelta(days=3), self.managers[0], lambda: self.insert(
            "CRM Evaluation", account=account["id"], demo_request=request.name, title=request.title, status="Testing" if in_progress else "Accepted",
            evaluation_owner=engineer, planned_end=(requested + timedelta(days=24)).isoformat(), acceptance="Pending" if in_progress else "Accepted",
            report_status="Not Ready" if in_progress else "Ready", report_version=0 if in_progress else 1,
            wafer_preparation_status="Completed", test_preparation_status="Completed",
        ))
        frappe.db.set_value("CRM Demo Request", request.name, "evaluation", evaluation.name, update_modified=False)
        for run_index in range(1 if in_progress else self.rng.randint(1, 2)):
            run_day = when - timedelta(days=self.rng.randint(1, 12) if in_progress else self.rng.randint(4, 14) + run_index * 3)
            self.at(run_day, engineer, lambda: self.insert(
                "CRM Test Run", evaluation=evaluation.name, run_date=run_day.isoformat(), lot=f"LOT{self.rng.randint(10000, 99999)}",
                wafers=self.rng.randint(2, 6), status="Completed",
            ))
            self.count("test runs")
        self.count("demo requests")
        return evaluation.name

    def rfq_record(self, spec: dict[str, Any], opp: dict[str, Any], when: date) -> str:
        rfq = self.at(when, self.managers[0], lambda: self.insert(
            "CRM RFQ", opportunity=opp["id"], account=spec["account"]["id"], sales_owner=spec["owner"],
            engineer_owner=self.rng.choice(self.engineers), status="Approved", latest_version_no=0,
            approved_by=self.managers[0], approved_at=datetime.combine(when, time(15, 0)),
        ))
        return rfq.name

    def quotation_record(self, spec: dict[str, Any], opp: dict[str, Any], when: date) -> str:
        account, owner = spec["account"], spec["owner"]
        unit = spec["amount"]
        ref_no = f"PK{when:%Y%m%d}-A{self.rng.randint(1, 9)}"
        quotation = self.at(when - timedelta(days=2), owner, lambda: self.insert(
            "CRM Quotation", ref_no=ref_no, quotation_type="Device", opportunity=opp["id"], account=account["id"],
            quotation_owner=owner, status="Published", latest_version_no=1,
        ))
        version = self.at(when, owner, lambda: self.insert(
            "CRM Quotation Version", quotation=quotation.name, version_no=1, quotation_type="Device", status="Published",
            approval_status="Approved", ref_no=ref_no, opportunity=opp["id"], account=account["id"], quotation_owner=owner,
            primary_contact=account["contacts"][0]["id"], address=account["sites"][0]["id"], quote_date=when.isoformat(),
            validity_months=3, valid_until=(when + timedelta(days=90)).isoformat(), currency=spec["currency"],
            items=[{"line_key": "device-1", "line_type": "Device", "item_name": f"{spec['tool']} {spec['tool_type']} System",
                    "model": spec["tool"], "pricing_mode": "Charged", "quantity": 1, "unit_price": unit, "line_amount": unit}],
            subtotal=unit, discount_type="None", discount_value=0, discount_amount=0, total=unit,
            payment_terms=[{"percentage": 30, "trigger_condition": "PO 签订"}, {"percentage": 60, "trigger_condition": "发货前"},
                           {"percentage": 10, "trigger_condition": "SAT 验收"}, {"percentage": 0, "trigger_condition": "质保期满"}],
            incoterm="DAP 客户厂区", delivery_months=4, warranty_months=12, published_at=datetime.combine(when, time(14, 20)),
        ))
        frappe.db.set_value("CRM Quotation", quotation.name, {"current_version": version.name, "current_published_version": version.name}, update_modified=False)
        self.count("quotations")
        return version.name

    def booking_draft(self, spec: dict[str, Any], po_day: date) -> dict[str, Any]:
        account = spec["account"]
        return {
            "primaryContactId": account["contacts"][0]["id"], "equipment": f"{spec['tool']} {spec['tool_type']} System", "quantity": 1,
            "ddl": (po_day + timedelta(days=self.rng.randint(90, 180))).isoformat(), "amount": spec["amount"], "currency": spec["currency"],
            # A foreign-currency order carries its amount in CNY; a CNY order's amount already is one.
            "amountCny": spec["amount_cny"] if spec["currency"] != "CNY" else "",
            "owner": spec["owner"], "note": "按报价条款执行，FAT 后发货。",
        }

    def advance(self, spec: dict[str, Any], opp: dict[str, Any], stage: str, when: date) -> dict[str, Any]:
        owner, opp_id = spec["owner"], opp["id"]
        if stage == "demo_done":
            evaluation = self.demo_records(spec, opp, when)
            self.at(when, self.engineers[0], lambda: opportunities.advance_opportunity_for_event(
                opp_id, "demo_customer_review", reference_doctype="CRM Evaluation", reference_name=evaluation))
        elif stage == "customer_budget_approved":
            self.at(when + timedelta(days=1), owner, lambda: opportunities.confirm_budget_approved(
                opp_id, {"approvedOn": when.isoformat()}, self.modified_of("CRM Opportunity", opp_id)))
        elif stage == "rfq_validated":
            rfq = self.rfq_record(spec, opp, when)
            self.at(when, self.managers[0], lambda: opportunities.advance_opportunity_for_event(
                opp_id, "rfq_approved", reference_doctype="CRM RFQ", reference_name=rfq))
        elif stage == "quotation_sent":
            version = self.quotation_record(spec, opp, when)
            self.at(when, self.managers[0], lambda: opportunities.advance_opportunity_for_event(
                opp_id, "quotation_published", reference_doctype="CRM Quotation Version", reference_name=version))
        elif stage == "internal_validation":
            draft = self.booking_draft(spec, when + timedelta(days=30))
            requested = self.at(when - timedelta(days=3), owner, lambda: opportunities.request_internal_validation(
                opp_id, {"reason": "客户已口头确认订单，申请提前启动生产准备。", "expectedPoDate": (when + timedelta(days=30)).isoformat(), "booking": draft},
                self.modified_of("CRM Opportunity", opp_id)))
            self.at(when, self.managers[1], lambda: opportunities.review_internal_validation(
                opp_id, {"validationId": requested["internalValidation"]["id"], "decision": "approved", "comment": "同意提前备料。"},
                self.modified_of("CRM Opportunity", opp_id)))
        return self.at(when, owner, lambda: opportunities.get_strategy_opportunity(opp_id))

    def seed_opportunities(self, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        for spec in specs:
            created, dates, ending = spec["created"], spec["dates"], spec["ending"]
            opp = self.create_opportunity(spec, created)
            owner, opp_id = spec["owner"], opp["id"]
            # Level moves: one raise on the way up, downgrades for a few open deals.
            if dates and self.rng.random() < 0.5 and spec["level"] != "committed":
                higher = {"low_probability": "pipeline", "pipeline": "upside", "upside": "committed"}[spec["level"]]
                bump_day = dates[0][1] + timedelta(days=2)
                self.at(bump_day, owner, lambda: opportunities.update_strategy_opportunity(
                    opp_id, {"probabilityLevel": higher}, self.modified_of("CRM Opportunity", opp_id)))
            for stage, when in dates:
                self.advance(spec, opp, stage, when)
            # Some first-stage deals have a demo under way: the test ran, the report is not out yet.
            if spec["kind"] == "qualified_opportunity" and self.rng.random() < 0.7:
                self.demo_records(spec, opp, self.today, in_progress=True)
            # Stakeholders and actions
            for contact in spec["account"]["contacts"][: self.rng.randint(1, 3)]:
                role = self.rng.choice(["Decision Maker", "Economic Buyer", "Technical Buyer", "User Buyer", "Champion", "Procurement"])
                self.at(created + timedelta(days=3), owner, lambda: opportunities.create_opportunity_stakeholder(opp_id, {
                    "contactId": contact["id"], "role": role, "influence": self.rng.choice(["High", "Medium", "Low"]),
                    "stance": self.rng.choice(["Support", "Support", "Neutral", "Against"]), "coverage": self.rng.choice(["每周沟通", "仅见过一次", "关系稳固", "待建立联系"]),
                }))
            ended = ending["type"] != "open"
            last_touch = ending.get("date", self.today)
            for action_index in range(self.rng.randint(1, 3)):
                action_day = created + timedelta(days=self.rng.randint(5, max(6, (last_touch - created).days or 6)))
                if ended and action_day > last_touch:
                    action_day = last_touch - timedelta(days=1)
                due = action_day + timedelta(days=self.rng.randint(5, 30))
                title = self.rng.choice(ACTIONS)
                action = self.at(action_day, owner, lambda: opportunities.create_opportunity_action(opp_id, {
                    "title": title, "owner": owner, "due": due.isoformat(), "status": "Open"}))
                done_day = due - timedelta(days=self.rng.randint(0, 3))
                if (ended or self.rng.random() < 0.55) and done_day <= min(last_touch, self.today):
                    self.at(done_day, owner, lambda: opportunities.update_opportunity_action(opp_id, action["id"], {
                        "title": title, "owner": owner, "due": due.isoformat(), "status": "Done"}))
                self.count("actions")
            if not ended and self.rng.random() < 0.55:
                recent_day = self.days_ago(1, 14)
                recent_title = self.rng.choice(ACTIONS)
                self.at(recent_day, owner, lambda: opportunities.create_opportunity_action(opp_id, {
                    "title": recent_title, "owner": owner, "due": (recent_day + timedelta(days=self.rng.randint(7, 21))).isoformat(), "status": "Open"}))
                self.count("actions")
            if ending["type"] == "lost":
                self.at(ending["date"], owner, lambda: opportunities.mark_opportunity_lost(
                    opp_id, {"lostReason": ending["reason"]}, self.modified_of("CRM Opportunity", opp_id)))
                self.count("lost")
            elif ending["type"] == "po":
                po_day = ending["date"]
                draft = self.booking_draft(spec, po_day)
                confirmed = self.at(po_day + timedelta(days=self.rng.randint(0, 2)), owner, lambda: opportunities.confirm_po(
                    opp_id, {"booking": draft, "actualPoDate": po_day.isoformat()}, self.modified_of("CRM Opportunity", opp_id)))
                booking_id = confirmed["liveBooking"]["id"]
                if ending.get("missing"):
                    frappe.db.set_value("CRM Booking", booking_id, {"actual_po_date": None, "actual_po_date_source": ""}, update_modified=False)
                elif spec["kind"] == "po_2025" or (spec["kind"] == "po_2026" and po_day < self.today - timedelta(days=150)):
                    convert_day = po_day + timedelta(days=self.rng.randint(60, 120))
                    if convert_day < self.today:
                        self.at(convert_day, owner, lambda: installed_tools.convert_booking_to_installed_tool(booking_id, {
                            "siteId": spec["account"]["sites"][0]["id"], "engineerOwner": self.rng.choice(self.engineers), "model": spec["tool"],
                            "location": f"{spec['account']['short']} Bay {self.rng.randint(1, 9)}", "software": "v3.2.1",
                        }, self.modified_of("CRM Booking", booking_id)))
                        self.count("installed tools")
                self.count("po received")
            else:
                # A few open deals lose confidence recently, with the reason Managers see in Review.
                if spec["kind"] in ("customer_budget_approved", "rfq_validated", "quotation_sent", "demo_done") and self.rng.random() < 0.35:
                    current = frappe.db.get_value("CRM Opportunity", opp_id, "probability_level")
                    lower = {"committed": "upside", "upside": "pipeline", "pipeline": "low_probability"}.get(current)
                    if lower:
                        self.at(self.days_ago(1, 20), owner, lambda: opportunities.update_strategy_opportunity(
                            opp_id, {"probabilityLevel": lower, "probabilityReason": self.rng.choice(DOWNGRADE_REASONS),
                                     "probabilityActionPlan": "Arrange a customer follow-up to validate the revised budget and agree next steps."},
                            self.modified_of("CRM Opportunity", opp_id)))
                        self.count("downgrades")
            results.append({"spec": spec, "id": opp_id, "created": created, "ending": ending})
            self.count("opportunities")
        return results

    # -- upsell bookings ----------------------------------------------------------------

    def seed_upsell(self) -> None:
        for index in range(3):
            account = self.accounts[(index * 5 + 1) % len(self.accounts)]
            po_day = self.days_ago(20, 200)
            tool, tool_type = TOOLS[index % len(TOOLS)]
            self.at(po_day + timedelta(days=1), account["owner"], lambda: bookings.create_booking({
                "accountId": account["id"], "primaryContactId": account["contacts"][0]["id"], "equipment": f"{tool} 升级套件" if index else "年度维保服务",
                "quantity": 1, "ddl": (po_day + timedelta(days=60)).isoformat(), "amount": self.money(400_000, 2_500_000), "currency": "CNY",
                "status": "Confirmed", "source": "Upsell", "bookingType": "Equipment" if index else "Service", "owner": account["owner"],
                "actualPoDate": po_day.isoformat(), "note": "老客户追加订单",
            }))
            self.count("upsell bookings")

    # -- visits -------------------------------------------------------------------------

    def seed_visits(self, deals: list[dict[str, Any]]) -> None:
        open_deals = [d for d in deals if d["ending"]["type"] == "open"]
        start = self.today - timedelta(days=400)
        day = start
        while day <= self.today + timedelta(days=12):
            for owner in self.sales:
                weekly = 2 if day > self.today - timedelta(days=120) else 1
                for _ in range(weekly):
                    visit_day = day + timedelta(days=self.rng.randint(0, 4))
                    candidates = [a for a in self.accounts if a["owner"] == owner]
                    account = self.rng.choice(candidates)
                    deal = next((d for d in open_deals if d["spec"]["account"]["id"] == account["id"]), None)
                    subject = self.rng.choice(VISIT_SUBJECTS)
                    payload = {
                        "accountId": account["id"], "subject": f"{account['short']} · {subject}", "objective": f"{subject}，确认下一步行动。",
                        "date": visit_day.isoformat(), "type": self.rng.choice(VISIT_TYPES), "owner": owner,
                        "primaryContactId": account["contacts"][0]["id"],
                    }
                    if deal:
                        payload["opportunityId"] = deal["id"]
                    visit = self.at(visit_day - timedelta(days=self.rng.randint(1, 5)), owner, lambda: visits.create_visit(payload))
                    self.count("visits")
                    if visit_day > self.today:
                        continue
                    self.at(datetime.combine(visit_day, time(16, 30)), owner, lambda: visit_meetings.update_record(visit["id"], {
                        "meetingStart": f"{visit_day} 10:00", "meetingEnd": f"{visit_day} 11:30", "purpose": subject,
                        "attendees": f"{account['contacts'][0]['name']}（{account['contacts'][0]['title']}）、我方销售",
                        "agenda": "1. 现状与需求 2. 方案讨论 3. 下一步", "summary": f"客户对{subject}反馈积极，关注交期与服务。",
                        "conclusion": "继续推进技术交流并准备报价。", "followup": "一周内发送会议纪要与资料。",
                    }))
                    if self.rng.random() < 0.85:
                        self.at(visit_day + timedelta(days=self.rng.randint(1, 3)), self.managers[0], lambda: visits.review_visit(
                            visit["id"], self.modified_of("CRM Visit", visit["id"])))
            day += timedelta(days=7)

    # -- targets ------------------------------------------------------------------------

    def seed_targets(self) -> None:
        today = self.today
        monday = today - timedelta(days=today.weekday())
        month = today.replace(day=1)
        quarter = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
        year = date(today.year, 1, 1)
        weekly = {"visits": 3, "leads": 1, "tests": 1, "quotes": 1}
        for index, owner in enumerate(self.sales):
            for metric, per_week in weekly.items():
                for period, anchor, factor in (("week", monday, 1), ("month", month, 4), ("quarter", quarter, 13), ("year", year, 50)):
                    self.at(datetime.combine(year, time(9, 0)) + timedelta(days=index), self.managers[0], lambda: cockpit.save_target({
                        "sales": owner, "metric": metric, "period": period, "anchor": anchor.isoformat(), "value": per_week * factor}))
            self.at(datetime.combine(year, time(9, 30)) + timedelta(days=index), self.managers[0], lambda: cockpit.save_target({
                "sales": owner, "metric": "orders", "period": "year", "anchor": year.isoformat(), "value": "60000000.00" if index == 0 else "45000000.00"}))
        self.count("targets")

    # -- run ----------------------------------------------------------------------------

    def run(self) -> dict[str, int]:
        _ensure_users()
        frappe.set_user("Administrator")
        self.clock.install()
        try:
            self.seed_customers()
            specs = self.opportunity_specs()
            self.seed_leads(specs)
            deals = self.seed_opportunities(specs)
            self.seed_upsell()
            self.seed_visits(deals)
            self.seed_targets()
        finally:
            self.clock.restore()
            frappe.set_user("Administrator")
        return self.log


def seed(confirm: str = "") -> dict[str, int]:
    _guard(confirm)
    if frappe.db.count("CRM Opportunity"):
        raise RuntimeError("Wipe the site before seeding; it still has Opportunities.")
    log = Seeder().run()
    frappe.db.commit()
    print(json.dumps(log, ensure_ascii=False, indent=2))
    return log
