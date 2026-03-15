# OpenMemory MCP 连接调试指南

## 诊断结论（2025-03）

- **服务端正常**：HTTPS 请求（跳过 SSL 校验）可成功建立 SSE 连接，返回 200
- **可能原因**：SSL 证书链问题（self-signed in chain），或 Cursor 对证书校验较严

## 快速验证

在终端执行（需替换为你的 API Key）：

```bash
# 测试 HTTPS（跳过证书校验）
curl -k -m 5 -H "Authorization: Bearer <your-api-key>" \
  "https://arthaszeng.top/memory-mcp/cursor/sse/arthaszeng"
```

若看到 `event: endpoint` 和 `data: /memory-mcp/messages/...`，说明服务端正常。

## 解决方案

### 1. 修复 SSL 证书（推荐）

确保 `arthaszeng.top` 使用受信任证书（如 Let's Encrypt）：

```bash
# 在服务器上检查证书链
openssl s_client -connect arthaszeng.top:443 -servername arthaszeng.top </dev/null 2>/dev/null | openssl x509 -noout -text
```

若证书链有问题，用 certbot 等工具更新证书。

### 2. 尝试 HTTP（绕过 SSL）

`nginx.cloud.conf` 已在 80 端口配置 MCP。若网络允许，可改用 HTTP：

```json
// ~/.cursor/mcp.json
{
  "mcpServers": {
    "OpenMemory": {
      "url": "http://arthaszeng.top/memory-mcp/cursor/sse/arthaszeng",
      "headers": {
        "Authorization": "Bearer <your-api-key>"
      }
    }
  }
}
```

注意：若在公司网络（如 Zscaler），HTTP 可能被拦截。

### 3. 本地开发用 localhost

若 OpenMemory 在本地运行：

```json
"OpenMemory": {
  "url": "http://localhost:8765/memory-mcp/cursor/sse/arthaszeng",
  "headers": {
    "Authorization": "Bearer <your-api-key>"
  }
}
```

### 4. Cursor 设置

- 打开 Cursor Settings → MCP → 查看 OpenMemory 的详细错误
- 重启 Cursor 后重试连接
- 确认 API Key 未过期（在 OpenMemory UI 的 API Keys 页面检查）

## 配置格式参考

| 场景 | URL 格式 |
|------|----------|
| 无项目 | `{base}/memory-mcp/{client}/sse/{user_id}` |
| 有项目 | `{base}/memory-mcp/p/{project_slug}/{client}/sse` |

示例：
- `https://arthaszeng.top/memory-mcp/cursor/sse/arthaszeng`
- `https://arthaszeng.top/memory-mcp/p/my-project/cursor/sse`

## 常见错误

| 现象 | 可能原因 |
|------|----------|
| MCP server errored | SSL 证书、网络、或 API Key 无效 |
| 401 Unauthorized | API Key 错误或已失效 |
| 404 | URL 路径错误，或 nginx 未正确代理 |
| 连接超时 | 防火墙/代理阻断，或服务未启动 |
