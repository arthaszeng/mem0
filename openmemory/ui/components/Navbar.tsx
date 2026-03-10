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
import { Settings, LogOut, Key, FolderKanban, Users, ChevronDown } from "lucide-react";
import { useConfig } from "@/hooks/useConfig";
import { deleteCookie } from "@/lib/auth";
import api from "@/lib/api";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const GLOBAL_ROUTES = ["/login", "/change-password", "/projects", "/api-keys", "/admin", "/settings"];

function extractProjectSlug(pathname: string): string {
  if (GLOBAL_ROUTES.some((r) => pathname === r || pathname.startsWith(r + "/"))) return "";
  const seg = pathname.split("/").filter(Boolean);
  return seg.length > 0 ? seg[0] : "";
}

interface ProjectInfo {
  id: string;
  name: string;
  slug: string;
}

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const projectSlug = extractProjectSlug(pathname);

  const [projects, setProjects] = useState<ProjectInfo[]>([]);

  const loadProjects = useCallback(async () => {
    try {
      const res = await api.get("/api/v1/projects");
      setProjects(res.data);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const currentProject = projects.find((p) => p.slug === projectSlug);

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
    const fetchers = getFetchersForPath(pathname);
    await Promise.allSettled(fetchers.map((fn) => fn()));
  };

  const handleSwitchProject = (slug: string) => {
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

  return (
    <header className="sticky top-0 z-50 w-full border-b border-zinc-800 bg-zinc-950/95 backdrop-blur supports-[backdrop-filter]:bg-zinc-950/60">
      <div className="container flex h-14 items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2">
            <Image src={`${basePath}/logo.svg`} alt="OpenMemory" width={26} height={26} />
            <span className="text-xl font-medium">OpenMemory</span>
          </Link>

          {!isLoginPage && projectSlug && projects.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1 border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800 ml-2">
                  <FolderKanban className="h-3.5 w-3.5" />
                  {currentProject?.name || projectSlug}
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

        {!isLoginPage && (
          <div className="flex items-center gap-2">
            {projectSlug && (
              <>
                <Link href={pHref("")}>
                  <Button
                    variant="outline"
                    size="sm"
                    className={`flex items-center gap-2 border-none ${isActive(pHref("")) && !pathname.includes("/memories") && !pathname.includes("/apps") ? activeClass : inactiveClass}`}
                  >
                    <HiHome /> Dashboard
                  </Button>
                </Link>
                <Link href={pHref("/memories")}>
                  <Button
                    variant="outline"
                    size="sm"
                    className={`flex items-center gap-2 border-none ${isActive(pHref("/memories")) ? activeClass : inactiveClass}`}
                  >
                    <HiMiniRectangleStack /> Memories
                  </Button>
                </Link>
                <Link href={pHref("/apps")}>
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
            <Link href="/projects">
              <Button
                variant="outline"
                size="sm"
                className={`flex items-center gap-2 border-none ${pathname.startsWith("/projects") ? activeClass : inactiveClass}`}
              >
                <FolderKanban className="h-4 w-4" /> Projects
              </Button>
            </Link>
            <Link href="/api-keys">
              <Button
                variant="outline"
                size="sm"
                className={`flex items-center gap-2 border-none ${pathname.startsWith("/api-keys") ? activeClass : inactiveClass}`}
              >
                <Key className="h-4 w-4" /> API Keys
              </Button>
            </Link>
            <Link href="/admin/users">
              <Button
                variant="outline"
                size="sm"
                className={`flex items-center gap-2 border-none ${pathname.startsWith("/admin") ? activeClass : inactiveClass}`}
              >
                <Users className="h-4 w-4" /> Users
              </Button>
            </Link>
            <Link href="/settings">
              <Button
                variant="outline"
                size="sm"
                className={`flex items-center gap-2 border-none ${pathname.startsWith("/settings") ? activeClass : inactiveClass}`}
              >
                <Settings /> Settings
              </Button>
            </Link>
          </div>
        )}

        {!isLoginPage && (
          <div className="flex items-center gap-4">
            <Button
              onClick={handleRefresh}
              variant="outline"
              size="sm"
              className="border-zinc-700/50 bg-zinc-900 hover:bg-zinc-800"
            >
              <FiRefreshCcw className="transition-transform duration-300 group-hover:rotate-180" />
              Refresh
            </Button>
            <CreateMemoryDialog />
            <Button
              onClick={handleLogout}
              variant="outline"
              size="sm"
              className="border-zinc-700/50 bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-white"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </header>
  );
}
