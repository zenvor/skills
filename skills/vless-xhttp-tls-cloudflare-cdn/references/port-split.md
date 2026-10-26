# 可选：代理面板与订阅下载入口

仅在用户需要通过 CDN 访问管理或订阅下载网址时使用。节点主流程不依赖 Nginx。以下为同域名分端口示例，路径、端口和证书均按现场替换，不整份覆盖已有网关。

```text
edge.example.com:443  → Cloudflare → Xray XHTTP TLS :31509
edge.example.com:8443 → Cloudflare → Nginx :8443 → 实际面板/订阅服务
```

## 切换顺序

1. 读取实际面板随机路径、订阅/provider 路径及各自服务端口；它们可能由不同进程提供。检查现有代理、监听和证书，备份相关配置/规则，沿用已有网关。
2. 准备管理入口，检查证书、上游验证与授权回源来源。新装 Nginx 时注意默认 `80` 站点及端口冲突；运行 `nginx -t` 后才 reload。
3. 用本机 `curl --resolve` 和适当 CA 验证 Nginx 及上游，再切换 Cloudflare 路由。节点入口与管理入口分别匹配；不能用覆盖整个域名的规则把二者送到同一错误端口。回源规则步骤见 [cloudflare-dashboard.md](cloudflare-dashboard.md)。
4. 验证浏览器页面、静态资源/API、订阅与 provider 及原 XHTTP 代理。确认稳定后只清理本次不再使用的配置；旧管理直连入口仅在明确授权且无遗留依赖时关闭。

## Nginx 结构示例

以下置于 `http` 上下文，使用 Nginx 1.25.1+ 的 `http2 on`。旧版采用其支持的 `listen ... ssl http2` 语法，并检查模块。示例假设：公网与 Nginx 均为 `8443`，面板和订阅恰好共用 HTTPS `58372`，上游证书覆盖 `panel-origin.example.com`。不满足这些假设时先调整路径、协议、端口、CA 和代理信任配置。

```nginx
map $http_upgrade $panel_connection_upgrade {
    default upgrade;
    '' close;
}
server {
    listen 8443 ssl;
    http2 on;
    server_name edge.example.com;
    ssl_certificate /etc/ssl/cloudflare/example-origin.pem;
    ssl_certificate_key /etc/ssl/cloudflare/example-origin.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    absolute_redirect off;

    # 文件中配置核实的 Cloudflare set_real_ip_from 网段。
    include /etc/nginx/snippets/cloudflare-real-ip.conf;
    real_ip_header CF-Connecting-IP;

    proxy_http_version 1.1;
    proxy_cache off;
    proxy_ssl_server_name on;
    proxy_ssl_verify on;
    proxy_ssl_verify_depth 3;
    proxy_ssl_name panel-origin.example.com;
    proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;

    location = /panel-random { return 308 /panel-random/; }
    location ^~ /panel-random/ {
        proxy_pass https://127.0.0.1:58372;
        include /etc/nginx/snippets/panel-proxy-headers.conf;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $panel_connection_upgrade;
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_hide_header Cache-Control;
        add_header Cache-Control "no-store" always;
    }
    location ^~ /feed/ {
        proxy_pass https://127.0.0.1:58372;
        include /etc/nginx/snippets/panel-proxy-headers.conf;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_hide_header Cache-Control;
        add_header Cache-Control "no-store" always;
    }
    location / { return 404; }
}
```

每个代理 location 引用的 `panel-proxy-headers.conf`：

```nginx
proxy_set_header Host $http_host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-Forwarded-Host $http_host;
proxy_set_header X-Forwarded-Port $server_port;
```

配置注意：

- `proxy_set_header` 按层整体继承；location 添加 Connection/Upgrade 后，不能指望父层 Host 等仍逐条继承，因此每个代理 location 都 include 公共头。
- `$http_host` 保留外部端口；只有公网和 Nginx 端口相同时才使用 `$server_port`。本机相对跳转由 `absolute_redirect off` 保持；上游 Location、Cookie 和生成的订阅 URL 仍需实测。
- `proxy_pass` 不带 URI 才保留完整请求路径；不要随意追加尾部 `/`。保留 UA、Cookie 和订阅响应头，核对 provider URL 的域名/外部端口，而节点仍指向既定公网入口。
- Nginx 上游 HTTPS 需正确 SNI、证书名和 CA。公开 CA 使用适当系统 CA 文件；Origin CA 使用独立官方根证书。不能把连接回环地址当成无需校验的理由。
- `proxy_cache off` 禁止继承的代理缓存；管理/订阅响应 no-store 与 Cloudflare 缓存规则另外核对。沿用合适的脱敏日志，不记录完整订阅令牌。
- 仅信任官方 Cloudflare 网段的 `CF-Connecting-IP`；源站访问限制按授权配置。只加 allow 规则不一定消除既有“允许全部”策略，也不能为套 CDN 自动切断运维入口。

## 共用公网 443

这是另一种网关布局：Cloudflare 首先回源网关 TLS 端口，再按路径分流。不能直接把上述管理 HTTP/1.1 反代块用于全部 XHTTP 模式。按核心及模式设计流式上行、HTTP/2/gRPC 上游、缓冲、请求体限制、超时和 TLS 验证，以真实协议请求验收。不得抢占其他节点已用的 `443`。

来源：[Nginx proxy 模块](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)、[相对跳转](https://nginx.org/en/docs/http/ngx_http_core_module.html#absolute_redirect)、[HTTP/2](https://nginx.org/en/docs/http/ngx_http_v2_module.html)、[Cloudflare IP 网段](https://www.cloudflare.com/ips/)、[XHTTP 项目说明](https://github.com/XTLS/Xray-core/discussions/4113)。官方只读网段 API `https://api.cloudflare.com/client/v4/ips` 需检查 success 和 IPv4/IPv6 CIDR 内容。
