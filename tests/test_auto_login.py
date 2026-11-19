"""离线回归检查：不访问校园网、不修改系统计划任务。"""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "auto_login.py"
spec = importlib.util.spec_from_file_location("auto_login", SOURCE)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def valid_config():
    return dict(app.DEFAULT_CONFIG, username="test-user", password_scheme="plain",
                password="test-password")


class ConfigTests(unittest.TestCase):
    def test_frozen_config_lives_next_to_executable(self):
        with tempfile.TemporaryDirectory(prefix="campus test ") as directory:
            exe = os.path.join(directory, "HHUCampusAutoLogin.exe")
            with mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(sys, "executable", exe):
                frozen_spec = importlib.util.spec_from_file_location("frozen_app", SOURCE)
                frozen_app = importlib.util.module_from_spec(frozen_spec)
                frozen_spec.loader.exec_module(frozen_app)
            self.assertEqual(frozen_app.CONFIG_FILE, os.path.join(directory, "config.json"))
            self.assertEqual(frozen_app.LOG_DIR, os.path.join(directory, "logs"))

    def test_setup_does_not_save_empty_credentials(self):
        with mock.patch.object(app, "load_json", return_value=app.DEFAULT_CONFIG.copy()), \
                mock.patch("builtins.input", return_value=""), \
                mock.patch.object(app.getpass, "getpass", return_value=""), \
                mock.patch.object(app, "save_json") as save, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.cmd_setup(), 2)
            save.assert_not_called()

    def test_invalid_task_intervals_are_rejected(self):
        for interval in (0, 1440, "2", True, 1.5):
            with self.subTest(interval=interval):
                with self.assertRaises(ValueError):
                    app.validate_config(dict(valid_config(), interval_minutes=interval))

    def test_uninstall_does_not_need_config(self):
        with mock.patch.object(sys, "argv", ["auto_login.py", "uninstall"]), \
                mock.patch.object(app, "setup_logging"), \
                mock.patch.object(app, "load_json", side_effect=AssertionError("config read")), \
                mock.patch.object(app, "cmd_uninstall", return_value=0) as uninstall:
            self.assertEqual(app.main(), 0)
            uninstall.assert_called_once_with(app.DEFAULT_TASK_NAME)

    @unittest.skipUnless(app.IS_WINDOWS, "Windows DPAPI only")
    def test_dpapi_round_trip(self):
        value = "test-password-密码".encode("utf-8")
        encrypted = app.dpapi(value)
        self.assertNotEqual(encrypted, value)
        self.assertEqual(app.dpapi(encrypted, decrypt=True), value)


class TaskTests(unittest.TestCase):
    def test_frozen_task_runs_hidden_worker_and_reports_trial_failure(self):
        with tempfile.TemporaryDirectory(prefix="campus test ") as directory:
            worker = Path(directory) / "HHUCampusAutoLogin-background.exe"
            worker.touch()
            output = io.StringIO()
            with mock.patch.object(app, "BASE_DIR", directory), \
                    mock.patch.object(app, "IS_WINDOWS", True), \
                    mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(app.subprocess, "run", return_value=
                                      subprocess.CompletedProcess([], 0, b"", b"")) as run, \
                    mock.patch.object(app, "cmd_login", return_value=1), \
                    contextlib.redirect_stdout(output):
                self.assertEqual(app.cmd_install(valid_config()), 0)
            command = run.call_args.args[0]
            self.assertEqual(command[command.index("/TR") + 1], '"%s"' % worker)
            self.assertIn("本次认证未成功", output.getvalue())

    def test_frozen_task_without_worker_uses_current_executable(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "executable", r"C:\Program Files\Campus\app.exe"), \
                mock.patch.object(app.os.path, "isfile", return_value=False), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app._task_command(), '"C:\\Program Files\\Campus\\app.exe"')

    def test_source_task_includes_script(self):
        with mock.patch.object(sys, "frozen", False, create=True), \
                mock.patch.object(app, "_pythonw", return_value=r"C:\Python\pythonw.exe"):
            self.assertEqual(app._task_command(), '"C:\\Python\\pythonw.exe" "%s"' % SOURCE)


class PortalTests(unittest.TestCase):
    def test_system_proxies_are_disabled(self):
        fake_opener = mock.Mock()
        with mock.patch.object(app.urllib.request, "build_opener", return_value=fake_opener) as build:
            app.Portal(valid_config())._request("http://10.96.0.155/eportal/", data=b"test")
        handlers = build.call_args.args
        self.assertTrue(any(isinstance(handler, app.urllib.request.ProxyHandler)
                            and handler.proxies == {} for handler in handlers))

    def test_stale_cached_query_is_not_used_to_log_in(self):
        portal = mock.Mock()
        portal.on_campus.return_value = True
        portal.is_online.return_value = False
        portal.discover_query_string.return_value = ""
        with mock.patch.object(app, "Portal", return_value=portal), \
                mock.patch.object(app, "load_json", return_value={"queryString": "wlanuserip=old"}):
            self.assertEqual(app.cmd_login(valid_config()), 1)
        portal.login.assert_not_called()

    def test_discovered_query_parameter_order_is_preserved(self):
        query = "nasip=example&wlanuserip=current&wlanacname=example"
        portal = mock.Mock()
        portal.on_campus.return_value = True
        portal.is_online.return_value = False
        portal.discover_query_string.return_value = query
        portal.login.return_value = {"result": "fail", "message": "test failure"}
        with mock.patch.object(app, "Portal", return_value=portal), \
                mock.patch.object(app, "load_json", return_value={}):
            self.assertEqual(app.cmd_login(valid_config()), 1)
        portal.login.assert_called_once_with(query)


if __name__ == "__main__":
    unittest.main()
