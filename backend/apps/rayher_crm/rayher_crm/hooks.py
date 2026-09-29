app_name = "rayher_crm"
app_title = "Rayher CRM"
app_publisher = "Rayher Semiconductor"
app_description = "Independent CRM application for Frappe and ERPNext"
app_email = "person023@crm.example.invalid"
app_license = "Proprietary"
app_version = "0.1.0"

required_apps = ["erpnext"]

after_install = "rayher_crm.setup.install.after_install"
after_migrate = "rayher_crm.setup.install.after_migrate"
before_tests = "rayher_crm.tests.safety.before_tests"

after_request = [
    "rayher_crm.security.session_cookie.enforce_browser_session_cookie",
    "rayher_crm.api.v1.controlled_documents.apply_delivery_headers",
]

permission_query_conditions = {
    "Customer": "rayher_crm.permissions.scope.customer_query",
    "Contact": "rayher_crm.permissions.scope.contact_query",
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
    "CRM Booking": "rayher_crm.permissions.scope.booking_query",
    "CRM Installed Tool": "rayher_crm.permissions.scope.installed_tool_query",
    "CRM Demo Request": "rayher_crm.permissions.scope.demo_request_query",
    "CRM Evaluation": "rayher_crm.permissions.scope.evaluation_query",
    "CRM Evaluation Customer Review": "rayher_crm.permissions.scope.evaluation_customer_review_query",
    "CRM Contact File": "rayher_crm.permissions.scope.contact_file_query",
    "CRM Status Attachment": "rayher_crm.permissions.scope.status_attachment_query",
    "CRM Demo Artifact": "rayher_crm.permissions.scope.demo_artifact_query",
    "CRM Notification Event": "rayher_crm.permissions.scope.notification_query",
    "CRM Visit": "rayher_crm.permissions.scope.visit_query",
    "CRM Visit Meeting Record": "rayher_crm.permissions.scope.visit_meeting_record_query",
    "CRM Quotation": "rayher_crm.permissions.scope.quotation_query",
    "CRM Quotation Version": "rayher_crm.permissions.scope.quotation_version_query",
    "CRM Quotation Approval": "rayher_crm.permissions.scope.quotation_approval_query",
    "CRM RFQ": "rayher_crm.permissions.scope.rfq_query",
    "CRM RFQ Version": "rayher_crm.permissions.scope.rfq_version_query",
}

has_permission = {
    "Customer": "rayher_crm.permissions.scope.has_crm_permission",
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
    "CRM Booking": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Installed Tool": "rayher_crm.permissions.scope.has_site_bearing_permission",
    "CRM Demo Request": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Evaluation": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Evaluation Customer Review": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Contact File": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Status Attachment": "rayher_crm.permissions.scope.has_status_attachment_permission",
    "CRM Demo Artifact": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Notification Event": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Visit": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Visit Meeting Record": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Quotation": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM Quotation Version": "rayher_crm.permissions.scope.has_quotation_version_permission",
    "CRM Quotation Approval": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM RFQ": "rayher_crm.permissions.scope.has_crm_permission",
    "CRM RFQ Version": "rayher_crm.permissions.scope.has_crm_permission",
}



delete_file_data_content = "rayher_crm.services.private_file_lifecycle.delete_file_content"

doc_events = {
    "File": {
        "before_insert": "rayher_crm.services.private_file_lifecycle.protect_private_upload",
    },
}

scheduler_events = {
    "daily": [
        "rayher_crm.services.quotations.expire_quotations",
        "rayher_crm.services.ddl_reminders.send_ddl_reminders",
        # Frappe runs each daily job on its own, in no set order; quotation_expiry itself skips versions past valid_until.
        "rayher_crm.services.warning_notifications.send_warning_notifications",
    ],
}
