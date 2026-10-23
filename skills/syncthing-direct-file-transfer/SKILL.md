---
name: syncthing-direct-file-transfer
description: 使用 Syncthing 在 macOS / Windows 设备间无中继直传大文件，按需处理代理分流，保留现有 TUN/VPN 与 Codex 连通性，并核对源清单及接收完整性。
license: MIT. See LICENSE.txt
---

# Syncthing macOS / Windows 无中继直传

支持 macOS↔macOS、macOS↔Windows、Windows↔Windows 的 Syncthing 工作流。macOS 已有真实公网 QUIC 成功经验；Windows 已实现适配但尚未经真实 Windows 机器或跨系统传输实测，不能称其已实测通过。保留设备现有且需要的 TUN/VPN 与 Codex 代理；没有代理的设备无需安装代理或配置 DIRECT。不切换全局代理、不启用文件中继、不改已有个人 Syncthing 配置。工具不能保证任意网络都能直连。

## 必要约束

- 两端专用配置：`relaysEnabled=false`，显式 TCP/QUIC 监听，GUI 只绑定回环。发现服务和 STUN 可协调连接，但不承载文件中继。
- 分别核实执行主机、网络和收发方向；不复制旧会话的 ID、IP、端口、密钥或源路径。文件发送方向可以与测试方向相反。
- 分别判断两端是否有运行中的代理，以及它是否接管 Syncthing。未安装/未运行代理，或已证实 Syncthing 未被接管时，跳过规则修改；安装过软件不代表正在接管流量。设备上没装代理仍可能有网关透明代理，按实际路径判断。
- 只有被接管或有证据表明分流影响直连时，才为 Syncthing 配置局部直连。保留其他应用及 Codex 的代理路径；已有有效直连规则无需重复添加。按 [references/proxy-routing.md](references/proxy-routing.md) 选择客户端分支；Clash 专用脚本不能用于 v2rayN 或其他格式。
- “规则已生成”“Syncthing 实际 TCP/QUIC”“流量实际走本地直连出口”是不同证据。只有规则文本或设备在线不能证明直传。核对主/次连接均无 relay，并检查真实对端地址；有代理接管时再核对运行时直连策略。控制接口不可读时明确证据边界，不能臆称实际分流已证实。
- 先验收合成文件，再传用户授权的数据。接收端须有发送端预期：测试文件名、1 MiB 大小和源哈希；用户文件须有源清单。空索引/空目录、连接成功或发送端完成不能代替接收验收。

## 执行顺序

先按 [references/platforms.md](references/platforms.md) 选择平台、命令及测试边界。完整 A/B 命令与脚本参数在 [references/commands.md](references/commands.md)，不要临时重新编写引导脚本。

1. 现场读取两端设备名称、活动网卡、本机地址及网关（Wi-Fi 时再核对 SSID），确认是在期望的网络。分别识别两端代理接管情况；无需分流的端跳过，有需要的端按代理参考配置 Syncthing 局部直连并核对生效，保留原有 TUN/VPN 和 Codex 连通性。
2. 用 scripts/launch.py 启动两个独立配置。它校验固定官方版本（macOS 已实测，Windows 未实测），打印本机 ID/源测试哈希，管理子进程及配置锁。后台运行时必须核实进程存活；不要假定临时终端跨消息仍存在。换官方版本使用新配置目录或先验证替换流程，缓存二进制不会被 --binary 静默替换。
3. 按参考中的 A 发送/B 接收顺序配对测试目录。必要时由 status 的 listener WAN 地址获取新的 QUIC 映射，在另一端用 peer --endpoint 更新，保留 dynamic。换网/改分流后旧代理出口可能仍在发现缓存；运行时更新地址，避免反复重启改变映射。
4. 接收端先 wait --id ... --folder-id p2p-direct-probe-v1，再 verify --expected-sha256，严格核对源哈希。launcher 只报告连接，不报告文件验收成功。两端实际 TCP/QUIC 路径与小文件验证均通过后再继续。
5. 由用户指定实际发送内容和接收位置。发送用专用只发送目录，保留原件，避免自动共享整个下载目录；先评估容量。发送端扫描后导出非空 manifest（名称/大小/SHA-256 与目录路径），通过双方现有协调渠道交给接收端，存到共享目录之外。
6. 接收端 offers 核对来源和目录 ID，再 accept 到新的空路径。使用 receiveonly；它仍会应用源端删除。wait 观察文件夹完成和无中继连接；约每分钟报告有意义进展，失败按日志推进，不能自动启用中继。
7. 接收端 verify --manifest，对照源清单严格检查实际文件、接收端本地与全局索引和哈希；ZIP 可加 --zip-crc，只检查不执行/解压。校验记录写到共享目录外，不覆盖已有文件。没有源清单就不能声称完成源文件级验收。
8. 一次性交付完成后 pause 该接收目录，保留文件/配置。需要停止独立实例时用 control.py stop；它不依赖 API 健康，只操作经启动时间及命令核实的本次父/子进程。保留用户需要的局部直连规则，不回滚之后的用户修改。

失败分界和本次必要经验见 [references/troubleshooting.md](references/troubleshooting.md)。回归测试使用合成配置、模拟 API 和无网络子进程，见 tests/test_regressions.py；真实双实例传输测试与这些离线测试的覆盖范围分别报告。
