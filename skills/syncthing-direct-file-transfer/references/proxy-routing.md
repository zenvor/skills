# 按设备判断代理分流

每台设备单独判断；一端需要配置不代表另一端也需要。保留用户需要的 TUN/VPN、其他应用分流和 Codex 网络路径，不切换全局直连。

## 先判断是否需要分流

读取运行中的客户端及版本、实际内核、系统代理/TUN/VPN 状态和 Syncthing 启动环境。结合系统路由及客户端连接日志判断；只看到软件已安装、虚拟网卡或一个代理环境变量，都不足以判断 Syncthing 实际被接管。启动环境中的代理变量可能影响发现等 HTTP 请求，不能据此推断所有同步 TCP/UDP 流量均走代理。不要全局清除变量或关闭代理。启动器默认保留代理环境变量；只有诊断确认这些变量干扰本次连接时，才显式加 `--bypass-proxy-env`，仅清除该 Syncthing 子进程的 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY，不改父进程、Codex 或全局设置。发现服务通过代理访问不等于文件同步使用代理或中继。

| 现场情况 | 操作 |
|---|---|
| 没有运行中的代理，网络路径也未见接管 | 跳过代理配置，直接配对并测试；不安装代理软件 |
| 只有浏览器/系统 HTTP(S)/SOCKS 代理 | 检查 Syncthing 自身是否使用代理；未被接管则跳过规则修改。不能仅凭“系统代理开启”认定 TCP/QUIC 被接管 |
| 已有有效的 Syncthing 局部直连策略 | 验证实际路径后复用，不重复添加 |
| TUN/VPN/透明代理接管 Syncthing | 按下面的客户端分支配置局部直连，核对 TCP 和 UDP 两种路径 |
| 本机无代理，但路由器/网关有透明代理 | 检查网关策略；本机 PROCESS-NAME 规则不能替代网关配置。缺少访问能力时说明限制，不盲改全网路由 |

## Clash Verge / Mihomo

只在相关客户端实际接管且需要分流时使用。核对实际进程名/路径；本技能 launcher 使用 macOS 的 syncthing 或 Windows 的 syncthing.exe；按实际运行进程名/路径确认。

先确认当前模式会执行分流规则；若处于忽略规则的全局模式，不自动切换模式影响 Codex，先核对可用的局部绕过方案。

Clash Verge 当前订阅的 prepend 扩展首条使用 macOS 的 `PROCESS-NAME,syncthing,DIRECT` 或 Windows 的 `PROCESS-NAME,syncthing.exe,DIRECT`。订阅正文会被更新覆盖；读取 profiles.yaml 的 current/option.rules 定位扩展，不硬编码 UID。

从技能目录执行；运行前先看 `--help`，核实文件格式和实际进程名：

```bash
python3 scripts/clash_rule.py --file /当前规则扩展.yaml --backup-dir /工作目录/私有备份
```

Windows 示例：`py -3 .\scripts\clash_rule.py --file "C:\实际扩展.yaml" --backup-dir "C:\工作目录\备份" --process-name syncthing.exe`。默认仍为 syncthing；不根据代理软件名称猜测进程。

脚本仅支持 Clash Verge 标准 prepend/append/delete 块列表，备份并置顶，保留其他规则；delete 冲突或不支持结构则停止人工核对。重新应用订阅，检查生成顺序及实际命中。其他 Mihomo 客户端可能使用不同的持久覆盖机制；确认格式前不要运行这个脚本。

## v2rayN 及其他客户端

先识别客户端版本、实际处理 TUN 的内核与平台支持，再现场查对应官方文档/生成配置。v2rayN 的客户端路由与内核配置不是 Clash 格式，不能粘贴 `PROCESS-NAME,syncthing,DIRECT`，也不能仅凭客户端名称假设某种内核或进程分流功能可用。

优先使用该客户端支持的应用/进程/路径局部直连功能，仅匹配实际 Syncthing 程序，将规则置于会提前截获它的规则之前。使用客户端持久设置而非会被重建的临时配置；加载后核对实际运行配置、TCP/UDP 出口和连接日志。内核命令若只有相对路径（如 `-c config.json`），需结合实际工作目录与配置目录参数定位；不能因某个候选文件存在，就断言它正在运行。`direct` 出站标签也须以实际配置为准。不要为“兼容”重写整份配置。

若当前版本不支持可靠的应用分流，不自动添加整网段、所有 UDP 或全局直连。仅在用户允许且目标范围明确时考虑可回滚的对端 IP 局部路由；它可能影响访问同一地址的其他应用，也不能覆盖发现/STUN 等其他目标，不应伪装成等价的全进程直连。无可验证方案时报告限制。

## DIRECT 证据边界

核对需要分流的端；无代理或未接管的端不要求 DIRECT 记录。区分以下证据，不把低层证据冒充高层结论：

- **配置准备**：规则文本存在、置顶、mode=rule 或 TUN 开启，只说明配置状态；生成文件不等于正在运行的配置。
- **精确运行时样本**：匹配采集时间、实际 Syncthing 进程/路径、协议、对端 IP 和目的端口，确认命中本地直连策略。公网映射端口可能不同于 22000；其他端口或旧端点的样本不能替代目标拨号。若有端口重写，先核实对应关系。
- **计数与接口**：累计 hitCount 不能证明本轮精确拨号；同一流量样本的发送计数增长只证明本地发起流量，不能证明对端收到或完成握手。系统显示 utun/TUN 接口也不等于经过代理服务器，DIRECT 流量仍可能先被 TUN 接管；不据此关闭 TUN。
- **连接与文件**：DIRECT 不保证 NAT 可穿透或 UDP 可达；实际无 relay 的 TCP/QUIC 连接和接收端源哈希校验分别证明连接和数据传输，不自动补足缺失的代理运行时证据。

无法取得精确流量的运行时样本时（如控制接口不可读且无其他观测），明确报告仅有生成配置等哪些证据，不能声称精确流量已证实 DIRECT，也不要用全局直连、关闭 TUN 或重启代理补证。按[换网复测](troubleshooting.md#换网复测)推进仍需分别保留这些判断边界。

## 分流修改后的核对

检查实际 TCP/UDP 流量命中的策略、真实出口及对端地址，并确认 Codex 仍可通信。未被接管的设备不要求提供 DIRECT 命中日志；无法读取运行时证据时说明限制。

配置、连接、代理路径与文件验收统一按[验收证据](troubleshooting.md#验收证据)分别报告；未使用 Syncthing relay 不能代替未经过代理服务器的证据。

官方参考（客户端功能与格式需按现场版本复核）：[Mihomo 规则](https://wiki.metacubex.one/en/config/rules/)、[Clash Verge 自定义规则](https://www.clashverge.dev/guide/rules.html)、[v2rayN 自定义路由](https://github.com/2dust/v2rayN/wiki/Description-of-custom-routing-rules)。
