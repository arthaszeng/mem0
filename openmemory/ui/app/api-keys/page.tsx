"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Plus, Copy, Trash2, Check } from "lucide-react";
import { TOKEN_COOKIE, getCookie } from "@/lib/auth";
import { toast } from "sonner";

interface ApiKeyItem {
  id: string;
  name: string;
  key_prefix: string;
  is_active: boolean;
  created_at: string | null;
  last_used_at: string | null;
}

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyValue, setNewKeyValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const authHeaders = useCallback(() => {
    const token = getCookie(TOKEN_COOKIE);
    return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  }, []);

  const fetchKeys = useCallback(async () => {
    const res = await fetch("/auth/api-keys", { headers: authHeaders() });
    if (res.ok) setKeys(await res.json());
  }, [authHeaders]);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  const handleCreate = async () => {
    if (!newKeyName.trim()) return;
    setLoading(true);
    try {
      const res = await fetch("/auth/api-keys", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ name: newKeyName }),
      });
      if (res.ok) {
        const data = await res.json();
        setNewKeyValue(data.key);
        await fetchKeys();
        toast.success("API key created");
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Failed to create API key");
      }
    } catch {
      toast.error("Failed to create API key");
    } finally {
      setLoading(false);
    }
  };

  const handleRevoke = async (id: string) => {
    try {
      await fetch(`/auth/api-keys/${id}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      await fetchKeys();
      toast.success("API key revoked");
    } catch {
      toast.error("Failed to revoke API key");
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(newKeyValue);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="text-white py-6">
      <div className="container mx-auto py-10 max-w-4xl">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">API Keys</h1>
            <p className="text-muted-foreground mt-1">
              Manage API keys for programmatic access to OpenMemory
            </p>
          </div>
          <Dialog
            open={dialogOpen}
            onOpenChange={(open) => {
              setDialogOpen(open);
              if (!open) {
                setNewKeyName("");
                setNewKeyValue("");
              }
            }}
          >
            <DialogTrigger asChild>
              <Button className="bg-purple-600 hover:bg-purple-700">
                <Plus className="mr-2 h-4 w-4" /> New API Key
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-zinc-900 border-zinc-700">
              <DialogHeader>
                <DialogTitle className="text-white">Create API Key</DialogTitle>
                <DialogDescription className="text-zinc-400">
                  {newKeyValue
                    ? "Copy your API key now. You won't be able to see it again."
                    : "Give your key a descriptive name."}
                </DialogDescription>
              </DialogHeader>
              {!newKeyValue ? (
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label className="text-zinc-300">Name</Label>
                    <Input
                      value={newKeyName}
                      onChange={(e) => setNewKeyName(e.target.value)}
                      placeholder="e.g. cursor-dev"
                      className="border-zinc-700 bg-zinc-800 text-white"
                    />
                  </div>
                  <DialogFooter>
                    <Button
                      onClick={handleCreate}
                      disabled={loading || !newKeyName.trim()}
                      className="bg-purple-600 hover:bg-purple-700"
                    >
                      {loading ? "Creating..." : "Create"}
                    </Button>
                  </DialogFooter>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <code className="flex-1 rounded bg-zinc-800 px-3 py-2 text-sm text-green-400 font-mono break-all">
                      {newKeyValue}
                    </code>
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={handleCopy}
                      className="shrink-0 border-zinc-700"
                    >
                      {copied ? (
                        <Check className="h-4 w-4 text-green-400" />
                      ) : (
                        <Copy className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                  <DialogFooter>
                    <Button
                      onClick={() => setDialogOpen(false)}
                      variant="outline"
                      className="border-zinc-700"
                    >
                      Done
                    </Button>
                  </DialogFooter>
                </div>
              )}
            </DialogContent>
          </Dialog>
        </div>

        <Card className="border-zinc-800 bg-zinc-900/50">
          <CardHeader>
            <CardTitle className="text-lg text-white">Your API Keys</CardTitle>
            <CardDescription>
              Use API keys with Bearer authentication to access the API
            </CardDescription>
          </CardHeader>
          <CardContent>
            {keys.length === 0 ? (
              <p className="text-zinc-500 text-sm py-4 text-center">
                No API keys yet. Create one to get started.
              </p>
            ) : (
              <div className="space-y-3">
                {keys.map((k) => (
                  <div
                    key={k.id}
                    className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-3">
                        <span className="font-medium text-white">
                          {k.name}
                        </span>
                        <code className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400 font-mono">
                          {k.key_prefix}...
                        </code>
                        {!k.is_active && (
                          <span className="rounded bg-red-900/30 px-2 py-0.5 text-xs text-red-400">
                            revoked
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-zinc-500">
                        Created{" "}
                        {k.created_at
                          ? new Date(k.created_at).toLocaleDateString()
                          : "unknown"}
                        {k.last_used_at && (
                          <>
                            {" · Last used "}
                            {new Date(k.last_used_at).toLocaleDateString()}
                          </>
                        )}
                      </p>
                    </div>
                    {k.is_active && (
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleRevoke(k.id)}
                        className="text-zinc-500 hover:text-red-400 hover:bg-red-900/20"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
