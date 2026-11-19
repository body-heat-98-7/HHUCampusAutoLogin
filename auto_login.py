#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HHUCampusAutoLogin — 河海大学校园网自动认证

适用于锐捷 RG-SAM+ ePortal（http://eportal.hhu.edu.cn/eportal/）。
纯标准库实现，不需要浏览器、不需要第三方依赖。

用法：
    python auto_login.py                 巡检一次：在线就退出，掉线就认证
    python auto_login.py setup           首次配置（学号 / 密码 / 运营商）
    python auto_login.py install         安装计划任务，每 N 分钟自动巡检
    python auto_login.py uninstall       删除计划任务
    python auto_login.py logout          主动下线（测试用）
    python auto_login.py check           只检测状态，不认证

可选参数：
    --verbose   输出调试日志
    --force     忽略"已在线"，强制重新认证
    --task-name 自定义计划任务名（默认 HHUCampusAutoLogin）

MIT License
"""

import argparse
import base64
import getpass
import json
import logging
import os
import platform
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from logging.handlers import RotatingFileHandler

APP_NAME = "HHUCampusAutoLogin"
DEFAULT_TASK_NAME = APP_NAME
IS_WINDOWS = platform.system().lower() == "windows"

BASE_DIR = os.path.dirname(os.path.abspath(
    sys.executable if getattr(sys, "frozen", False) else __file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
CACHE_FILE = os.path.join(BASE_DIR, "cache.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "auto_login.log")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

log = logging.getLogger("campus")

# 常州校区门户的四个服务名（setup 时可改）
KNOWN_SERVICES = [
    ("校园网 (Campus NET)", "校园外网服务(out-campus NET)"),
    ("中国移动 (CMCC NET)", "中国移动(CMCC NET)"),
    ("中国电信 (CTCC NET)", "中国电信(常州)"),
    ("中国联通 (CUCC NET)", "中国联通(常州)"),
]

DEFAULT_CONFIG = {
    "portal_host": "eportal.hhu.edu.cn",
    "portal_ip": "10.96.0.155",
    "campus_ip_prefix": "10.",
    "username": "",
    "password_scheme": "dpapi",   # dpapi | plain
    "password": "",
    "service": "校园外网服务(out-campus NET)",
    "campus_ssid": "Hohai University",
    "interval_minutes": 2,
}


# ================================================================= 基础工具
def setup_logging(verbose=False, quiet_without_console=True):
    os.makedirs(LOG_DIR, exist_ok=True)
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    if not log.handlers:
        fh = RotatingFileHandler(LOG_FILE, maxBytes=256 * 1024, backupCount=2, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
        # 计划任务用 pythonw 运行时没有控制台
        if sys.stdout is not None and not (quiet_without_console and sys.stdout is None):
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(fmt)
            log.addHandler(sh)


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def current_ssid():
    """当前连着的 WiFi 名字；未连接或非 Windows 返回空串。"""
    if not IS_WINDOWS:
        return ""
    try:
        out = subprocess.run(["netsh", "wlan", "show", "interfaces"],
                             capture_output=True, timeout=10).stdout
        m = re.search(r"^\s*SSID\s*:\s*(.+)$", out.decode("gbk", "replace"), re.M)
        return m.group(1).strip() if m else ""
    except Exception:
        return ""


def validate_config(cfg, require_credentials=True):
    """在联网或安装任务前检查常见的配置错误。"""
    for key in ("portal_host", "portal_ip", "service"):
        if not isinstance(cfg.get(key), str) or not cfg[key].strip():
            raise ValueError("配置项 %s 不能为空" % key)
    minutes = cfg.get("interval_minutes")
    if type(minutes) is not int or not 1 <= minutes <= 1439:
        raise ValueError("interval_minutes 必须是 1 到 1439 的整数")
    if cfg.get("password_scheme") not in ("dpapi", "plain"):
        raise ValueError("password_scheme 必须是 dpapi 或 plain")
    if require_credentials:
        for key in ("username", "password"):
            if not isinstance(cfg.get(key), str) or not cfg[key].strip():
                raise ValueError("账号或密码为空，请重新运行配置向导")


# ================================================================= 密码保护
def dpapi(data, decrypt=False):
    """Windows DPAPI：用当前用户凭据加密，换机器/换用户都解不开。"""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    blob_in = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)),
                                               ctypes.POINTER(ctypes.c_ubyte)))
    blob_out = DATA_BLOB()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    fn = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    fn.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                   ctypes.POINTER(DATA_BLOB)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def get_password(cfg):
    raw = cfg.get("password", "")
    if not raw:
        return ""
    if cfg.get("password_scheme") == "dpapi":
        if not IS_WINDOWS:
            raise RuntimeError("配置里的密码是用 Windows DPAPI 加密的，非 Windows 平台请改用 plain")
        return dpapi(base64.b64decode(raw), decrypt=True).decode("utf-8")
    return raw


def set_password(cfg, password):
    if IS_WINDOWS:
        cfg["password_scheme"] = "dpapi"
        cfg["password"] = base64.b64encode(dpapi(password.encode("utf-8"))).decode("ascii")
    else:
        cfg["password_scheme"] = "plain"
        cfg["password"] = password


# ================================================================= 门户客户端
class Portal:
    def __init__(self, cfg):
        self.cfg = cfg
        self.host = cfg["portal_host"]
        self.ip = cfg["portal_ip"]
        self.base = "http://%s" % self.ip          # 直连 IP：掉线时 DNS 往往不可用
        self.index_url = self.base + "/eportal/index.jsp"
        self.login_api = self.base + "/eportal/InterFace.do?method=login"
        self.keepalive_api = self.base + "/eportal/InterFace.do?method=keepalive"
        self.logout_api = self.base + "/eportal/InterFace.do?method=logout"

    # ---------------------------------------------------------- HTTP
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    def _request(self, url, data=None, follow=True, timeout=8, host=None):
        # 校园认证需要直接访问网关，不能经过系统代理。
        handlers = [urllib.request.ProxyHandler({})]
        if not follow:
            handlers.append(self._NoRedirect)
        opener = urllib.request.build_opener(*handlers)
        headers = {"User-Agent": UA}
        if host:
            headers["Host"] = host
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        req = urllib.request.Request(url, data=data, headers=headers)
        return opener.open(req, timeout=timeout)

    # ---------------------------------------------------------- 状态
    def local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((self.ip, 80))
            return s.getsockname()[0]
        except Exception:
            return ""
        finally:
            s.close()

    def on_campus(self):
        ip = self.local_ip()
        if not ip.startswith(self.cfg.get("campus_ip_prefix", "10.")):
            # 从手机热点切回校园网时，Windows 会拿旧租约去续，常被 DHCP 服务器拒绝
            # （DHCPNAK），表现就是"连上 WiFi 了但一直没有 IP"。这里主动重取一次。
            if self._renew_dhcp(ip):
                ip = self.local_ip()
            if not ip.startswith(self.cfg.get("campus_ip_prefix", "10.")):
                log.debug("本机地址 %s 不在校园网段，跳过", ip or "未知")
                return False
        for target in (self.ip, self.host):
            try:
                with socket.create_connection((target, 80), timeout=3):
                    return True
            except Exception:
                continue
        return False

    def _renew_dhcp(self, ip):
        """只在"确实连在校园 SSID 上、但 IP 不属于校园网段"时动 DHCP。"""
        wanted = (self.cfg.get("campus_ssid") or "").strip()
        ssid = current_ssid()
        if not wanted or ssid != wanted:
            return False
        log.info("已连上 %s，但 IP 是 %s，尝试重新获取 DHCP 租约", ssid, ip or "无")
        try:
            subprocess.run(["ipconfig", "/release"], capture_output=True, timeout=20)
            subprocess.run(["ipconfig", "/renew"], capture_output=True, timeout=45)
        except Exception as e:
            log.debug("ipconfig 执行失败: %s", e)
            return False
        prefix = self.cfg.get("campus_ip_prefix", "10.")
        deadline = time.time() + 25
        while time.time() < deadline:
            if self.local_ip().startswith(prefix):
                log.info("已重新拿到校园网 IP")
                return True
            time.sleep(2)
        log.warning("重新获取 IP 超时")
        return False

    def is_online(self, timeout=5):
        for url in ("http://connect.rom.miui.com/generate_204",
                    "http://edge-http.microsoft.com/captiveportal/generate_204"):
            try:
                with self._request(url, timeout=timeout) as r:
                    if r.status == 204:      # 只有 204 才算真在线
                        return True
            except Exception:
                continue
        return False

    # ---------------------------------------------------------- 参数
    @staticmethod
    def _extract_qs(text):
        if not text:
            return ""
        for pat in (re.compile(r"index\.jsp\?([^'\"\s<>]+)"),
                    re.compile(r"(wlanuserip=[^'\"\s<>]+)")):
            m = pat.search(text)
            if m:
                return m.group(1) if m.groups() else m.group(0)
        return ""

    def discover_query_string(self):
        """掉线时网关会把 HTTP 请求换成跳转页，里面带着绑定本机 IP 的 queryString。"""
        for url, host in (("http://connect.rom.miui.com/generate_204", None),
                          ("http://www.baidu.com/", None),
                          (self.index_url, self.host)):
            try:
                with self._request(url, follow=False, timeout=6, host=host) as r:
                    loc = r.headers.get("Location") or ""
                    qs = self._extract_qs(loc)
                    if qs:
                        log.info("从重定向头拿到 queryString")
                        return qs
                    if r.status == 200:
                        qs = self._extract_qs(r.read(4096).decode("utf-8", "replace"))
                        if qs:
                            log.info("从网关跳转页拿到 queryString")
                            return qs
            except urllib.error.HTTPError as e:
                qs = self._extract_qs(e.headers.get("Location") or "")
                if qs:
                    log.info("从重定向头拿到 queryString")
                    return qs
            except Exception as e:
                log.debug("探测 %s 失败: %s", url, e)
        return ""

    @staticmethod
    def enc(s):
        """门户页面用的是 encodeURIComponent 两次。"""
        return urllib.parse.quote(urllib.parse.quote(s, safe=""), safe="")

    # ---------------------------------------------------------- 动作
    def login(self, query_string):
        cfg = self.cfg
        body = ("userId=" + self.enc(cfg["username"]) +
                "&password=" + self.enc(get_password(cfg)) +
                "&service=" + self.enc(cfg.get("service", "")) +
                "&queryString=" + self.enc(query_string) +
                "&operatorPwd=&operatorUserId=&validcode=&passwordEncrypt=false")
        with self._request(self.login_api, data=body.encode(),
                           timeout=15, host=self.host) as r:
            text = r.read().decode("utf-8", "replace")
        # 门户响应可能包含 userIndex 等会话凭据，不记录完整响应。
        try:
            return json.loads(text)
        except Exception:
            return {"result": "fail", "message": text[:200]}

    def keepalive(self, user_index):
        try:
            with self._request(self.keepalive_api,
                               data=("userIndex=" + user_index).encode(),
                               timeout=8, host=self.host) as r:
                txt = r.read().decode("utf-8", "replace")
            return json.loads(txt).get("result") == "success"
        except Exception as e:
            log.debug("keepalive 失败: %s", e)
            return False

    def logout(self, user_index):
        with self._request(self.logout_api,
                           data=("userIndex=" + user_index).encode(),
                           timeout=10, host=self.host) as r:
            txt = r.read().decode("utf-8", "replace")
        try:
            return json.loads(txt)
        except Exception:
            return {"result": "fail", "message": txt[:200]}


# ================================================================= 主流程
def cmd_check(cfg, force=False):
    p = Portal(cfg)
    if not p.on_campus():
        log.debug("当前不在校园网内")
        return 0
    if p.is_online() and not force:
        log.info("网络正常")
        return 0
    log.info("当前未联网")
    return 1


def cmd_login(cfg, force=False):
    p = Portal(cfg)
    if not p.on_campus():
        log.debug("当前不在校园网内，跳过")
        return 0

    cache = load_json(CACHE_FILE)
    online = p.is_online()

    if online and not force:
        log.debug("在线正常")
        if cache.get("userIndex"):
            p.keepalive(cache["userIndex"])
        return 0

    log.info("检测到掉线，开始认证" if not online else "强制重新认证")

    # 参数绑定当前网络和本机地址；旧缓存不能用于新的认证。
    qs = p.discover_query_string()

    if not qs and online:
        # 已在线时网关不会下发参数，没必要也没办法再认证一次
        log.info("当前已在线，跳过重复认证（要换运营商请先 logout）")
        return 0
    if not qs:
        log.error("拿不到 queryString，无法认证")
        return 1

    res = p.login(qs)
    if res.get("result") == "success":
        log.info("登录成功")
        if res.get("userIndex"):
            cache["userIndex"] = res["userIndex"]
        cache["queryString"] = qs
        save_json(CACHE_FILE, cache)
        for _ in range(8):
            time.sleep(1)
            if p.is_online(timeout=3):
                log.info("网络已恢复")
                return 0
        log.warning("接口返回成功，但网络尚未恢复")
        return 1

    msg = res.get("message") or ""
    log.warning("登录失败：%s", msg)
    if "设备未注册" in msg:
        log.error("门户要求本机设备先注册：用账号在 %s 登录一次，"
                  "或在 ePortal 自助服务里添加本机 MAC", cfg["portal_host"])
    elif "服务" in msg:
        log.error("服务名不对，请双击 install.cmd 重新选择运营商，或运行程序的 setup 命令")
    elif "密码" in msg:
        log.error("账号或密码不对，请双击 install.cmd 重新填写，或运行程序的 setup 命令")
    return 1


def cmd_logout(cfg):
    cache = load_json(CACHE_FILE)
    if not cache.get("userIndex"):
        print("没有 userIndex，先运行一次认证")
        return 1
    print(Portal(cfg).logout(cache["userIndex"]))
    return 0


# ================================================================= 计划任务
def _pythonw():
    exe = sys.executable
    if IS_WINDOWS and exe.lower().endswith("python.exe"):
        cand = exe[:-len("python.exe")] + "pythonw.exe"
        if os.path.exists(cand):
            return cand
    return exe


def _task_command():
    if getattr(sys, "frozen", False):
        worker = os.path.join(BASE_DIR, APP_NAME + "-background.exe")
        if os.path.isfile(worker):
            return '"%s"' % worker
        print("提示：未找到后台程序，计划任务将使用当前程序，运行时可能显示窗口。")
        return '"%s"' % sys.executable
    return '"%s" "%s"' % (_pythonw(), os.path.abspath(__file__))




def cmd_install(cfg, task_name=DEFAULT_TASK_NAME):
    if not IS_WINDOWS:
        print("非 Windows 平台，请用 cron 定时执行本脚本，例如：\n"
              "  */2 * * * * /usr/bin/python3 %s >/dev/null 2>&1" % os.path.abspath(__file__))
        return 1

    validate_config(cfg)
    minutes = int(cfg["interval_minutes"])
    tr = _task_command()
    event_task = task_name + "-OnConnect"

    # 1) 定时兜底
    r = subprocess.run(["schtasks", "/Create", "/TN", task_name, "/TR", tr,
                        "/SC", "MINUTE", "/MO", str(minutes), "/F"],
                       capture_output=True)
    print((r.stdout + r.stderr).decode("gbk", "replace").strip())
    if r.returncode != 0:
        return 1

    # 2) 网络一连上就立刻跑一次，避免"断几秒要等下一轮巡检"
    r2 = subprocess.run(["schtasks", "/Create", "/TN", event_task, "/TR", tr,
                         "/SC", "ONEVENT",
                         "/EC", "Microsoft-Windows-NetworkProfile/Operational",
                         "/MO", "*[System[EventID=10000]]", "/F"],
                        capture_output=True)
    event_ok = r2.returncode == 0
    print((r2.stdout + r2.stderr).decode("gbk", "replace").strip())

    print("\n已安装：")
    print("  · %s —— 每 %d 分钟兜底巡检" % (task_name, minutes))
    if event_ok:
        print("  · %s —— 网络连上时立即触发（断线恢复是秒级）" % event_task)
    else:
        print("  · 事件触发器安装失败，仅靠定时巡检（最慢 %d 分钟恢复）" % minutes)

    print("\n立即试运行一次…")
    if cmd_login(cfg) != 0:
        print("提示：计划任务已安装，但本次认证未成功。请检查日志或重新配置账号。")
    return 0


def cmd_uninstall(task_name=DEFAULT_TASK_NAME):
    ok = True
    for name in (task_name, task_name + "-OnConnect"):
        r = subprocess.run(["schtasks", "/Delete", "/TN", name, "/F"], capture_output=True)
        out = (r.stdout + r.stderr).decode("gbk", "replace").strip()
        print(out)
        if r.returncode != 0 and "找不到" not in out and "cannot find" not in out.lower():
            ok = False
    return 0 if ok else 1


# ================================================================= 配置向导
def cmd_setup():
    cfg = load_json(CONFIG_FILE, DEFAULT_CONFIG.copy())
    if not isinstance(cfg, dict):
        print("配置文件格式错误，请修复 config.json 后重试。")
        return 2
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)

    print("=" * 52)
    print(" %s 配置向导" % APP_NAME)
    print("=" * 52)

    def ask(label, default=""):
        cur = cfg.get(label, default)
        tip = " [%s]" % cur if cur else ""
        val = input("%s%s: " % (label, tip)).strip()
        return val or cur

    print("\n【门户地址】一般不用改，换校区才需要")
    cfg["portal_host"] = ask("portal_host")
    cfg["portal_ip"] = ask("portal_ip")

    print("\n【账号】")
    cfg["username"] = ask("username") or cfg.get("username", "")

    print("\n【密码】输入时不回显")
    pwd = getpass.getpass("password: ")
    if pwd:
        set_password(cfg, pwd)
    elif not cfg.get("password"):
        print("!! 没有密码，配置不完整")

    print("\n【运营商服务】")
    for i, (label, value) in enumerate(KNOWN_SERVICES, 1):
        mark = " *" if cfg.get("service") == value else ""
        print("  %d) %s%s" % (i, label, mark))
    print("  %d) 自定义" % (len(KNOWN_SERVICES) + 1))
    choice = input("选择 [1]: ").strip() or "1"
    if choice.isdigit() and 1 <= int(choice) <= len(KNOWN_SERVICES):
        cfg["service"] = KNOWN_SERVICES[int(choice) - 1][1]
    elif choice.isdigit() and int(choice) == len(KNOWN_SERVICES) + 1:
        cfg["service"] = input("请输入服务名（可与门户 getServices 返回一致）: ").strip()

    try:
        validate_config(cfg)
    except ValueError as e:
        print("配置未保存：%s" % e)
        return 2
    save_json(CONFIG_FILE, cfg)
    print("\n已保存到 %s" % CONFIG_FILE)
    print("提示：%s" % ("密码已用 Windows DPAPI 加密" if cfg["password_scheme"] == "dpapi"
                       else "密码以明文保存"))
    return 0


# ================================================================= 入口
def build_parser():
    ap = argparse.ArgumentParser(description="河海大学校园网自动认证")
    ap.add_argument("command", nargs="?", default="login",
                    choices=["login", "check", "setup", "install", "uninstall", "logout"])
    ap.add_argument("--verbose", action="store_true", help="输出调试日志")
    ap.add_argument("--force", action="store_true", help="忽略已在线，强制重新认证")
    ap.add_argument("--task-name", default=DEFAULT_TASK_NAME, help="计划任务名")
    return ap


def main():
    args = build_parser().parse_args()
    setup_logging(args.verbose)

    if args.command == "setup":
        return cmd_setup()
    if args.command == "uninstall":
        return cmd_uninstall(args.task_name)

    cfg = load_json(CONFIG_FILE)
    if not cfg:
        print("还没有配置文件，请先双击 install.cmd 或运行程序的 setup 命令。")
        return 2
    if not isinstance(cfg, dict):
        print("配置文件格式错误，请修复 config.json 后重试。")
        return 2
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    try:
        validate_config(cfg, require_credentials=args.command in ("login", "install"))
    except ValueError as e:
        print("配置错误：%s" % e)
        return 2

    if args.command == "install":
        return cmd_install(cfg, args.task_name)
    if args.command == "logout":
        return cmd_logout(cfg)
    if args.command == "check":
        return cmd_check(cfg, args.force)
    return cmd_login(cfg, args.force)


def run():
    """兜底：任何异常都落盘，绝不静默失败。"""
    try:
        # 英文 Windows 的重定向输出可能默认 cp1252，帮助和日志都包含中文。
        # 无控制台的后台程序中，这两个流可能是 None。
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                try:
                    reconfigure(encoding="utf-8", errors="backslashreplace")
                except (OSError, ValueError):
                    pass
        return main()
    except KeyboardInterrupt:
        return 130
    except Exception:
        log.exception("未捕获异常")
        return 1


if __name__ == "__main__":
    sys.exit(run())
