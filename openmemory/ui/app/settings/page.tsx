"use client";

import { useState, useEffect } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ShieldAlert, Users, FolderKanban, Settings, Key, Clock, Bot } from "lucide-react";
import { getCookie, TOKEN_COOKIE, decodeJwtPayload } from "@/lib/auth";
import { useRouter } from "next/navigation";
import { UsersTab } from "./components/UsersTab";
import { ProjectsTab } from "./components/ProjectsTab";
import { ApiKeysTab } from "./components/ApiKeysTab";
import { SystemSettingTab } from "./components/SystemSettingTab";
import { ArchivePoliciesTab } from "./components/ArchivePoliciesTab";
import { AgentInstructionsTab } from "./components/AgentInstructionsTab";

export default function AdminSettingsPage() {
  const router = useRouter();
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);

  useEffect(() => {
    const token = getCookie(TOKEN_COOKIE);
    if (!token) { router.push("/login"); return; }
    const payload = decodeJwtPayload(token);
    if (!payload?.is_superadmin) {
      setIsAdmin(false);
    } else {
      setIsAdmin(true);
    }
  }, [router]);

  if (isAdmin === null) {
    return <div className="flex items-center justify-center h-[60vh] text-zinc-400">Loading...</div>;
  }

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center gap-4">
        <ShieldAlert className="h-16 w-16 text-red-400" />
        <h1 className="text-2xl font-bold text-white">Access Denied</h1>
        <p className="text-zinc-400 max-w-md">
          You do not have admin privileges. Please contact a system administrator if you believe this is an error.
        </p>
      </div>
    );
  }

  return (
    <div className="text-white py-6">
      <div className="container mx-auto py-6 max-w-5xl">
        <div className="animate-fade-slide-down mb-8">
          <h1 className="text-3xl font-bold tracking-tight">Admin Settings</h1>
          <p className="text-muted-foreground mt-1">Manage users, projects, API keys, and system configuration</p>
        </div>

        <Tabs defaultValue="users" className="w-full animate-fade-slide-down delay-1">
          <TabsList className="grid w-full grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 mb-8">
            <TabsTrigger value="users" className="flex items-center gap-2">
              <Users className="h-4 w-4" /> Users
            </TabsTrigger>
            <TabsTrigger value="projects" className="flex items-center gap-2">
              <FolderKanban className="h-4 w-4" /> Projects
            </TabsTrigger>
            <TabsTrigger value="api-keys" className="flex items-center gap-2">
              <Key className="h-4 w-4" /> API Keys
            </TabsTrigger>
            <TabsTrigger value="policies" className="flex items-center gap-2">
              <Clock className="h-4 w-4" /> Policies
            </TabsTrigger>
            <TabsTrigger value="agents" className="flex items-center gap-2">
              <Bot className="h-4 w-4" /> Agents
            </TabsTrigger>
            <TabsTrigger value="system" className="flex items-center gap-2">
              <Settings className="h-4 w-4" /> System Setting
            </TabsTrigger>
          </TabsList>

          <TabsContent value="users">
            <UsersTab />
          </TabsContent>
          <TabsContent value="projects">
            <ProjectsTab />
          </TabsContent>
          <TabsContent value="api-keys">
            <ApiKeysTab />
          </TabsContent>
          <TabsContent value="policies">
            <ArchivePoliciesTab />
          </TabsContent>
          <TabsContent value="agents">
            <AgentInstructionsTab />
          </TabsContent>
          <TabsContent value="system">
            <SystemSettingTab />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
