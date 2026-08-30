from __future__ import annotations

import unittest

from rayher_crm.security.session_cookie import make_sid_cookie_session_only


class _CookieManager:
    def __init__(self, cookies):
        self.cookies = cookies


class TestSessionCookie(unittest.TestCase):
    def test_sid_loses_only_persistence_attributes(self):
        other_cookie = {
            "value": "language-value",
            "expires": "tomorrow",
            "max_age": 300,
            "httponly": False,
        }
        manager = _CookieManager({
            "sid": {
                "value": "opaque-session-value",
                "expires": "tomorrow",
                "max_age": 612000,
                "httponly": True,
                "samesite": "Lax",
                "secure": True,
            },
            "preferred_language": other_cookie.copy(),
        })

        make_sid_cookie_session_only(manager)

        self.assertEqual(manager.cookies["sid"], {
            "value": "opaque-session-value",
            "expires": None,
            "max_age": None,
            "httponly": True,
            "samesite": "Lax",
            "secure": True,
        })
        self.assertEqual(manager.cookies["preferred_language"], other_cookie)

    def test_missing_sid_is_a_no_op(self):
        cookies = {"full_name": {"value": "CRM User", "max_age": 60}}
        manager = _CookieManager(cookies.copy())

        make_sid_cookie_session_only(manager)

        self.assertEqual(manager.cookies, cookies)

    def test_malformed_sid_is_a_no_op(self):
        manager = _CookieManager({"sid": "not-cookie-options"})

        make_sid_cookie_session_only(manager)

        self.assertEqual(manager.cookies, {"sid": "not-cookie-options"})


if __name__ == "__main__":
    unittest.main()
