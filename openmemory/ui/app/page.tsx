"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";

export default function RootPage() {
  const router = useRouter();
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/api/v1/projects")
      .then((res) => {
        const projects = res.data;
        if (projects.length > 0) {
          router.replace(`/${projects[0].slug}`);
        } else {
          setError("No projects found. Create one first.");
        }
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
