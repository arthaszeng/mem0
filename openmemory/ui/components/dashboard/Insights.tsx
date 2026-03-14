"use client";

import React, { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { useProjectSlug } from "@/hooks/useProjectSlug";
import {
  Brain,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Minus,
  BarChart3,
  RefreshCw,
  Loader2,
} from "lucide-react";

interface UserProfile {
  summary: string;
  generated_at: string;
}

interface TopicTrend {
  topic: string;
  trend: "rising" | "stable" | "declining";
  recent_count: number;
  previous_count: number;
}

interface CategoryItem {
  name: string;
  count: number;
  pct: number;
}

interface DomainItem {
  name: string;
  count: number;
  pct: number;
}

interface KnowledgeCoverage {
  total_categories: number;
  total_domains: number;
  top_categories: CategoryItem[];
  sparse_categories: CategoryItem[];
  domain_coverage: DomainItem[];
}

interface InsightsData {
  user_profile: UserProfile | null;
  topic_trends: TopicTrend[];
  knowledge_coverage: KnowledgeCoverage;
}

const fetchInsights = async (
  projectSlug: string,
  refresh = false
): Promise<InsightsData> => {
  const params = new URLSearchParams({ project_slug: projectSlug });
  if (refresh) params.set("refresh", "true");
  const res = await api.get<InsightsData>(`/api/v1/memories/stats/insights?${params}`);
  return res.data;
};

const formatTimestamp = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

export function Insights() {
  const projectSlug = useProjectSlug();
  const [data, setData] = useState<InsightsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [profileRefreshing, setProfileRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    (refresh = false) => {
      if (!projectSlug) return;
      if (refresh) setProfileRefreshing(true);
      else setLoading(true);
      setError(null);
      fetchInsights(projectSlug, refresh)
        .then(setData)
        .catch(() => setError("Failed to load insights"))
        .finally(() => {
          setLoading(false);
          setProfileRefreshing(false);
        });
    },
    [projectSlug]
  );

  useEffect(() => {
    load();
  }, [load]);

  if (!projectSlug) return null;

  if (loading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="bg-zinc-900 rounded-lg border border-zinc-800 p-12 flex flex-col gap-4"
          >
            <div className="h-6 w-32 rounded animate-shimmer" />
            <div className="space-y-2">
              <div className="h-4 w-full rounded animate-shimmer" />
              <div className="h-4 w-4/5 rounded animate-shimmer" />
              <div className="h-4 w-3/4 rounded animate-shimmer" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-zinc-900 rounded-lg border border-zinc-800 p-12 flex items-center justify-center">
        <p className="text-zinc-400">{error}</p>
      </div>
    );
  }

  if (!data) return null;

  const { user_profile, topic_trends, knowledge_coverage } = data;
  const trends = topic_trends.slice(0, 10);
  const topCategories = knowledge_coverage.top_categories ?? [];
  const sparseCategories = knowledge_coverage.sparse_categories ?? [];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="bg-zinc-900 rounded-lg border border-zinc-800 overflow-hidden">
        <div className="bg-zinc-800 border-b border-zinc-800 p-4 flex items-center justify-between">
          <h2 className="text-white text-lg font-semibold flex items-center gap-2">
            <Brain className="h-5 w-5 text-violet-500" />
            Memory Profile
          </h2>
          <button
            onClick={() => load(true)}
            disabled={profileRefreshing}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
          >
            {profileRefreshing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Refresh
          </button>
        </div>
        <div className="p-4">
          {profileRefreshing && !user_profile ? (
            <div className="space-y-2">
              <div className="h-4 w-full rounded animate-shimmer" />
              <div className="h-4 w-4/5 rounded animate-shimmer" />
              <div className="h-4 w-3/4 rounded animate-shimmer" />
              <p className="text-zinc-500 text-sm mt-2">Generating...</p>
            </div>
          ) : user_profile?.summary ? (
            <>
              <p className="text-zinc-300 text-sm leading-relaxed">
                {user_profile.summary}
              </p>
              {user_profile.generated_at && (
                <p className="text-zinc-500 text-xs mt-3">
                  {formatTimestamp(user_profile.generated_at)}
                </p>
              )}
            </>
          ) : (
            <p className="text-zinc-500 text-sm">No profile summary yet</p>
          )}
        </div>
      </div>

      <div className="bg-zinc-900 rounded-lg border border-zinc-800 overflow-hidden">
        <div className="bg-zinc-800 border-b border-zinc-800 p-4">
          <h2 className="text-white text-lg font-semibold flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-violet-500" />
            Trending Topics
          </h2>
        </div>
        <div className="p-4">
          {trends.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {trends.map((t) => (
                <div
                  key={t.topic}
                  className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${
                    t.trend === "rising"
                      ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                      : t.trend === "declining"
                        ? "bg-red-500/20 text-red-400 border border-red-500/30"
                        : "bg-zinc-700/50 text-zinc-300 border border-zinc-600"
                  }`}
                >
                  {t.trend === "rising" && <TrendingUp className="h-4 w-4" />}
                  {t.trend === "declining" && (
                    <TrendingDown className="h-4 w-4" />
                  )}
                  {t.trend === "stable" && <Minus className="h-4 w-4" />}
                  <span>{t.topic}</span>
                  <span className="text-zinc-500 text-xs">
                    {t.recent_count} vs {t.previous_count}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-zinc-500 text-sm">No topic trends yet</p>
          )}
        </div>
      </div>

      <div className="bg-zinc-900 rounded-lg border border-zinc-800 overflow-hidden">
        <div className="bg-zinc-800 border-b border-zinc-800 p-4">
          <h2 className="text-white text-lg font-semibold flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-blue-500" />
            Knowledge Coverage
          </h2>
        </div>
        <div className="p-4 space-y-4">
          <div className="flex gap-4 text-sm">
            <span className="text-zinc-400">
              {knowledge_coverage.total_categories} categories
            </span>
            <span className="text-zinc-400">
              {knowledge_coverage.total_domains} domains
            </span>
          </div>
          {topCategories.length > 0 ? (
            <div className="space-y-3">
              {topCategories.map((c) => (
                <div key={c.name}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-zinc-300">{c.name}</span>
                    <span className="text-zinc-500">
                      {c.count} ({c.pct.toFixed(1)}%)
                    </span>
                  </div>
                  <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all"
                      style={{ width: `${Math.min(c.pct, 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-zinc-500 text-sm">No category data yet</p>
          )}
          {sparseCategories.length > 0 && (
            <div className="pt-2 border-t border-zinc-800">
              <p className="text-zinc-500 text-xs mb-2">Needs attention</p>
              <div className="flex flex-wrap gap-1.5">
                {sparseCategories.map((c) => (
                  <span
                    key={c.name}
                    className="inline-flex items-center px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 text-xs"
                  >
                    {c.name} ({c.count})
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
