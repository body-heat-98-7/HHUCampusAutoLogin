"""离线回归检查：不访问校园网、不修改系统计划任务。"""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "auto_login.py"
spec = importlib.util.spec_from_file_location("auto_login", SOURCE)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def valid_config():
    return dict(app.DEFAULT_CONFIG, username="test-user", password_scheme="plain",
                password="test-password")


class OutputTests(unittest.TestCase):
    def test_help_is_utf8_on_english_windows_output_streams(self):
        output_bytes = io.BytesIO()
        error_bytes = io.BytesIO()
        output = io.TextIOWrapper(output_bytes, encoding="cp1252")
        errors = io.TextIOWrapper(error_bytes, encoding="cp1252")
        with mock.patch.object(sys, "stdout", output), \
                mock.patch.object(sys, "stderr", errors), \
                mock.patch.object(sys, "argv", ["HHUCampusAutoLogin.exe", "--help"]), \
                mock.patch.object(app, "Portal", side_effect=AssertionError("network access")):
            with self.assertRaises(SystemExit) as result:
                app.run()
        output.flush()
        self.assertEqual(result.exception.code, 0)
        self.assertIn("河海大学校园网自动认证", output_bytes.getvalue().decode("utf-8"))
        self.assertEqual(errors.encoding, "utf-8")

    def test_hidden_worker_tolerates_missing_output_streams(self):
        with mock.patch.object(sys, "stdout", None), \
                mock.patch.object(sys, "stderr", None), \
                mock.patch.object(sys, "argv", ["HHUCampusAutoLogin-background.exe", "--help"]):
            with self.assertRaises(SystemExit) as result:
                app.run()
        self.assertEqual(result.exception.code, 0)


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


class WlanDetectionTests(unittest.TestCase):
    """netsh 输出编码随系统代码页变化，解码错会让"已连接"被误判成"未连接"，
    进而反复重连、把正常连接打断（v1.0.4 修复的真实事故）。"""

    @staticmethod
    def _fake_run(payload):
        return mock.patch.object(app, "_run",
                                 return_value=mock.Mock(stdout=payload, returncode=0))

    def test_connected_state_from_utf8_chinese_output(self):
        payload = "系统上有 1 个接口\n\n    状态 : 已连接\n    SSID : Hohai University\n".encode("utf-8")
        with self._fake_run(payload):
            self.assertTrue(app.wlan_connected())

    def test_connected_state_from_gbk_chinese_output(self):
        payload = "系统上有 1 个接口\n\n    状态 : 已连接\n    SSID : Hohai University\n".encode("gbk")
        with self._fake_run(payload):
            self.assertTrue(app.wlan_connected())

    def test_connected_state_from_english_output(self):
        payload = "    State                  : connected\n    SSID : Hohai University\n".encode("ascii")
        with self._fake_run(payload):
            self.assertTrue(app.wlan_connected())

    def test_disconnected_state_is_detected(self):
        with self._fake_run("    State                  : disconnected\n".encode("ascii")):
            self.assertFalse(app.wlan_connected())

    def test_unknown_output_does_not_force_reconnect(self):
        # 拿不到状态时必须保守当作"已连接"，否则会误断用户的网络
        with self._fake_run(b""):
            self.assertTrue(app.wlan_connected())

    def test_ssid_is_read_from_gbk_output(self):
        with self._fake_run("    SSID                   : Hohai University\n".encode("gbk")):
            self.assertEqual(app.current_ssid(), "Hohai University")

    def test_ensure_wifi_does_not_touch_an_existing_connection(self):
        with mock.patch.object(app, "wlan_connected", return_value=True), \
                mock.patch.object(app, "current_ssid", return_value="Hohai University"), \
                mock.patch.object(app, "_run") as run:
            self.assertFalse(app.ensure_wifi(valid_config()))
        run.assert_not_called()


class CampusDetectionTests(unittest.TestCase):
    """开了 Clash TUN 之后，「路由到门户时的源地址」会变成 198.18.0.1，
    不能再拿它判断是否在校园网，否则自动登录会静默失效。"""

    def _cfg(self):
        cfg = valid_config()
        cfg["campus_ssid"] = "Hohai University"
        return cfg

    def test_on_campus_true_when_ssid_matches(self):
        portal = app.Portal(self._cfg())
        with mock.patch.object(app, "current_ssid", return_value="Hohai University"):
            self.assertTrue(portal.on_campus())

    def test_on_campus_false_on_other_network(self):
        portal = app.Portal(self._cfg())
        with mock.patch.object(app, "current_ssid", return_value="体温电台"), \
                mock.patch.object(app, "wlan_ip", return_value="172.20.10.2"):
            self.assertFalse(portal.on_campus())

    def test_on_campus_uses_adapter_ip_not_tun_ip(self):
        """TUN 开启时 local_ip() 是 198.18.0.1，但 wlan_ip() 应是真实网卡地址。"""
        portal = app.Portal(self._cfg())
        with mock.patch.object(app, "current_ssid", return_value="体温电台"), \
                mock.patch.object(app, "wlan_ip", return_value="10.113.69.145"), \
                mock.patch.object(portal, "local_ip", return_value="198.18.0.1"), \
                mock.patch.object(app.socket, "create_connection") as conn:
            self.assertTrue(portal.on_campus())
        conn.assert_called()



class WifiAutoConnectTests(unittest.TestCase):
    """WiFi 断开后连回校园网的三条安全约束。

    背景：v1.0.7/v1.0.8 曾有严重 bug —— WiFi 重连瞬间读不到 SSID，
    脚本误判成"完全没连网络"，强行切到校园网，抢走用户正在用的手机热点，
    而且每次切换又触发"网络已连接"事件，形成反复重连的死循环。
    """

    def _cfg(self, **kw):
        cfg = valid_config()
        cfg["campus_ssid"] = "Hohai University"
        cfg.update(kw)
        return cfg

    def test_does_nothing_when_already_connected(self):
        """已连着任何网络（热点/校园网）时绝不插手。"""
        with mock.patch.object(app, "wlan_connected", return_value=True), \
                mock.patch.object(app, "_run") as run:
            self.assertFalse(app.ensure_wifi(self._cfg()))
        run.assert_not_called()

    def test_waits_and_skips_when_connection_recovers(self):
        """断开不满 5 秒就自己连回来了，不抢。"""
        with mock.patch.object(app, "wlan_connected", side_effect=[False, True]), \
                mock.patch.object(app.time, "sleep"), \
                mock.patch.object(app, "_run") as run:
            self.assertFalse(app.ensure_wifi(self._cfg()))
        run.assert_not_called()

    def test_rate_limited(self):
        """60 秒内只尝试一次，避免反复切网。"""
        with mock.patch.object(app, "wlan_connected", return_value=False), \
                mock.patch.object(app.time, "sleep"), \
                mock.patch.object(app, "campus_ssid_visible", return_value=True), \
                mock.patch.object(app, "load_json",
                                  return_value={"wifi_connect_attempt": time.time()}), \
                mock.patch.object(app, "save_json"), \
                mock.patch.object(app, "_run") as run:
            self.assertFalse(app.ensure_wifi(self._cfg()))
        run.assert_not_called()

    def test_can_be_disabled_via_config(self):
        with mock.patch.object(app, "wlan_connected", return_value=False), \
                mock.patch.object(app, "_run") as run:
            self.assertFalse(app.ensure_wifi(self._cfg(auto_connect_wifi=False)))
        run.assert_not_called()

    def test_connects_when_truly_disconnected(self):
        """真的断开且持续 5 秒、不在冷却期、能扫到校园网 → 才去连。"""
        with mock.patch.object(app, "wlan_connected", side_effect=[False, False, True]), \
                mock.patch.object(app.time, "sleep"), \
                mock.patch.object(app, "campus_ssid_visible", return_value=True), \
                mock.patch.object(app, "load_json", return_value={}), \
                mock.patch.object(app, "save_json"), \
                mock.patch.object(app, "_run") as run:
            self.assertTrue(app.ensure_wifi(self._cfg()))
        run.assert_called_once()
if __name__ == "__main__":
    unittest.main()
