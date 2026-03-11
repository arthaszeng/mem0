"use client";

import { Install } from "@/components/dashboard/Install";
import Stats from "@/components/dashboard/Stats";
import { MemoryFilters } from "@/app/[projectSlug]/memories/components/MemoryFilters";
import { MemoriesSection } from "@/app/[projectSlug]/memories/components/MemoriesSection";
import "@/styles/animation.css";

export default function ProjectDashboardPage() {
  return (
    <div className="text-white py-6">
      <div className="container">
        <div className="w-full mx-auto space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 animate-fade-slide-down">
              <Install />
            </div>
            <div className="lg:col-span-1 animate-fade-slide-down delay-1">
              <Stats />
            </div>
          </div>
          <div>
            <div className="animate-fade-slide-down delay-2">
              <MemoryFilters />
            </div>
            <div className="animate-fade-slide-down delay-3">
              <MemoriesSection />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
