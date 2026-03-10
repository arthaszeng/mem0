# AI 客户端接入指南

本目录包含将各类 AI 客户端接入 OpenMemory 和 Concierge 的配置模板。

## 服务端点

| 服务 | HTTP (MCP SSE) | REST API |
|------|----------------|----------|
| OpenMemory MCP | `http://<host>/memory-mcp/{client}/sse/{user_id}` | — |
| OpenMemory API | — | `/api/v1/memories/` (需 X-API-Key) |
| Concierge MCP | `http://<host>/concierge-mcp/sse` | — |
| Concierge API | — | `/concierge-mcp/api/chat`, `/concierge-mcp/api/search` (需 Sanofi 会话) |

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
提供两套独立配置，可创建两个 GPT 或按需组合。

#### 2a. OpenMemory GPT（记忆系统）

**配置文件**:
- OpenAPI Schema: [`chatgpt-memory-schema.json`](./chatgpt-memory-schema.json)
- System Prompt: [`system-prompt-memory.md`](./system-prompt-memory.md)

**设置步骤**:
1. 在 ChatGPT 中创建自定义 GPT
2. 粘贴 `system-prompt-memory.md` 的内容作为 Instructions
3. 在 Actions → Import from URL / Paste Schema 中导入 `chatgpt-memory-schema.json`
4. 配置 Authentication:
   - Authentication Type: **API Key**
   - API Key: 服务器上 `docker exec openmemory-openmemory-mcp-1 env | grep API_KEY` 的值
   - Auth Type: **Custom**
   - Custom Header Name: `X-API-Key`
5. 点击 "Test" 验证每个 Action 能否正常调用

#### 2b. Concierge GPT（Sanofi AI 助手）

**配置文件**:
- OpenAPI Schema: [`chatgpt-concierge-schema.json`](./chatgpt-concierge-schema.json)
- System Prompt: [`system-prompt-concierge.md`](./system-prompt-concierge.md)

**设置步骤**:
1. 在 ChatGPT 中创建自定义 GPT
2. 粘贴 `system-prompt-concierge.md` 的内容作为 Instructions
3. 在 Actions → Paste Schema 中导入 `chatgpt-concierge-schema.json`
4. Authentication: **None**（Concierge 使用服务器端 Sanofi 会话，无需 API Key）
5. **前提**：使用前需通过 Concierge Chrome 扩展完成 Sanofi 认证
6. 点击 "Test" 验证 `conciergeAuthStatus` 返回 `{"connected": true}`

**Cloudflare Tunnel（绕过 ICP）**:

ChatGPT Actions 从海外服务器发起请求，域名未备案时阿里云网关返回 403，
IP 直连又有 SSL 证书不匹配问题。Cloudflare Tunnel 从服务器主动向外建连，
完全绕过 ICP 入站拦截。

Tunnel 已作为 systemd 服务运行，开机自启：

```bash
# 查看当前 Tunnel URL（Quick Tunnel 每次重启 URL 会变）
ssh -i ~/.ssh/arthas admin@47.108.141.20 \
  "sudo journalctl -u cloudflared-tunnel --no-pager -n 20 | grep trycloudflare"

# 管理服务
sudo systemctl status cloudflared-tunnel   # 查看状态
sudo systemctl restart cloudflared-tunnel  # 重启（URL 会变）
sudo systemctl stop cloudflared-tunnel     # 停止
```

> **注意**: Quick Tunnel 的 URL 在每次服务重启时会变化。
> 如需固定 URL，可升级为 Cloudflare Named Tunnel（需 Cloudflare 账号登录）。

**流量路径**: ChatGPT → HTTPS → Cloudflare Edge → Tunnel → nginx:80 → 后端

Tunnel 现在指向 nginx HTTP (port 80)，nginx 根据路径路由到不同后端：
- `/api/` → OpenMemory (port 8765)
- `/concierge-mcp/` → Concierge (port 8767)

**认证差异**:
- OpenMemory API：需要 `X-API-Key` header（在 ChatGPT Actions 中配置）
- Concierge API：需要服务器上有 Sanofi 活跃会话（通过 Chrome 扩展注入 token），无需额外 header

### 3. Lobe Chat（内置）

Lobe Chat 已部署在同一服务器，通过 `https://arthaszeng.top:3211/` 访问。
可在 Lobe Chat 插件设置中配置 OpenMemory API 地址为 `http://127.0.0.1:8765`。
