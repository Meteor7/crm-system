"""The ClamAV client's deadline and a request's scan budget, without a database or a real clamd."""

import socket
import threading
import time
from unittest import TestCase
from unittest.mock import patch

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import file_security
from rayher_crm.services.file_security import (
    REQUEST_SCAN_BUDGET_SECONDS,
    SCAN_BUDGET_MESSAGE,
    SCAN_TIMEOUT_SECONDS,
    TXT_MIME,
    ClamdScanner,
    scan_content,
    validate_and_scan,
)


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class _RecordingScanner:
    """Stands in for ClamdScanner and records the timeout it was given."""

    made: list = []

    def __init__(self, timeout=SCAN_TIMEOUT_SECONDS):
        self.timeout = timeout
        _RecordingScanner.made.append(self)

    def scan(self, content):
        return True


class TestClamdDeadline(TestCase):
    def test_a_clamd_that_keeps_trickling_cannot_outlast_the_whole_scan_deadline(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        stop = threading.Event()

        def trickle():
            connection, _ = server.accept()
            with connection:
                try:
                    connection.recv(65536)
                    while not stop.is_set():
                        connection.sendall(b"s")
                        time.sleep(0.05)
                except OSError:
                    return

        thread = threading.Thread(target=trickle, daemon=True)
        thread.start()
        self.addCleanup(server.close)
        self.addCleanup(stop.set)
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            ClamdScanner("127.0.0.1", server.getsockname()[1], timeout=0.5).scan(b"x" * 10)
        # Each read alone would succeed within its own timeout; only a whole-scan deadline ends this.
        self.assertLess(time.monotonic() - started, 2.0)


class TestRequestScanBudget(TestCase):
    def setUp(self):
        _RecordingScanner.made = []
        self.clock = _Clock()
        for target in (
            patch.object(file_security.time, "monotonic", self.clock),
            patch.object(file_security, "ClamdScanner", _RecordingScanner),
        ):
            target.start()
            self.addCleanup(target.stop)
        self.addCleanup(self._forget_deadline)

    def _forget_deadline(self):
        try:
            del frappe.local.crm_scan_deadline
        except AttributeError:
            pass

    def _in_request(self):
        context = patch.object(frappe.local, "request", object(), create=True)
        context.start()
        self.addCleanup(context.stop)

    def test_outside_a_request_each_scan_has_the_full_timeout(self):
        self._forget_deadline()
        with patch.object(frappe.local, "request", None, create=True):
            for _ in range(3):
                self.clock.now += 50
                self.assertTrue(scan_content(b"x"))
        self.assertEqual([made.timeout for made in _RecordingScanner.made], [SCAN_TIMEOUT_SECONDS] * 3)

    def test_the_scans_of_one_request_share_its_budget(self):
        self._in_request()
        scan_content(b"one")
        self.clock.now += 50
        scan_content(b"two")
        self.clock.now += REQUEST_SCAN_BUDGET_SECONDS - 50
        with self.assertRaises(CrmApiException) as caught:
            validate_and_scan("three.txt", TXT_MIME, b"three")
        self.assertEqual((caught.exception.code, caught.exception.public_message), ("VALIDATION_ERROR", SCAN_BUDGET_MESSAGE))
        self.assertEqual([made.timeout for made in _RecordingScanner.made], [SCAN_TIMEOUT_SECONDS, REQUEST_SCAN_BUDGET_SECONDS - 50])

    def test_a_scan_the_budget_cuts_short_asks_for_fewer_files(self):
        self._in_request()
        clock = self.clock
        scan_content(b"first")
        clock.now += REQUEST_SCAN_BUDGET_SECONDS - 10

        class _Slow(_RecordingScanner):
            def scan(self, content):
                clock.now += self.timeout
                raise TimeoutError("timed out")

        with patch.object(file_security, "ClamdScanner", _Slow), self.assertRaises(CrmApiException) as caught:
            validate_and_scan("late.txt", TXT_MIME, b"late")
        self.assertEqual(caught.exception.public_message, SCAN_BUDGET_MESSAGE)

    def test_clamd_itself_timing_out_is_still_the_scanner_being_unavailable(self):
        self._in_request()
        clock = self.clock

        class _Slow(_RecordingScanner):
            def scan(self, content):
                clock.now += self.timeout
                raise TimeoutError("timed out")

        with patch.object(file_security, "ClamdScanner", _Slow), self.assertRaises(CrmApiException) as caught:
            validate_and_scan("slow.txt", TXT_MIME, b"slow")
        self.assertEqual((caught.exception.code, caught.exception.public_message), ("INTERNAL_ERROR", "File security scanner is unavailable."))

    def test_a_new_request_starts_a_new_budget(self):
        self._in_request()
        scan_content(b"first")
        self.clock.now += REQUEST_SCAN_BUDGET_SECONDS * 2
        # The next request on this thread (the patch from _in_request puts the attribute back afterwards).
        frappe.local.request = object()
        self.assertTrue(scan_content(b"next request"))
        self.assertEqual(_RecordingScanner.made[-1].timeout, SCAN_TIMEOUT_SECONDS)

    def test_a_given_scanner_is_used_as_it_is(self):
        self._in_request()
        self.clock.now += REQUEST_SCAN_BUDGET_SECONDS * 2

        class _Given:
            def scan(self, content):
                return False

        self.assertFalse(scan_content(b"x", _Given()))
