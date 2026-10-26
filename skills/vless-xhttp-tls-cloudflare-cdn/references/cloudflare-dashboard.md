# Cloudflare：DNS、严格回源与端口规则

以下示例使用 `edge.example.com`、VPS 地址 `192.0.2.10`。所有值按现场替换；正确的既有记录及规则直接保留。菜单翻译会变化，按实际字段核对。

| 配置 | 常见入口 | 作用 |
|---|---|---|
| DNS 与橙云 | DNS → 记录 | 指向源站并开启代理 |
| Origin CA | SSL/TLS → 源服务器 → Origin 证书 | 签发部署在 VPS 上的站点证书 |
| Full (strict) | SSL/TLS → 概述 → 配置 | 对 HTTPS 回源严格校验证书 |
| Origin Rules | 规则 → 概述 → Origin Rules | 按条件改写回源端口 |

## 1. DNS 与边缘证书

在 **DNS → 记录 → 添加记录** 创建或编辑 A 记录：名称 `edge`，地址为目标 VPS IPv4，代理状态为 **已代理 / Proxied**（橙云），TTL 使用界面允许的自动值。保存后确认完整域名和地址，不改无关记录。只有确认源站 IPv6 与服务可用时才添加 AAAA。

橙云启用后，公共解析应返回 Cloudflare 边缘地址；控制台记录内容仍是源站地址。不要把本机 TUN 的 Fake-IP 结果当成公共 DNS。核对 **SSL/TLS → 边缘证书** 中覆盖代理域名的证书已生效，并通过客户端正常 TLS 校验。

## 2. 源站证书与 Full (strict)

先按 [origin-ca-bootstrap.md](origin-ca-bootstrap.md) 将合格证书配置到 XHTTP TLS 入站，并验证实际监听呈现的证书。已有覆盖该域名的公开可信 CA 证书也可使用，不必改签 Origin CA。

在 **SSL/TLS → 概述 → 配置** 选择 **Full (strict)**。中文界面可能显示“完全（严格）”或“完整（严格）”，以实际选项为准。它严格校验 HTTPS 回源证书，不自动将所有客户端 HTTP 请求跳转为 HTTPS；跳转和其他源连接设置不属于此步骤。区域级模式变更前检查其他主机名的影响，已配置正确则保持。

官方条件：[Full (strict)](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/)。

## 3. 按需配置 Origin Rule

公网节点端口与源站 TLS 端口相同且既有规则未改变目标时，可省略端口重写。不同才在 **规则 → 概述 → Origin Rules → 创建规则** 配置；已有对应规则则编辑，避免重复覆盖。

例如公网 `443`、Xray 入站 `31509`：

```text
(http.host eq "edge.example.com" and cf.edge.server_port eq 443)
```

- 目标端口选择“重写到”，填实际 XHTTP TLS 入站的 **Basics → Port**，例 `31509`。
- Host、SNI、DNS 目标保持原值，本方案不依赖高级重写。
- 检查规则顺序及其他匹配项，防止后续规则覆盖目标；保存后核对条件、端口和活动状态。

`cf.edge.server_port` 是 Cloudflare 接收请求的端口，不是源站端口。源站自定义端口无需等于客户端端口；客户端应使用 [Cloudflare 支持的 HTTPS 入口端口](https://developers.cloudflare.com/fundamentals/reference/network-ports/)。公网入口支持不代表所有 XHTTP 模式均兼容，按实际模式测试。

若 Cloudflare 首先连接的是网关，规则应指向网关 TLS 端口；面板/订阅下载分流见 [port-split.md](port-split.md)。不要让只按域名匹配的规则把其他入口也送到 XHTTP。

官方参考：[Origin Rules 设置](https://developers.cloudflare.com/rules/origin-rules/features/)、[入口端口字段](https://developers.cloudflare.com/ruleset-engine/rules-language/fields/reference/cf.edge.server_port/)。

## 4. 对应核验

确认橙云、边缘证书、源站证书、严格模式和有效回源目标，再按 `SKILL.md` 使用实际导出的节点验收。配置页面正确不等于代理成功。

部分 3X-UI 自定义分支提供 **Subconverter → 订阅 Edit → 对应 XHTTP 入站 → CDN Override**：Server 和 SNI 为橙云域名，Port 为公网入口。此项只覆盖导出地址，不创建 DNS、回源规则或证书，也不改变源站入站端口。没有此功能时按实际版本的分享地址配置处理。
