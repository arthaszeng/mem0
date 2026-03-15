"use client";

import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { HiHome, HiMiniRectangleStack } from "react-icons/hi2";
import { RiApps2AddFill } from "react-icons/ri";
import { FiRefreshCcw } from "react-icons/fi";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { CreateMemoryDialog } from "@/app/[projectSlug]/memories/components/CreateMemoryDialog";
import { useMemoriesApi } from "@/hooks/useMemoriesApi";
import Image from "next/image";
import { useStats } from "@/hooks/useStats";
import { useAppsApi } from "@/hooks/useAppsApi";
import { LogOut, FolderKanban, ChevronDown, ShieldCheck, UserPlus, Copy, X, Check, Loader2, Menu } from "lucide-react";
import { toast } from "sonner";
import { useConfig } from "@/hooks/useConfig";
import { deleteCookie, getCookie, TOKEN_COOKIE, decodeJwtPayload } from "@/lib/auth";
import api from "@/lib/api";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";
const appVersion = process.env.NEXT_PUBLIC_APP_VERSION || "dev";

const GLOBAL_ROUTES = ["/login", "/change-password", "/settings", "/invite"];
const LAST_PROJECT_KEY = "om_last_project";

function extractProjectSlug(pathname: string): string {
  if (GLOBAL_ROUTES.some((r) => pathname === r || pathname.startsWith(r + "/"))) return "";
  const seg = pathname.split("/").filter(Boolean);
  return seg.length > 0 ? seg[0] : "";
}

interface ProjectInfo {
  id: string;
  name: string;
  slug: string;
  my_role?: string;
}

interface InviteRecord {
  id: string;
  token: string;
  role: string;
  status: string;
  created_by: string | null;
  accepted_by: string | null;
  expires_at: string | null;
  created_at: string | null;
  accepted_at: string | null;
}

interface MemberRecord {
  id: string;
  username: string;
  role: string;
  created_at: string | null;
}

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const projectSlug = extractProjectSlug(pathname);

  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [isSuperadmin, setIsSuperadmin] = useState(false);

  const loadProjects = useCallback(async () => {
    try {
      const res = await api.get("/api/v1/projects");
      setProjects(res.data);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    loadProjects();
    const token = getCookie(TOKEN_COOKIE);
    if (token) {
      const payload = decodeJwtPayload(token);
      setIsSuperadmin(!!payload?.is_superadmin);
    } else {
      setIsSuperadmin(false);
    }
    if (projectSlug) {
      localStorage.setItem(LAST_PROJECT_KEY, projectSlug);
    }
  }, [loadProjects, pathname, projectSlug]);

  const currentProject = projects.find((p) => p.slug === projectSlug);
  const canInvite = isSuperadmin || currentProject?.my_role === "owner" || currentProject?.my_role === "admin";

  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteRole, setInviteRole] = useState("read_write");
  const [inviteExpiry, setInviteExpiry] = useState(7);
  const [invites, setInvites] = useState<InviteRecord[]>([]);
  const [members, setMembers] = useState<MemberRecord[]>([]);
  const [createdLink, setCreatedLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const loadInvitePanel = useCallback(async () => {
    if (!projectSlug) return;
    try {
      const [invRes, memRes] = await Promise.all([
        api.get(`/api/v1/projects/${projectSlug}/invites`),
        api.get(`/api/v1/projects/${projectSlug}/members`),
      ]);
      setInvites(invRes.data);
      setMembers(memRes.data);
    } catch { /* ignore */ }
  }, [projectSlug]);

  useEffect(() => {
    if (inviteOpen) loadInvitePanel();
  }, [inviteOpen, loadInvitePanel]);

  const handleCreateInvite = async () => {
    setInviteLoading(true);
    try {
      const res = await api.post(`/api/v1/projects/${projectSlug}/invites`, {
        role: inviteRole,
        expires_in_days: inviteExpiry,
      });
      const token = res.data.token;
      const link = `${window.location.origin}${basePath}/invite/${token}`;
      setCreatedLink(link);
      loadInvitePanel();
      toast.success("Invite link created");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to create invite");
    } finally {
      setInviteLoading(false);
    }
  };

  const handleRevokeInvite = async (token: string) => {
    try {
      await api.post(`/api/v1/projects/${projectSlug}/invites/revoke`, { token });
      loadInvitePanel();
      toast.success("Invite revoked");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to revoke invite");
    }
  };

  const handleCopyLink = () => {
    if (createdLink) {
      navigator.clipboard.writeText(createdLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const memoriesApi = useMemoriesApi();
  const appsApi = useAppsApi();
  const statsApi = useStats();
  const configApi = useConfig();

  const handleLogout = async () => {
    await fetch(`${basePath}/api/auth/logout`, { method: "POST" });
    deleteCookie("om_token");
    deleteCookie("om_user");
    router.push("/login");
    router.refresh();
  };

  const routeBasedFetchMapping: {
    match: RegExp;
    getFetchers: (params: Record<string, string>) => (() => Promise<any>)[];
  }[] = [
    {
      match: /^\/[^/]+\/memory\/([^/]+)$/,
      getFetchers: ({ memory_id }) => [
        () => memoriesApi.fetchMemoryById(memory_id),
        () => memoriesApi.fetchAccessLogs(memory_id),
        () => memoriesApi.fetchRelatedMemories(memory_id),
      ],
    },
    {
      match: /^\/[^/]+\/apps\/([^/]+)$/,
      getFetchers: ({ app_id }) => [
        () => appsApi.fetchAppMemories(app_id),
        () => appsApi.fetchAppAccessedMemories(app_id),
        () => appsApi.fetchAppDetails(app_id),
      ],
    },
    {
      match: /^\/[^/]+\/memories$/,
      getFetchers: () => [memoriesApi.fetchMemories],
    },
    {
      match: /^\/[^/]+\/apps$/,
      getFetchers: () => [appsApi.fetchApps],
    },
    {
      match: /^\/[^/]+$/,
      getFetchers: () => [statsApi.fetchStats, memoriesApi.fetchMemories],
    },
    {
      match: /^\/settings$/,
      getFetchers: () => [configApi.fetchConfig],
    },
  ];

  const getFetchersForPath = (path: string) => {
    for (const route of routeBasedFetchMapping) {
      const match = path.match(route.match);
      if (match) {
        if (route.match.source.includes("memory")) return route.getFetchers({ memory_id: match[1] });
        if (route.match.source.includes("app")) return route.getFetchers({ app_id: match[1] });
        return route.getFetchers({});
      }
    }
    return [];
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const fetchers = getFetchersForPath(pathname);
      await Promise.allSettled(fetchers.map((fn) => fn()));
    } finally {
      setRefreshing(false);
    }
  };

  const handleSwitchProject = (slug: string) => {
    localStorage.setItem(LAST_PROJECT_KEY, slug);
    const segments = pathname.split("/").filter(Boolean);
    if (segments.length === 0 || GLOBAL_ROUTES.some((r) => pathname.startsWith(r))) {
      router.push(`/${slug}`);
      return;
    }
    segments[0] = slug;
    router.push(`/${segments.join("/")}`);
  };

  const pHref = (path: string) => (projectSlug ? `/${projectSlug}${path}` : path);

  const isActive = (href: string) => {
    if (href === `/${projectSlug}`) return pathname === href;
    return pathname.startsWith(href);
  };

  const activeClass = "bg-zinc-800 text-white border-zinc-600";
  const inactiveClass = "text-zinc-300";

  const isLoginPage = pathname === "/login" || pathname === "/change-password";
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navLinks = (
    <>
      {projectSlug && (
        <>
          <Link href={pHref("")} onClick={() => setMobileMenuOpen(false)}>
            <Button
              variant="outline"
              size="sm"
              className={`flex items-center gap-2 border-none ${isActive(pHref("")) && !pathname.includes("/memories") && !pathname.includes("/apps") ? activeClass : inactiveClass}`}
            >
              <HiHome /> Dashboard
            </Button>
          </Link>
          <Link href={pHref("/memories")} onClick={() => setMobileMenuOpen(false)}>
            <Button
              variant="outline"
              size="sm"
              className={`flex items-center gap-2 border-none ${isActive(pHref("/memories")) ? activeClass : inactiveClass}`}
            >
              <HiMiniRectangleStack /> Memories
            </Button>
          </Link>
          <Link href={pHref("/apps")} onClick={() => setMobileMenuOpen(false)}>
            <Button
              variant="outline"
              size="sm"
              className={`flex items-center gap-2 border-none ${isActive(pHref("/apps")) ? activeClass : inactiveClass}`}
            >
              <RiApps2AddFill /> Apps
            </Button>
          </Link>
        </>
      )}
      {isSuperadmin && (
        <Link href="/settings" onClick={() => setMobileMenuOpen(false)}>
          <Button
            variant="outline"
            size="sm"
            className={`flex items-center gap-2 border-none ${pathname.startsWith("/settings") ? activeClass : inactiveClass}`}
          >
            <ShieldCheck className="h-4 w-4" /> Admin Settings
          </Button>
        </Link>
      )}
    </>
  );

  const actionButtons = (
    <>
      <Button
        onClick={handleRefresh}
        variant="outline"
        size="sm"
        className="border-zinc-700/50 bg-zinc-900 hover:bg-zinc-800"
        disabled={refreshing}
      >
        {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <FiRefreshCcw className="transition-transform duration-300 group-hover:rotate-180" />}
        <span className="hidden sm:inline">Refresh</span>
      </Button>
      {canInvite && projectSlug && (
        <Dialog open={inviteOpen} onOpenChange={(open) => { setInviteOpen(open); if (!open) { setCreatedLink(null); setCopied(false); } }}>
          <DialogTrigger asChild>
            <Button variant="outline" size="sm" className="flex items-center gap-2 border-zinc-700/50 bg-zinc-900 hover:bg-zinc-800">
              <UserPlus className="h-4 w-4" /> <span className="hidden sm:inline">Invite</span>
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-zinc-900 border-zinc-700 max-w-lg max-h-[80vh] overflow-y-auto">
            <DialogHeader><DialogTitle>Invite to {currentProject?.name || projectSlug}</DialogTitle></DialogHeader>

            <div className="space-y-4">
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <Label className="text-xs text-zinc-400">Role</Label>
                  <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} className="w-full rounded-md bg-zinc-800 border border-zinc-700 p-2 text-sm text-white mt-1">
                    <option value="read_only">Read Only</option>
                    <option value="read_write">Read / Write</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>
                <div className="w-24">
                  <Label className="text-xs text-zinc-400">Expires (days)</Label>
                  <input type="number" min={1} max={365} value={inviteExpiry} onChange={(e) => setInviteExpiry(Number(e.target.value))} className="w-full rounded-md bg-zinc-800 border border-zinc-700 p-2 text-sm text-white mt-1" />
                </div>
                <Button size="sm" onClick={handleCreateInvite} disabled={inviteLoading}>{inviteLoading ? "Creating..." : "Create Link"}</Button>
              </div>

              {createdLink && (
                <div className="flex items-center gap-2 rounded-md bg-zinc-800 border border-zinc-700 p-2">
                  <input readOnly value={createdLink} className="flex-1 bg-transparent text-xs text-zinc-200 outline-none" />
                  <Button size="sm" variant="ghost" onClick={handleCopyLink} className="h-7 w-7 p-0">
                    {copied ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
                  </Button>
                </div>
              )}

              <div>
                <h4 className="text-sm font-medium text-zinc-300 mb-2">Team Members ({members.length})</h4>
                {members.length === 0 ? <p className="text-xs text-zinc-500">No members yet.</p> : (
                  <div className="space-y-1">
                    {members.map((m) => (
                      <div key={m.id} className="flex items-center justify-between rounded bg-zinc-800/60 px-3 py-1.5">
                        <span className="text-sm text-white">{m.username}</span>
                        <span className="text-xs px-2 py-0.5 rounded bg-zinc-700 text-zinc-300">{m.role}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <h4 className="text-sm font-medium text-zinc-300 mb-2">Invite History ({invites.length})</h4>
                {invites.length === 0 ? <p className="text-xs text-zinc-500">No invites yet.</p> : (
                  <div className="space-y-1">
                    {invites.map((inv) => (
                      <div key={inv.id} className="flex items-center justify-between rounded bg-zinc-800/60 px-3 py-1.5">
                        <div className="flex-1 min-w-0">
                          <span className="text-xs text-zinc-400">
                            {`${inv.role} \u00B7 ${inv.status}`}
                            {inv.accepted_by && ` by ${inv.accepted_by}`}
                            {inv.created_at && ` \u00B7 ${new Date(inv.created_at).toLocaleDateString()}`}
                          </span>
                        </div>
                        {inv.status === "pending" && (
                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-red-400 hover:text-red-300" onClick={() => handleRevokeInvite(inv.token)}>
                            <X className="h-3 w-3" />
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}
      <CreateMemoryDialog />
      <Button
        onClick={handleLogout}
        variant="outline"
        size="sm"
        className="border-zinc-700/50 bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-white"
      >
        <LogOut className="h-4 w-4" />
      </Button>
    </>
  );

  return (
    <header className="sticky top-0 z-50 w-full border-b border-zinc-800 bg-zinc-950/95 backdrop-blur supports-[backdrop-filter]:bg-zinc-950/60">
      <div className="container flex h-14 items-center justify-between gap-2">
        {/* Left: Logo + Project Selector */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <Link href="/" className="flex items-center gap-2">
            <Image src={`${basePath}/logo.svg`} alt="Memverse" width={26} height={26} />
            <span className="text-xl font-medium hidden sm:inline">Memverse</span>
            <span className="text-[10px] text-zinc-500 font-mono hidden sm:inline">v{appVersion}</span>
          </Link>

          {!isLoginPage && projectSlug && projects.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1 border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800 ml-2">
                  <FolderKanban className="h-3.5 w-3.5" />
                  <span className="max-w-[100px] truncate">{currentProject?.name || projectSlug}</span>
                  <ChevronDown className="h-3 w-3 opacity-60" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="bg-zinc-900 border-zinc-700">
                {projects.map((p) => (
                  <DropdownMenuItem
                    key={p.slug}
                    onClick={() => handleSwitchProject(p.slug)}
                    className={p.slug === projectSlug ? "bg-zinc-800" : ""}
                  >
                    {p.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        {/* Center: Nav Links - hidden on small screens */}
        {!isLoginPage && (
          <div className="hidden xl:flex items-center gap-2">
            {navLinks}
          </div>
        )}

        {/* Right: Action Buttons + Mobile Menu Toggle */}
        {!isLoginPage && (
          <div className="flex items-center gap-2">
            <div className="hidden xl:flex items-center gap-2">
              {actionButtons}
            </div>
            <Button
              variant="outline"
              size="sm"
              className="xl:hidden border-zinc-700/50 bg-zinc-900 hover:bg-zinc-800"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              <Menu className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>

      {/* Mobile/Tablet expanded menu */}
      {!isLoginPage && mobileMenuOpen && (
        <div className="xl:hidden border-t border-zinc-800 bg-zinc-950/98 backdrop-blur">
          <div className="container py-3 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              {navLinks}
            </div>
            <div className="flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-3">
              {actionButtons}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
