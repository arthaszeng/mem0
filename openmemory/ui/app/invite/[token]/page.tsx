"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";
import { getCookie, TOKEN_COOKIE } from "@/lib/auth";
import { UserPlus, AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

interface InviteInfo {
  token: string;
  project_name: string;
  project_slug: string;
  role: string;
  created_by: string | null;
  expires_at: string | null;
}

export default function InviteAcceptPage() {
  const params = useParams();
  const router = useRouter();
  const token = params.token as string;

  const [info, setInfo] = useState<InviteInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [accepted, setAccepted] = useState(false);

  useEffect(() => {
    const loggedIn = !!getCookie(TOKEN_COOKIE);
    if (!loggedIn) {
      const returnUrl = encodeURIComponent(`/invite/${token}`);
      router.push(`/login?redirect=${returnUrl}`);
      return;
    }

    api
      .get(`/api/v1/projects/invites/${token}/info`)
      .then((res) => setInfo(res.data))
      .catch((err) => setError(err?.response?.data?.detail || "Invite not found or expired"))
      .finally(() => setLoading(false));
  }, [token, router]);

  const handleAccept = async () => {
    setAccepting(true);
    try {
      const res = await api.post(`/api/v1/projects/invites/${token}/accept`);
      setAccepted(true);
      setTimeout(() => router.push(`/${res.data.project_slug}`), 1500);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Failed to accept invite");
    } finally {
      setAccepting(false);
    }
  };

  const roleLabel: Record<string, string> = {
    read_only: "Read Only",
    read_write: "Read / Write",
    admin: "Admin",
    owner: "Owner",
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="h-8 w-8 animate-spin text-zinc-400" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center gap-4">
        <AlertCircle className="h-16 w-16 text-red-400" />
        <h1 className="text-2xl font-bold text-white">Invalid Invite</h1>
        <p className="text-zinc-400 max-w-md">{error}</p>
        <Button variant="outline" onClick={() => router.push("/")}>Go Home</Button>
      </div>
    );
  }

  if (accepted) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center gap-4">
        <CheckCircle2 className="h-16 w-16 text-green-400" />
        <h1 className="text-2xl font-bold text-white">Joined!</h1>
        <p className="text-zinc-400">Redirecting to {info?.project_name}...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center h-[60vh] text-center gap-6">
      <UserPlus className="h-16 w-16 text-blue-400" />
      <div>
        <h1 className="text-2xl font-bold text-white">Project Invitation</h1>
        <p className="text-zinc-400 mt-2">
          You&apos;ve been invited to join <span className="text-white font-semibold">{info?.project_name}</span>
        </p>
      </div>

      <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-6 w-full max-w-sm space-y-3">
        <div className="flex justify-between text-sm">
          <span className="text-zinc-400">Role</span>
          <span className="text-white font-medium">{roleLabel[info?.role || ""] || info?.role}</span>
        </div>
        {info?.created_by && (
          <div className="flex justify-between text-sm">
            <span className="text-zinc-400">Invited by</span>
            <span className="text-white">{info.created_by}</span>
          </div>
        )}
        {info?.expires_at && (
          <div className="flex justify-between text-sm">
            <span className="text-zinc-400">Expires</span>
            <span className="text-white">{new Date(info.expires_at).toLocaleDateString()}</span>
          </div>
        )}
      </div>

      <Button size="lg" onClick={handleAccept} disabled={accepting} className="gap-2">
        {accepting ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
        Accept Invitation
      </Button>
    </div>
  );
}
