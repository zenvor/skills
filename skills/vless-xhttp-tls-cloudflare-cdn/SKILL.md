---
name: vless-xhttp-tls-cloudflare-cdn
description: 在已有 3X-UI 中搭建、迁移和排查经 Cloudflare CDN 的 VLESS + XHTTP + TLS 节点，涵盖源站证书、DNS 橙云、严格回源、独立客户端、节点分享或订阅导出与真实代理验收。面板及订阅下载入口的 Nginx 代理为按需扩展；不用于通用面板管理、纯 Reality 调参或服务器重装。
---

# VLESS XHTTP TLS 套 Cloudflare CDN

主链路：支持 XHTTP 的客户端 → Cloudflare 边缘 HTTPS → 源站 Xray 的 XHTTP TLS 入站。默认采用公网 `443`，源站可用其他空闲 TLS 端口；端口不同才需要回源端口重写。3X-UI 是本技能的实施前提。

按任务读取：

- 创建、迁移入站及客户端：[xhttp-inbound.md](references/xhttp-inbound.md)。
- 首次签发、复用或更换证书：[origin-ca-bootstrap.md](references/origin-ca-bootstrap.md)。用户明确要求清除后重建时，使用其中的[无证书起点验收](references/origin-ca-bootstrap.md#无证书起点的实战验收)。
- DNS、严格模式、回源规则：[cloudflare-dashboard.md](references/cloudflare-dashboard.md)。
- 仅当用户还需要代理面板或订阅下载网址时，读取 [port-split.md](references/port-split.md)。节点接入 CDN 不要求安装 Nginx 或迁移管理入口。

## 实施顺序

1. 确认目标 SSH 主机/IP、Cloudflare 区域、域名、面板/核心版本、实际监听与已有服务。记录入站端口、路径、客户端绑定和 flow，备份本次涉及的配置及规则。采用独立 Subconverter 模块的分支还需备份其 `subconverter.db`；按现场确认路径，不能假定面板主库已包含订阅配置。已有节点做真实代理基线；故障或新建时如实记录失败或缺失状态。
2. 核对或签发源站证书，部署到实际 TLS 终止点。新建节点优先使用独立客户端、独立 UUID、空 flow；原 Reality 的凭据和 flow 保持原值。共享客户端仅在明确需要时采用，并核验全局值未被改写。
3. 配好 XHTTP、TLS 和客户端后启用目标入站，验证本机监听、证书链、域名及实际呈现的证书，再切换公网入口。动态入站可能未写入磁盘 Xray JSON，结合面板/API、数据库、监听和连接判断，不为生成文件缺项重启服务。
4. 配置或核对 DNS 橙云、边缘证书和 Full (strict)。回源端口不同时，精确匹配域名和节点入口端口，重写到实际源站 TLS 端口。已有严格模式保持原值；首次切换前检查区域内其他源站的影响。
5. 导出节点分享或订阅，用实际导出参数完成下面的验收。只改节点时保留原面板和订阅下载入口。

Origin CA 站点证书及私钥供源站使用，根证书供校验使用；客户端连接 Cloudflare 时信任边缘证书。不能用 Flexible、关闭证书校验或 `curl -k` 作为成功依据。只读调查、解释或审查技能不触发线上修改。

## 验收与交付

- 核对源站实际端口、回源规则（若有），以及导出节点的域名/公网端口、UUID、XHTTP 路径/模式、TLS/SNI 和 flow。
- 采用订阅时，以 `User-Agent: clash` 下载实际订阅；若 YAML 使用 `proxy-providers`，确认 URL 属于授权服务后继续下载 provider，检查真实节点。单节点分享或文件交付不要求另建订阅。
- 用支持 XHTTP 的客户端加载实际导出节点，经 Cloudflare 完成真实代理请求并核对响应。可用隔离的本机 SOCKS 测试进程，结束后清理；不改变用户现用代理。TCP/TLS 成功、根路径 404、流量计数和 YAML 解析均不能替代协议验收。
- 面向大陆使用时，从可用且已授权的大陆测试点复测。区分直连与 VPN/TUN 路径；云服务器测试不等于 Windows 导入或各运营商均通过。没有测试条件时列明缺口。
- 本次还代理面板/订阅下载入口时，追加页面、静态资源/API、外部 URL、缓存和端口分流验证，要求见可选文档。

失败时保存证据，按本次备份恢复或暂停目标服务；不反复切换 SSL 模式、累积规则或扩大放行范围。交付实际变更、地址/配置、测试结果和保留入口，区分新签发、复用与清除后重建。私钥、UUID、订阅令牌不写进技能、通用报告或截图；交付配置按敏感文件保存。
