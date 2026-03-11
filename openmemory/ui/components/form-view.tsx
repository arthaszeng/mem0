"use client"

import { useState, useEffect } from "react"
import { Eye, EyeOff, Download, Upload, Trash2 } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card"
import { Input } from "./ui/input"
import { Label } from "./ui/label"
import { Slider } from "./ui/slider"
import { Switch } from "./ui/switch"
import { Button } from "./ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select"
import { Textarea } from "./ui/textarea"
import { useRef, useState as useReactState } from "react"
import { TOKEN_COOKIE, getCookie } from "@/lib/auth"
import api from "@/lib/api"
import { toast } from "sonner"

interface FormViewProps {
  settings: any
  onChange: (settings: any) => void
}

export function FormView({ settings, onChange }: FormViewProps) {
  const [showLlmAdvanced, setShowLlmAdvanced] = useState(false)
  const [showLlmApiKey, setShowLlmApiKey] = useState(false)
  const [showEmbedderApiKey, setShowEmbedderApiKey] = useState(false)
  const [isUploading, setIsUploading] = useReactState(false)
  const [selectedImportFileName, setSelectedImportFileName] = useReactState("")
  const [importResult, setImportResult] = useReactState("")
  const [projects, setProjects] = useReactState<{slug: string; name: string}[]>([])
  const [selectedProjectSlug, setSelectedProjectSlug] = useReactState("")
  const [clearConfirmText, setClearConfirmText] = useReactState("")
  const [isClearing, setIsClearing] = useReactState(false)
  const [clearResult, setClearResult] = useReactState("")
  const [isExporting, setIsExporting] = useReactState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8765"

  useEffect(() => {
    api.get("/api/v1/projects").then((res) => {
      const list = (res.data || []).map((p: any) => ({ slug: p.slug, name: p.name }))
      setProjects(list)
      if (list.length > 0 && !selectedProjectSlug) {
        setSelectedProjectSlug(list[0].slug)
      }
    }).catch(() => {})
  }, [])

  const handleOpenMemoryChange = (key: string, value: any) => {
    onChange({
      ...settings,
      openmemory: {
        ...settings.openmemory,
        [key]: value,
      },
    })
  }

  const handleLlmProviderChange = (value: string) => {
    onChange({
      ...settings,
      mem0: {
        ...settings.mem0,
        llm: {
          ...settings.mem0.llm,
          provider: value,
        },
      },
    })
  }

  const handleLlmConfigChange = (key: string, value: any) => {
    onChange({
      ...settings,
      mem0: {
        ...settings.mem0,
        llm: {
          ...settings.mem0.llm,
          config: {
            ...settings.mem0.llm.config,
            [key]: value,
          },
        },
      },
    })
  }

  const handleEmbedderProviderChange = (value: string) => {
    onChange({
      ...settings,
      mem0: {
        ...settings.mem0,
        embedder: {
          ...settings.mem0.embedder,
          provider: value,
        },
      },
    })
  }

  const handleEmbedderConfigChange = (key: string, value: any) => {
    onChange({
      ...settings,
      mem0: {
        ...settings.mem0,
        embedder: {
          ...settings.mem0.embedder,
          config: {
            ...settings.mem0.embedder.config,
            [key]: value,
          },
        },
      },
    })
  }

  const handleVectorStoreProviderChange = (value: string) => {
    onChange({
      ...settings,
      mem0: {
        ...settings.mem0,
        vector_store: {
          ...settings.mem0.vector_store,
          provider: value,
        },
      },
    })
  }

  const handleVectorStoreConfigChange = (key: string, value: any) => {
    onChange({
      ...settings,
      mem0: {
        ...settings.mem0,
        vector_store: {
          ...settings.mem0.vector_store,
          config: {
            ...settings.mem0.vector_store?.config,
            [key]: value,
          },
        },
      },
    })
  }

  const needsLlmApiKey = settings.mem0?.llm?.provider?.toLowerCase() !== "ollama"
  const needsEmbedderApiKey = settings.mem0?.embedder?.provider?.toLowerCase() !== "ollama"
  const isLlmOllama = settings.mem0?.llm?.provider?.toLowerCase() === "ollama"
  const isEmbedderOllama = settings.mem0?.embedder?.provider?.toLowerCase() === "ollama"

  const LLM_PROVIDERS = {
    "OpenAI": "openai",
    "Anthropic": "anthropic", 
    "Azure OpenAI": "azure_openai",
    "Ollama": "ollama",
    "Together": "together",
    "Groq": "groq",
    "Litellm": "litellm",
    "Mistral AI": "mistralai",
    "Google AI": "google_ai",
    "AWS Bedrock": "aws_bedrock",
    "Gemini": "gemini",
    "DeepSeek": "deepseek",
    "xAI": "xai",
    "LM Studio": "lmstudio",
    "LangChain": "langchain",
  }

  const EMBEDDER_PROVIDERS = {
    "OpenAI": "openai",
    "Azure OpenAI": "azure_openai", 
    "Ollama": "ollama",
    "Hugging Face": "huggingface",
    "Vertex AI": "vertexai",
    "Gemini": "gemini",
    "LM Studio": "lmstudio",
    "Together": "together",
    "LangChain": "langchain",
    "AWS Bedrock": "aws_bedrock",
  }

  const VECTOR_STORE_PROVIDERS = {
    "Qdrant": "qdrant",
    "Chroma": "chroma",
    "Pinecone": "pinecone",
    "Milvus": "milvus",
    "PgVector": "pgvector",
    "Redis": "redis",
  }

  return (
    <div className="space-y-8">
      {/* OpenMemory Settings */}
      <Card>
        <CardHeader>
          <CardTitle>OpenMemory Settings</CardTitle>
          <CardDescription>Configure your OpenMemory instance settings</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="custom-instructions">Custom Instructions</Label>
            <Textarea
              id="custom-instructions"
              placeholder="Enter custom instructions for memory management..."
              value={settings.openmemory?.custom_instructions || ""}
              onChange={(e) => handleOpenMemoryChange("custom_instructions", e.target.value)}
              className="min-h-[100px]"
            />
            <p className="text-xs text-muted-foreground mt-1">
              Custom instructions that will be used to guide memory processing and fact extraction.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* LLM Settings */}
      <Card>
        <CardHeader>
          <CardTitle>LLM Settings</CardTitle>
          <CardDescription>Configure your Large Language Model provider and settings</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="llm-provider">LLM Provider</Label>
            <Select 
              value={settings.mem0?.llm?.provider || ""}
              onValueChange={handleLlmProviderChange}
            >
              <SelectTrigger id="llm-provider">
                <SelectValue placeholder="Select a provider" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(LLM_PROVIDERS).map(([provider, value]) => (
                  <SelectItem key={value} value={value}>
                    {provider}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="llm-model">Model</Label>
            <Input
              id="llm-model"
              placeholder="Enter model name"
              value={settings.mem0?.llm?.config?.model || ""}
              onChange={(e) => handleLlmConfigChange("model", e.target.value)}
            />
          </div>

          {isLlmOllama && (
            <div className="space-y-2">
              <Label htmlFor="llm-ollama-url">Ollama Base URL</Label>
              <Input
                id="llm-ollama-url"
                placeholder="http://host.docker.internal:11434"
                value={settings.mem0?.llm?.config?.ollama_base_url || ""}
                onChange={(e) => handleLlmConfigChange("ollama_base_url", e.target.value)}
              />
              <p className="text-xs text-muted-foreground mt-1">
                Leave empty to use default: http://host.docker.internal:11434
              </p>
            </div>
          )}

          {needsLlmApiKey && (
            <div className="space-y-2">
              <Label htmlFor="llm-api-key">API Key</Label>
              <div className="relative">
                <Input
                  id="llm-api-key"
                  type={showLlmApiKey ? "text" : "password"}
                  placeholder="env:API_KEY"
                  value={settings.mem0?.llm?.config?.api_key || ""}
                  onChange={(e) => handleLlmConfigChange("api_key", e.target.value)}
                />
                <Button 
                  variant="ghost" 
                  size="icon" 
                  type="button" 
                  className="absolute right-2 top-1/2 transform -translate-y-1/2 h-7 w-7"
                  onClick={() => setShowLlmApiKey(!showLlmApiKey)}
                >
                  {showLlmApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Use "env:API_KEY" to load from environment variable, or enter directly
              </p>
            </div>
          )}

          <div className="flex items-center space-x-2 pt-2">
            <Switch id="llm-advanced-settings" checked={showLlmAdvanced} onCheckedChange={setShowLlmAdvanced} />
            <Label htmlFor="llm-advanced-settings">Show advanced settings</Label>
          </div>

          {showLlmAdvanced && (
            <div className="space-y-6 pt-2">
              <div className="space-y-2">
                <div className="flex justify-between">
                  <Label htmlFor="temperature">Temperature: {settings.mem0?.llm?.config?.temperature}</Label>
                </div>
                <Slider
                  id="temperature"
                  min={0}
                  max={1}
                  step={0.1}
                  value={[settings.mem0?.llm?.config?.temperature || 0.7]}
                  onValueChange={(value) => handleLlmConfigChange("temperature", value[0])}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="max-tokens">Max Tokens</Label>
                <Input
                  id="max-tokens"
                  type="number"
                  placeholder="2000"
                  value={settings.mem0?.llm?.config?.max_tokens || ""}
                  onChange={(e) => handleLlmConfigChange("max_tokens", Number.parseInt(e.target.value) || "")}
                />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Embedder Settings */}
      <Card>
        <CardHeader>
          <CardTitle>Embedder Settings</CardTitle>
          <CardDescription>Configure your Embedding Model provider and settings</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="embedder-provider">Embedder Provider</Label>
            <Select 
              value={settings.mem0?.embedder?.provider || ""} 
              onValueChange={handleEmbedderProviderChange}
            >
              <SelectTrigger id="embedder-provider">
                <SelectValue placeholder="Select a provider" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(EMBEDDER_PROVIDERS).map(([provider, value]) => (
                  <SelectItem key={value} value={value}>
                    {provider}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="embedder-model">Model</Label>
            <Input
              id="embedder-model"
              placeholder="Enter model name"
              value={settings.mem0?.embedder?.config?.model || ""}
              onChange={(e) => handleEmbedderConfigChange("model", e.target.value)}
            />
          </div>

          {isEmbedderOllama && (
            <div className="space-y-2">
              <Label htmlFor="embedder-ollama-url">Ollama Base URL</Label>
              <Input
                id="embedder-ollama-url"
                placeholder="http://host.docker.internal:11434"
                value={settings.mem0?.embedder?.config?.ollama_base_url || ""}
                onChange={(e) => handleEmbedderConfigChange("ollama_base_url", e.target.value)}
              />
              <p className="text-xs text-muted-foreground mt-1">
                Leave empty to use default: http://host.docker.internal:11434
              </p>
            </div>
          )}

          {needsEmbedderApiKey && (
            <div className="space-y-2">
              <Label htmlFor="embedder-api-key">API Key</Label>
              <div className="relative">
                <Input
                  id="embedder-api-key"
                  type={showEmbedderApiKey ? "text" : "password"}
                  placeholder="env:API_KEY"
                  value={settings.mem0?.embedder?.config?.api_key || ""}
                  onChange={(e) => handleEmbedderConfigChange("api_key", e.target.value)}
                />
                <Button 
                  variant="ghost" 
                  size="icon" 
                  type="button" 
                  className="absolute right-2 top-1/2 transform -translate-y-1/2 h-7 w-7"
                  onClick={() => setShowEmbedderApiKey(!showEmbedderApiKey)}
                >
                  {showEmbedderApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Use "env:API_KEY" to load from environment variable, or enter directly
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Vector Store Settings */}
      <Card>
        <CardHeader>
          <CardTitle>Vector Store Settings</CardTitle>
          <CardDescription>Configure the vector database for memory storage and retrieval</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="vs-provider">Provider</Label>
            <Select
              value={settings.mem0?.vector_store?.provider || "qdrant"}
              onValueChange={handleVectorStoreProviderChange}
            >
              <SelectTrigger id="vs-provider">
                <SelectValue placeholder="Select a vector store" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(VECTOR_STORE_PROVIDERS).map(([label, value]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="vs-host">Host</Label>
            <Input
              id="vs-host"
              placeholder="mem0_store"
              value={settings.mem0?.vector_store?.config?.host || ""}
              onChange={(e) => handleVectorStoreConfigChange("host", e.target.value)}
            />
            <p className="text-xs text-muted-foreground mt-1">
              Docker service name or hostname (e.g. mem0_store, localhost)
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="vs-port">Port</Label>
            <Input
              id="vs-port"
              type="number"
              placeholder="6333"
              value={settings.mem0?.vector_store?.config?.port || ""}
              onChange={(e) => handleVectorStoreConfigChange("port", Number.parseInt(e.target.value) || "")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="vs-collection">Collection Name</Label>
            <Input
              id="vs-collection"
              placeholder="openmemory"
              value={settings.mem0?.vector_store?.config?.collection_name || ""}
              onChange={(e) => handleVectorStoreConfigChange("collection_name", e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="vs-dims">Embedding Dimensions</Label>
            <Input
              id="vs-dims"
              type="number"
              placeholder="1536"
              value={settings.mem0?.vector_store?.config?.embedding_model_dims || ""}
              onChange={(e) => handleVectorStoreConfigChange("embedding_model_dims", Number.parseInt(e.target.value) || "")}
            />
            <p className="text-xs text-muted-foreground mt-1">
              Must match the embedder model output dimensions (e.g. 1536 for text-embedding-3-small)
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Backup (Export / Import) */}
      <Card>
        <CardHeader>
          <CardTitle>Backup</CardTitle>
          <CardDescription>Export or import your memories</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Project selector */}
          <div className="space-y-2">
            <Label>Target Project</Label>
            <Select value={selectedProjectSlug} onValueChange={setSelectedProjectSlug}>
              <SelectTrigger>
                <SelectValue placeholder="Select a project" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All Projects</SelectItem>
                {projects.map((p) => (
                  <SelectItem key={p.slug} value={p.slug}>{p.name} ({p.slug})</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Export: filter by project (or All). Import: target project for imported memories.
            </p>
          </div>

          {/* Export Section */}
          <div className="p-4 border border-zinc-800 rounded-lg space-y-2">
            <div className="text-sm font-medium">Export</div>
            <p className="text-xs text-muted-foreground">Download a ZIP containing your memories.</p>
            <div>
              <Button
                type="button"
                className="bg-zinc-800 hover:bg-zinc-700"
                disabled={isExporting}
                onClick={async () => {
                  try {
                    setIsExporting(true)
                    const token = getCookie(TOKEN_COOKIE)
                    const slug = selectedProjectSlug === "__all__" ? "" : selectedProjectSlug
                    const res = await fetch(`${API_URL}/api/v1/backup/export`, {
                      method: "POST",
                      headers: {
                        "Content-Type": "application/json",
                        Accept: "application/zip",
                        ...(token ? { Authorization: `Bearer ${token}` } : {}),
                      },
                      body: JSON.stringify({ project_slug: slug || undefined }),
                    })
                    if (!res.ok) throw new Error(`Export failed with status ${res.status}`)
                    const blob = await res.blob()
                    const url = window.URL.createObjectURL(blob)
                    const a = document.createElement("a")
                    a.href = url
                    a.download = `memories_export.zip`
                    document.body.appendChild(a)
                    a.click()
                    a.remove()
                    window.URL.revokeObjectURL(url)
                    toast.success("Export downloaded")
                  } catch (e) {
                    console.error(e)
                    toast.error("Export failed. Check console for details.")
                  } finally {
                    setIsExporting(false)
                  }
                }}
              >
                <Download className="h-4 w-4 mr-2" /> {isExporting ? "Exporting..." : "Export Memories"}
              </Button>
            </div>
          </div>

          {/* Import Section */}
          <div className="p-4 border border-zinc-800 rounded-lg space-y-2">
            <div className="text-sm font-medium">Import</div>
            <p className="text-xs text-muted-foreground">Upload a ZIP exported by OpenMemory. Memories will be imported into the selected project.</p>
            <div className="flex items-center gap-3 flex-wrap">
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip"
                className="hidden"
                onChange={(evt) => {
                  const f = evt.target.files?.[0]
                  if (!f) return
                  setSelectedImportFileName(f.name)
                  setImportResult("")
                }}
              />
              <Button
                type="button"
                className="bg-zinc-800 hover:bg-zinc-700"
                onClick={() => {
                  if (fileInputRef.current) fileInputRef.current.click()
                }}
              >
                <Upload className="h-4 w-4 mr-2" /> Choose ZIP
              </Button>
              <span className="text-xs text-muted-foreground truncate max-w-[220px]">
                {selectedImportFileName || "No file selected"}
              </span>
              <div className="ml-auto">
                <Button
                  type="button"
                  disabled={isUploading || !fileInputRef.current}
                  className="bg-primary hover:bg-primary/80 disabled:opacity-50"
                  onClick={async () => {
                    const file = fileInputRef.current?.files?.[0]
                    if (!file) return
                    try {
                      setIsUploading(true)
                      setImportResult("")
                      const form = new FormData()
                      form.append("file", file)
                      const slug = selectedProjectSlug === "__all__" ? "" : selectedProjectSlug
                      if (slug) form.append("project_slug", slug)
                      const importToken = getCookie(TOKEN_COOKIE)
                      const res = await fetch(`${API_URL}/api/v1/backup/import`, {
                        method: "POST",
                        headers: importToken ? { Authorization: `Bearer ${importToken}` } : {},
                        body: form,
                      })
                      if (!res.ok) throw new Error(`Import failed with status ${res.status}`)
                      const data = await res.json()
                      const taskId = data.task_id
                      setImportResult(
                        `DB imported ${data.imported ?? 0}, skipped ${data.skipped ?? 0}. Embedding ${data.to_embed ?? 0} vectors...`
                      )
                      if (fileInputRef.current) fileInputRef.current.value = ""
                      setSelectedImportFileName("")
                      setIsUploading(false)

                      if (taskId && (data.to_embed ?? 0) > 0) {
                        const poll = setInterval(async () => {
                          try {
                            const statusRes = await api.get(`/api/v1/backup/import-status/${taskId}`)
                            const s = statusRes.data
                            if (s.done) {
                              clearInterval(poll)
                              setImportResult(
                                `Done! DB: ${s.sqlite_imported ?? data.imported} imported. Vectors: ${s.embedded}/${s.total} embedded, ${s.failed} failed → ${s.project_slug ?? data.project_slug}`
                              )
                            } else {
                              setImportResult(
                                `DB imported ${data.imported}. Embedding: ${s.embedded}/${s.total}...`
                              )
                            }
                          } catch {
                            clearInterval(poll)
                          }
                        }, 3000)
                      }
                    } catch (e) {
                      console.error(e)
                      toast.error("Import failed. Check console for details.")
                      setIsUploading(false)
                    }
                  }}
                >
                  {isUploading ? "Uploading..." : "Import"}
                </Button>
              </div>
            </div>
            {importResult && (
              <p className="text-xs text-green-400 mt-2">{importResult}</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Danger Zone */}
      <Card className="border-red-900/50">
        <CardHeader>
          <CardTitle className="text-red-400">Danger Zone</CardTitle>
          <CardDescription>Irreversible operations. Proceed with caution.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="p-4 border border-red-900/50 rounded-lg space-y-3">
            <div className="text-sm font-medium text-red-400">Clear All Memory Data</div>
            <p className="text-xs text-muted-foreground">
              Delete all your memories from both the database and vector store. User, project, and app records will be preserved. This action cannot be undone.
            </p>
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">
                Type <span className="font-mono text-red-400">DELETE</span> to confirm
              </Label>
              <Input
                className="max-w-[240px] border-red-900/50 focus-visible:ring-red-500"
                placeholder="DELETE"
                value={clearConfirmText}
                onChange={(e) => {
                  setClearConfirmText(e.target.value)
                  setClearResult("")
                }}
              />
            </div>
            <Button
              type="button"
              variant="destructive"
              disabled={clearConfirmText !== "DELETE" || isClearing}
              className="disabled:opacity-50"
              onClick={async () => {
                try {
                  setIsClearing(true)
                  setClearResult("")
                  const res = await api.post("/api/v1/backup/clear-data")
                  const d = res.data
                  setClearResult(
                    `Cleared ${d.sqlite_deleted ?? 0} DB records + ${d.qdrant_deleted ?? 0} vectors.`
                  )
                  setClearConfirmText("")
                } catch (e: any) {
                  setClearResult(`Failed: ${e?.response?.data?.detail || e.message}`)
                } finally {
                  setIsClearing(false)
                }
              }}
            >
              <Trash2 className="h-4 w-4 mr-2" />
              {isClearing ? "Clearing..." : "Clear All Memories"}
            </Button>
            {clearResult && (
              <p className={`text-xs mt-1 ${clearResult.startsWith("Failed") ? "text-red-400" : "text-green-400"}`}>
                {clearResult}
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
} 