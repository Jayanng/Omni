"""Unit tests for the Omni Actions Engine (1:1 CLI to UI parity)."""

from __future__ import annotations

import unittest

from omni.actions import (
    TerminalLogBuffer,
    WebDaemonManager,
    run_report,
)


class TestTerminalLogBuffer(unittest.TestCase):
    def test_buffer_append_and_clear(self):
        buf = TerminalLogBuffer(maxlen=10)
        buf.clear()
        self.assertEqual(len(buf.get_all()), 1)  # contains "Console cleared"

        buf.append("test line 1")
        buf.append("test line 2")
        logs = buf.get_all()
        self.assertIn("test line 1", logs)
        self.assertIn("test line 2", logs)

    def test_buffer_extend(self):
        buf = TerminalLogBuffer(maxlen=10)
        buf.extend(["line A", "line B", "line C"])
        logs = buf.get_all()
        self.assertIn("line A", logs)
        self.assertIn("line B", logs)
        self.assertIn("line C", logs)


class TestWebDaemonManager(unittest.TestCase):
    def test_daemon_status_schema(self):
        mgr = WebDaemonManager()
        st = mgr.status()
        self.assertTrue(st["ok"])
        self.assertFalse(st["running"])
        self.assertIn("interval", st)
        self.assertIn("cycles_completed", st)
        self.assertIn("last_action", st)

    def test_daemon_stop_when_idle(self):
        mgr = WebDaemonManager()
        res = mgr.stop()
        self.assertTrue(res["ok"])
        self.assertFalse(res["running"])


class TestActionsReport(unittest.TestCase):
    def test_report_structure(self):
        res = run_report()
        self.assertTrue(res["ok"])
        self.assertIn("metrics", res)
        self.assertIn("files", res)
        self.assertIn("logs", res)

        metrics = res["metrics"]
        self.assertIn("runs", metrics)
        self.assertIn("risk_violation_rate", metrics)
        self.assertIn("protective_action_share", metrics)


if __name__ == "__main__":
    unittest.main()
