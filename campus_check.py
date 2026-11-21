# -*- coding: utf-8 -*-
"""校园网一键诊断 v2：区分「认证状态」和「DNS 是否可用」。

用法：双击桌面的「校园网诊断.cmd」
报告：桌面\校园网诊断.txt
"""
import io
import os
import socket
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import auto_login as a  # noqa: E402

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
REPORT = os.path.join(DESKTOP, "校园网诊断.txt")
SERVICES = ["校园外网服务(out-campus NET)", "中国移动(CMCC NET)",
            "中国电信(常州)", "中国联通(常州)"]
DNS_SERVERS = ["223.5.5.5", "223.6.6.6", "114.114.114.114", "8.8.8.8", "1.1.1.1"]

lines = []


def say(s=""):
    print(s)
    lines.append(s)


def raw_http(ip, host=None, timeout=4):
    """返回 (状态码, 响应原文)；失败返回 (None, 错误信息)。"""
    try:
        body = a.Portal._http_get_raw(ip, host=host, timeout=timeout)
    except Exception as e:
        return None, str(e)
    status = ""
    first = body.split("\r\n", 1)[0]
    if first.startswith("HTTP/"):
        parts = first.split()
        if len(parts) > 1:
            status = parts[1]
    return status, body


def nslookup(server, name="www.baidu.com"):
    try:
        r = subprocess.run(["nslookup", "-timeout=3", name, server],
                           capture_output=True, timeout=15)
        out = (r.stdout + r.stderr).decode("gbk", "replace")
        low = out.lower()
        if "timed out" in low or "超时" in out:
            return "超时"
        for ln in out.splitlines():
            if "Address" in ln:
                val = ln.split(":")[-1].strip()
                if val and val != server and any(ch.isdigit() for ch in val):
                    return val
        return "无结果"
    except Exception as e:
        return "异常:%s" % e


def main():
    say("=" * 62)
    say("校园网诊断 v2   %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    say("=" * 62)

    ssid = a.current_ssid() or "(无)"
    ip = a.wlan_ip() or "(无)"
    say("\n[1] 连接状态")
    say("  SSID  : %s" % ssid)
    say("  网卡IP: %s" % ip)

    say("\n[2] 认证状态（拦截页还在不在）")
    verdict = []
    for target in ("223.5.5.5", "1.1.1.1", "114.114.114.114", "10.96.0.155"):
        host = "eportal.hhu.edu.cn" if target == "10.96.0.155" else None
        status, body = raw_http(target, host=host)
        if status is None:
            say("  %-16s 连接失败: %s" % (target, body[:60]))
            continue
        intercepted = "wlanuserip" in body
        loc = ""
        for ln in body.split("\r\n"):
            if ln.lower().startswith("location:"):
                loc = ln[9:].strip()[:80]
                break
        verdict.append(intercepted)
        say("  %-16s HTTP %s  拦截页=%s  %s"
            % (target, status, "是" if intercepted else "否", loc))
    if verdict and any(verdict):
        say("  >>> 结论：仍被拦截（未认证）")
    elif verdict:
        say("  >>> 结论：没有拦截页（看起来已认证）")

    say("\n[3] DNS 逐个测试（解析 www.baidu.com）")
    for server in DNS_SERVERS:
        say("  %-16s -> %s" % (server, nslookup(server)))

    say("\n[4] 系统当前 DNS 解析")
    try:
        say("  gethostbyname 成功: %s" % socket.gethostbyname("www.baidu.com"))
    except Exception as e:
        say("  gethostbyname 失败: %s" % e)

    say("\n[5] 不依赖 DNS 的连通性")
    try:
        sock = socket.create_connection(("223.5.5.5", 443), timeout=5)
        sock.close()
        say("  TCP 223.5.5.5:443 成功 → 外网 IP 可以通")
    except Exception as e:
        say("  TCP 223.5.5.5:443 失败: %s" % e)

    cfg = a.load_json(a.CONFIG_FILE, {})
    for k, v in a.DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    if cfg.get("username") and cfg.get("password"):
        say("\n[6] 逐个运营商尝试登录")
        for svc in SERVICES:
            cfg["service"] = svc
            p = a.Portal(cfg)
            try:
                p.logout()
            except Exception:
                pass
            time.sleep(1)
            qs = p.discover_query_string()
            if not qs:
                say("  %-28s 没有 queryString（可能已认证）" % svc)
                continue
            try:
                res = p.login(qs)
                result = res.get("result") if isinstance(res, dict) else "?"
                msg = (res.get("message") or "")[:50] if isinstance(res, dict) else ""
            except Exception as e:
                result, msg = "异常", str(e)[:50]
            time.sleep(5)
            _status, body = raw_http("1.1.1.1")
            still = "wlanuserip" in (body or "")
            say("  %-28s 接口=%s 仍在拦截=%s %s"
                % (svc, result, "是" if still else "否", msg))
            if not still:
                say("  >>> 用 %s 登录后已放行" % svc)
                break

    say("\n[7] 怎么看这份报告")
    say("  [2] 没有拦截页 + [4] 解析失败  → 认证是通的，问题出在 DNS")
    say("  [3] 全部超时                    → 校园网封了外部 DNS，要换 DNS 或开 DoH")
    say("  [2] 仍有拦截页 + [6] 接口成功   → 门户收了但没放行，账号侧问题")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        lines.append(traceback.format_exc())
    finally:
        try:
            with io.open(REPORT, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            print("\n报告已保存到：%s" % REPORT)
        except Exception as e:
            print("写报告失败: %s" % e)
        if "--pause" in sys.argv:
            try:
                input("\n按回车关闭…")
            except (EOFError, OSError):
                pass
