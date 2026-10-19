"""A site-level release gate for new attachments, including native File APIs."""

import frappe


MESSAGE = "上线初期暂不开放附件上传，请联系演示员工170；已有附件仍可按权限查看。"


def uploads_paused():
    return str(frappe.conf.get("crm_attachment_uploads_paused", 0)).lower() in {"1", "true"}


def reject_new_file():
    """Run before core File.before_insert can write or fetch any bytes.

    This also applies to Administrator and background jobs. Reopening uploads
    is an explicit site configuration change, never a client-supplied bypass.
    """
    if uploads_paused():
        frappe.local.flags.disable_traceback = True
        frappe.throw(MESSAGE, frappe.PermissionError)


def reject_upload_request():
    """Stop multipart uploads before scanners, converters or business writes."""
    request = getattr(frappe.local, "request", None)
    if request is not None and getattr(request, "files", None):
        reject_new_file()


def reject_file_write(file_size):
    """Stop legacy save_file before its writer runs, including background calls.

    Frappe 15's file_manager.save_file writes bytes before inserting File. Its
    before_write_file hook is therefore required in addition to before_insert.
    Keep the insert guard too: hash-deduplicated files skip this write hook.
    """
    reject_new_file()
