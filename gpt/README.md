# AI 客户端接入指南

本目录包含将各类 AI 客户端接入 OpenMemory 和 Concierge 的配置模板。

## 服务端点

| 服务 | HTTP (MCP SSE) | REST API |
|------|----------------|----------|
| OpenMemory MCP | `http://<host>/memory-mcp/{client}/sse/{user_id}` | — |
| OpenMemory API | — | `/api/v1/memories/` (需 OAuth2 Bearer token) |
| Concierge MCP | `http://<host>/concierge-mcp/sse` | — |
| Concierge API | — | `/concierge-mcp/api/chat`, `/concierge-mcp/api/search` (需 Sanofi 会话) |

> `<host>` = `arthaszeng.top`（域名已完成 ICP 备案）或 `47.108.141.20`（IP 直连）

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

因 GPT Actions 不支持 SSE，通过 REST API 接入。有两个版本：

#### 2a. 公开版 — OpenMemory GPT（仅记忆，OAuth2）

面向公网发布的 GPT，仅包含 OpenMemory 记忆功能。用户通过 OAuth2 登录认证。

**配置文件**:
- OpenAPI Schema: [`chatgpt-action-schema-public.json`](./chatgpt-action-schema-public.json)
- System Prompt: [`system-prompt-public.md`](./system-prompt-public.md)

**设置步骤**:
1. 在 ChatGPT 中创建自定义 GPT
2. 粘贴 `system-prompt-public.md` 的内容作为 Instructions
3. 在 Actions → Paste Schema 中导入 `chatgpt-action-schema-public.json`
4. 配置 Authentication:
   - Authentication Type: **OAuth**
   - Client ID: 通过 auth-service 动态注册获取（见下方）
   - Client Secret: 留空（public client）
   - Authorization URL: `https://arthaszeng.top/auth/authorize`
   - Token URL: `https://arthaszeng.top/auth/token`
   - Scope: 留空
5. 保存后 ChatGPT 会给你一个 Callback URL，需要注册到 auth-service
6. 点击 "Test" 验证 `searchMemories` 能正常调用

**注册 OAuth Client**:

```bash
# 1. 获取 ChatGPT 的 callback URL（在 Actions 配置页面底部）
#    格式类似: https://chatgpt.com/aip/<plugin-id>/oauth/callback

# 2. 注册 OAuth client
curl -X POST https://arthaszeng.top/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "ChatGPT-OpenMemory-Public",
    "redirect_uris": ["<ChatGPT-Callback-URL>"],
    "grant_types": ["authorization_code", "refresh_token"],
    "token_endpoint_auth_method": "none"
  }'

# 3. 返回的 client_id 填入 ChatGPT Actions 的 Client ID 字段
```

#### 2b. 私有版 — Arthas AI Platform GPT（记忆 + Concierge，Bearer token）

仅 Arthas 个人使用，包含 OpenMemory + Concierge 双服务。使用长期 JWT Bearer token 认证。

**配置文件**:
- OpenAPI Schema: [`chatgpt-action-schema.json`](./chatgpt-action-schema.json)
- System Prompt: [`system-prompt.md`](./system-prompt.md)

**设置步骤**:
1. 在 ChatGPT 中创建自定义 GPT（不发布，仅自己可见）
2. 粘贴 `system-prompt.md` 的内容作为 Instructions
3. 在 Actions → Paste Schema 中导入 `chatgpt-action-schema.json`
4. 配置 Authentication:
   - Authentication Type: **API Key**
   - API Key: 从 auth-service 签发的长期 JWT token（见下方）
   - Auth Type: **Bearer**
5. 点击 "Test" 验证 `searchMemories` 和 `conciergeAuthStatus` 能正常调用

**生成长期 JWT Token**:

```bash
# 通过 auth-service 登录获取 token，或直接在服务器上签发长期 token：
ssh -i ~/.ssh/arthas admin@47.108.141.20 \
  "docker exec openmemory-auth-service-1 python -c \"
from jwt_utils import sign_access_token
token = sign_access_token(user_id=1, username='arthaszeng', scopes='', expires_seconds=31536000)
print(token)
\""
```

> 上述命令签发有效期 1 年的 token。ChatGPT 会在每次 API 调用中发送 `Authorization: Bearer <token>`。

**流量路径**: ChatGPT → HTTPS → arthaszeng.top (nginx:443) → 后端

> 域名已完成 ICP 备案，不再需要 Cloudflare Tunnel 绕行。

**认证差异**:
- OpenMemory API：通过 Bearer JWT token 认证（nginx auth_request 校验）
- Concierge API：需要服务器上有 Sanofi 活跃会话（通过 Chrome 扩展注入 token）

### 3. Lobe Chat（内置）

Lobe Chat 已部署在同一服务器，通过 `https://arthaszeng.top:3211/` 访问。
可在 Lobe Chat 插件设置中配置 OpenMemory API 地址为 `http://127.0.0.1:8765`。
