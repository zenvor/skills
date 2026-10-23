# Syncthing 必要排查经验

| 现象 | 下一步 |
|---|---|
| 用户说换网，但仍拿到热点地址 | 核对工具执行的机器名、SSID、网关，区分macOS 与 Windows 设备；不用假设代替实测 |
| 无代理或已证实 Syncthing 未被代理接管 | 跳过代理规则，不安装 Clash；直接验证连接与文件 |
| 局部直连规则未生效/保存后消失 | 先识别客户端、实际内核和配置优先级；Clash Verge 用当前订阅 prepend，其他客户端按各自持久机制，见 proxy-routing.md |
| 公网查询显示代理节点 | 核实查询工具和 Syncthing 各自的出口；仅被接管的端核对局部直连策略，保留已有 TUN/VPN，不把代理出口当本机入口 |
| API 拒绝连接 | 先查独立 launcher/child 存活与日志；stop 不依赖 API，也可清理本次残留进程 |
| ID 正确、设备仍未连 | ID 只用于配对；查两端实例、互加设备、当前映射及发现缓存 |
| 发现地址还是旧代理出口 | status 读取运行中 QUIC listener 最新 WAN 映射，双方 peer --endpoint 互填并保留 dynamic；避免不断重启 |
| 日志为 Symmetric NAT / cannot punch | 一次有界探测后换网络或检查可达入口；不自动启用中继，不宣称所有工具都不可能成功 |
| Port restricted NAT | 具备尝试条件，仍需实际连接与合成文件源哈希验证 |
| 已连接但文件进度 0% | 检查接收方向、目录 ID/共享设备、是否接受新目录、索引、磁盘容量与权限 |
| idle 且零文件 | 可能还没收到索引；不能验收，按固定测试文件预期或源清单检查 |
| wait 超时 | 不代表后台已停止；区分文件仍在增长、地址陈旧、传输错误，再决定继续/换网 |

## 已验证的成功链路

以下是 macOS 已验证的 Clash Verge 个案，不要求所有设备采用同一客户端。其他客户端的适配是条件指引，尚非本次实测结果。

本次热点网络的对称 NAT 未穿透；切到家庭 Wi-Fi 后，两端取得端口受限 NAT 映射。保持 Clash TUN，用 Syncthing 的持久 DIRECT 规则和双方最新 QUIC WAN 映射绕过旧缓存，建立真实 QUIC 连接。先完成合成小文件哈希比对，再反向接收大 ZIP，检查 CRC，最后暂停接收目录。

原始大文件交付只计算了本地 SHA-256，未独立比对发送端完整哈希；新版工作流增加源清单，不能把新增能力描述成原始传输已经验证过的证据。receiveonly 仍应用源端删除，因此一次性交付校验后暂停。

本次公网成功为 QUIC。QUIC 使用可靠、加密的 UDP 流；UDP 映射不能直接给 TCP 使用，连接 client/server 不决定文件发送方向。通用 TCP 打洞理论不属于此技能的操作流程。

## 验收边界

- 配置层：两端 relaysEnabled=false，监听地址没有 relay/default。
- 连接层：两端实际 tcp-client/server 或 quic-client/server，主/次连接无 relay。
- 代理层：无代理/未接管的端记录跳过依据；被接管的端核对其客户端运行时直连策略及真实出口/对端地址。生成文本只是准备证据，不能代替运行时证据。未使用 Syncthing relay 与未经过代理服务器需分别判断。
- 文件层：接收文件与源清单的名称/大小/SHA-256 一致，索引完成且无错误；需要时另做 ZIP CRC。

Windows 进程锁/PowerShell/CIM、停止清理、防火墙和真实跨平台传输均需原生 Windows 验证；模拟分支测试通过不能补足这些实测证据。

## 官方参考

- [Syncthing 配置](https://docs.syncthing.net/users/config.html)
- [禁用中继与 NAT 配置](https://docs.syncthing.net/users/tuning.html)
- [实际连接类型](https://docs.syncthing.net/rest/system-connections-get.html)
- [Clash Verge 持久自定义规则](https://www.clashverge.dev/guide/rules.html)
