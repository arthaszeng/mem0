# MCP Streamable HTTP 兼容性问题汇总

## 问题现象

Cursor 连接 Memverse MCP 时报错：

```
Error POSTing to endpoint: {"detail":"Method Not Allowed"}
```

## 根本原因

**Cursor 已默认使用 Streamable HTTP 传输**，而 Memverse 目前只实现了 legacy SSE 传输，两者协议不兼容。

| 传输方式 | 客户端行为 | 服务端当前实现 |
|----------|------------|----------------|
| **SSE (legacy)** | 1) GET 建立连接 → 2) 解析 endpoint → 3) POST 到 messages 端点 | ✅ 已支持 |
| **Streamable HTTP (Cursor 默认)** | 直接 POST 到配置的 URL | ❌ 未支持（该路径仅接受 GET） |

## 技术细节

### 当前 SSE 流程

1. 客户端 GET `https://host/memverse-mcp/cursor/sse/arthaszeng`
2. 服务端建立 SSE 连接，返回 `event: endpoint`，`data: /memverse-mcp/messages/?session_id=xxx`
3. 客户端 POST 到 `https://host/memverse-mcp/messages/?session_id=xxx` 发送 MCP 消息

### Cursor (Streamable HTTP) 实际行为

1. 客户端直接 **POST** 到配置的 URL：`https://host/memverse-mcp/cursor/sse/arthaszeng`
2. 服务端该路径只有 GET 处理器 → **405 Method Not Allowed**

### 受影响的路径

所有 SSE 端点路径，当收到 POST 时都会返回 405：

- `GET /memverse-mcp/{client_name}/sse` ✅
- `GET /memverse-mcp/{client_name}/sse/{user_id}` ✅
- `POST /memverse-mcp/{client_name}/sse` ❌ 无处理器
- `POST /memverse-mcp/{client_name}/sse/{user_id}` ❌ 无处理器
- `GET /memverse-mcp/p/{project_slug}/{client_name}/sse` ✅
- `POST /memverse-mcp/p/{project_slug}/{client_name}/sse` ❌ 无处理器

## 解决方案（服务端修复）

### 方案 A：为 SSE 路径增加 POST 支持（推荐）

在现有 SSE 路径上同时支持 POST，用于 Streamable HTTP 客户端：

- 为 `/{client_name}/sse`、`/{client_name}/sse/{user_id}`、`/p/{project_slug}/{client_name}/sse` 等路径添加 POST 处理器
- POST 时从 path 解析 `client_name`、`user_id`、`project_slug`，设置 context vars
- 使用 mcp 包的 `StreamableHTTPSessionManager` 或 `streamable_http` 模块处理请求

### 方案 B：新增独立 Streamable HTTP 端点

- 新增统一端点，如 `POST /memory-mcp/mcp` 或 `POST /memory-mcp/sse`（支持 POST）
- 用户身份通过 gateway headers（X-Auth-Username）或 path 参数传递
- 需要用户修改 Cursor 配置中的 URL

### 方案 C：双传输并存

- 保留现有 SSE 实现
- 使用 mcp 包的 `mcp.server.streamable_http` 增加 Streamable HTTP 支持
- 同一 MCP 服务同时支持 SSE 和 Streamable HTTP 客户端

## 参考资源

- mcp Python SDK: `mcp.server.streamable_http`, `mcp.server.streamable_http_manager`
- MCP 规范：SSE 已 deprecated，Streamable HTTP 为推荐传输
- Cursor 支持：SSE 与 Streamable HTTP，对远程 URL 默认使用 Streamable HTTP

## 影响范围

- **所有通过 Cursor 连接 Memverse MCP 的用户** 都会遇到此问题
- 其他仍使用 legacy SSE 的客户端（如旧版 MCP Inspector）不受影响
- 修复后需重新部署服务，用户无需改 Cursor 配置
