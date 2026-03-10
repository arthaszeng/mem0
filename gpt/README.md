# AI 客户端接入指南

本目录包含将各类 AI 客户端接入 OpenMemory MCP 和 Concierge MCP 的配置模板。

## 服务端点

| 服务 | HTTP (MCP SSE) | HTTPS (REST API) |
|------|----------------|-------------------|
| OpenMemory MCP | `http://<host>/memory-mcp/{client}/sse/{user_id}` | — |
| OpenMemory API | — | `https://<host>/api/v1/memories/` |
| Concierge MCP | `http://<host>/concierge-mcp/sse` | — |

> `<host>` = `47.108.141.20`（IP 直连）或 `arthaszeng.top`（需 ICP 备案后才能用域名）

## 接入方式

### 1. MCP SSE 客户端（Cursor / Claude Desktop / 其他 MCP 客户端）

适用于支持 MCP SSE 传输协议的客户端。

**配置文件**: [`mcp-config.json`](./mcp-config.json)

```jsonc
{
  "mcpServers": {
    "OpenMemory": {
      "url": "http://47.108.141.20/memory-mcp/cursor/sse/arthaszeng"
      //                                    ^^^^^^     ^^^^^^^^^^
      //                                  客户端名称    用户 ID
    },
    "Concierge": {
      "url": "http://47.108.141.20/concierge-mcp/sse"
    }
  }
}
```

**配置位置**:

| 客户端 | 配置文件路径 |
|--------|-------------|
| Cursor | `~/.cursor/mcp.json` |
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` |

**注意事项**:
- MCP 端点使用 **HTTP**（非 HTTPS），因为本地代理（如 Shadowrocket）可能劫持 DNS 导致 TLS 握手失败
- 如果本地有代理，需将 `arthaszeng.top` 加入 DIRECT 规则
- `client_name` 参数（如 `cursor`）会记录到 access log，便于区分不同客户端的访问

### 2. ChatGPT Custom GPT（Actions / REST API）

适用于 OpenAI ChatGPT 自定义 GPT。因 GPT Actions 不支持 SSE，通过 REST API 接入。

**配置文件**:
- OpenAPI Schema: [`chatgpt-action-schema.json`](./chatgpt-action-schema.json)
- System Prompt: [`system-prompt.md`](./system-prompt.md)

**设置步骤**:
1. 在 ChatGPT 中创建自定义 GPT
2. 粘贴 `system-prompt.md` 的内容作为 Instructions
3. 在 Actions → Import from URL / Paste Schema 中导入 `chatgpt-action-schema.json`
4. 配置 Authentication:
   - Authentication Type: **API Key**
   - API Key: 填入 nginx 中配置的 `X-API-Key` 值（见 `nginx/nginx.conf` 中 `/api/` location 的 `proxy_set_header`）
   - Auth Type: **Custom**
   - Custom Header Name: `X-API-Key`
5. 点击 "Test" 验证每个 Action 能否正常调用

> **注意**: nginx 的 `/api/` location 会自动注入 `X-API-Key` header，
> 所以即使 ChatGPT 发送的 key 值与实际不同也不影响。但 ChatGPT 要求
> Authentication 必须配置后才允许发起请求。

**服务器 URL 选择**:
- Schema 默认使用 `https://arthaszeng.top`（需域名已完成 ICP 备案）
- 如域名不通，可改为 `https://47.108.141.20`（需在 ChatGPT 中忽略证书警告，可能不支持）
- 最稳定方案: 通过 Cloudflare Tunnel 暴露一个海外可达的 HTTPS 端点

**已知限制**:
- ChatGPT Actions 从美国/海外服务器发起请求，直连中国阿里云服务器可能被 ICP 拦截
- 域名未备案时，阿里云网关返回 403（"Non-compliance ICP Filing"）
- 可选方案: Cloudflare Tunnel（`cloudflared tunnel`）暴露本地 8765 端口到公网

### 3. Lobe Chat（内置）

Lobe Chat 已部署在同一服务器，通过 `https://arthaszeng.top:3211/` 访问。
可在 Lobe Chat 插件设置中配置 OpenMemory API 地址为 `http://127.0.0.1:8765`。
