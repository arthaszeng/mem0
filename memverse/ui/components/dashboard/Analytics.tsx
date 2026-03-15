"use client";

import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { useProjectSlug } from "@/hooks/useProjectSlug";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Loader2, BarChart3, TrendingUp, Archive, Layers } from "lucide-react";

interface MemoryGrowthPoint {
  date: string;
  count: number;
  cumulative: number;
}

interface CategoryItem {
  name: string;
  count: number;
}

interface RecentActivity {
  created_last_7d: number;
  created_last_30d: number;
  archived_count: number;
  total_active: number;
}

interface AnalyticsData {
  memory_growth: MemoryGrowthPoint[];
  category_distribution: CategoryItem[];
  recent_activity: RecentActivity;
}

const formatShortDate = (dateStr: string) => {
  const d = new Date(dateStr);
  return `${d.getMonth() + 1}/${d.getDate()}`;
};

export function Analytics() {
  const projectSlug = useProjectSlug();
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (projectSlug) params.set("project_slug", projectSlug);
    api
      .get<AnalyticsData>(`/api/v1/memories/stats/analytics?${params}`)
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load analytics"))
      .finally(() => setLoading(false));
  }, [projectSlug]);

  if (loading) {
    return (
      <div className="bg-zinc-900 rounded-lg border border-zinc-800 p-12 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-violet-500" />
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

  if (!data) {
    return null;
  }

  const { memory_growth, category_distribution, recent_activity } = data;
  const topCategories = category_distribution.slice(0, 10);
  const hasGrowthData = memory_growth.some((d) => d.count > 0);
  const hasCategoryData = topCategories.length > 0;

  return (
    <div className="bg-zinc-900 rounded-lg border border-zinc-800 overflow-hidden">
      <div className="bg-zinc-800 border-b border-zinc-800 p-4">
        <h2 className="text-white text-xl font-semibold">Memory Analytics</h2>
      </div>
      <div className="p-4 space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-zinc-800/50 rounded-lg border border-zinc-700 p-4">
            <div className="flex items-center gap-2 text-zinc-400 text-sm mb-1">
              <TrendingUp className="h-4 w-4" />
              Last 7 days
            </div>
            <p className="text-xl font-bold text-white">
              {recent_activity.created_last_7d}
            </p>
          </div>
          <div className="bg-zinc-800/50 rounded-lg border border-zinc-700 p-4">
            <div className="flex items-center gap-2 text-zinc-400 text-sm mb-1">
              <BarChart3 className="h-4 w-4" />
              Last 30 days
            </div>
            <p className="text-xl font-bold text-white">
              {recent_activity.created_last_30d}
            </p>
          </div>
          <div className="bg-zinc-800/50 rounded-lg border border-zinc-700 p-4">
            <div className="flex items-center gap-2 text-zinc-400 text-sm mb-1">
              <Archive className="h-4 w-4" />
              Archived
            </div>
            <p className="text-xl font-bold text-white">
              {recent_activity.archived_count}
            </p>
          </div>
          <div className="bg-zinc-800/50 rounded-lg border border-zinc-700 p-4">
            <div className="flex items-center gap-2 text-zinc-400 text-sm mb-1">
              <Layers className="h-4 w-4" />
              Total active
            </div>
            <p className="text-xl font-bold text-white">
              {recent_activity.total_active}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 min-h-[280px] bg-zinc-800/30 rounded-lg border border-zinc-700 p-4">
            <h3 className="text-zinc-300 text-sm font-medium mb-4">
              Memory Growth (30 days)
            </h3>
            {hasGrowthData ? (
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={memory_growth}>
                  <defs>
                    <linearGradient
                      id="growthGradient"
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop
                        offset="0%"
                        stopColor="#8b5cf6"
                        stopOpacity={0.4}
                      />
                      <stop
                        offset="100%"
                        stopColor="#8b5cf6"
                        stopOpacity={0}
                      />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="#3f3f46"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="date"
                    tickFormatter={formatShortDate}
                    stroke="#71717a"
                    fontSize={11}
                  />
                  <YAxis stroke="#71717a" fontSize={11} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#27272a",
                      border: "1px solid #3f3f46",
                      borderRadius: "6px",
                    }}
                    labelStyle={{ color: "#a1a1aa" }}
                    formatter={(value: number) => [value, ""]}
                    labelFormatter={formatShortDate}
                  />
                  <Area
                    type="monotone"
                    dataKey="count"
                    stroke="#8b5cf6"
                    strokeWidth={2}
                    fill="url(#growthGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[240px] flex items-center justify-center text-zinc-500 text-sm">
                No growth data in the last 30 days
              </div>
            )}
          </div>

          <div className="min-h-[280px] bg-zinc-800/30 rounded-lg border border-zinc-700 p-4">
            <h3 className="text-zinc-300 text-sm font-medium mb-4">
              Top Categories
            </h3>
            {hasCategoryData ? (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart
                  data={topCategories}
                  layout="vertical"
                  margin={{ top: 0, right: 0, left: 0, bottom: 0 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="#3f3f46"
                    horizontal={false}
                  />
                  <XAxis type="number" stroke="#71717a" fontSize={11} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={80}
                    stroke="#71717a"
                    fontSize={11}
                    tick={{ fill: "#a1a1aa" }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#27272a",
                      border: "1px solid #3f3f46",
                      borderRadius: "6px",
                    }}
                  />
                  <Bar
                    dataKey="count"
                    fill="#8b5cf6"
                    radius={[0, 4, 4, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[240px] flex items-center justify-center text-zinc-500 text-sm">
                No categories yet
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
