"use client";

import React, { useEffect, useState, useCallback, useRef } from "react";
import api from "@/lib/api";
import { useProjectSlug } from "@/hooks/useProjectSlug";
import { Loader2, Network, AlertCircle } from "lucide-react";

import ForceGraph2D from "react-force-graph-2d";

const TYPE_COLORS: Record<string, string> = {
  person: "#3b82f6",
  project: "#22c55e",
  technology: "#a855f7",
  organization: "#f59e0b",
  location: "#06b6d4",
  unknown: "#71717a",
};

interface GraphNode {
  id: string;
  type: string;
  memory_count: number;
}

interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  memory_id: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export function GraphView() {
  const projectSlug = useProjectSlug();
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ limit: "50" });
    if (projectSlug) params.set("project_slug", projectSlug);
    api
      .get<GraphData>(`/api/v1/entities/graph?${params}`)
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load graph"))
      .finally(() => setLoading(false));
  }, [projectSlug]);

  const graphData = React.useMemo(() => {
    if (!data?.nodes?.length) return null;
    return {
      nodes: data.nodes,
      links: data.edges.map((e) => ({
        source: e.source,
        target: e.target,
        relation: e.relation,
      })),
    };
  }, [data]);

  const nodeColor = useCallback((node: GraphNode) => {
    return TYPE_COLORS[node.type?.toLowerCase()] ?? TYPE_COLORS.unknown;
  }, []);

  const nodeLabel = useCallback((node: GraphNode) => {
    return `${node.id} (${node.memory_count})`;
  }, []);

  const linkLabel = useCallback((link: { relation?: string }) => link.relation ?? "", []);

  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode(node);
  }, []);

  const handleBackgroundClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  if (loading) {
    return (
      <div className="bg-zinc-900 rounded-lg border border-zinc-800">
        <div className="bg-zinc-800 border-b border-zinc-800 rounded-t-lg p-4">
          <div className="text-white text-xl font-semibold flex items-center gap-2">
            <Network className="w-5 h-5" />
            Knowledge Graph
          </div>
        </div>
        <div className="flex items-center justify-center h-64 text-zinc-400">
          <Loader2 className="w-8 h-8 animate-spin" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-zinc-900 rounded-lg border border-zinc-800">
        <div className="bg-zinc-800 border-b border-zinc-800 rounded-t-lg p-4">
          <div className="text-white text-xl font-semibold flex items-center gap-2">
            <Network className="w-5 h-5" />
            Knowledge Graph
          </div>
        </div>
        <div className="flex items-center justify-center h-64 text-zinc-400 gap-2">
          <AlertCircle className="w-6 h-6" />
          {error}
        </div>
      </div>
    );
  }

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div className="bg-zinc-900 rounded-lg border border-zinc-800">
        <div className="bg-zinc-800 border-b border-zinc-800 rounded-t-lg p-4">
          <div className="text-white text-xl font-semibold flex items-center gap-2">
            <Network className="w-5 h-5" />
            Knowledge Graph
          </div>
        </div>
        <div className="flex items-center justify-center h-64 text-zinc-500">
          No entities yet
        </div>
      </div>
    );
  }

  return (
    <div className="bg-zinc-900 rounded-lg border border-zinc-800" ref={containerRef}>
      <div className="bg-zinc-800 border-b border-zinc-800 rounded-t-lg p-4 flex items-center justify-between">
        <div className="text-white text-xl font-semibold flex items-center gap-2">
          <Network className="w-5 h-5" />
          Knowledge Graph
        </div>
        {selectedNode && (
          <div className="text-sm text-zinc-300">
            {selectedNode.id} · {selectedNode.memory_count} memories
          </div>
        )}
      </div>
      <div className="relative h-80 w-full">
        <ForceGraph2D
          graphData={graphData}
          nodeColor={nodeColor}
          nodeLabel={nodeLabel}
          linkLabel={linkLabel}
          onNodeClick={handleNodeClick}
          onBackgroundClick={handleBackgroundClick}
          backgroundColor="rgb(24 24 27)"
          linkColor={() => "rgb(63 63 70)"}
          nodeRelSize={6}
          cooldownTicks={100}
        />
      </div>
    </div>
  );
}
