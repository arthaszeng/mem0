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

interface ApiKeyItem {
  id: string;
  name: string;
  key_prefix: string;
  is_active: boolean;
  created_at: string | null;
  last_used_at: string | null;
  username: string;
}

export function ApiKeysTab() {
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyValue, setNewKeyValue] = useState("");
  const [creating, setCreating] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const authHeaders = useCallback(() => {
    const token = getCookie(TOKEN_COOKIE);
    return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  }, []);

  const fetchKeys = useCallback(async () => {
    try {
      const res = await fetch("/auth/api-keys/admin/all", { headers: authHeaders() });
      if (res.ok) setKeys(await res.json());
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [authHeaders]);

  useEffect(() => { fetchKeys(); }, [fetchKeys]);

  const handleCreate = async () => {
    if (!newKeyName.trim()) return;
    setCreating(true);
    const res = await fetch("/auth/api-keys", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ name: newKeyName }),
    });
    if (res.ok) {
      const data = await res.json();
      setNewKeyValue(data.key);
      await fetchKeys();
    }
    setCreating(false);
  };

  const handleRevoke = async (id: string) => {
    if (!confirm("Revoke this API key?")) return;
    await fetch(`/auth/api-keys/admin/${id}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    await fetchKeys();
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(newKeyValue);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const grouped = keys.reduce<Record<string, ApiKeyItem[]>>((acc, k) => {
    (acc[k.username] ??= []).push(k);
    return acc;
  }, {});

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-white">API Keys</h2>
          <p className="text-sm text-zinc-400 mt-1">Manage API keys across all users</p>
        </div>
        <Dialog
          open={dialogOpen}
          onOpenChange={(open) => {
            setDialogOpen(open);
            if (!open) { setNewKeyName(""); setNewKeyValue(""); }
          }}
        >
          <DialogTrigger asChild>
            <Button size="sm" className="gap-2"><Plus className="h-4 w-4" /> New API Key</Button>
          </DialogTrigger>
          <DialogContent className="bg-zinc-900 border-zinc-700">
            <DialogHeader>
              <DialogTitle className="text-white">Create API Key</DialogTitle>
              <DialogDescription className="text-zinc-400">
                {newKeyValue
                  ? "Copy your API key now. You won't be able to see it again."
                  : "This key will be created under your admin account."}
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
                  <Button onClick={handleCreate} disabled={creating || !newKeyName.trim()}>
                    {creating ? "Creating..." : "Create"}
                  </Button>
                </DialogFooter>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded bg-zinc-800 px-3 py-2 text-sm text-green-400 font-mono break-all">
                    {newKeyValue}
                  </code>
                  <Button variant="outline" size="icon" onClick={handleCopy} className="shrink-0 border-zinc-700">
                    {copied ? <Check className="h-4 w-4 text-green-400" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
                <DialogFooter>
                  <Button onClick={() => setDialogOpen(false)} variant="outline" className="border-zinc-700">Done</Button>
                </DialogFooter>
              </div>
            )}
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <p className="text-zinc-400">Loading...</p>
      ) : keys.length === 0 ? (
        <p className="text-zinc-400">No API keys across any users.</p>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([username, userKeys]) => (
            <Card key={username} className="border-zinc-800 bg-zinc-900/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-base text-white flex items-center gap-2">
                  <span className="inline-flex items-center justify-center h-6 w-6 rounded-full bg-zinc-700 text-xs font-bold text-zinc-200">
                    {username[0].toUpperCase()}
                  </span>
                  {username}
                  <span className="text-xs text-zinc-500 font-normal">{userKeys.length} key(s)</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {userKeys.map((k) => (
                  <div
                    key={k.id}
                    className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-3">
                        <span className="font-medium text-white">{k.name}</span>
                        <code className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400 font-mono">
                          {k.key_prefix}...
                        </code>
                        {!k.is_active && (
                          <span className="rounded bg-red-900/30 px-2 py-0.5 text-xs text-red-400">revoked</span>
                        )}
                      </div>
                      <p className="text-xs text-zinc-500">
                        Created {k.created_at ? new Date(k.created_at).toLocaleDateString() : "unknown"}
                        {k.last_used_at && <> &middot; Last used {new Date(k.last_used_at).toLocaleDateString()}</>}
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
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
