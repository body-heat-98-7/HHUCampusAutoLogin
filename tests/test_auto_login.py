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
            commands = [c.args[0] for c in run.call_args_list if c.args]
            create = next(c for c in commands if "/Create" in c and "/TR" in c)
            self.assertEqual(create[create.index("/TR") + 1], '"%s"' % worker)
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


class CampusDetectionTests(unittest.TestCase):
    """开了 Clash TUN 之后，「路由到门户时的源地址」会变成 198.18.0.1，
    不能再拿它判断是否在校园网，否则自动登录会静默失效。"""

    def _cfg(self):
        cfg = valid_config()
        cfg["campus_ssid"] = "Hohai University"
        return cfg

    def test_on_campus_true_when_ssid_matches(self):
        portal = app.Portal(self._cfg())
        with mock.patch.object(app, "current_ssid", return_value="Hohai University"), \
                mock.patch.object(app, "wlan_ip", return_value="10.113.69.145"):
            self.assertTrue(portal.on_campus())

    def test_on_campus_false_on_other_network(self):
        portal = app.Portal(self._cfg())
        with mock.patch.object(app, "current_ssid", return_value="体温电台"), \
                mock.patch.object(app, "wlan_ip", return_value="172.20.10.2"):
            self.assertFalse(portal.on_campus())

    def test_on_campus_does_not_skip_dhcp_when_lease_expired(self):
        """连着校园 SSID 但 DHCP 租约过期、拿不到 IP 时，必须先去修 DHCP。

        真实事故（2026-11-20 开机）：SSID 匹配就直接返回 True，跳过了 DHCP 重取，
        结果本机没有 IP，认证必然失败，日志里反复「拿不到 queryString」。"""
        portal = app.Portal(self._cfg())
        with mock.patch.object(app, "current_ssid", return_value="Hohai University"), \
                mock.patch.object(app, "wlan_ip", return_value="172.20.10.2"), \
                mock.patch.object(portal, "_renew_dhcp", return_value=False) as renew:
            self.assertFalse(portal.on_campus())
        renew.assert_called_once()

    def test_on_campus_recovers_after_dhcp_renew(self):
        """重取到校园网 IP 之后应当正常返回 True。"""
        portal = app.Portal(self._cfg())
        with mock.patch.object(app, "current_ssid", return_value="Hohai University"), \
                mock.patch.object(app, "wlan_ip",
                                  side_effect=["172.20.10.2", "10.113.69.145"]), \
                mock.patch.object(portal, "_renew_dhcp", return_value=True):
            self.assertTrue(portal.on_campus())

    def test_on_campus_uses_adapter_ip_not_tun_ip(self):
        """TUN 开启时 local_ip() 是 198.18.0.1，但 wlan_ip() 应是真实网卡地址。"""
        portal = app.Portal(self._cfg())
        with mock.patch.object(app, "current_ssid", return_value="体温电台"), \
                mock.patch.object(app, "wlan_ip", return_value="10.113.69.145"), \
                mock.patch.object(portal, "local_ip", return_value="198.18.0.1"), \
                mock.patch.object(app.socket, "create_connection") as conn:
            self.assertTrue(portal.on_campus())
        conn.assert_called()




class InterceptProbeTests(unittest.TestCase):
    """认证前校园网 DNS 被封，只能靠纯 IP 探测拿 queryString。

    真实事故（2026-11-20）：脚本用域名探测，getaddrinfo 全失败；
    改用 urllib 访问 IP 时又被网关 RST（WinError 10054），最后用裸 socket 才拿到。
    """

    def test_uses_ip_probe_before_dns_probe(self):
        cfg = valid_config()
        cfg["campus_ssid"] = "Hohai University"
        portal = app.Portal(cfg)
        body = ("HTTP/1.1 200 OK\r\n\r\n<script>top.self.location.href="
                "'http://eportal.hhu.edu.cn/eportal/index.jsp?wlanuserip=ABC123&nasip=DEF</script>")
        calls = []

        def fake_raw(ip, host=None, timeout=4):
            calls.append(ip)
            if ip == "223.5.5.5":
                raise OSError("reset")
            return body

        with mock.patch.object(portal, "_http_get_raw", side_effect=fake_raw):
            qs = portal.discover_query_string()

        self.assertIn("wlanuserip=ABC123", qs)
        self.assertEqual(calls[0], "223.5.5.5", "首个探测必须是纯 IP，不能依赖 DNS")

    def test_falls_through_when_no_intercept(self):
        cfg = valid_config()
        portal = app.Portal(cfg)
        with mock.patch.object(portal, "_http_get_raw", return_value="HTTP/1.1 200 OK\r\n\r\nhello"):
            qs = portal.discover_query_string()
        self.assertEqual(qs, "")



class BootStartupTests(unittest.TestCase):
    """开机启动项：引用的文件不存在时绝不能写，否则开机会弹「找不到文件」。

    真实事故（2026-11-27）：vbs 里写的是早已删除的 .venv\\Scripts\\python.exe，
    而且没带脚本路径，每次开机都弹一次文件缺失窗口。
    """

    def test_skips_vbs_when_referenced_file_missing(self):
        with tempfile.TemporaryDirectory(prefix="boot vbs ") as directory:
            startup = os.path.join(directory, "Startup")
            out = io.StringIO()
            with mock.patch.object(app, "STARTUP_DIR", startup), \
                    mock.patch.object(app, "IS_WINDOWS", True), \
                    mock.patch.object(app, "_task_command",
                                      return_value='"C:\\nope\\pythonw.exe" "C:\\nope\\auto_login.py"'), \
                    mock.patch.object(app, "_run",
                                      return_value=subprocess.CompletedProcess([], 0, b"", b"")), \
                    mock.patch.object(app, "cmd_login", return_value=0), \
                    contextlib.redirect_stdout(out):
                app.cmd_install(valid_config())
            self.assertFalse(os.path.exists(os.path.join(startup, app.BOOT_VBS)))
            self.assertIn("开机启动项未创建", out.getvalue())

    def test_vbs_contains_file_guard(self):
        with tempfile.TemporaryDirectory(prefix="boot vbs2 ") as directory:
            startup = os.path.join(directory, "Startup")
            fake_py = os.path.join(directory, "pythonw.exe")
            fake_script = os.path.join(directory, "auto_login.py")
            open(fake_py, "wb").close()
            open(fake_script, "wb").close()
            with mock.patch.object(app, "STARTUP_DIR", startup), \
                    mock.patch.object(app, "IS_WINDOWS", True), \
                    mock.patch.object(app, "_task_command",
                                      return_value='"%s" "%s"' % (fake_py, fake_script)), \
                    mock.patch.object(app, "_run",
                                      return_value=subprocess.CompletedProcess([], 0, b"", b"")), \
                    mock.patch.object(app, "cmd_login", return_value=0), \
                    contextlib.redirect_stdout(io.StringIO()):
                app.cmd_install(valid_config())
            path = os.path.join(startup, app.BOOT_VBS)
            self.assertTrue(os.path.exists(path))
            text = open(path, encoding="utf-8").read()
            self.assertIn("FileExists", text, "vbs 必须自带文件校验，缺文件时静默退出")
            self.assertIn(" boot", text)
if __name__ == "__main__":
    unittest.main()
