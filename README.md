# HHUCampusAutoLogin
水之子们好！\
河海sb校园网困扰我们已久，想要找自动连接脚本却发现都是前辈们的旧代码，使用起来效果不理想，本人调教了dsh和gpt3天，并结合了前辈们开源的部分代码，搓出来了这一款自动连接脚本\
该脚本考虑了多种连接可能性，包括开机自启，热点切校园网，windows网络自动断连等，大部分情况均可自连\
做了傻瓜式安装，根据指引一步步操作即可（你也可以把网址丢给dsh让它帮你装）\
大部分常见事项都在下面，仔细看就行\
纯 Python 标准库实现：**不需要浏览器、不需要 chromedriver、没有常驻进程**。

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

- **开机自动联网**：开机登录 Windows ，WiFi自动连接，脚本立刻认证，实测 6 秒内就能上网；另外还有每 2 分钟一次的兜底巡检
- **断线秒级恢复**：掉了也不用管，重连后约 1 秒自动重新认证（实测 0.6 秒）
- **WiFi 掉线自动连回**：Windows 开机只尝试连一次 WiFi，脚本每 2 分钟检查一次，发现网卡确实断开、且能扫到校园 SSID 时主动连一次。
- **只在完全没连网络时才动手**：你正在用手机热点或家里 WiFi 时绝不抢占；断开持续 5 秒以上才尝试，60 秒内最多试一次
- **切网自动修复 DHCP**：从手机热点切回校园网时，Windows 常拿旧租约去续租而被服务器拒绝（DHCPNAK），表现就是"连上 WiFi 却一直没 IP"。脚本检测到"连着校园 SSID 但 IP 不属于校园网段"时会自动释放并重取租约
- **换网段自适应**：`queryString` 绑定本机 IP，脚本每次从网关跳转页实时抓取，换 AP / 换楼不会失效
- **密码 DPAPI 加密**：用当前 Windows 用户凭据加密，拷走配置文件也解不开
- **跳过其他网络**：先检查本机地址和门户可达性，未识别为校园网时跳过认证
- **诊断信息**：认证过程写入日志，配置错误会给出提示，便于排查原因

## 快速开始（Windows）（安装看这里）

### 推荐：下载可执行版，无需安装 Python

1. 打开 [最新版本下载](https://github.com/body-heat-98-7/HHUCampusAutoLogin/releases/latest)，下载那个文件体量最大的zip
2. 将 ZIP **全部解压**到一个长期保留、当前用户可写的文件夹，例如 `文档\HHUCampusAutoLogin`。不要直接在压缩包内运行！
3. 双击 `install.cmd`，填写学号、密码并选择运营商。配置完成后会建立计划任务并立即试运行一次。（门户地址回车即可）
4. 保留整个文件夹。登录 Windows 后，计划任务按设定间隔检查网络；就ok了
> 小提示：不要关掉校园网 WiFi 的「自动连接」开关。关着也能用，但开机上网会从"几秒"变成"最多 2 分钟"。

适用于 Windows 10 / 11 的 x64 电脑。`HHUCampusAutoLogin.exe` 用于配置和手动操作，`HHUCampusAutoLogin-background.exe` 用于后台巡检，两个文件都要保留。

修改账号或运营商：再次双击 `install.cmd`，或在该文件夹打开终端运行 `.\HHUCampusAutoLogin.exe setup`。查看日志：`logs/auto_login.log`。

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
$guid = (Get-NetAdapter -Name "WLAN").InterfaceGuid
$cls  = "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}"

Get-ChildItem $cls -ErrorAction SilentlyContinue | ForEach-Object {
    $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
    if ($p.NetCfgInstanceId -eq "{$guid}") {
        Set-ItemProperty $_.PSPath -Name PnPCapabilities -Value 0 -Type DWord
        Write-Host "已恢复省电: $($p.DriverDesc)"
    }
}
```

### 取舍

关闭省电后，网卡在空闲时不会断电，**电池续航可能略有下降**
（通常为毫瓦级，日常使用难以察觉）。

如果你的机器很少出现掉线，**完全可以不做这一步**——程序内置的
「网络已连接」事件触发与自动重连，已能在掉线后约 1 秒重新完成认证。

## 常见问题

### 排查第一步：看日志

打开安装文件夹 → 进 `logs` → 用记事本打开 `auto_login.log`，看最后 10 行。

---

**Q1：日志报「设备未注册」**

自己用浏览器登录一次校园网就行
你平常怎么登录，这里怎么操作
嫌慢的可以在浏览器地址栏输入 `http://10.96.0.155`，用学号和密码登录，看到「登录成功」页面就完事。

登录完脚本还是没反应，就**重启电脑**。

---

**Q2：连上了校园网，但一直上不了网**

看日志最后几行，对号入座：

| 日志里看到 | 原因 | 怎么办 |
|---|---|---|
| `拿不到 queryString` | 系统代理还开着 | 按 README 顶部「特别提醒」关掉系统代理 |
| `设备未注册` | 学校没登记这台电脑 | 按 Q1 操作 |
| `服务名不对` | 运营商选错了 | 双击 `install.cmd` 重选 |
| 账号 / 密码相关 | 填错了 | 双击 `install.cmd` 重填 |
| 什么都没有，或只有「在线正常」 | 还没轮到 | 等 2 分钟 |

---

**Q3：从手机热点切回校园网，连上了却没网**

Windows 拿着上一次的 IP 去续，被学校服务器拒绝了。

**等 30 秒**。如果还是没网，按顺序试：
1. 打开浏览器随便访问一个网页——如果跳出学校的登录页，就手动登录一次
2. 还不行就**重启电脑**

---

**Q4：开机后 WiFi 没连上**

Windows 开机只会尝试连一次 WiFi，失败就不管了。脚本每 2 分钟检查一次，会自动帮你连。\
嫌慢不想等，就手动点右下角网络图标，选 `Hohai University` 连上——连上之后脚本会自动登录，1s左右完成\
想以后开机连点都不用点：打开 `设置 → 网络和 Internet → WLAN → 管理已知网络` → 点 `Hohai University` → 打开「连接时自动连接」，这条上面也提过了

---

**Q5：用着用着断几秒又好了**

分两种情况：

- **WiFi 图标断开了** → 关掉网卡省电。具体方法看上面「可选优化：关闭无线网卡省电」那一节。
- **WiFi 一直连着但没网** → 学校的登录过期了，脚本 1 秒内会自动重新登录，不用管。

---

**Q6：换校区 / 换运营商**

**换运营商**：双击 `install.cmd`，重新选一次就行。

**换校区**：一般**不用改**。默认的 `eportal.hhu.edu.cn` / `10.96.0.155` 是学校统一的认证门户，
江宁和常州用的是同一套

服务名里带「常州」只是运营商通道的名字，跟你人在哪个校区没关系。

只有学校调整了门户地址时，才需要改 `config.json` 里的 `portal_host` 和 `portal_ip`。

## 免责声明

- 请使用**自己的账号**，不要共享账号：校园网通常限制同时在线设备数，多设备互踢只会谁都上不了。
- 请遵守所在学校的网络使用规定。
- 本项目仅自动化"打开认证页填表提交"这一人工操作，不绕过任何认证机制。
- 按 MIT 协议使用，作者不对因使用本工具造成的任何后果负责。

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

可执行版将命令中的 `python auto_login.py` 换成 `.\HHUCampusAutoLogin.exe`，例如 `.\HHUCampusAutoLogin.exe check`。后台程序无需手动打开。

## 配置项

`config.json`（由 `setup` 生成，已在 `.gitignore` 中）：

| 字段 | 说明 |
|---|---|
| `portal_host` | 门户域名，默认 `eportal.hhu.edu.cn` |
| `portal_ip` | 门户 IP，默认 `10.96.0.155`（掉线时 DNS 不可用，必须直连 IP） |
| `campus_ip_prefix` | 校园网段前缀，默认 `10.` |
| `campus_ssid` | 校园 WiFi 名称，默认 `Hohai University`。脚本靠它判断“现在是不是在校园网”、WiFi 掉线后要不要连回、以及连错网段时重取 DHCP |
| `auto_connect_wifi` | WiFi 掉线时是否自动连回校园网，默认 `true`。改成 `false` 后脚本完全不碰 WiFi，只负责连上之后的认证 |
| `username` | 学号 |
| `password` / `password_scheme` | DPAPI 密文，或 `plain` 明文 |
| `service` | 运营商服务名，见下 |
| `interval_minutes` | 巡检间隔，默认 2 分钟 |

可选的服务名（来自门户 `getServices`，江宁、常州是同一套）：

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

## License

[MIT](LICENSE)
