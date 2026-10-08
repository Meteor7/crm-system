app_name = "rayher_crm"
app_title = "Rayher CRM"
app_publisher = "Rayher Semiconductor"
app_description = "Independent CRM application for Frappe and ERPNext"
app_email = "person023@crm.example.invalid"
app_license = "Proprietary"
app_version = "0.1.0"

required_apps = ["erpnext"]

override_doctype_class = {"File": "rayher_crm.overrides.file.ManagedFile"}

after_install = "rayher_crm.setup.install.after_install"
after_migrate = "rayher_crm.setup.install.after_migrate"
before_tests = "rayher_crm.tests.safety.before_tests"

auth_hooks = [
    "rayher_crm.security.api_session.require_session_for_crm_api",
]

after_request = [
    "rayher_crm.security.session_cookie.enforce_browser_session_cookie",
    "rayher_crm.api.v1.controlled_documents.apply_delivery_headers",
]

override_whitelisted_methods = {
    "frappe.desk.search.search_link": "rayher_crm.api.search.search_link",
    "frappe.desk.search.search_widget": "rayher_crm.api.search.search_widget",
}

permission_query_conditions = {
    "Allowed To Transact With": "rayher_crm.permissions.scope.scoped_child_query",
    "Customer Credit Limit": "rayher_crm.permissions.scope.scoped_child_query",
    "Party Account": "rayher_crm.permissions.scope.scoped_child_query",
    "Sales Team": "rayher_crm.permissions.scope.scoped_child_query",
    "Portal User": "rayher_crm.permissions.scope.scoped_child_query",
    "File": "rayher_crm.services.managed_file_access.file_query",
    "Customer": "rayher_crm.permissions.scope.customer_query",
    "Address": "rayher_crm.permissions.scope.address_query",
    "Contact": "rayher_crm.permissions.scope.contact_query",
    "Contact Email": "rayher_crm.permissions.scope.scoped_child_query",
    "Contact Phone": "rayher_crm.permissions.scope.scoped_child_query",
    "Dynamic Link": "rayher_crm.permissions.scope.scoped_child_query",
    "Event Participants": "rayher_crm.permissions.scope.scoped_child_query",
    "Event Notifications": "rayher_crm.permissions.scope.scoped_child_query",
    "Communication Link": "rayher_crm.permissions.scope.scoped_child_query",
    "CRM Note": "rayher_crm.permissions.scope.scoped_child_query",
    "Lead": "rayher_crm.permissions.scope.lead_query",
    "CRM Opportunity": "rayher_crm.permissions.scope.opportunity_query",
    "CRM Opportunity Probability History": "rayher_crm.permissions.scope.opportunity_probability_history_query",
    "CRM Probability Recovery": "rayher_crm.permissions.scope.probability_recovery_query",
    "CRM Probability Recovery Revision": "rayher_crm.permissions.scope.probability_recovery_revision_query",
    "CRM Opportunity Loss Review": "rayher_crm.permissions.scope.opportunity_loss_review_query",
    "CRM Opportunity Loss Review Revision": "rayher_crm.permissions.scope.opportunity_loss_review_revision_query",
    "CRM Opportunity Stage History": "rayher_crm.permissions.scope.opportunity_stage_history_query",
    "CRM Opportunity Internal Validation": "rayher_crm.permissions.scope.opportunity_internal_validation_query",
    "CRM Opportunity Action": "rayher_crm.permissions.scope.opportunity_action_query",
    "CRM Opportunity History": "rayher_crm.permissions.scope.opportunity_history_query",
    "CRM Opportunity Stakeholder": "rayher_crm.permissions.scope.opportunity_stakeholder_query",
    "CRM Booking": "rayher_crm.permissions.scope.booking_query",
    "CRM Installed Tool": "rayher_crm.permissions.scope.installed_tool_query",
    "CRM Installed Tool Lifecycle History": "rayher_crm.permissions.scope.installed_tool_lifecycle_history_query",
    "CRM Installed Tool Service History": "rayher_crm.permissions.scope.installed_tool_service_history_query",
    "CRM Installed Tool Version History": "rayher_crm.permissions.scope.installed_tool_version_history_query",
    "CRM Account Engineer Assignment": "rayher_crm.permissions.scope.account_engineer_assignment_query",
    "CRM Demo Request": "rayher_crm.permissions.scope.demo_request_query",
    "CRM Demo Comment": "rayher_crm.permissions.scope.demo_comment_query",
    "CRM Demo Request History": "rayher_crm.permissions.scope.demo_request_history_query",
    "CRM Evaluation": "rayher_crm.permissions.scope.evaluation_query",
    "CRM Evaluation Customer Review": "rayher_crm.permissions.scope.evaluation_customer_review_query",
    "CRM Evaluation History": "rayher_crm.permissions.scope.evaluation_history_query",
    "CRM Test Run": "rayher_crm.permissions.scope.test_run_query",
    "CRM Contact File": "rayher_crm.permissions.scope.contact_file_query",
    "CRM Status Attachment": "rayher_crm.permissions.scope.status_attachment_query",
    "CRM Demo Artifact": "rayher_crm.permissions.scope.demo_artifact_query",
    "CRM Notification Event": "rayher_crm.permissions.scope.notification_query",
    "CRM Document Access Request": "rayher_crm.permissions.scope.document_access_request_query",
    "CRM Visit": "rayher_crm.permissions.scope.visit_query",
    "CRM Event": "rayher_crm.permissions.scope.event_query",
    "CRM Visit Meeting Record": "rayher_crm.permissions.scope.visit_meeting_record_query",
    "CRM Quotation": "rayher_crm.permissions.scope.quotation_query",
    "CRM Quotation Version": "rayher_crm.permissions.scope.quotation_version_query",
    "CRM Quotation Item": "rayher_crm.permissions.scope.scoped_child_query",
    "CRM Quotation Follow Up": "rayher_crm.permissions.scope.scoped_child_query",
    "CRM Query Recipient": "rayher_crm.permissions.scope.scoped_child_query",
    "CRM Quotation Payment Term": "rayher_crm.permissions.scope.scoped_child_query",
    "CRM Quotation Approval": "rayher_crm.permissions.scope.quotation_approval_query",
    "CRM RFQ": "rayher_crm.permissions.scope.rfq_query",
    "CRM RFQ Version": "rayher_crm.permissions.scope.rfq_version_query",
    # Restrict CRM User list rows while preserving valid Manager lookups.
    "User": "rayher_crm.permissions.native_lists.user_query",
    # User's child tables are listed on User's DocType-level read alone (#219).
    "Has Role": "rayher_crm.permissions.scope.scoped_child_query",
    "DefaultValue": "rayher_crm.permissions.scope.scoped_child_query",
    "User Email": "rayher_crm.permissions.scope.scoped_child_query",
    "User Social Login": "rayher_crm.permissions.scope.scoped_child_query",
    "Block Module": "rayher_crm.permissions.scope.scoped_child_query",
}

has_permission = {
    "File": "rayher_crm.services.managed_file_access.file_permission",
    "Customer": "rayher_crm.permissions.scope.has_crm_permission",
    "Address": "rayher_crm.permissions.scope.has_address_permission",
    "Contact": "rayher_crm.permissions.scope.has_site_bearing_permission",
    "Lead": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Opportunity": "rayher_crm.permissions.scope.has_site_bearing_permission",
    "CRM Opportunity Probability History": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Probability Recovery": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Probability Recovery Revision": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Opportunity Loss Review": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Opportunity Loss Review Revision": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Opportunity Stage History": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Opportunity Internal Validation": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Opportunity Action": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Opportunity History": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Opportunity Stakeholder": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Booking": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Installed Tool": "rayher_crm.permissions.scope.has_site_bearing_permission",
    "CRM Installed Tool Lifecycle History": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Installed Tool Service History": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Installed Tool Version History": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Account Engineer Assignment": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Demo Request": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Demo Comment": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Demo Request History": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Evaluation": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Evaluation Customer Review": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Evaluation History": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Test Run": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Contact File": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Status Attachment": "rayher_crm.permissions.scope.has_status_attachment_permission",
    "CRM Demo Artifact": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Notification Event": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Document Access Request": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Visit": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Event": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Visit Meeting Record": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Quotation": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Quotation Version": "rayher_crm.permissions.scope.has_quotation_version_permission",
    "CRM Quotation Approval": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM RFQ": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM RFQ Version": "rayher_crm.permissions.scope.has_crm_permission",
}


delete_file_data_content = "rayher_crm.services.private_file_lifecycle.delete_file_content"

doc_events = {
    "DocShare": {
        "validate": [
            "rayher_crm.permissions.scope.prevent_scoped_docshare",
            "rayher_crm.services.managed_file_access.protect_share",
        ],
    },
    "Address": {
        # Native deletion is guarded by has_address_permission("delete");
        # Frappe 15 raises no before_delete event.
        "before_save": "rayher_crm.permissions.scope.revoke_address_shares_entering_crm",
        "before_rename": "rayher_crm.permissions.scope.protect_standard_crm_merge",
    },
    "Customer": {
        "before_save": "rayher_crm.permissions.scope.revoke_customer_address_shares_entering_crm",
        "before_rename": "rayher_crm.permissions.scope.protect_standard_crm_merge",
    },
    "Customer Group": {
        "before_rename": "rayher_crm.permissions.scope.protect_crm_customer_group_name",
    },
    "Contact": {
        "before_save": "rayher_crm.permissions.scope.revoke_contact_shares_entering_crm",
        "before_rename": "rayher_crm.permissions.scope.protect_standard_crm_merge",
    },
    "Lead": {
        "before_save": "rayher_crm.permissions.scope.revoke_lead_shares_entering_crm",
        "before_rename": "rayher_crm.permissions.scope.protect_standard_crm_merge",
    },
    "User": {
        "before_save": "rayher_crm.permissions.scope.revoke_shares_when_user_enters_crm",
        "before_rename": "rayher_crm.services.cockpit_identity.lock_users_before_rename",
        "after_rename": "rayher_crm.permissions.scope.reconcile_shares_after_user_rename",
    },
    "File": {
        "before_insert": "rayher_crm.services.private_file_lifecycle.protect_private_upload",
        "before_validate": "rayher_crm.services.managed_file_access.protect_file_write",
    },
}

scheduler_events = {
    "daily": [
        "rayher_crm.services.quotations.expire_quotations",
        "rayher_crm.services.ddl_reminders.send_ddl_reminders",
        # Frappe runs each daily job on its own, in no set order; quotation_expiry itself skips versions past valid_until.
        "rayher_crm.services.warning_notifications.send_warning_notifications",
        "rayher_crm.services.demo_resources.capture_impacts",
    ],
}
