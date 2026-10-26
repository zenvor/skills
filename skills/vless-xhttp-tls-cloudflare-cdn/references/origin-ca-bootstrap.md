# 源站证书：首次部署、复用与更换

Cloudflare 到 Xray 的 HTTPS 回源必须加载覆盖目标域名的合格证书；Origin CA 或公开可信 CA 均可满足 Full (strict)。已有证书先检查再复用；没有证书时执行首次签发。仅在用户明确要求时执行文末清除重建演练。

客户端到 Cloudflare 使用边缘证书，Cloudflare 到源站使用站点证书。Origin CA 根证书用于验证签发链，不能代替站点证书或私钥填进入站，也不应为此加入系统信任。

## 1. 在 Cloudflare 签发

进入目标区域 **SSL/TLS → 源服务器 → Origin 证书 → 创建证书**，按[官方流程](https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/)操作。

1. 确认 SAN 覆盖实际回源域名及有效期；`*.example.com` 只覆盖一层子域名。Origin CA 不签发 IP SAN。
2. 选择一种密钥方式：
   - **Cloudflare 生成私钥和 CSR**：创建后以 PEM 格式分别保存 Origin Certificate 和 Private Key。离开页面后不能再次取回该私钥。
   - **自有 CSR**：在 VPS 准备私钥和对应 CSR，只向 Cloudflare 提交公开 CSR。下载签发后的站点证书；Cloudflare 不再提供私钥文件，私钥留在 VPS。
3. 首次或明确从零演练使用新密钥；正常续签按用户意图选择复用或轮换。证书必须与实际私钥配对，不能混用另一份密钥。

## 2. 部署与配对检查

文件路径示例：

```text
/etc/ssl/cloudflare/example-origin.pem
/etc/ssl/cloudflare/example-origin.key
```

检查同名文件与引用，普通替换保留回滚材料；演练备份与部署位置隔离，不参与新部署。自有 CSR 方式只传回证书。运行 Xray 的用户必须能读取文件及遍历父目录，私钥使用 `0600` 或必要的 `0640`；容器或远端节点路径必须在实际 Xray 环境可见。

在支持以下选项的 Bash/OpenSSL 环境执行，只输出元信息和公钥摘要：

```bash
set -euo pipefail
openssl x509 -in /etc/ssl/cloudflare/example-origin.pem -noout -subject -issuer -dates -ext subjectAltName
openssl x509 -in /etc/ssl/cloudflare/example-origin.pem -pubkey -noout \
  | openssl pkey -pubin -outform DER | openssl dgst -sha256
openssl pkey -in /etc/ssl/cloudflare/example-origin.key -pubout -outform DER \
  | openssl dgst -sha256
```

各命令必须成功，后两条摘要应一致；不能将命令失败产生的空输入摘要视为配对成功。摘要只证明密钥配对，仍需验证签发链、SAN、有效期和服务实际呈现的证书。OpenSSL/LibreSSL 选项不同时适配命令，不跳过校验。

## 3. 在入站中引用

常见路径：**Inbounds → 目标入站 Edit → Security → TLS → Digital Certificate**。

| 模式 | Public Key 字段 | Private Key 字段 |
|---|---|---|
| File Path（本流程） | 完整站点证书 PEM 文件路径 | 配对私钥文件路径 |
| File Content | 完整站点证书 PEM 内容 | 完整配对私钥 PEM 内容 |

这里的 Public Key 实际接收站点证书，不是单独公钥或 Reality 的 `pbk`。路径与内容不能混填；`Set Cert from Panel` 的实际结果需核对，不假定面板证书就是目标源站证书。保存时保留其他 TLS 参数，按该版本正常应用配置。

## 4. 验证真实 TLS 与严格回源

1. 从官方页面取得与签发链对应的根证书，在独立 CA 文件中验证站点证书及目标域名；公开可信 CA 则使用适当系统信任库。下载文件需确认是有效 PEM，不能把错误页当证书。
2. 对真实入站端口建立带正确 SNI 的新 TLS 连接，开启链与域名校验，并比较实际呈现证书和部署文件的指纹。不以磁盘文件、旧连接或 `curl -k` 作为成功依据。
3. 在 **SSL/TLS → 概述 → 配置** 核对/启用 Full (strict)。首次切换前检查区域影响，已启用则保持；不同时更改无关源连接设置。
4. 按 `SKILL.md` 用实际导出节点完成经 Cloudflare 的代理请求。525 优先排查 TLS 握手，526 优先排查源站证书；不以降低 SSL 模式代替修复。

源站证书不绑定 TCP 端口。若另加 Nginx 管理代理，即使复用同一证书，也必须在 Nginx 显式加载；Nginx 到本机 HTTPS 服务还要独立验证该上游证书。该上游仍在使用的证书继续承担续期责任。

## 无证书起点的实战验收

仅用于用户明确要求清除旧源站证书后从零演练；普通部署不删除有效证书。

1. 查清旧证书/私钥被哪些入站、面板、订阅及网关引用，备份配置与必要回滚材料。目标是让本次入站没有旧部署，不删除其他服务证书、系统根证书或未授权的共享文件。
2. 暂停目标入站，清除其证书引用，移除授权范围内的旧证书与私钥。记录旧指纹，确认部署路径不存在、引用已清空、旧监听已消失。只改名或继续使用进程内旧证书不算清理完成。
3. 按本文第 1—3 节重新生成密钥、签发、部署并配置新证书。核对新指纹/序列号与旧值不同，以及实际监听呈现新证书。
4. 保持严格模式，重做实际代理请求及本次使用的订阅/provider 验收，确认其他节点及面板证书未变；失败按备份恢复或保持目标暂停。

有些面板不允许保存证书为空的 TLS 表单：在目标禁用时临时保存 Security=None，记录并在恢复时还原 SNI、ALPN 等可能被重置的参数；新证书配好后才恢复 TLS 并启用。不得开放临时无 TLS 的入站。

移除本机旧文件不等于撤销 Cloudflare 证书记录，未核清其他主机引用时不撤销共享旧证书。回滚备份不参与演练成功路径，验证后按约定处理临时私钥副本。
