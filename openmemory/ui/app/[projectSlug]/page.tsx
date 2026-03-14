"use client";

import dynamic from "next/dynamic";
import { Install } from "@/components/dashboard/Install";
import Stats from "@/components/dashboard/Stats";
import { ReleaseTree } from "@/components/dashboard/ReleaseTree";
import "@/styles/animation.css";

const GraphView = dynamic(() => import("@/components/dashboard/GraphView").then((m) => ({ default: m.GraphView })), {
  ssr: false,
});

const Analytics = dynamic(
  () => import("@/components/dashboard/Analytics").then((m) => ({ default: m.Analytics })),
  { ssr: false }
);

const Insights = dynamic(
  () => import("@/components/dashboard/Insights").then((m) => ({ default: m.Insights })),
  { ssr: false }
);

export default function ProjectDashboardPage() {
  return (
    <div className="text-white py-6">
      <div className="container">
        <div className="w-full mx-auto space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <div className="lg:col-span-3 animate-fade-slide-down">
              <Install />
            </div>
            <div className="lg:col-span-1 animate-fade-slide-down delay-1">
              <Stats />
            </div>
          </div>
          <div className="animate-fade-slide-down delay-1">
            <Analytics />
          </div>
          <div className="animate-fade-slide-down delay-2">
            <Insights />
          </div>
          <div className="animate-fade-slide-down delay-3">
            <GraphView />
          </div>
          <div className="animate-fade-slide-down delay-4">
            <ReleaseTree />
          </div>
        </div>
      </div>
    </div>
  );
}
