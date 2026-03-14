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
import { Plus, Trash2, Play } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

interface PolicyItem {
  id: string;
  criteria_type: string;
  criteria_id: string | null;
  days_to_archive: number;
  created_at: string;
}

export function ArchivePoliciesTab() {
  const [policies, setPolicies] = useState<PolicyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [criteriaType, setCriteriaType] = useState("global");
  const [criteriaId, setCriteriaId] = useState("");
  const [days, setDays] = useState(90);
  const [creating, setCreating] = useState(false);
  const [applying, setApplying] = useState(false);

  const fetchPolicies = useCallback(async () => {
    try {
      const res = await api.get<PolicyItem[]>("/api/v1/memories/archive-policies");
      setPolicies(res.data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchPolicies(); }, [fetchPolicies]);

  const handleCreate = async () => {
    setCreating(true);
    try {
      const body: Record<string, unknown> = { criteria_type: criteriaType, days_to_archive: days };
      if (criteriaType === "app" && criteriaId) body.criteria_id = criteriaId;
      await api.post("/api/v1/memories/archive-policies", body);
      toast.success("Policy created");
      setDialogOpen(false);
      setCriteriaType("global");
      setCriteriaId("");
      setDays(90);
      await fetchPolicies();
    } catch {
      toast.error("Failed to create policy");
    } finally { setCreating(false); }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/api/v1/memories/archive-policies/${id}`);
      toast.success("Policy deleted");
      await fetchPolicies();
    } catch {
      toast.error("Failed to delete policy");
    }
  };

  const handleApply = async () => {
    setApplying(true);
    try {
      const res = await api.post<{ archived: number }>("/api/v1/memories/archive-policies/apply");
      toast.success(`Archived ${res.data.archived} memories`);
    } catch {
      toast.error("Failed to apply policies");
    } finally { setApplying(false); }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-white">Archive Policies</h2>
          <p className="text-sm text-zinc-400 mt-1">
            Auto-archive memories older than a threshold. Policies run hourly.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleApply} disabled={applying}>
            <Play className="h-4 w-4 mr-1" /> {applying ? "Applying..." : "Apply Now"}
          </Button>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm"><Plus className="h-4 w-4 mr-1" /> New Policy</Button>
            </DialogTrigger>
            <DialogContent className="bg-zinc-900 border-zinc-800">
              <DialogHeader>
                <DialogTitle>Create Archive Policy</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div>
                  <Label>Criteria Type</Label>
                  <select
                    value={criteriaType}
                    onChange={(e) => setCriteriaType(e.target.value)}
                    className="w-full mt-1 rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white"
                  >
                    <option value="global">Global — all memories</option>
                    <option value="app">App — specific app only</option>
                  </select>
                </div>
                {criteriaType === "app" && (
                  <div>
                    <Label>App ID (UUID)</Label>
                    <Input
                      value={criteriaId}
                      onChange={(e) => setCriteriaId(e.target.value)}
                      placeholder="e.g. bede6d9c-2a4f-4117-b797-c9e87c9782f8"
                      className="bg-zinc-800 border-zinc-700"
                    />
                  </div>
                )}
                <div>
                  <Label>Days until archive</Label>
                  <Input
                    type="number"
                    min={1}
                    value={days}
                    onChange={(e) => setDays(Number(e.target.value))}
                    className="bg-zinc-800 border-zinc-700"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button onClick={handleCreate} disabled={creating}>
                  {creating ? "Creating..." : "Create Policy"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-8 text-zinc-400">Loading...</div>
      ) : policies.length === 0 ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-12 text-center">
          <p className="text-zinc-400">No archive policies configured yet.</p>
          <p className="text-zinc-500 text-sm mt-1">Create a policy to auto-archive old memories.</p>
        </div>
      ) : (
        <div className="rounded-lg border border-zinc-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-zinc-800">
              <tr>
                <th className="text-left px-4 py-3 text-zinc-400 font-medium">Type</th>
                <th className="text-left px-4 py-3 text-zinc-400 font-medium">Target</th>
                <th className="text-left px-4 py-3 text-zinc-400 font-medium">Days</th>
                <th className="text-left px-4 py-3 text-zinc-400 font-medium">Created</th>
                <th className="text-right px-4 py-3 text-zinc-400 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {policies.map((p) => (
                <tr key={p.id} className="bg-zinc-900 hover:bg-zinc-800/50">
                  <td className="px-4 py-3 text-white capitalize">{p.criteria_type}</td>
                  <td className="px-4 py-3 text-zinc-300">{p.criteria_id || "—"}</td>
                  <td className="px-4 py-3 text-white">{p.days_to_archive}d</td>
                  <td className="px-4 py-3 text-zinc-400">{p.created_at?.split("T")[0] || "—"}</td>
                  <td className="px-4 py-3 text-right">
                    <Button variant="ghost" size="sm" onClick={() => handleDelete(p.id)}>
                      <Trash2 className="h-4 w-4 text-red-400" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
