# 临时传输与脚本命令

本流程用于新建临时独立传输及其验收；排查已有客户端时先用[排障表](troubleshooting.md)，不要直接重建配置。`control.py` 只操作 `launch.py` 创建的专用配置。

以下命令从技能目录执行，先运行 `python3 scripts/launch.py --help` 与 `python3 scripts/control.py --help` 查看参数。脚本需要 Python 3.9+ 标准库；Windows 命令换用 `py -3`，进程与防火墙注意事项见[设备操作经验](platforms.md)。转交代码，不转交配置、证书或数据库。A/B 是测试角色，实际大文件可以反向传输；每台机器使用专用绝对配置目录。

## 1. 按需检查代理

分别检查 A/B。无运行中代理或已证实 Syncthing 未被接管的设备，直接进入第 2 步；不要为了此流程安装代理或创建 DIRECT 规则。有 TUN/VPN/透明代理接管时，按 [proxy-routing.md](proxy-routing.md) 选择对应分支，只调整 Syncthing，保留 Codex 的原有网络路径。

## 2. 启动与合成小文件

A 先启动，打印 A_ID 和测试文件 SHA256：

```bash
python3 scripts/launch.py --root /工作目录/A --sender
```

B 获得 A_ID 后启动，已有初始测试目录会加入 A，无需重复 accept：

```bash
python3 scripts/launch.py --root /工作目录/B --peer A_ID
```

B 打印 B_ID。A 另开终端运行：

```bash
python3 scripts/control.py --root /工作目录/A peer --id B_ID
python3 scripts/control.py --root /工作目录/A probe-share --id B_ID
```

两端 status 获取自己 listener 的新 WAN QUIC 映射：

```bash
python3 scripts/control.py --root /工作目录/A status
python3 scripts/control.py --root /工作目录/B status
```

把该映射填入另一端设备地址。请替换占位 ID/IP/端口，不能原样执行：

```bash
# A 填 B 的地址；B 填 A 的地址。必要时执行，不要求每次重启。
python3 scripts/control.py --root /工作目录/A peer --id B_ID --endpoint 'quic4://B的真实公网IPv4:B的实际UDP端口'
python3 scripts/control.py --root /工作目录/B peer --id A_ID --endpoint 'quic4://A的真实公网IPv4:A的实际UDP端口'
```

B 必须等待目录而不仅是连接，再用 A 打印的哈希验收：

```bash
python3 scripts/control.py --root /工作目录/B wait --id A_ID --folder-id p2p-direct-probe-v1 --timeout 90
python3 scripts/control.py --root /工作目录/B verify --folder-id p2p-direct-probe-v1 --expected-sha256 A打印的SHA256
```

若 B 已在未加 peer 时启动，应先停止其独立 launcher，再加 --peer 启动一次；之后通过运行时 peer 更新映射。不要把同 ID 初始测试目录 accept 到不同位置。

默认自动下载固定官方 v2.1.7 并核对按平台/架构固定的 SHA-256。也可 `--binary /已核实的官方/syncthing`；已有缓存不会替换，升级使用新的配置目录。未来下载不可用时现场核实官方发布，不跳过校验。默认继承代理环境，只有已诊断代理变量干扰时才显式使用 --bypass-proxy-env，仅影响本次 Syncthing 子进程；不为无代理/未接管设备添加该选项。端口冲突可选 `--gui-port`、`--listen-port`。`--no-discovery` 只用于显式地址的隔离局域网测试，公网穿透不要使用。

macOS 的 Agent 需要跨消息保持进程时可按下例后台启动（Windows 前台运行示例见 [设备操作经验](platforms.md)，不照搬 start_new_session），launcher 会自动记录父/子 PID、启动时间和命令，持有配置锁；其子进程也继承锁，意外残留时阻止重写配置：

```python
from pathlib import Path
import subprocess, sys
root = Path('/工作目录/A').resolve()
root.mkdir(parents=True, exist_ok=True)
with (root / 'launcher.log').open('a') as log:
    process = subprocess.Popen(
        [sys.executable, '-u', '/脚本绝对路径/launch.py', '--root', str(root), '--sender'],
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True)
```

然后通过 status 验证启动，不能以 Popen 返回就当服务已可用。前台停止用 Control+C，后台停止：

```bash
python3 scripts/control.py --root /工作目录/A stop
```

stop 无需健康 HTTP API，也不要求 config.xml 可解析；但需要本技能的配置标记与进程记录。它核实进程身份，等待停止并在必要时清理自己的残留子进程，不使用 killall。

## 3. 用户文件（S 发送、R 接收）

前提：双方直连/小文件验收已通过，用户已授权源目录及接收。S/R 根目录可以分别是 B/A。

```bash
# S：扫描授权的独立目录，保留原件。
python3 scripts/control.py --root /工作目录/S share --id R_ID --folder-id transfer-unique --path /授权的独立发送目录 --label '本次文件'
python3 scripts/control.py --root /工作目录/S wait --folder-id transfer-unique --timeout 60
python3 scripts/control.py --root /工作目录/S manifest --folder-id transfer-unique --out /工作目录/源清单.json
```

这一步源端 wait 仅等待扫描索引稳定，并不证明 R 收完。将源清单文件或 JSON 文本通过双方已有协调渠道交给 R，存到 R 共享目录外；源端数据变化后要重建清单，不能继续使用旧快照。

```bash
# R：核对来源、目录 ID、文件预期与磁盘空间。
python3 scripts/control.py --root /工作目录/R offers
python3 scripts/control.py --root /工作目录/R accept --folder-id transfer-unique --path /新的空接收目录
python3 scripts/control.py --root /工作目录/R wait --id S_ID --folder-id transfer-unique --timeout 600
python3 scripts/control.py --root /工作目录/R verify --folder-id transfer-unique --manifest /工作目录/源清单.json --zip-crc --report /交付目录/校验.json
```

verify 拒绝空索引、预期文件缺失/额外文件、数量/大小/哈希不符、传输错误或未完成状态；报告不覆盖现有文件。文件在校验期间变化也拒绝。ZIP CRC 通过与源哈希匹配分别记录。wait 超时不意味着后台传输已停止，先查进度、地址和日志。

一次性交付验收通过后，如需隔离后续源端变化，可执行 `python3 scripts/control.py --root /工作目录/R pause --folder-id transfer-unique`。持续同步或用户要求保持运行时不要暂停。`receiveonly` 仍应用源端删除。

## 4. 维护脚本时验证

```bash
python3 -m unittest discover -s tests -v
```

这些测试不验证公网可达性：它们检查规则优先级、源文件预期、API 离线停止、SIGTERM 清理和残留实例保护。公网验收仍需真实对端与实际文件证据。

源清单 v2 记录所有文件及目录路径（包括空目录）；验收同时检查本地/全局目录计数。旧 v1 清单无法证明目录树完整，必须由源端重新导出，不降级跳过检查。
