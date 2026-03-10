"use client";

import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";
import { Plus, Trash2, Users, Settings2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface Project {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  owner_username: string;
  member_count: number;
  created_at: string;
}

interface Member {
  user_id: string;
  username: string;
  role: string;
  joined_at: string;
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newSlug, setNewSlug] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [addMemberOpen, setAddMemberOpen] = useState(false);
  const [newMemberUsername, setNewMemberUsername] = useState("");
  const [newMemberRole, setNewMemberRole] = useState("normal");

  const fetchProjects = useCallback(async () => {
    try {
      const res = await api.get("/api/v1/projects");
      setProjects(res.data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchMembers = useCallback(async (slug: string) => {
    try {
      const res = await api.get(`/api/v1/projects/${slug}/members`);
      setMembers(res.data);
    } catch {
      setMembers([]);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  useEffect(() => {
    if (selectedProject) fetchMembers(selectedProject);
  }, [selectedProject, fetchMembers]);

  const handleCreate = async () => {
    try {
      await api.post("/api/v1/projects", {
        name: newName,
        slug: newSlug || undefined,
        description: newDesc || undefined,
      });
      setCreateOpen(false);
      setNewName("");
      setNewSlug("");
      setNewDesc("");
      fetchProjects();
    } catch (err: any) {
      alert(err?.response?.data?.detail || "Failed to create project");
    }
  };

  const handleDelete = async (slug: string) => {
    if (!confirm(`Delete project "${slug}"? This cannot be undone.`)) return;
    try {
      await api.delete(`/api/v1/projects/${slug}`);
      setSelectedProject(null);
      fetchProjects();
    } catch (err: any) {
      alert(err?.response?.data?.detail || "Failed to delete project");
    }
  };

  const handleAddMember = async () => {
    if (!selectedProject) return;
    try {
      await api.post(`/api/v1/projects/${selectedProject}/members`, {
        username: newMemberUsername,
        role: newMemberRole,
      });
      setAddMemberOpen(false);
      setNewMemberUsername("");
      setNewMemberRole("normal");
      fetchMembers(selectedProject);
    } catch (err: any) {
      alert(err?.response?.data?.detail || "Failed to add member");
    }
  };

  const handleRemoveMember = async (username: string) => {
    if (!selectedProject) return;
    try {
      await api.delete(`/api/v1/projects/${selectedProject}/members/${username}`);
      fetchMembers(selectedProject);
    } catch (err: any) {
      alert(err?.response?.data?.detail || "Failed to remove member");
    }
  };

  return (
    <div className="container mx-auto max-w-4xl py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Projects</h1>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button size="sm" className="gap-2">
              <Plus className="h-4 w-4" /> New Project
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-zinc-900 border-zinc-700">
            <DialogHeader>
              <DialogTitle>Create Project</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div>
                <Label>Name</Label>
                <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="My Project" className="bg-zinc-800 border-zinc-700" />
              </div>
              <div>
                <Label>Slug (optional, auto-generated)</Label>
                <Input value={newSlug} onChange={(e) => setNewSlug(e.target.value)} placeholder="my-project" className="bg-zinc-800 border-zinc-700" />
              </div>
              <div>
                <Label>Description</Label>
                <Input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="Description..." className="bg-zinc-800 border-zinc-700" />
              </div>
            </div>
            <DialogFooter>
              <Button onClick={handleCreate} disabled={!newName.trim()}>Create</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <p className="text-zinc-400">Loading...</p>
      ) : projects.length === 0 ? (
        <p className="text-zinc-400">No projects yet. Create one to get started.</p>
      ) : (
        <div className="grid gap-4">
          {projects.map((p) => (
            <div
              key={p.id}
              className={`rounded-lg border p-4 cursor-pointer transition-colors ${
                selectedProject === p.slug
                  ? "border-blue-500 bg-zinc-800/80"
                  : "border-zinc-700 bg-zinc-900 hover:bg-zinc-800/50"
              }`}
              onClick={() => setSelectedProject(p.slug === selectedProject ? null : p.slug)}
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-white">{p.name}</h3>
                  <p className="text-sm text-zinc-400">
                    slug: {p.slug} &middot; owner: {p.owner_username} &middot; {p.member_count} member(s)
                  </p>
                  {p.description && <p className="text-sm text-zinc-500 mt-1">{p.description}</p>}
                </div>
                <Button variant="ghost" size="icon" className="text-red-400 hover:text-red-300 hover:bg-red-900/20" onClick={(e) => { e.stopPropagation(); handleDelete(p.slug); }}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>

              {selectedProject === p.slug && (
                <div className="mt-4 border-t border-zinc-700 pt-4">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-medium text-zinc-300 flex items-center gap-2">
                      <Users className="h-4 w-4" /> Members
                    </h4>
                    <Dialog open={addMemberOpen} onOpenChange={setAddMemberOpen}>
                      <DialogTrigger asChild>
                        <Button size="sm" variant="outline" className="gap-1 text-xs border-zinc-600">
                          <Plus className="h-3 w-3" /> Add Member
                        </Button>
                      </DialogTrigger>
                      <DialogContent className="bg-zinc-900 border-zinc-700">
                        <DialogHeader><DialogTitle>Add Member</DialogTitle></DialogHeader>
                        <div className="space-y-4 py-2">
                          <div>
                            <Label>Username</Label>
                            <Input value={newMemberUsername} onChange={(e) => setNewMemberUsername(e.target.value)} className="bg-zinc-800 border-zinc-700" />
                          </div>
                          <div>
                            <Label>Role</Label>
                            <select value={newMemberRole} onChange={(e) => setNewMemberRole(e.target.value)} className="w-full rounded-md bg-zinc-800 border border-zinc-700 p-2 text-sm text-white">
                              <option value="read">Read</option>
                              <option value="normal">Normal</option>
                              <option value="admin">Admin</option>
                            </select>
                          </div>
                        </div>
                        <DialogFooter>
                          <Button onClick={handleAddMember} disabled={!newMemberUsername.trim()}>Add</Button>
                        </DialogFooter>
                      </DialogContent>
                    </Dialog>
                  </div>
                  {members.length === 0 ? (
                    <p className="text-xs text-zinc-500">No members.</p>
                  ) : (
                    <div className="space-y-2">
                      {members.map((m) => (
                        <div key={m.username} className="flex items-center justify-between rounded bg-zinc-800/60 px-3 py-2">
                          <span className="text-sm text-white">{m.username}</span>
                          <div className="flex items-center gap-3">
                            <span className="text-xs px-2 py-0.5 rounded bg-zinc-700 text-zinc-300">{m.role}</span>
                            <Button variant="ghost" size="icon" className="h-6 w-6 text-red-400 hover:text-red-300" onClick={() => handleRemoveMember(m.username)}>
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
