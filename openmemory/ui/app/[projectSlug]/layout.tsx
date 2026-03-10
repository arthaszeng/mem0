"use client";

import { use } from "react";
import { ProjectProvider } from "@/contexts/ProjectContext";

export default function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ projectSlug: string }>;
}) {
  const { projectSlug } = use(params);
  return (
    <ProjectProvider slug={projectSlug}>{children}</ProjectProvider>
  );
}
