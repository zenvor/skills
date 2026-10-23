# 按设备判断代理分流

每台设备单独判断；一端需要配置不代表另一端也需要。保留用户需要的 TUN/VPN、其他应用分流和 Codex 网络路径，不切换全局直连。

## 先识别，再决定是否修改

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

```bash
python3 clash_rule.py --file /当前规则扩展.yaml --backup-dir /工作目录/私有备份
```

Windows 示例：`py -3 clash_rule.py --file "C:\实际扩展.yaml" --backup-dir "C:\工作目录\备份" --process-name syncthing.exe`。默认仍为 syncthing；不根据代理软件名称猜测进程。

脚本仅支持 Clash Verge 标准 prepend/append/delete 块列表，备份并置顶，保留其他规则；delete 冲突或不支持结构则停止人工核对。重新应用订阅，检查生成顺序及实际命中。其他 Mihomo 客户端可能使用不同的持久覆盖机制；确认格式前不要运行这个脚本。

## v2rayN 及其他客户端

先识别客户端版本、实际处理 TUN 的内核与平台支持，再现场查对应官方文档/生成配置。v2rayN 的客户端路由与内核配置不是 Clash 格式，不能粘贴 `PROCESS-NAME,syncthing,DIRECT`，也不能仅凭客户端名称假设某种内核或进程分流功能可用。

优先使用该客户端支持的应用/进程/路径局部直连功能，仅匹配实际 Syncthing 程序，将规则置于会提前截获它的规则之前。使用客户端持久设置而非会被重建的临时配置；加载后核对实际运行配置、TCP/UDP 出口和连接日志。`direct` 出站标签也须以实际配置为准。不要为“兼容”重写整份配置。

若当前版本不支持可靠的应用分流，不自动添加整网段、所有 UDP 或全局直连。仅在用户允许且目标范围明确时考虑可回滚的对端 IP 局部路由；它可能影响访问同一地址的其他应用，也不能覆盖发现/STUN 等其他目标，不应伪装成等价的全进程直连。无可验证方案时报告限制。

## 生效证据

通用验收仍是双方中继关闭、实际 TCP/QUIC 主/次连接无 relay、真实对端地址及合成文件源哈希一致。有代理接管时额外核对运行时直连策略和出口；没有代理的端不要求提供不存在的 DIRECT 命中日志。修改后确认 Codex 仍可通信。

“Syncthing 未使用 relay”不等于“没有经过代理服务器”；二者分别报告。证据不足时明确哪一层尚未验证，不改用中继冒充成功。

官方参考（客户端功能与格式需按现场版本复核）：[Mihomo 规则](https://wiki.metacubex.one/en/config/rules/)、[Clash Verge 自定义规则](https://www.clashverge.dev/guide/rules.html)、[v2rayN 自定义路由](https://github.com/2dust/v2rayN/wiki/Description-of-custom-routing-rules)。Clash Verge 分支来自本次实测，其他分支是适配指引，不宣称已实测。
