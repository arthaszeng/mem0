# Nginx 反向代理配置

管理阿里云服务器 (47.108.141.20) 上的 Nginx 配置。

## 服务器部署方式

Nginx 以 Docker 容器运行，使用 `--network host` 模式：

```bash
docker run -d \
  --name nginx \
  --network host \
  --restart unless-stopped \
  -v /home/admin/nginx/conf/nginx.conf:/etc/nginx/nginx.conf:ro \
  -v /home/admin/nginx/cert:/etc/nginx/cert:ro \
  nginx:alpine
```

## 路由表

| 路径 | 协议 | 上游端口 | 服务 |
|------|------|----------|------|
| `/memory-mcp/` | HTTP + HTTPS | 8765 | OpenMemory MCP SSE |
| `/concierge-mcp/` | HTTP + HTTPS | 8767 | Concierge MCP SSE |
| `/api/` | HTTPS | 8765 | OpenMemory REST API |
| `/memory` | HTTPS | 3001 | OpenMemory UI |
| `/agent/` | HTTPS | 8766 | LangGraph Agent |
| `/chat` | HTTPS | 302 → :3211 | Lobe Chat |
| `:3211/` | HTTPS | 3210 | Lobe Chat (直连) |

MCP 路径在 HTTP 80 端口保持直通（不做 301→HTTPS），因为 Cursor 的 SSE 连接在本地代理环境下 TLS 握手会失败。

## 部署更新

```bash
# 1. 编辑本地 nginx.conf

# 2. 同步到服务器
scp -i ~/.ssh/arthas nginx/nginx.conf admin@47.108.141.20:~/nginx/conf/nginx.conf

# 3. 测试配置
ssh -i ~/.ssh/arthas admin@47.108.141.20 "docker exec nginx nginx -t"

# 4. 热重载（不中断连接）
ssh -i ~/.ssh/arthas admin@47.108.141.20 "docker exec nginx nginx -s reload"
```

## SSL 证书

- 路径: `/home/admin/nginx/cert/arthaszeng.top.{pem,key}`
- 颁发: DigiCert (Encryption Everywhere DV TLS CA - G2)
- 有效期至: 2026-06-03
- 证书不纳入 git 管理（敏感文件）
