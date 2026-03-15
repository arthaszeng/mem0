"use client";

import React, { useState, useMemo } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Check,
  Loader2,
  ChevronRight,
  Sparkles,
  Shield,
  Brain,
  Search,
  GitBranch,
  Layers,
  Wrench,
  Zap,
  Clock,
  Globe,
  Link2,
  MessagesSquare,
  LucideIcon,
  CircleDot,
} from "lucide-react";
import { parseRoadmap, ReleaseStatus, ReleaseData, FeatureData } from "@/lib/parseRoadmap";
import roadmapRaw from "@/data/roadmap.md";
import "@/styles/release-tree.css";

// ---------------------------------------------------------------------------
// Icon registry — maps markdown icon names to Lucide components
// ---------------------------------------------------------------------------

const ICON_MAP: Record<string, LucideIcon> = {
  layers: Layers,
  "link-2": Link2,
  sparkles: Sparkles,
  globe: Globe,
  "messages-square": MessagesSquare,
  shield: Shield,
  brain: Brain,
  clock: Clock,
  search: Search,
  "git-branch": GitBranch,
  wrench: Wrench,
  zap: Zap,
};

function resolveIcon(name: string): React.ReactNode {
  const Icon = ICON_MAP[name] ?? CircleDot;
  return <Icon className="w-4 h-4" />;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatusIcon({ status }: { status: ReleaseStatus }) {
  if (status === "completed") return <Check className="w-3 h-3 text-emerald-400" />;
  if (status === "in_progress") return <Loader2 className="w-3 h-3 text-purple-400 animate-spin" />;
  return null;
}

function StatusBadge({ status, date }: { status: ReleaseStatus; date: string }) {
  const base = "text-[11px] font-medium px-2 py-0.5 rounded-full";
  if (status === "completed")
    return <span className={`${base} bg-emerald-500/15 text-emerald-400 border border-emerald-500/25`}>{date}</span>;
  if (status === "in_progress")
    return <span className={`${base} bg-purple-500/15 text-purple-400 border border-purple-500/25`}>{date}</span>;
  return <span className={`${base} bg-zinc-800 text-zinc-500 border border-zinc-700`}>{date}</span>;
}

function FeatureList({ features }: { features: FeatureData[] }) {
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {features.map((f) => (
        <span
          key={f.name}
          title={f.description}
          className={`rt-feature-chip inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border cursor-default
            ${f.status === "completed"
              ? "border-emerald-500/20 text-emerald-300/80 bg-emerald-500/5"
              : f.status === "in_progress"
              ? "border-purple-500/20 text-purple-300/80 bg-purple-500/5"
              : "border-zinc-700/50 text-zinc-500 bg-zinc-800/30"
            }`}
        >
          <StatusIcon status={f.status} />
          {f.name}
        </span>
      ))}
    </div>
  );
}

function TimelineNode({ status }: { status: ReleaseStatus }) {
  return (
    <div className="relative flex items-center justify-center flex-shrink-0">
      <div className={`w-3 h-3 rounded-full rt-node-${status}`} />
    </div>
  );
}

function ConnectorLine({ status }: { status: ReleaseStatus }) {
  return <div className={`w-0.5 flex-1 min-h-[20px] rt-line-${status}`} />;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ReleaseTree() {
  const releases = useMemo(() => parseRoadmap(roadmapRaw), []);

  const [openVersions, setOpenVersions] = useState<Set<string>>(
    () => new Set(releases.filter((r) => r.status !== "upcoming").map((r) => r.version))
  );

  const toggle = (version: string) => {
    setOpenVersions((prev) => {
      const next = new Set(prev);
      if (next.has(version)) next.delete(version);
      else next.add(version);
      return next;
    });
  };

  const counts = {
    completed: releases.filter((r) => r.status === "completed").length,
    in_progress: releases.filter((r) => r.status === "in_progress").length,
    upcoming: releases.filter((r) => r.status === "upcoming").length,
  };

  return (
    <div className="w-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold text-white">Release Roadmap</h2>
          <Brain className="w-5 h-5 text-purple-400 opacity-60" />
        </div>
        <div className="flex items-center gap-3 text-[12px]">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
            <span className="text-zinc-400">{counts.completed} completed</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-purple-500 inline-block animate-pulse" />
            <span className="text-zinc-400">{counts.in_progress} in progress</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-zinc-600 inline-block" />
            <span className="text-zinc-400">{counts.upcoming} upcoming</span>
          </span>
        </div>
      </div>

      {/* Scrollable timeline */}
      <div className="rt-scroll-container rounded-xl border border-zinc-800 bg-zinc-900/60 backdrop-blur-sm">
        <ScrollArea className="h-[560px]">
          <div className="p-6 pr-4">
            {releases.map((release, idx) => {
              const isLast = idx === releases.length - 1;
              const isOpen = openVersions.has(release.version);

              return (
                <div
                  key={release.version}
                  className="rt-item-enter flex gap-4"
                  style={{ animationDelay: `${idx * 70}ms` }}
                >
                  {/* Left rail: node + connector */}
                  <div className="flex flex-col items-center pt-1">
                    <TimelineNode status={release.status} />
                    {!isLast && <ConnectorLine status={release.status} />}
                  </div>

                  {/* Right: card */}
                  <div className={`flex-1 mb-5`}>
                    <Collapsible open={isOpen} onOpenChange={() => toggle(release.version)}>
                      <CollapsibleTrigger asChild>
                        <button
                          className={`w-full text-left rounded-lg px-4 py-3 transition-all duration-200
                            bg-zinc-900 border border-zinc-800 hover:border-zinc-700
                            hover:-translate-y-0.5 cursor-pointer group
                            rt-card-${release.status}`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex items-center gap-2.5 min-w-0">
                              <span
                                className={`rt-version-badge inline-flex items-center gap-1 text-[11px] font-mono font-bold px-2 py-0.5 rounded
                                  ${release.status === "completed"
                                    ? "bg-emerald-500/10 text-emerald-400"
                                    : release.status === "in_progress"
                                    ? "bg-purple-500/10 text-purple-400"
                                    : "bg-zinc-800 text-zinc-500"
                                  }`}
                              >
                                {resolveIcon(release.icon)}
                                {release.version}
                              </span>
                              <span className="text-sm font-medium text-white truncate">
                                {release.title}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 flex-shrink-0">
                              <StatusBadge status={release.status} date={release.date} />
                              <ChevronRight
                                className={`w-4 h-4 text-zinc-500 transition-transform duration-200
                                  ${isOpen ? "rotate-90" : ""} group-hover:text-zinc-300`}
                              />
                            </div>
                          </div>
                          <p className={`text-[12px] mt-1.5 leading-relaxed
                            ${release.status === "upcoming" ? "text-zinc-600" : "text-zinc-400"}`}>
                            {release.description}
                          </p>
                        </button>
                      </CollapsibleTrigger>

                      <CollapsibleContent className="rt-collapsible-content">
                        <div className="px-4 pb-1 pt-0.5">
                          <FeatureList features={release.features} />
                        </div>
                      </CollapsibleContent>
                    </Collapsible>
                  </div>
                </div>
              );
            })}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}

export default ReleaseTree;
