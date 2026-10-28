---
name: macos-v2rayn-troubleshooting
description: 排查 macOS v2rayN、Xray 与 sing-box TUN 的连接报错，定位 Fake-IP 残留、后台进程重试、TCP 关闭错误及 TUN 栈兼容性；不用于服务器节点部署或邮箱账户迁移。
---

# macOS v2rayN 排障

先区分代理整体不可用、单一目标失败和关闭连接时报错，不要通过屏蔽日志替代修复。

## 保持排障通道可用

Codex 可能依赖正在排查的 v2rayN 联网。开始操作前确认此依赖；依赖同一代理时，保持客户端运行，不通过退出 v2rayN、关闭 TUN 或终止代理进程来修改配置，否则可能切断 Codex 自己的网络。

优先在运行中的“设置 → 参数设置”修改指定字段并保存，必要时仅“重启服务”。重启服务也会短暂断网，提前说明并保留明确的恢复方式。设置菜单自动化不可靠时，请用户手动修改指定选项，随后读取保存配置和实际运行配置核实；不要用退出客户端替代设置操作。完整退出前应已有可用的独立联网通道或用户明确安排的恢复步骤。

## 定位

- 从日志提取时间、目标、端口及 direct/proxy 出站。`Xray started` 的 Warning 是启动消息，`accepted` 是连接记录；单次 SOCKS EOF 不足以证明故障。
- 用 ps 确认内核，用 `lsof -nP -iTCP@目标IP` 找应用。常见配置目录为 `~/Library/Application Support/v2rayN/binConfigs`，先验证当前路径。Xray 和 sing-box 同时运行可以是正常的 TUN → SOCKS → Xray 链路。
- 读取配置只输出必要字段，不输出节点密码、UUID、订阅或 API secret。普通用户 lsof 可能看不到 root 服务，不能据此断言没有后台请求。
- 优先查询已有的本地 sing-box Clash API `/connections`，查看 metadata.processPath、目标、开始时间和双向字节数。按当前配置认证，不输出 secret，也不把 API 开放到局域网。下方脚本自动从 configPre.json 发现本地 API。

## Fake-IP 超时

确认 `198.18.*` 是否属于旧代理的 Fake-IP 池。它必须由拥有映射的内核还原，不能直接当公网 IP 拨号。检查旧 Clash 配置、当前路由和其他代理是否仍运行。

用户授权修复后，先 `dscacheutil -flushcache`，正常退出并重开已定位的来源应用，再从 v2rayN 界面重启服务；这里的来源应用不包括为 Codex 提供网络的 v2rayN。不要默认重启所有应用或清理整个缓存目录。该命令成功不等于所有系统和应用缓存都已清空；必要时再由用户以管理员权限刷新 mDNSResponder。

若仍复发，检查 root daemon 和登录项。核对 LaunchDaemon plist 的 Label、ProgramArguments、KeepAlive，再重启指定服务。权限不足时给用户明确命令，由用户输入密码，不要绕过权限。

实际案例：腾讯柠檬主程序及 LemonMonitor 重启后恢复真实 IP，但 `/Library/Application Support/Lemon/LemonDaemon (root)` 仍请求旧 Fake-IP。核对本机 label 仍匹配后可执行：

```sh
sudo launchctl kickstart -k system/com.tencent.LemonDaemon
```

不要触碰 com.tencent.Lemon.uninstall，也不要套用到别的服务。把虚拟 IP 改成 proxy/direct 都不能凭空恢复旧映射。

## Notes / IMAP 993

- 根据进程及 DNS 关联目标；Notes 可以通过 IMAP 同步第三方邮箱。不要通过删除账户或禁用同步来消除日志。
- `connection download closed ... endpoint not connected` 是关闭路径报错，本身不能区分主动取消、重连、协议失败或内核问题。检查是否持续重复，以及新连接是否有双向数据。
- TLS 测试使用真实邮箱域名，携带 SNI，验证证书链与主机名。直接连 IP、未提供 server_hostname/-servername 时可能得到 invalid2.invalid、No SNI provided 等默认证书，不能据此断定邮箱证书坏了。不得用关闭证书验证作为修复。
- TUN/Xray 启用 sniffing 时，SNI 也可能改变实际出站目标，不能用不同 SNI 的证书反推原始 IP 身份。
- 分别测试 TUN 与显式 SOCKS。curl SOCKS 测试使用 `--noproxy '' --socks5-hostname 127.0.0.1:端口`；`--noproxy '*'` 会绕过代理，不能用于证明 SOCKS 成功。
- TLS 后仅读取 greeting 并执行未认证 CAPABILITY，不读取邮件/笔记、不索取密码或 OAuth token。连接层通过不等于实际登录或内容同步已验证。
- 当前不复现时先观察，不要强行修改 TUN stack、DNS 或邮箱。持续复现才重启已定位应用并比较前后；仅在证据指向 TUN stack 时试受支持的替代配置，保留回滚。

## TCP 关闭错误与替代 TUN 栈

遇到多个应用反复出现 `connection download closed: close tcp ... endpoint not connected`，先区分关闭错误与 `dial ... timeout`、TLS 握手失败，核实业务影响、来源和双向数据。不能将所有关闭日志一律判为无害，也不能将某条 993 连接的结论推广到所有 HTTPS 连接。

当证据指向 gVisor 的关闭路径且用户授权处理时，核对已安装版本是否支持 `system`，备份原配置后，在保持客户端运行的情况下只切换 TUN stack。读取生成配置确认实际生效，比较其他字段，保留原日志级别与 DNS/分流。替代栈无效或出现访问回归时，恢复原字段并重启服务。

验证正常访问、正确 SNI 的 TLS/IMAP、主动取消连接及原有长连接；观察覆盖已知重试间隔。若先前在约十分钟时出现错误，不能以 65 秒或五分钟无错误判定长期修复。长连接保持超过十分钟只证明该观察窗口内稳定，不能声称已经重现并验证原来的关闭事件。

涉及本次版本的源码解释、切换操作和验证边界时，读取 [system 切换实战记录](references/system-stack-case.md)。本次访问回归测试通过，观察窗口内未再收到同类错误；这不代表修复了 gVisor 本身，也不是所有版本的通用默认配置。实际日志路径会将已识别的关闭错误归入 trace，因此 warn 层没有收到日志不能证明底层不再发生关闭错误。

## 复查

连续观察至少多个原有重试周期，短时间没有 socket 不是根治证据。已有 Clash API 的 `/logs?level=warn` WebSocket 可观察新日志，保留认证，不清除历史日志来制造成功。区分观测跨度和日志流实际连接时间；记录重连盲区，不能用“未收到”推导“全程没有发生”。

核对应用/daemon PID、新连接真实目标、双向流量及代理可用性；记录观察时长，复发继续归因。汇报区分已验证的网络层、未验证的实际同步及仍需用户执行的权限步骤。

## 只读脚本

```sh
python3 scripts/diagnose.py --target-ip 198.18.1.146 --samples 4 --interval 10
python3 scripts/diagnose.py --target-ip 192.179.26.109 --imap-host imap.gmail.com --socks-port 10808
```

替换为当次目标。脚本仅查询本地连接元数据，可选执行无认证 IMAP 测试；不会修改配置或重启服务。

脚本判定 CAPABILITY 成功需要非空的 untagged CAPABILITY 数据和匹配 tag 的 OK 完成响应；协议关键字忽略大小写，tag 精确匹配，并支持 PREAUTH greeting。修改脚本后运行离线回归：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

测试使用模拟 IMAP 流和临时本地 HTTP 服务，不访问邮箱、不读取真实代理凭据，也不修改系统配置；它不代替实际路径及 TLS 验证。

参考：[sing-box Clash API](https://sing-box.sagernet.org/configuration/experimental/clash-api/)、[Mihomo Fake-IP](https://wiki.metacubex.one/config/dns/)、[curl 证书验证](https://curl.se/docs/sslcerts.html)、[Gmail IMAP](https://developers.google.com/workspace/gmail/imap/imap-smtp)。
