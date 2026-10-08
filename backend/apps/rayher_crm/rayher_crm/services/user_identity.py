"""Lock native User identity changes before business Link traversal."""
import frappe


def lock_user_pair(old, new):
    # Frappe merge otherwise only locks the source at deletion, after its Links.
    return frappe.db.sql("SELECT name FROM `tabUser` WHERE name IN (%s, %s) ORDER BY name FOR UPDATE",
                         (old, new.strip()))


def lock_users_before_rename(doc, method, old, new, merge):
    # Frappe interprets a nonempty hook return as a replacement rename target.
    lock_user_pair(old, new)
