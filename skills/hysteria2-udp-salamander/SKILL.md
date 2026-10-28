---
name: hysteria2-udp-salamander
description: 在已有 3X-UI/Xray 中部署和排查直连 Hysteria2 UDP + Salamander 节点，使用有效 TLS 证书、独立客户端及 Mihomo 真实代理验收；适合 TCP 受限而 UDP 可能仍可用的恢复场景。不用于 Cloudflare CDN 节点、独立 Hysteria 服务端安装或 ICMP 隧道。
---

# Hysteria2 UDP + Salamander

链路：Mihomo 客户端 → VPS 的 UDP 端口 → Xray Hysteria2 入站 → 互联网。保留现有 Reality、面板及订阅，不因新增 UDP 节点改变它们。

本流程基于 `zenvor/3x-ui` 3.9.0、Xray 26.6.27、Mihomo 1.19.32 的实测，见 [验证记录与官方资料](references/verified-workflow.md)。其他版本先核对对应界面和导出字段；不自动升级面板或核心。

## 1. 确认现场与备份

- 核对 SSH 主机/IP、面板所属服务器、面板与核心版本、现有入站/客户端关联、证书路径、UDP 监听及防火墙。管理路径不通时先使用已有可用 SSH、海外测试点或供应商控制台，不重置服务器。
- 区分 ICMP、TCP 和 UDP。ping 或 TCPing 不能证明 Hysteria2 可用；UDP 是否可用由后续真实协议测试判断。Salamander 不能突破对 UDP 的整体阻断。
- 默认选择空闲 UDP 443；已有 TCP 443 可并存，检查 `ss -lunp` 确认 UDP 未被占用。按现场选择其他单一 UDP 端口也可，不预设跳跃端口或范围放行。
- 用 SQLite 在线备份或面板支持的方式备份实际主库；本次分支默认路径为 `/etc/x-ui/x-ui.db`。独立订阅模块另有 `/etc/x-ui/subconverter.db`，涉及它时一并备份。记录原入站、客户端绑定、flow、监听和防火墙基线。备份目录 0700、文件 0600，留在受控服务器上，不提交仓库。

## 2. 核验证书

本流程前提是服务器已有可用的公网信任 TLS 证书及对应私钥。此次实战复用 Let’s Encrypt；没有合适证书时，先按该服务器的证书管理方式完成签发和部署，再继续，不把已有证书当成首次签发结果。

- 核对有效期、SAN 是否包含节点 SNI、证书与私钥匹配，以及 Xray 服务身份能否读取文件。使用完整证书链文件及私钥的实际路径，核对现有续期机制。
- 入站「安全 → TLS → Digital Certificate / 数字证书 → File Path / 文件路径」中，Public Key 填完整证书链文件路径，Private Key 填私钥路径。这里的 Public Key 字段指证书文件，不是 Reality 公钥。
- 「从面板设置证书」仅在面板证书的域名、信任链和读取权限都适用时使用；面板能打开不代表其证书适用于节点 SNI。
- 这是客户端直连 VPS：不能直接套用仅受 Cloudflare 信任的 Origin CA 证书。保留客户端证书校验，不用 `skip-cert-verify: true` 或 `curl -k` 通过验收。

## 3. 创建独立入站和客户端

在「入站 → 添加入站」中新建，避免克隆原 Reality 后遗留协议参数。先保存为禁用状态；临时恢复可使用明确的临时备注，并设为「从订阅排除」。

| 设置位置 | 配置及核对值 |
| --- | --- |
| 基础 | 协议 `hysteria`，选定 UDP 端口，监听所需公网接口 |
| 传输 | `hysteria`，版本 **2**；UDP 空闲超时此次使用默认 60 秒 |
| 安全 | TLS、节点 SNI、有效证书/私钥文件路径、ALPN `h3` |
| UDP 混淆 / FinalMask | `salamander`，独立生成强随机混淆密码 |

本次分支导出的 `streamSettings` 使用 `network: hysteria`、`hysteriaSettings.version: 2` 和 `security: tls`；Salamander 位于 `finalmask.udp[]`，类型为 `salamander`，密码位于该项 `settings.password`。新版本官方文档可能使用 `method`，以当前面板和核心实际生成并接受的字段为准，不照搬不同版本的 JSON 或直接改运行库。

在「客户端 → 添加客户端」中新建专用客户端：

1. 启用客户端，仅勾选刚创建的 Hysteria 入站；清除默认选中的其他入站，不复用或改写原 Reality 客户端的 flow/凭据。
2. 在「凭据 / Credentials」中生成并保存 Hysteria 的 **Auth**。这是客户端认证密码，和入站的 **Salamander 混淆密码**是两个独立值。不能拿 VLESS UUID 或其他协议的 Password 字段代替 Auth。
3. 保存后核对实际绑定和导出数据：专用客户端已启用、Auth 非空，仅关联目标入站。

实战中客户端入站选择器只列出已启用入站。如果禁用入站不可选，可先启用目标入站，保持其外网 UDP 入口被防火墙挡住，完成专用客户端与 Auth 后再放行。若该端口已经对外放行，不能假定入口已被挡住，应先确认未认证连接会被拒绝或先收紧新端口。不要为了让选择器显示而改选 Reality 入站。

## 4. 启用并放行 UDP

核对证书、专用客户端及 Auth、Salamander 配置后启用目标入站，确认 Xray 运行正常且 UDP 端口由预期进程监听。

- 在实际使用的主机防火墙和供应商安全组中放行目标 **UDP** 端口。UFW 示例：`ufw allow 443/udp`；只放 TCP 不够。核对 IPv4，以及实际使用 IPv6 时的规则。
- 节点地址用实际 VPS IP 或指向它的「仅 DNS」域名。普通 Cloudflare 橙云不能代理此 Hysteria2 UDP 链路；本流程不改 Cloudflare、面板或订阅入口。
- 结合面板/API、实际配置及监听核对。面板动态加入的入站不一定立即写入磁盘 Xray JSON，不能仅因 JSON 缺项就重启整个服务。

## 5. 导出与真实代理验收

优先使用面板导出的节点核对参数；客户端支持不完整时，用 [Mihomo 配置模板](assets/mihomo-template.yaml) 填入同一组实际参数，不使用模板的示例地址和示例密码发起连接。

- `type: hysteria2`；`server` 为 VPS 地址，`port` 为 UDP 端口；`password` 对应专用客户端 **Auth**。
- `sni` 对应证书域名；`skip-cert-verify: false`，`alpn: [h3]`；`obfs: salamander`，`obfs-password` 对应入站混淆密码。含特殊字符的凭据通过 YAML 序列化器正确转义。
- 分享链接采用 Hysteria2 URI，认证段及查询值正确百分号编码，包含 SNI、混淆类型和密码，不打开不安全证书选项。导入后复核客户端是否保留这些参数。
- 临时单节点测试不要求加入原订阅；需要订阅时再明确关联范围，核对最终实际导出内容。
- 配置与分享链接含认证材料，按敏感文件保存，Unix 权限 0600；不写入 Skill、公共日志、截图或 Git。

采用隔离 Mihomo 进程与独立配置目录，保留用户现用代理。模板的本地端口若被占用则选其他空闲端口，保持仅绑定回环地址、TUN 关闭、没有 DIRECT 回退。依次完成：

1. **配置检查**：`mihomo -t -d TEST_DIR -f CONFIG_FILE`，通过后用同样的目录和文件启动测试实例。语法通过仅说明配置可加载。
2. **直连路径**：检查已有 TUN、VPN 和系统路由；本次本机使用实际物理接口 `en0`、大陆 Linux 使用 `eth0`，通过测试配置 `interface-name` 绑定。每台设备先核对真实接口，不把这些名字硬编码到交付文件；必要时用路由/抓包确认去 VPS 的 UDP 没经另一个代理。
3. **正向请求**：经隔离实例的回环 HTTP/SOCKS 代理访问测试目标。示例：`curl --noproxy "" --proxy http://127.0.0.1:7890 --connect-timeout 7 --max-time 15 -sS -o /dev/null -w '%{http_code}' https://www.gstatic.com/generate_204`，预期 204；再经同一代理访问 `https://www.cloudflare.com/cdn-cgi/trace`，预期 200，核对 `ip=` 为目标 VPS 的实际出口，并查客户端日志确认选中此节点。存在上游出口/NAT 时先确认预期出口。
4. **大陆复测**：面向大陆使用时，从可用且已授权的大陆直连测试点重复协议请求。记录测试点和路径；没有条件就明确缺口。海外成功不能代替大陆验收。
5. **认证反例**：仅在测试配置副本中把 Auth 改为错误值，保留正确的混淆密码和 TLS 设置，确认代理请求被认证拒绝，再恢复正确 Auth。应能看到认证失败证据；任意超时不能当作认证生效。不要改服务器或用户正在使用的凭据。
6. **保持原有服务**：对照备份核对原入站、客户端绑定、Reality flow 和原订阅；计数或更新时间的正常变化不等于配置被改。检查本次涉及数据库的 `PRAGMA quick_check`，结果应为 `ok`。

上述 HTTP 请求验证的是经 Hysteria2 的真实 TCP 应用流量，不能宣称已覆盖任意 UDP 应用、整机 TUN、游戏、长期吞吐或全部运营商。监听、端口扫描、流量计数和导入成功都不能代替真实代理验收。

## 6. 交付、故障与回退

交付节点配置/分享文件、实际监听端口、证书复用情况、测试点/结果和未覆盖项。结束测试实例并清除临时凭据副本、进程、下载的测试程序，保留用户所需导入文件及受控备份；临时节点是否继续保留按用户决定，不自动到期删除。

失败按链路排查：UDP 无包先查路径/防火墙；TLS 失败查 SNI、时间、链与文件权限；握手超时也核对两端 Salamander 密码；认证失败核对独立客户端 Auth/启用/绑定。用有限测试和证据定位，不连续换端口、叠加混淆或关闭证书校验。

需要回退时，仅停用/移除本次新增入站和专用关联，撤销本次新加且无其他用途的 UDP 规则，清理测试进程；共享证书和原客户端不删。优先精确回退新增项目，完整数据库恢复前先核对备份后的其他变更，避免覆盖用户工作。清理后复查监听、防火墙和原服务。
