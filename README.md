# HHUCampusAutoLogin
水之子们好！\
河海sb校园网困扰我们已久，想要找自动连接脚本却发现都是前辈们的旧代码，使用起来效果不理想。为了让我们用起来不烧心，本人调教了dsh和gpt3天，并结合了前辈们开源的部分代码，搓出来这一款自动连接脚本\
该脚本考虑了多种连接可能性，包括开机自启，热点切校园网，windows网络自动断连等，绝大部分情况均可自动连接。也做了傻瓜式安装（你也可以把网址丢给dsh让它帮你装）\
目前江宁校区使用体验良好，金坛网络可能还要做特别优化，不过应该也能凑合用\
大部分常见事项都在下面，包括对连接稳定的进一步优化（比如更改网卡设置等）\
纯 Python 标准库实现：**不需要浏览器、不需要 chromedriver、没有常驻进程**。提供 Windows 免安装 Python 的可执行版。

## ⚠️ 特别提醒

**校园网下不要挂梯子！！！！！！！！**
**校园网下不要挂梯子！！！！！！！！**
**校园网下不要挂梯子！！！！！！！！** 
会让脚本失效 而且蜀黍可能请你去喝茶 不要作死
如果你是在**手机热点或家里**用梯子，脚本会自动跳过（0.09 秒退出），不会冲突
代理本身出问题请按你所用软件的说明排查，不属于本项目的范围。

> 唯一和脚本相关的排查：如果"浏览器打不开网页但显示连接正常"，先看
> `设置 → 网络和 Internet → 代理` 里的「使用代理服务器」是不是还开着。
## 特性（脚本功能作用大致描述）

- **WiFi 掉线自动连回且带开机自启**：开机后 Windows 有时不再自动重连；脚本发现"完全没连上 WiFi"且能扫到校园 SSID 时会主动连接一次（有别的网络在用时不会抢占）
- **断线秒级恢复**：除了每 2 分钟兜底巡检，还注册了「网络已连接」事件触发，Wi-Fi 重连后**约 1 秒**就会重新认证（实测 0.6 秒）
- **切网自动修复 DHCP**：从手机热点切回校园网时，Windows 常拿旧租约去续租而被服务器拒绝（DHCPNAK），表现就是"连上 WiFi 却一直没 IP"。脚本检测到"连着校园 SSID 但 IP 不属于校园网段"时会自动释放并重取租约
- **换网段自适应**：`queryString` 绑定本机 IP，脚本每次从网关跳转页实时抓取，换 AP / 换楼不会失效
- **密码 DPAPI 加密**：用当前 Windows 用户凭据加密，拷走配置文件也解不开
- **跳过其他网络**：先检查本机地址和门户可达性，未识别为校园网时跳过认证
- **诊断信息**：认证过程写入日志，配置错误会给出提示，便于排查原因
- **两种使用方式**：Windows 可执行版无需安装 Python；源码运行只需 Python 3.8+

## 快速开始（Windows）（安装看这里）

### 推荐：下载可执行版，无需安装 Python

1. 打开 [最新版本下载](https://github.com/body-heat-98-7/HHUCampusAutoLogin/releases/latest)，下载那个文件体量最大的zip
2. 将 ZIP **全部解压**到一个长期保留、当前用户可写的文件夹，例如 `文档\HHUCampusAutoLogin`。不要直接在压缩包内运行！
3. 双击 `install.cmd`，填写学号、密码并选择运营商。配置完成后会建立计划任务并立即试运行一次。（门户地址回车即可）
4. 保留整个文件夹。登录 Windows 后，计划任务按设定间隔检查网络；就ok了

适用于 Windows 10 / 11 的 x64 电脑。`HHUCampusAutoLogin.exe` 用于配置和手动操作，`HHUCampusAutoLogin-background.exe` 用于后台巡检，两个文件都要保留。

修改账号或运营商：再次双击 `install.cmd`，或在该文件夹打开终端运行 `./HHUCampusAutoLogin.exe setup`。查看日志：`logs/auto_login.log`。

卸载：双击 `uninstall.cmd`，确认计划任务删除成功后再删除文件夹。移动文件夹或升级版本后，请重新运行 `install.cmd` 更新计划任务中的路径。卸载只删除计划任务，不删除本地账号配置。

**Code → Download ZIP 下载的是源码，不包含 EXE。无需 Python 的用户请下载 Releases 中的 Windows ZIP。**
## 可选优化：关闭无线网卡省电 追求绝对稳定的看这里

Windows 允许系统"为省电"临时关闭无线网卡，这可能造成偶发的短暂掉线。
在事件日志里表现为 `Microsoft-Windows-WLAN-AutoConfig` 的 **8003** 事件，
原因为 **"网络被驱动程序断开连接"**。

本程序**不会自动修改**系统电源设置（需要管理员权限，且属于系统策略变更，
应由使用者自行决定）。如需优化，手动设置一次即可，永久生效。

### 方法一 图形界面（推荐）

1. `Win + X` → **设备管理器**
2. 展开 **网络适配器**，找到无线网卡（例如 `Realtek 8922AE-VP WiFi 7 PCI-E NIC`）选你自己的网卡型号，不确定问唐包或者肥鱼
3. 右键 → **属性** → **电源管理** 标签
4. 取消勾选 **"允许计算机关闭此设备以节约电源"** → 确定
5. 断开并重新连接一次 WiFi 使其生效

### 方法二 命令行（需管理员 PowerShell）

```powershell
$guid = (Get-NetAdapter -Name "WLAN").InterfaceGuid
$cls  = "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}"

Get-ChildItem $cls -ErrorAction SilentlyContinue | ForEach-Object {
    $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
    if ($p.NetCfgInstanceId -eq "{$guid}") {
        Set-ItemProperty $_.PSPath -Name PnPCapabilities -Value 0x10 -Type DWord
        Write-Host "已关闭省电: $($p.DriverDesc)"
    }
}
```

`PnPCapabilities` 的 `0x10` 位表示"禁止系统为省电关闭该设备"。

### 如何还原

把 `PnPCapabilities` 改回 `0`，或在设备管理器中重新勾选该选项：

```powershell
Set-ItemProperty $_.PSPath -Name PnPCapabilities -Value 0 -Type DWord
```

### 取舍

关闭省电后，网卡在空闲时不会断电，**电池续航可能略有下降**
（通常为毫瓦级，日常使用难以察觉）。

如果你的机器很少出现掉线，**完全可以不做这一步**——程序内置的
「网络已连接」事件触发与自动重连，已能在掉线后约 1 秒重新完成认证。

### 使用源码运行的方法（小白别看）

先安装 Python 3.8+，然后运行：

```powershell
git clone https://github.com/body-heat-98-7/HHUCampusAutoLogin.git
cd HHUCampusAutoLogin

python auto_login.py setup      # 填学号、密码，选运营商
python auto_login.py install    # 安装计划任务（每 2 分钟一次）
```

安装了 Python 后，也可以直接双击源码目录中的 `install.cmd`。

计划任务在当前 Windows 用户下运行。密码使用该用户的 DPAPI 加密，请用日常登录 Windows 的账号配置和安装。

## 命令

| 命令 | 作用 |
|---|---|
| `python auto_login.py` | 巡检一次：在线就退出，掉线就认证 |
| `python auto_login.py setup` | 修改账号 / 密码 / 运营商 |
| `python auto_login.py install` | 安装计划任务 |
| `python auto_login.py uninstall` | 删除计划任务 |
| `python auto_login.py check` | 只检测状态 |
| `python auto_login.py logout` | 主动下线（测试用） |
| `--verbose` | 输出调试日志 |
| `--force` | 忽略"已在线"，强制认证 |

可执行版将命令中的 `python auto_login.py` 换成 `./HHUCampusAutoLogin.exe`，例如 `./HHUCampusAutoLogin.exe check`。后台程序无需手动打开。

## 配置项

`config.json`（由 `setup` 生成，已在 `.gitignore` 中）：

| 字段 | 说明 |
|---|---|
| `portal_host` | 门户域名，默认 `eportal.hhu.edu.cn` |
| `portal_ip` | 门户 IP，默认 `10.96.0.155`（掉线时 DNS 不可用，必须直连 IP） |
| `campus_ip_prefix` | 校园网段前缀，默认 `10.` |
| `campus_ssid` | 校园 WiFi 名称，默认 `Hohai University`。只有连在这个 SSID 上才会自动重取 DHCP，避免误伤其他网络 |
| `username` | 学号 |
| `password` / `password_scheme` | DPAPI 密文，或 `plain` 明文（非 Windows） |
| `service` | 运营商服务名，见下 |
| `interval_minutes` | 巡检间隔，默认 2 分钟 |

常州校区可选的服务名（来自门户 `getServices`）：

```
校园外网服务(out-campus NET)     # 校园网
中国移动(CMCC NET)
中国电信(常州)
中国联通(常州)
```

## 工作原理

掉线时，网关会把任意 HTTP 请求替换成一个跳转页：

```html
<script>top.self.location.href='http://eportal.hhu.edu.cn/eportal/index.jsp?
  wlanuserip=<加密的本机IP>&wlanacname=...&nasip=...&mac=...&t=wireless-v2&...'</script>
```

脚本从中提取 `queryString`，再直连门户 IP 提交认证：

```
POST http://10.96.0.155/eportal/InterFace.do?method=login
Host: eportal.hhu.edu.cn
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

userId=<双层URL编码的学号>&password=<双层URL编码的密码>&service=<服务名>
&queryString=<双层URL编码的参数>&operatorPwd=&operatorUserId=&validcode=
&passwordEncrypt=false
```

返回 `{"result":"success","userIndex":"..."}` 即成功。在线期间每 2 分钟调用
`InterFace.do?method=keepalive` 续期。

几个必须注意的点（都是踩过的坑）：

1. **在线判断只认 HTTP 204**。掉线时网关返回 200 + 跳转页，把 200 当"在线"会导致永远不登录。
2. **必须直连 IP 并伪造 Host 头**。认证前 DNS 通常不通，用域名会直接解析失败。
3. **`queryString` 绑定 IP**，缓存会失效，必须每次重新抓。
4. **值要双层 URL 编码**，与页面 `encodeURIComponent(encodeURIComponent(x))` 一致。

## 常见问题

**Q：日志报"设备未注册"**
门户做了终端绑定。浏览器打开 `http://10.96.0.155` 用学号登录一次，通常自动登记；
仍不行则进自助服务 `http://10.96.0.154:8080/selfservice` 添加本机 MAC。

**Q：连上校园网但认证页打不开**
大概率是系统代理指向了一个没在运行的端口。检查：

```powershell
Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" |
    Select-Object ProxyEnable, ProxyServer
```

把 `ProxyEnable` 设为 0，或把 `*.hhu.edu.cn` 加入代理绕过列表。

**Q：从手机热点切回校园网，连上了却上不了网**
这是 Windows 的 DHCP 行为：切回来时它拿着上一次的租约去续，被服务器拒绝（`DHCPNAK`），
在你手动重连或等它重新发现 DHCP 之前一直拿不到 IP。判定方法：

```powershell
Get-WinEvent -LogName "Microsoft-Windows-Dhcp-Client/Admin" -MaxEvents 10 |
    Where-Object { $_.Id -eq 1002 }
```

脚本已内置处理：当它发现"连着校园 SSID（`campus_ssid`）但 IP 不在 `campus_ip_prefix` 网段"，
会自动执行 `ipconfig /release` + `/renew` 重取租约，随后完成认证。
另外，任务里注册了「网络已连接」事件触发器，Wi-Fi 重连后约 1 秒就会重新认证。

**Q：开机后 WiFi 干脆没连上，也不会自己连回来**
Windows 的"自动连接"基本只在开机时试一次，失败后不会持续重试。脚本已内置处理：
检测到无线网卡处于未连接状态、且能扫描到 `campus_ssid` 时，会执行
`netsh wlan connect name=<SSID>` 主动连一次（当前若连着别的网络则不抢占）。
若仍反复出现，多半是无线网卡驱动在启动阶段不稳，建议更新驱动。

**Q：用着用着会断几秒再自动连上**
先分清是"Wi-Fi 链路断了"还是"认证掉了"：

```powershell
Get-WinEvent -LogName "Microsoft-Windows-WLAN-AutoConfig/Operational" -MaxEvents 30 |
    Where-Object { $_.Id -eq 8003 }   # 8003 = 无线网络断开
```

- 有大量 8003，说明是无线链路层断开（驱动省电、漫游、AP 侧踢）。可尝试在设备管理器里
  关闭无线网卡的"允许计算机关闭此设备以节约电源"，或更新无线网卡驱动。
- 没有 8003 但认证掉了，属于门户 session 到期。事件触发器+巡检会在 1 秒内重新认证，
  在线期间也会按间隔发 `keepalive` 续期。

**Q：日志报"服务名不对"**
双击 `install.cmd` 或运行程序的 `setup` 命令，重新选择运营商。

**Q：换了校区能用吗**
默认门户和服务名来自常州校区。其他校区能否使用，取决于实际门户协议、地址、网段和服务名；可修改配置适配，尚未逐校区验证。

**Q：安装成功但立即试运行失败**
计划任务可能已经创建成功。连接校园网后查看 `logs/auto_login.log`，核对账号、密码、运营商和终端注册情况；下一次巡检会再次尝试。安装与打包测试不代表已在所有校园网环境完成实际认证验证。

**Q：HTTP 和密码保护有什么区别**
DPAPI 保护本机保存的密码。本项目按现有门户的 HTTP 接口提交认证，DPAPI 不会为网络传输增加 HTTPS 加密。认证请求绕过系统代理，直接连接配置的门户地址。

## 构建 Windows 可执行版（开发者）

构建需要 Windows x64、Python 3.12 和 PowerShell；使用者下载成品无需 Python。

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-build.txt
./build.ps1 -Python ./.venv/Scripts/python.exe -Version v1.0.3
```

成品位于 `dist/`，包括 Windows ZIP 和 SHA256 校验文件。打包采用文件白名单，不会收集 `config.json`、`cache.json` 或日志。

推送 `v*` 版本标签时，GitHub Actions 会运行测试、构建 Windows 版本并上传到对应 Release；推送 `main` 或手动运行时可从 Actions 下载构建产物。

## 非 Windows

调度部分用 cron 代替：

```cron
*/2 * * * * /usr/bin/python3 /path/to/auto_login.py >/dev/null 2>&1
```

密码需改为明文保存（`password_scheme: "plain"`），因为 DPAPI 是 Windows 机制。

## 免责声明

- 请使用**自己的账号**，不要共享账号：校园网通常限制同时在线设备数，多设备互踢只会谁都上不了。
- 请遵守所在学校的网络使用规定。
- 本项目仅自动化"打开认证页填表提交"这一人工操作，不绕过任何认证机制。
- 按 MIT 协议使用，作者不对因使用本工具造成的任何后果负责。

## License

[MIT](LICENSE)
