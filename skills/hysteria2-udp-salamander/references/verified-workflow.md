# 实战验证范围

2026-10-27 在 DMIT 上完成部署和验收。此记录说明流程的依据，不代表后续版本或当前网络状态已自动复测。

## 实际完成的步骤

- 环境：Debian，`zenvor/3x-ui` 3.9.0，Xray 26.6.27，Mihomo 1.19.32。
- 故障基线：大陆测试点 ICMP 可达，多组 TCP 端口不可达；海外 TCP 正常。新增节点后通过实际代理请求确认 UDP 可用，而非根据 ping 推断。
- 备份主库和独立订阅库；新增 Hysteria 入站，版本 2、UDP 443、TLS、ALPN `h3`、Salamander。TCP 443 的已有服务保留。
- 复用已部署的 Let’s Encrypt 证书文件和私钥路径；没有在本轮新签发证书，也未使用 Cloudflare Origin CA。
- 新建专用客户端，填写 Hysteria Auth，仅绑定该入站；原八个 Reality 入站和原客户端配置未改，临时入站从原订阅排除。
- 客户端选择器仅列出启用入站：先启用目标入站但保持 UDP 防火墙未放行，完成客户端后再放行 UDP 443。最终监听由 Xray 持有，UFW 有 IPv4/IPv6 的 UDP 规则。
- 本机物理 `en0` 和大陆腾讯云 `eth0` 各运行隔离 Mihomo 实例，TLS 校验开启。两处均获得 gstatic 204、Cloudflare trace 200，出口为目标 VPS。
- 仅改测试配置中的 Auth 后，日志明确报告认证失败，代理请求失败；正确配置成功。SQLite `quick_check` 为 `ok`。
- 导出完整 Mihomo YAML 和 Hysteria2 分享链接，文件权限 0600；清理测试程序和冗余凭据副本。用户选择保留临时节点。

HTTP 代理测试未覆盖原生 UDP 应用、Windows GUI 导入、全机 TUN、长期吞吐或每家运营商；不把这些写成已通过。

## 官方资料与版本边界

- [Xray Hysteria 入站](https://xtls.github.io/en/config/inbounds/hysteria.html)：核对 Hysteria 用户认证字段及版本。
- [Xray Hysteria 传输](https://xtls.github.io/en/config/transports/hysteria.html)：核对 Hysteria2、TLS 及当前核心字段。线上文档可能使用更新的 `method`；本次分支已验证的是 `network: hysteria`。
- [Xray FinalMask](https://xtls.github.io/en/config/transports/finalmask.html)：核对 UDP Salamander 的结构和参数。
- [Mihomo Hysteria2](https://wiki.metacubex.one/en/config/proxies/hysteria2/)：核对客户端 `password`、`obfs`、`obfs-password` 等字段。
- [Hysteria2 URI](https://v2.hysteria.network/docs/developers/URI-Scheme/)：核对分享链接、认证段百分号编码和 TLS 参数。
- [Hysteria2 混淆说明](https://v2.hysteria.network/docs/advanced/Full-Server-Config/#obfuscation)：Salamander 将包混淆为随机字节，客户端/服务器密码一致。这里是独立 Hysteria 服务端的 YAML，不能直接填进 Xray 的 JSON。

复用时检查现场版本、证书和实际网络；字段缺失或名称变化时核对当前面板生成配置，不因一个新版本示例而改写已工作服务。本 Skill 不要求安装官方独立 Hysteria 服务，也不以 Cloudflare CDN、Nginx 或 Remnawave 为前提。
