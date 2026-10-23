# 平台选择与验证范围

| 平台 | 使用方式 | 当前证据 |
|---|---|---|
| macOS Apple Silicon / Intel | python3，下载 macos-arm64/amd64 | 原流程有 macOS 公网 QUIC 成功；新版回归和双实例本地传输单独记录 |
| Windows 10/11 x64 / ARM64 | PowerShell 中 py -3，下载 windows-amd64/arm64 | 已实现 Windows 分支；无真实 Windows 主机实测，进程锁/继承/停止、权限、防火墙和跨设备传输尚待原生验证 |

不支持 Linux、32 位 Windows、手机启动器。不得把当前机器上的模拟 Windows 分支测试写成 Windows 实测。没有合适设备时交付可测试实现及原生验收步骤，不伪造测试结论。

## Windows 启动

先安装 Python 3.9+，检查 `py -3 --version`、`curl.exe --version` 与系统 Windows PowerShell 可用。启动器通过系统 CIM 读取进程命令及原生 API 核对创建时间；查询失败时拒绝猜测或停止不明进程。无需先安装代理软件。保留已运行的个人 Syncthing，另选新配置目录和空闲端口。

PowerShell 示例，假设 scripts 在 `C:\Tools\syncthing-direct-file-transfer\scripts`（替换为实际解压或安装路径）：

```powershell
Set-Location "C:\Tools\syncthing-direct-file-transfer\scripts"
# A 发送合成测试文件，前台终端保持运行。
py -3 .\launch.py --root "$env:LOCALAPPDATA\SyncthingDirect\A" --sender
# B 在另一台机器启动，替换为 A 的实际设备 ID。
py -3 .\launch.py --root "$env:LOCALAPPDATA\SyncthingDirect\B" --peer "A_ID"
```

后续配对、status、peer、wait、manifest、verify、pause 均使用 commands.md 中相同子命令，替换 python3 为 py -3，所有路径改为本机绝对路径。例如另开一个 PowerShell 查看或停止本次实例：

```powershell
py -3 .\control.py --root "$env:LOCALAPPDATA\SyncthingDirect\A" status
py -3 .\control.py --root "$env:LOCALAPPDATA\SyncthingDirect\A" stop
```

文件路径支持空格与中文；避免打开两个 launcher 操作同一 root。Windows 使用独占文件句柄并仅向本次子进程继承该句柄；强制结束 launcher 可能留下子进程，stop 通过记录的 PID/创建时间/命令只清理该配置。禁止 taskkill /IM syncthing.exe、停止所有 Python 或改写个人 Syncthing 配置。优先前台 Control+C；stop 在 Windows 先停止已验证子进程，再收尾父进程，不能依赖 TerminateProcess 执行 Python finally。

首次联网若 Windows 防火墙提示，核实程序路径是本次配置中的 syncthing.exe。按用户所需活动网络配置文件，仅允许该程序的同步 TCP/UDP；本技能默认 TCP 22000、UDP 22000（改端口则按实际值）。不要关闭防火墙或允许所有程序，GUI 8385 仅回环访问，不开放到外网。局域网防火墙放行不代表已解决运营商 NAT。

代理分流是条件步骤，见 proxy-routing.md。无代理或未接管时直接跳过；v2rayN 不能粘贴 Clash 规则，按现场版本、内核、实际 syncthing.exe 路径进行局部分流。保留 Codex 的原有代理路径，不为传文件关闭 TUN/VPN。

## 原生 Windows 验收清单（尚未执行）

1. 用含中文和空格的全新 root 启动，验证官方包校验、正确 exe、回环 API、中继关闭及显式 TCP/QUIC；拒绝已有无标记配置、占用端口和重复启动，原文件保持不变。
2. 验证 Control+C、stop 在 API 离线/损坏配置时均可停止本次父子；强制结束父进程后，子进程仍阻止配置重写；PID/创建时间或命令不匹配时不停止其他进程。
3. Windows↔Mac 或 Windows↔Windows 核对无中继实际主/次 TCP/QUIC，合成文件 SHA-256；再验收用户授权文件源清单（名称/大小/哈希）、索引与错误状态，必要时 ZIP CRC，完成后暂停接收目录。
4. 无代理端跳过规则。有代理端按实际客户端验证局部分流，确认 Codex 仍正常通信；将客户端/内核、Windows 架构及 TCP/QUIC 类型记入证据。不能把一次 x64/TCP 验证推及 ARM64/QUIC。

官方依据：[Windows 下载](https://syncthing.net/downloads/)、[防火墙](https://docs.syncthing.net/users/firewall.html)、[Microsoft 句柄继承](https://learn.microsoft.com/en-us/windows/win32/procthread/inheritance)。
