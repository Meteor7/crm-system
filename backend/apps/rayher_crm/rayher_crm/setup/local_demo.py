"""Append fictional demo data to the explicitly named local Docker site only."""
from datetime import timedelta
import frappe
from rayher_crm.setup import staging_dataset as base

PREFIX = "[演示]"
STAFF = {
    "sales": [("demo.sales1@example.com", "演示·林悦"), ("demo.sales2@example.com", "演示·陈舟")],
    "managers": [("demo.manager1@example.com", "演示·演示员工14"), ("demo.manager2@example.com", "演示·许晴")],
    "engineers": [("demo.engineer1@example.com", "演示·苏辰"), ("demo.engineer2@example.com", "演示·唐禾")],
}

class LocalSeeder(base.Seeder):
    def seed_customers(self):
        for index, (name, short, segment, tier, city, region, process, domain) in enumerate(base.CUSTOMERS):
            name, short = PREFIX + name, PREFIX + short
            owner = self.sales[index % 2]
            created = self.today - timedelta(days=self.rng.randint(280, 640))
            account = self.at(created, owner, lambda: base.accounts.create_account({
                "name": name, "shortName": short, "segment": segment, "tier": tier,
                "city": city, "region": region, "owner": owner,
            }))
            site_rows = []
            for si in range(1 if tier == "B" else 2):
                site_rows.append(self.at(created + timedelta(days=si), owner, lambda: base.sites.create_site(account["id"], {
                    "name": short + ("一厂" if si == 0 else "二厂"), "city": city,
                    "type": "OSAT" if segment == "Advanced Packaging" else "Fab", "process": process,
                    "status": "量产" if si == 0 else "建设中",
                })))
            contact_rows = []
            for ci in range(3):
                title, department = base.CONTACT_TITLES[(index + ci) % len(base.CONTACT_TITLES)]
                person = PREFIX + self.person()
                contact_rows.append(self.at(created + timedelta(days=ci+2), owner, lambda: base.contacts.create_contact({
                    "accountId": account["id"], "siteId": site_rows[0]["id"], "name": person,
                    "title": title, "department": department, "phone": "000-0000-0000",
                    "email": f"demo.contact{index+1}.{ci+1}@example.com", "relationship": "Developing",
                    "status": "Active", "owner": owner,
                })))
            self.accounts.append({"id": account["id"], "name": name, "short": short, "segment": segment,
                "region": region, "owner": owner, "sites": site_rows, "contacts": contact_rows,
                "created": created, "process": process, "domain": domain})
            self.count("customers")

    def lead_payload(self, account, owner, index, status, created):
        values = super().lead_payload(account, owner, index, status, created)
        values.update(name=PREFIX + values["name"], phone="000-0000-0000", email=f"demo.lead{index+1}@example.com")
        return values

    def opportunity_specs(self):
        specs = super().opportunity_specs()
        for spec in specs:
            if spec["ending"].get("missing"):
                spec["ending"]["missing"] = False
        return specs


def seed(confirm=""):
    if frappe.local.site != "planck-crm.localhost" or confirm != frappe.local.site:
        raise RuntimeError("This seed is only for the confirmed local Docker CRM site.")
    existing = frappe.db.count("Customer", {"customer_name": ["like", PREFIX + "%"]})
    if existing:
        return {"created": False, "demo_customers": existing, "message": "Existing demo batch preserved."}
    original_staff = base.STAFF
    original_user = frappe.session.user
    try:
        frappe.flags.mute_emails = True
        base.STAFF = STAFF
        frappe.set_user("Administrator")
        result = LocalSeeder().run()
        frappe.db.commit()
        return {"created": True, **result}
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        base.STAFF = original_staff
        frappe.set_user(original_user)
