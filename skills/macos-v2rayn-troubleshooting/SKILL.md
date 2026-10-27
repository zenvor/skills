---
name: macos-v2rayn-troubleshooting
description: 排查 macOS v2rayN、Xray 与 sing-box TUN 的连接报错，定位切换 Clash 后的 Fake-IP 残留、后台进程重试和 IMAP 993 关闭连接错误；不用于服务器节点部署或邮箱账户迁移。
---

# macOS v2rayN 排障

先区分代理整体不可用、单一目标失败和关闭连接时报错，不要通过屏蔽日志替代修复。

## 定位

- 从日志提取时间、目标、端口及 direct/proxy 出站。`Xray started` 的 Warning 是启动消息，`accepted` 是连接记录；单次 SOCKS EOF 不足以证明故障。
- 用 ps 确认内核，用 `lsof -nP -iTCP@目标IP` 找应用。常见配置目录为 `~/Library/Application Support/v2rayN/binConfigs`，先验证当前路径。Xray 和 sing-box 同时运行可以是正常的 TUN → SOCKS → Xray 链路。
- 读取配置只输出必要字段，不输出节点密码、UUID、订阅或 API secret。普通用户 lsof 可能看不到 root 服务，不能据此断言没有后台请求。
- 优先查询已有的本地 sing-box Clash API `/connections`，查看 metadata.processPath、目标、开始时间和双向字节数。按当前配置认证，不输出 secret，也不把 API 开放到局域网。下方脚本自动从 configPre.json 发现本地 API。

## Fake-IP 超时

确认 `198.18.*` 是否属于旧代理的 Fake-IP 池。它必须由拥有映射的内核还原，不能直接当公网 IP 拨号。检查旧 Clash 配置、当前路由和其他代理是否仍运行。

用户授权修复后，先 `dscacheutil -flushcache`，正常退出并重开已定位的应用，再从 v2rayN 界面重启服务。不要默认重启所有应用或清理整个缓存目录。该命令成功不等于所有系统和应用缓存都已清空；必要时再由用户以管理员权限刷新 mDNSResponder。

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

## 复查

连续观察至少多个原有重试周期，短时间没有 socket 不是根治证据。已有 Clash API 的 `/logs?level=warn` WebSocket 可观察新日志，保留认证，不清除历史日志来制造成功。

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
