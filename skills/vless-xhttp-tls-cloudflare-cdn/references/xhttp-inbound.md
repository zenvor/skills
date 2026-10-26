# 3X-UI 入站、客户端与节点导出

先确认新建或迁移；保留未要求更改的用户、额度、路径和入站。界面名称随版本变化，以下使用常见的 Inbounds、Clients 及入站编辑页签。

## 1. 创建入站

在 **Inbounds → Add Inbound** 创建，或 Edit 目标入站。新入站在 TLS 和客户端配好前保持禁用。

| 位置 | 设置 |
|---|---|
| Basics → Protocol | `vless` |
| Basics → Port | 已确认空闲的源站端口，例 `31509` |
| Basics → Address / Listen | 能收到预期回源连接；Cloudflare 直接回源不能只监听回环 |
| Protocol | 本方案使用 `decryption: none`，不额外启用 VLESS Encryption 扩展 |
| Stream → Transmission | `XHTTP` |
| Stream → Path | 以 `/` 开头的非空路径；迁移保持原值，客户端必须一致 |
| Stream → Mode | 先使用双方支持的 `auto` 或已验证模式 |
| Security | `TLS`，按[证书文档](origin-ca-bootstrap.md)引用证书及配对私钥 |

服务端的 Host、SNI 限制及 ALPN 按当前核心与实际模式配置，不从客户端字段机械照抄。需要 HTTP/2 时，源站 ALPN 必须支持 `h2`。其他缓冲、填充等参数先保留合理默认或已验证值。

Transmission 与 Security 是不同字段；本方案为 XHTTP + TLS，不是 RAW/TCP、WebSocket 或 Reality。客户端核心必须明确支持 XHTTP，不能仅凭“Clash”名称或 YAML 可解析判定兼容。

## 2. 创建或关联客户端

**优先独立客户端：**在该版本的 Clients 新增入口或入站客户端区生成独立 UUID，flow 留空，只关联目标 XHTTP 入站。保持原 Reality 客户端凭据、flow 和绑定不变；Reality 并不代表已经开启 Vision。

部分分支将客户端独立管理，新入站可能显示 0 clients。创建/关联客户端后，核对实际绑定及入站认可的 UUID。部分界面的 **more → Attach Existing Clients…** 用于关联已有客户端；勾选订阅中的 Associated Inbounds 不能替代这项绑定。

**仅在明确需要共享身份或额度时复用：**读取原全局 flow，确认部署版本支持按入站覆盖。例如 **Basics → Disable XTLS flow** 应只用于目标 XHTTP。操作后同时核对全局客户端值、Reality 的服务端/导出参数未变，XHTTP 的有效及导出 flow 为空。没有可靠隔离机制时使用独立客户端，不为 XHTTP 清空共享用户的 flow，也不顺带给原 Reality 开启 Vision。

删除旧入站前，先按需要取消其订阅关联，再核对共享客户端的生命周期及其他绑定。不能按删除提示猜测会保留或删除哪些全局用户；清理后确认保留的客户端、节点参数与监听符合预期。

## 3. 应用 TLS 与回源配置

TLS、客户端和路径配好后启用入站，检查 Xray 状态、实际监听、证书链/域名和呈现指纹，再配置公网路由。只 reload 必要服务，不为验证重启整个面板。防火墙/安全组需允许授权回源到达该端口；变更访问范围时保留既有依赖。

按 [Cloudflare 文档](cloudflare-dashboard.md) 配好橙云和 Full (strict)。直接回源时，端口重写（若需要）的目标等于实际 XHTTP TLS 入站 Port；经过网关时应先指向网关 TLS 端口。

`auto` 的具体选择随核心版本及传输条件而定。TLS H2 下采用带 gRPC 请求头的模式时，检查 **Cloudflare → 网络 → gRPC**、HTTP/2 和源站 ALPN；不要把所有 403 都归为证书故障。按 [XHTTP 项目说明](https://github.com/XTLS/Xray-core/discussions/4113) 和 [Cloudflare gRPC 条件](https://developers.cloudflare.com/network/grpc-connections/)核对端口及协议限制，再实测该模式，不能仅凭端口属于 HTTPS 支持列表就宣告兼容。

## 4. 导出与订阅

核对实际导出节点：

| 字段 | 本方案要求 |
|---|---|
| 协议 / 地址 | VLESS / 橙云域名，例如 `edge.example.com` |
| Port | 公网入口，通常 `443`，不是源站自定义端口 |
| UUID | 与目标入站认可的客户端一致 |
| Transport / Path / Mode | XHTTP；路径与服务端一致；模式双方支持 |
| TLS / SNI | 开启 TLS，SNI 为边缘证书覆盖的代理域名，正常验证证书 |
| Flow / Encryption | 空 flow；不启用额外 VLESS Encryption，分享链接中通常为 `encryption=none` |

部分自定义分支可用 **Subconverter → 订阅 Edit → XHTTP 入站 → CDN Override** 设定 Server、Port、SNI；其他版本使用其实际支持的分享地址配置。覆盖导出地址不改变源站监听端口。

独立客户端的订阅只选择所需入站与用户。若聚合另一个 Reality 用户，先检查订阅对共同客户端和流量统计的限制，不能为让表单通过而把新用户关联到所有入站；必要时使用两个订阅，由支持的客户端本地聚合。

分享链接、配置文件或订阅/provider 都必须核对真实节点参数，并用实际导出节点完成 `SKILL.md` 中的代理验收。订阅下载入口即使使用 `8443`，其中的 XHTTP 节点仍使用既定公网入口。

将导出节点转换为另一核心的测试配置时，也保留其 ALPN、TLS 指纹和 XHTTP 扩展参数。例如 `client-fingerprint` 对应 Xray 的 `tlsSettings.fingerprint`，`xhttp-opts.x-padding-bytes` 对应 `xhttpSettings.xPaddingBytes`；遗漏这些字段后的测试不能代表原导出配置。

协议参考：[VLESS](https://xtls.github.io/config/inbounds/vless.html)、[XHTTP](https://xtls.github.io/config/transports/xhttp.html)。面板/核心版本不同，不用最新文档示例直接覆盖面板管理的生成配置。
