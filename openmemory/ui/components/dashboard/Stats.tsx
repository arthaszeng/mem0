import React, { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { RootState } from "@/store/store";
import { useStats } from "@/hooks/useStats";
import Image from "next/image";
import { constants } from "@/components/shared/source-app";
import api from "@/lib/api";
import { useProjectSlug } from "@/hooks/useProjectSlug";

const TYPE_COLORS: Record<string, string> = {
  fact: "bg-blue-500",
  preference: "bg-purple-500",
  session: "bg-yellow-500",
  episodic: "bg-green-500",
  untyped: "bg-zinc-600",
};

const Stats = () => {
  const totalMemories = useSelector(
    (state: RootState) => state.profile.totalMemories
  );
  const totalApps = useSelector((state: RootState) => state.profile.totalApps);
  const apps = useSelector((state: RootState) => state.profile.apps).slice(
    0,
    4
  );
  const { fetchStats } = useStats();
  const projectSlug = useProjectSlug();
  const [typeDistribution, setTypeDistribution] = useState<Record<string, number>>({});

  useEffect(() => {
    fetchStats();
    const params = projectSlug ? `?project_slug=${projectSlug}` : "";
    api.get(`/api/v1/memories/stats/types${params}`)
      .then((res) => setTypeDistribution(res.data.distribution || {}))
      .catch(() => {});
  }, []);

  const typeTotal = Object.values(typeDistribution).reduce((a, b) => a + b, 0);

  return (
    <div className="bg-zinc-900 rounded-lg border border-zinc-800">
      <div className="bg-zinc-800 border-b border-zinc-800 rounded-t-lg p-4">
        <div className="text-white text-xl font-semibold">Memories Stats</div>
      </div>
      <div className="space-y-3 p-4">
        <div>
          <p className="text-zinc-400">Total Memories</p>
          <h3 className="text-lg font-bold text-white">
            {totalMemories} Memories
          </h3>
        </div>
        <div>
          <p className="text-zinc-400">Total Apps Connected</p>
          <div className="flex flex-col items-start gap-1 mt-2">
            <div className="flex -space-x-2">
              {apps.map((app) => (
                <div
                  key={app.id}
                  className={`h-8 w-8 rounded-full bg-primary flex items-center justify-center text-xs`}
                >
                  <div>
                    <div className="w-7 h-7 rounded-full bg-zinc-700 flex items-center justify-center overflow-hidden">
                      <Image
                        src={
                          constants[app.name as keyof typeof constants]
                            ?.iconImage || ""
                        }
                        alt={
                          constants[app.name as keyof typeof constants]?.name
                        }
                        width={32}
                        height={32}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <h3 className="text-lg font-bold text-white">{totalApps} Apps</h3>
          </div>
        </div>
        {typeTotal > 0 && (
          <div>
            <p className="text-zinc-400 mb-2">Memory Types</p>
            <div className="flex w-full h-3 rounded-full overflow-hidden mb-2">
              {Object.entries(typeDistribution).map(([type, count]) => (
                <div
                  key={type}
                  className={`${TYPE_COLORS[type] || "bg-zinc-600"} transition-all`}
                  style={{ width: `${(count / typeTotal) * 100}%` }}
                  title={`${type}: ${count}`}
                />
              ))}
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {Object.entries(typeDistribution).map(([type, count]) => (
                <div key={type} className="flex items-center gap-1">
                  <span className={`inline-block w-2 h-2 rounded-full ${TYPE_COLORS[type] || "bg-zinc-600"}`} />
                  <span className="text-xs text-zinc-400">{type}</span>
                  <span className="text-xs text-zinc-500">{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Stats;
