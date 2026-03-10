"use client";

import { use } from "react";
import { ProjectProvider, useProject } from "@/contexts/ProjectContext";
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";

function ProjectGuard({ children }: { children: React.ReactNode }) {
  const { notFound, loading, projectSlug } = useProject();

  if (loading) return null;

  if (notFound) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center gap-4">
        <AlertCircle className="h-16 w-16 text-yellow-400" />
        <h1 className="text-2xl font-bold text-white">Project Not Found</h1>
        <p className="text-zinc-400 max-w-md">
          The project <span className="font-mono text-white">{projectSlug}</span> does not exist or you don&apos;t have access to it.
          It may have been deleted.
        </p>
        <Link href="/">
          <Button variant="outline">Go to Dashboard</Button>
        </Link>
      </div>
    );
  }

  return <>{children}</>;
}

export default function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ projectSlug: string }>;
}) {
  const { projectSlug } = use(params);
  return (
    <ProjectProvider slug={projectSlug}>
      <ProjectGuard>{children}</ProjectGuard>
    </ProjectProvider>
  );
}
