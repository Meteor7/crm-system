"""Presentation-only branding for the portfolio sign-in page."""

def update_website_context(context):
    if context.get("path") != "login":
        return
    context.update({
        "app_name": "栖衡 CRM",
        "title": "登录 · 栖衡 CRM",
        "logo": "/assets/rayher_crm/images/qiheng-logo.svg",
        "favicon": "/assets/rayher_crm/images/qiheng-icon.svg",
    })
