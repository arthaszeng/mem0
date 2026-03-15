"use client";

import React, { useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Copy, Check, ExternalLink } from "lucide-react";
import Image from "next/image";
import { useProject } from "@/contexts/ProjectContext";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

interface TabDef {
  key: string;
  label: string;
  icon: string;
  gradient: string;
}

const tabs: TabDef[] = [
  {
    key: "register",
    label: "Registration",
    icon: "📋",
    gradient:
      "data-[state=active]:bg-[linear-gradient(to_top,_rgba(234,179,8,0.3),_rgba(234,179,8,0))] data-[state=active]:border-[#EAB308]",
  },
  {
    key: "mcp",
    label: "MCP Link",
    icon: "🔗",
    gradient:
      "data-[state=active]:bg-[linear-gradient(to_top,_rgba(126,63,242,0.3),_rgba(126,63,242,0))] data-[state=active]:border-[#7E3FF2]",
  },
  {
    key: "openclaw",
    label: "OpenClaw",
    icon: "🐾",
    gradient:
      "data-[state=active]:bg-[linear-gradient(to_top,_rgba(239,108,60,0.3),_rgba(239,108,60,0))] data-[state=active]:border-[#EF6C3C]",
  },
  {
    key: "cursor",
    label: "Cursor",
    icon: `${basePath}/images/cursor.png`,
    gradient:
      "data-[state=active]:bg-[linear-gradient(to_top,_rgba(255,255,255,0.08),_rgba(255,255,255,0))] data-[state=active]:border-[#708090]",
  },
  {
    key: "copilot",
    label: "GitHub Copilot",
    icon: "🤖",
    gradient:
      "data-[state=active]:bg-[linear-gradient(to_top,_rgba(33,135,255,0.3),_rgba(33,135,255,0))] data-[state=active]:border-[#2187FF]",
  },
  {
    key: "chatgpt",
    label: "ChatGPT",
    icon: "💬",
    gradient:
      "data-[state=active]:bg-[linear-gradient(to_top,_rgba(16,163,127,0.3),_rgba(16,163,127,0))] data-[state=active]:border-[#10A37F]",
  },
];

function CodeBlock({
  code,
  copied,
  onCopy,
}: {
  code: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="relative">
      <pre className="bg-zinc-800 px-4 py-3 rounded-md overflow-x-auto text-sm leading-relaxed">
        <code className="text-gray-300">{code}</code>
      </pre>
      <button
        className="absolute top-0 right-0 py-3 px-4 rounded-md hover:bg-zinc-600 bg-zinc-700"
        aria-label="Copy to clipboard"
        onClick={onCopy}
      >
        {copied ? (
          <Check className="h-4 w-4 text-green-400" />
        ) : (
          <Copy className="h-4 w-4 text-zinc-400" />
        )}
      </button>
    </div>
  );
}

function Step({
  n,
  children,
}: {
  n: number;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-3 items-start">
      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-purple-600/30 text-purple-400 text-xs font-bold flex items-center justify-center mt-0.5">
        {n}
      </span>
      <div className="text-sm text-zinc-300 leading-relaxed flex-1">
        {children}
      </div>
    </div>
  );
}

export const Install = () => {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const { projectSlug } = useProject();

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8765";
  const mcpBase = projectSlug
    ? `${API_URL}/memverse-mcp/p/${projectSlug}`
    : `${API_URL}/memverse-mcp`;
  const sseUrl = (client: string) => `${mcpBase}/${client}/sse`;
  const HOST = API_URL.replace(/:\d+$/, "");

  const handleCopy = async (id: string, text: string) => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 1500);
    } catch (e) {
      console.error("Copy failed:", e);
    }
  };

  const cursorConfig = `// ~/.cursor/mcp.json
{
  "mcpServers": {
    "Memverse": {
      "url": "${sseUrl("cursor")}",
      "headers": {
        "Authorization": "Bearer <your-api-token>"
      }
    }
  }
}`;

  const copilotConfig = `// ~/.config/github-copilot/intellij/mcp.json
{
  "mcpServers": {
    "Memverse": {
      "type": "sse",
      "url": "${sseUrl("github-copilot")}",
      "tools": ["*"],
      "headers": {
        "Authorization": "Bearer <your-token>"
      }
    }
  }
}`;

  const openClawConfig = `// OpenClaw Settings → Plugins → mem0
{
  "serverUrl": "${API_URL}",
  "userId": "<your-user-id>",
  "autoCapture": true,
  "autoRecall": true
}`;

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">Install Memverse</h2>

      <Tabs defaultValue="register" className="w-full">
        <TabsList className="bg-transparent border-b border-zinc-800 rounded-none w-full justify-start gap-0 p-0 flex flex-wrap sm:flex-nowrap overflow-x-auto">
          {tabs.map(({ key, label, icon, gradient }) => (
            <TabsTrigger
              key={key}
              value={key}
              className={`flex-shrink-0 px-3 pb-2 rounded-none ${gradient} data-[state=active]:border-b-2 data-[state=active]:shadow-none text-zinc-400 data-[state=active]:text-white flex items-center justify-center gap-1.5 text-sm whitespace-nowrap`}
            >
              {icon.startsWith("/") ? (
                <div className="w-6 h-6 rounded-full bg-zinc-700 flex items-center justify-center overflow-hidden">
                  <Image src={icon} alt={label} width={40} height={40} />
                </div>
              ) : (
                <span className="text-base">{icon}</span>
              )}
              <span>{label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        {/* Registration */}
        <TabsContent value="register" className="mt-6">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardContent className="py-5 space-y-5">
              <div className="bg-yellow-900/20 border border-yellow-700/40 rounded-lg px-4 py-3">
                <p className="text-sm text-yellow-300/90 font-medium">Invite Only</p>
                <p className="text-sm text-zinc-400 mt-1">
                  Memverse is currently invite-only. You need an account to use the service.
                </p>
              </div>
              <div className="space-y-3">
                <Step n={1}>
                  Contact the admin to receive an invitation and create your account.
                </Step>
                <Step n={2}>
                  Visit the{" "}
                  <a
                    href={`${HOST}/memory`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-purple-400 hover:underline inline-flex items-center gap-1"
                  >
                    Memverse Dashboard <ExternalLink className="h-3 w-3" />
                  </a>{" "}
                  to log in and manage your memories.
                </Step>
                <Step n={3}>
                  Once logged in, choose a client tab above to set up your preferred AI tool.
                </Step>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* MCP Link */}
        <TabsContent value="mcp" className="mt-6">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardContent className="py-5 space-y-4">
              <p className="text-sm text-zinc-400">
                SSE endpoint for any MCP-compatible client. Copy and paste into your client&apos;s MCP configuration.
              </p>
              <CodeBlock
                code={sseUrl("your-client")}
                copied={copiedId === "mcp"}
                onCopy={() => handleCopy("mcp", sseUrl("your-client"))}
              />
              <p className="text-xs text-zinc-500">
                Replace <code className="text-zinc-400">your-client</code> with your client name (e.g. claude, windsurf).
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        {/* OpenClaw */}
        <TabsContent value="openclaw" className="mt-6">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardContent className="py-5 space-y-4">
              <div className="space-y-3">
                <Step n={1}>
                  Install the <code className="text-purple-400">openclaw-memverse</code> plugin from the OpenClaw Plugin Marketplace.
                </Step>
                <Step n={2}>
                  Configure the plugin in <code className="text-purple-400">Settings → Plugins → memverse</code>:
                </Step>
              </div>
              <CodeBlock
                code={openClawConfig}
                copied={copiedId === "openclaw"}
                onCopy={() => handleCopy("openclaw", openClawConfig)}
              />
              <div className="space-y-3">
                <Step n={3}>
                  The plugin auto-captures important facts from conversations and auto-recalls relevant memories. No manual action needed.
                </Step>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Cursor */}
        <TabsContent value="cursor" className="mt-6">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardContent className="py-5 space-y-4">
              <div className="space-y-3">
                <Step n={1}>
                  Open (or create) <code className="text-purple-400">~/.cursor/mcp.json</code>
                </Step>
                <Step n={2}>
                  Add the following configuration:
                </Step>
              </div>
              <CodeBlock
                code={cursorConfig}
                copied={copiedId === "cursor"}
                onCopy={() => handleCopy("cursor", cursorConfig)}
              />
              <div className="space-y-3">
                <Step n={3}>
                  Replace <code className="text-purple-400">&lt;your-api-token&gt;</code> with your API token. Contact <strong className="text-white">Arthas</strong> to obtain one.
                </Step>
                <Step n={4}>
                  Restart Cursor. The Memverse tools will appear in the MCP panel.
                </Step>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* GitHub Copilot */}
        <TabsContent value="copilot" className="mt-6">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardContent className="py-5 space-y-4">
              <div className="space-y-3">
                <Step n={1}>
                  Enable <code className="text-purple-400">Agent Mode</code> in IntelliJ IDEA Copilot settings.
                </Step>
                <Step n={2}>
                  Open (or create) <code className="text-purple-400">~/.config/github-copilot/intellij/mcp.json</code>:
                </Step>
              </div>
              <CodeBlock
                code={copilotConfig}
                copied={copiedId === "copilot"}
                onCopy={() => handleCopy("copilot", copilotConfig)}
              />
              <div className="space-y-3">
                <Step n={3}>
                  Replace <code className="text-purple-400">&lt;your-token&gt;</code> with your API token. Contact <strong className="text-white">Arthas</strong> to obtain one.
                </Step>
                <Step n={4}>
                  Restart IntelliJ IDEA. Use <code className="text-purple-400">@Memverse</code> in Copilot Chat to access memories.
                </Step>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ChatGPT */}
        <TabsContent value="chatgpt" className="mt-6">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardContent className="py-5 space-y-5">
              <p className="text-sm text-zinc-400">
                Use Memverse directly in ChatGPT via the <strong className="text-white">Memory Universe</strong> GPT.
              </p>
              <div className="space-y-3">
                <Step n={1}>
                  Open{" "}
                  <a
                    href="https://chatgpt.com/g/g-69b3d10d0c488191929f0fdb728997cd-memory-universe"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-purple-400 hover:underline inline-flex items-center gap-1"
                  >
                    Memory Universe GPT <ExternalLink className="h-3 w-3" />
                  </a>{" "}
                  or search <code className="text-purple-400">Memory Universe</code> in the{" "}
                  <a
                    href="https://chatgpt.com/gpts"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-purple-400 hover:underline inline-flex items-center gap-1"
                  >
                    GPT Store <ExternalLink className="h-3 w-3" />
                  </a>.
                </Step>
                <Step n={2}>
                  Start a conversation. When the GPT needs to access your memories, it will prompt you to log in with your Memverse account.
                </Step>
                <Step n={3}>
                  After authorization, the GPT can search, create, and manage your memories seamlessly within ChatGPT.
                </Step>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default Install;
