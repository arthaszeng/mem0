"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";

const LAST_PROJECT_KEY = "om_last_project";

export default function RootPage() {
  const router = useRouter();
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/api/v1/projects")
      .then((res) => {
        const projects = res.data;
        if (projects.length === 0) {
          setError("No projects found. Create one first.");
          return;
        }
        const saved = localStorage.getItem(LAST_PROJECT_KEY);
        const match = saved && projects.find((p: any) => p.slug === saved);
        router.replace(`/${match ? match.slug : projects[0].slug}`);
      })
      .catch(() => setError("Failed to load projects"));
  }, [router]);

  if (error) {
    return (
      <div className="flex items-center justify-center h-[60vh] text-zinc-400">
        <p>{error}</p>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center h-[60vh]">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
    </div>
  );
}
