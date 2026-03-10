"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "@/lib/api";

interface ProjectInfo {
  id: string;
  name: string;
  slug: string;
  description: string | null;
}

interface ProjectContextValue {
  projectSlug: string;
  project: ProjectInfo | null;
  projects: ProjectInfo[];
  loading: boolean;
  notFound: boolean;
  refreshProjects: () => Promise<void>;
}

const ProjectContext = createContext<ProjectContextValue>({
  projectSlug: "",
  project: null,
  projects: [],
  loading: true,
  notFound: false,
  refreshProjects: async () => {},
});

export function useProject() {
  return useContext(ProjectContext);
}

export function ProjectProvider({
  slug,
  children,
}: {
  slug: string;
  children: React.ReactNode;
}) {
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const refreshProjects = useCallback(async () => {
    try {
      const res = await api.get("/api/v1/projects");
      setProjects(res.data);
    } catch {
      // ignore — auth may not be ready yet
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshProjects();
  }, [refreshProjects]);

  const project = projects.find((p) => p.slug === slug) ?? null;
  const notFound = !loading && slug !== "" && project === null;

  return (
    <ProjectContext.Provider
      value={{ projectSlug: slug, project, projects, loading, notFound, refreshProjects }}
    >
      {children}
    </ProjectContext.Provider>
  );
}
