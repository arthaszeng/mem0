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
  concept: "#ec4899",
  place: "#06b6d4",
  location: "#06b6d4",
  unknown: "#71717a",
};

interface GraphNode {
  id: string;
  type: string;
  memory_count: number;
  x?: number;
  y?: number;
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

const GRAPH_HEIGHT = 360;

export function GraphView() {
  const projectSlug = useProjectSlug();
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: GRAPH_HEIGHT });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width } = entries[0].contentRect;
      if (width > 0) setDimensions({ width, height: GRAPH_HEIGHT });
    });
    ro.observe(el);
    setDimensions({ width: el.clientWidth || 800, height: GRAPH_HEIGHT });
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ limit: "100" });
    if (projectSlug) params.set("project_slug", projectSlug);
    api
      .get<GraphData>(`/api/v1/entities/graph?${params}`)
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load graph"))
      .finally(() => setLoading(false));
  }, [projectSlug]);

  const graphData = React.useMemo(() => {
    if (!data?.nodes?.length) return null;
    const nodeIds = new Set(data.nodes.map((n) => n.id));
    return {
      nodes: data.nodes,
      links: data.edges
        .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
        .map((e) => ({ source: e.source, target: e.target, relation: e.relation })),
    };
  }, [data]);

  const nodeCanvasObject = useCallback(
    (node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      const color = TYPE_COLORS[node.type?.toLowerCase()] ?? TYPE_COLORS.unknown;
      const isHovered = hoveredNode?.id === node.id;
      const isSelected = selectedNode?.id === node.id;
      const radius = isHovered || isSelected ? 6 : 4;

      ctx.beginPath();
      ctx.arc(x, y, radius, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();

      if (isHovered || isSelected) {
        ctx.strokeStyle = "rgba(255,255,255,0.6)";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      const showLabel = isHovered || isSelected || globalScale > 1.5;
      if (showLabel) {
        const label = node.id;
        const fontSize = Math.max(12 / globalScale, 3);
        ctx.font = `${fontSize}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";

        const textWidth = ctx.measureText(label).width;
        const padding = 2 / globalScale;
        ctx.fillStyle = "rgba(0,0,0,0.7)";
        ctx.fillRect(
          x - textWidth / 2 - padding,
          y + radius + 2 / globalScale,
          textWidth + padding * 2,
          fontSize + padding * 2
        );

        ctx.fillStyle = "#e4e4e7";
        ctx.fillText(label, x, y + radius + 2 / globalScale + padding);
      }
    },
    [hoveredNode, selectedNode]
  );

  const handleNodeHover = useCallback((node: GraphNode | null) => {
    setHoveredNode(node);
  }, []);

  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode((prev) => (prev?.id === node.id ? null : node));
  }, []);

  const handleBackgroundClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  const headerContent = (
    <div className="bg-zinc-800 border-b border-zinc-800 rounded-t-lg px-4 py-3 flex items-center justify-between">
      <div className="text-white text-lg font-semibold flex items-center gap-2">
        <Network className="w-5 h-5" />
        Knowledge Graph
      </div>
      {(selectedNode || hoveredNode) && (
        <div className="text-sm text-zinc-300 truncate max-w-[50%]">
          {(selectedNode || hoveredNode)!.id} · {(selectedNode || hoveredNode)!.memory_count} memories
        </div>
      )}
    </div>
  );

  if (loading) {
    return (
      <div className="bg-zinc-900 rounded-lg border border-zinc-800">
        {headerContent}
        <div className="flex items-center justify-center h-64 text-zinc-400">
          <Loader2 className="w-8 h-8 animate-spin" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-zinc-900 rounded-lg border border-zinc-800">
        {headerContent}
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
        {headerContent}
        <div className="flex items-center justify-center h-64 text-zinc-500">
          No entities yet
        </div>
      </div>
    );
  }

  return (
    <div className="bg-zinc-900 rounded-lg border border-zinc-800">
      {headerContent}
      <div className="overflow-hidden" style={{ height: GRAPH_HEIGHT }} ref={containerRef}>
        <ForceGraph2D
          graphData={graphData}
          width={dimensions.width}
          height={dimensions.height}
          nodeCanvasObject={nodeCanvasObject}
          nodeLabel=""
          linkLabel={(link: { relation?: string }) => link.relation ?? ""}
          onNodeHover={handleNodeHover}
          onNodeClick={handleNodeClick}
          onBackgroundClick={handleBackgroundClick}
          backgroundColor="rgb(24 24 27)"
          linkColor={() => "rgba(113, 113, 122, 0.4)"}
          nodeRelSize={4}
          cooldownTicks={100}
          enableZoomInteraction={true}
          enablePanInteraction={true}
        />
      </div>
      {data && (
        <div className="px-4 py-2 border-t border-zinc-800 flex gap-3 flex-wrap text-xs text-zinc-500">
          {Object.entries(TYPE_COLORS)
            .filter(([k]) => k !== "unknown" && k !== "location")
            .map(([type, color]) => (
              <span key={type} className="flex items-center gap-1">
                <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                {type}
              </span>
            ))}
          <span className="ml-auto">{data.nodes.length} entities · {data.edges.length} relations</span>
        </div>
      )}
    </div>
  );
}
