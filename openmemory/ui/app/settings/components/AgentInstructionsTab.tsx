"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Plus, Trash2, ChevronDown, ChevronUp, Save, X } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

interface AgentItem {
  agent_id: string;
  instructions: string;
  updated_at: string;
}

export function AgentInstructionsTab() {
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newAgentId, setNewAgentId] = useState("");
  const [newInstructions, setNewInstructions] = useState("");
  const [creating, setCreating] = useState(false);
  const [editingAgent, setEditingAgent] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  const fetchAgents = useCallback(async () => {
    try {
      const res = await api.get<AgentItem[]>("/api/v1/memories/agent-instructions");
      setAgents(res.data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAgents(); }, [fetchAgents]);

  const handleCreate = async () => {
    if (!newAgentId.trim() || !newInstructions.trim()) return;
    setCreating(true);
    try {
      await api.put(`/api/v1/memories/agent-instructions/${newAgentId.trim()}`, {
        instructions: newInstructions.trim(),
      });
      toast.success(`Instructions set for ${newAgentId}`);
      setDialogOpen(false);
      setNewAgentId("");
      setNewInstructions("");
      await fetchAgents();
    } catch {
      toast.error("Failed to create agent instructions");
    } finally { setCreating(false); }
  };

  const handleSaveEdit = async (agentId: string) => {
    try {
      await api.put(`/api/v1/memories/agent-instructions/${agentId}`, {
        instructions: editText.trim(),
      });
      toast.success("Instructions updated");
      setEditingAgent(null);
      await fetchAgents();
    } catch {
      toast.error("Failed to update instructions");
    }
  };

  const handleDelete = async (agentId: string) => {
    try {
      await api.delete(`/api/v1/memories/agent-instructions/${agentId}`);
      toast.success("Agent instructions deleted");
      await fetchAgents();
    } catch {
      toast.error("Failed to delete");
    }
  };

  const startEditing = (agent: AgentItem) => {
    setEditingAgent(agent.agent_id);
    setEditText(agent.instructions);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-white">Agent Instructions</h2>
          <p className="text-sm text-zinc-400 mt-1">
            Per-agent custom instructions for memory extraction. Each AI agent can have its own rules.
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button size="sm"><Plus className="h-4 w-4 mr-1" /> Add Agent</Button>
          </DialogTrigger>
          <DialogContent className="bg-zinc-900 border-zinc-800">
            <DialogHeader>
              <DialogTitle>Add Agent Instructions</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div>
                <Label>Agent ID</Label>
                <Input
                  value={newAgentId}
                  onChange={(e) => setNewAgentId(e.target.value)}
                  placeholder="e.g. cursor, chatgpt, openclaw"
                  className="bg-zinc-800 border-zinc-700"
                />
              </div>
              <div>
                <Label>Instructions</Label>
                <textarea
                  value={newInstructions}
                  onChange={(e) => setNewInstructions(e.target.value)}
                  placeholder="Custom instructions for this agent's memory extraction..."
                  rows={5}
                  className="w-full mt-1 rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
            </div>
            <DialogFooter>
              <Button onClick={handleCreate} disabled={creating || !newAgentId.trim()}>
                {creating ? "Saving..." : "Save Instructions"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <div className="text-center py-8 text-zinc-400">Loading...</div>
      ) : agents.length === 0 ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-12 text-center">
          <p className="text-zinc-400">No agent instructions configured yet.</p>
          <p className="text-zinc-500 text-sm mt-1">
            Each AI agent (Cursor, ChatGPT, etc.) can have its own memory extraction rules.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {agents.map((agent) => (
            <div
              key={agent.agent_id}
              className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden"
            >
              <div className="flex items-center justify-between px-4 py-3">
                <div className="flex items-center gap-3">
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-500/20 text-purple-300">
                    {agent.agent_id}
                  </span>
                  <span className="text-xs text-zinc-500">
                    Updated {agent.updated_at?.split("T")[0] || "—"}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      editingAgent === agent.agent_id
                        ? setEditingAgent(null)
                        : startEditing(agent)
                    }
                  >
                    {editingAgent === agent.agent_id ? (
                      <ChevronUp className="h-4 w-4" />
                    ) : (
                      <ChevronDown className="h-4 w-4" />
                    )}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => handleDelete(agent.agent_id)}>
                    <Trash2 className="h-4 w-4 text-red-400" />
                  </Button>
                </div>
              </div>

              {editingAgent === agent.agent_id ? (
                <div className="border-t border-zinc-800 px-4 py-3 space-y-3">
                  <textarea
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    rows={5}
                    className="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                  <div className="flex gap-2 justify-end">
                    <Button variant="outline" size="sm" onClick={() => setEditingAgent(null)}>
                      <X className="h-4 w-4 mr-1" /> Cancel
                    </Button>
                    <Button size="sm" onClick={() => handleSaveEdit(agent.agent_id)}>
                      <Save className="h-4 w-4 mr-1" /> Save
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="border-t border-zinc-800 px-4 py-3">
                  <p className="text-sm text-zinc-300 line-clamp-3 cursor-pointer hover:text-white" onClick={() => startEditing(agent)}>
                    {agent.instructions}
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
