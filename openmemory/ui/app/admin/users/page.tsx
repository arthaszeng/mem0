"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";
import { getCookie, decodeJwtPayload, TOKEN_COOKIE } from "@/lib/auth";
import { Plus, Trash2, RotateCcw, ShieldCheck, ShieldOff } from "lucide-react";
import { toast } from "sonner";
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

interface UserRecord {
  id: string;
  username: string;
  email: string | null;
  is_superadmin: boolean;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
}

const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

export default function AdminUsersPage() {
  const router = useRouter();
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [isSuperadmin, setIsSuperadmin] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    const token = getCookie(TOKEN_COOKIE);
    if (!token) { router.replace("/login"); return; }
    const payload = decodeJwtPayload(token);
    if (!payload?.is_superadmin) {
      toast.error("Superadmin access required");
      router.replace("/");
    }
  }, [router]);

  const fetchUsers = useCallback(async () => {
    try {
      const res = await api.get("/auth/users");
      setUsers(res.data);
    } catch (err: any) {
      if (err?.response?.status === 403) {
        toast.error("Superadmin access required");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleCreate = async () => {
    setActionLoading(true);
    try {
      await api.post("/auth/users", {
        username: newUsername,
        password: newPassword,
        email: newEmail || undefined,
        is_superadmin: isSuperadmin,
      });
      setCreateOpen(false);
      setNewUsername("");
      setNewPassword("");
      setNewEmail("");
      setIsSuperadmin(false);
      fetchUsers();
      toast.success("User created");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to create user");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeactivate = async (userId: string) => {
    if (!confirm("Deactivate this user?")) return;
    try {
      await api.delete(`/auth/users/${userId}`);
      fetchUsers();
      toast.success("User deactivated");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed");
    }
  };

  const handleResetPassword = async (userId: string) => {
    const newPw = prompt("Enter new temporary password:");
    if (!newPw) return;
    try {
      await api.post(`/auth/users/${userId}/reset-password`, {
        new_password: newPw,
      });
      toast.success("Password reset. User will be prompted to change on next login.");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed");
    }
  };

  return (
    <div className="container mx-auto max-w-4xl py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">User Management</h1>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button size="sm" className="gap-2">
              <Plus className="h-4 w-4" /> Create User
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-zinc-900 border-zinc-700">
            <DialogHeader>
              <DialogTitle>Create User</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div>
                <Label>Username</Label>
                <Input value={newUsername} onChange={(e) => setNewUsername(e.target.value)} className="bg-zinc-800 border-zinc-700" />
              </div>
              <div>
                <Label>Temporary Password</Label>
                <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className="bg-zinc-800 border-zinc-700" />
              </div>
              <div>
                <Label>Email (optional)</Label>
                <Input value={newEmail} onChange={(e) => setNewEmail(e.target.value)} className="bg-zinc-800 border-zinc-700" />
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" id="superadmin" checked={isSuperadmin} onChange={(e) => setIsSuperadmin(e.target.checked)} className="rounded" />
                <Label htmlFor="superadmin">Superadmin</Label>
              </div>
            </div>
            <DialogFooter>
              <Button onClick={handleCreate} disabled={!newUsername.trim() || !newPassword.trim() || actionLoading}>{actionLoading ? "Creating..." : "Create"}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <p className="text-zinc-400">Loading...</p>
      ) : users.length === 0 ? (
        <p className="text-zinc-400">No users found (you may not have superadmin access).</p>
      ) : (
        <div className="space-y-3">
          {users.map((u) => (
            <div key={u.id} className="flex items-center justify-between rounded-lg border border-zinc-700 bg-zinc-900 p-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-white font-medium">{u.username}</span>
                  {u.is_superadmin && (
                    <span className="text-xs px-2 py-0.5 rounded bg-amber-800/40 text-amber-300 border border-amber-700/50">
                      superadmin
                    </span>
                  )}
                  {!u.is_active && (
                    <span className="text-xs px-2 py-0.5 rounded bg-red-800/40 text-red-300 border border-red-700/50">
                      inactive
                    </span>
                  )}
                  {u.must_change_password && (
                    <span className="text-xs px-2 py-0.5 rounded bg-yellow-800/40 text-yellow-300 border border-yellow-700/50">
                      must change pw
                    </span>
                  )}
                </div>
                <p className="text-xs text-zinc-500 mt-1">
                  {u.email || "no email"} &middot; created {new Date(u.created_at).toLocaleDateString()}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="icon" title="Reset password" className="text-zinc-400 hover:text-white" onClick={() => handleResetPassword(u.id)}>
                  <RotateCcw className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="icon" title="Deactivate" className="text-red-400 hover:text-red-300" onClick={() => handleDeactivate(u.id)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
