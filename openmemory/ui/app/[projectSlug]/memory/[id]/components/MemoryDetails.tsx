"use client";
import { useMemoriesApi } from "@/hooks/useMemoriesApi";
import { MemoryActions } from "./MemoryActions";
import { ArrowLeft, Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";
import { AccessLog } from "./AccessLog";
import Image from "next/image";
import Categories from "@/components/shared/categories";
import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { RootState } from "@/store/store";
import { constants } from "@/components/shared/source-app";
import { RelatedMemories } from "./RelatedMemories";

interface MemoryDetailsProps {
  memory_id: string;
}

export function MemoryDetails({ memory_id }: MemoryDetailsProps) {
  const router = useRouter();
  const { fetchMemoryById, hasUpdates } = useMemoriesApi();
  const memory = useSelector(
    (state: RootState) => state.memories.selectedMemory
  );
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (memory?.id) {
      await navigator.clipboard.writeText(memory.id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  useEffect(() => {
    fetchMemoryById(memory_id);
  }, []);

  return (
    <div className="container mx-auto py-6 px-4">
      <Button
        variant="ghost"
        className="mb-4 text-zinc-400 hover:text-white"
        onClick={() => router.back()}
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Memories
      </Button>
      <div className="flex flex-col lg:flex-row gap-4 w-full">
        <div className="rounded-lg w-full lg:w-2/3 border h-fit pb-2 border-zinc-800 bg-zinc-900 overflow-hidden">
          <div className="">
            <div className="flex px-6 py-3 justify-between items-center mb-6 bg-zinc-800 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <h1 className="font-semibold text-white">
                  Memory{" "}
                  <span className="ml-1 text-zinc-400 text-sm font-normal">
                    #{memory?.id?.slice(0, 6)}
                  </span>
                </h1>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-4 w-4 text-zinc-400 hover:text-white -ml-[5px] mt-1"
                  onClick={handleCopy}
                >
                  {copied ? (
                    <Check className="h-3 w-3" />
                  ) : (
                    <Copy className="h-3 w-3" />
                  )}
                </Button>
              </div>
              <MemoryActions
                memoryId={memory?.id || ""}
                memoryContent={memory?.text || ""}
                memoryState={memory?.state || ""}
              />
            </div>

            <div className="px-6 py-2">
              <div className="border-l-2 border-primary pl-4 mb-6">
                <p
                  className={`${
                    memory?.state === "archived" || memory?.state === "paused"
                      ? "text-zinc-400"
                      : "text-white"
                  }`}
                >
                  {memory?.text}
                </p>
              </div>

              <div className="mt-6 pt-4 border-t border-zinc-800">
                <div className="flex justify-between items-center">
                  <div className="">
                    <Categories
                      categories={memory?.categories || []}
                      isPaused={
                        memory?.state === "archived" ||
                        memory?.state === "paused"
                      }
                    />
                  </div>
                  <div className="flex items-center gap-2 justify-end flex-shrink-0 flex-wrap">
                    {(memory as any)?.memory_type && (
                      <div className="flex items-center gap-1 bg-zinc-700 px-3 py-1 rounded-lg">
                        <span className="text-sm text-zinc-400">Type:</span>
                        <span className={`text-sm font-semibold ${
                          {
                            fact: "text-blue-400",
                            preference: "text-purple-400",
                            session: "text-yellow-400",
                            episodic: "text-green-400",
                          }[(memory as any).memory_type] || "text-zinc-100"
                        }`}>{(memory as any).memory_type}</span>
                      </div>
                    )}
                    {(memory as any)?.agent_id && (
                      <div className="flex items-center gap-1 bg-zinc-700 px-3 py-1 rounded-lg">
                        <span className="text-sm text-zinc-400">Agent:</span>
                        <p className="text-sm text-zinc-100 font-semibold">{(memory as any).agent_id}</p>
                      </div>
                    )}
                    {(memory as any)?.run_id && (
                      <div className="flex items-center gap-1 bg-zinc-700 px-3 py-1 rounded-lg">
                        <span className="text-sm text-zinc-400">Run:</span>
                        <p className="text-sm text-zinc-100 font-semibold">{(memory as any).run_id}</p>
                      </div>
                    )}
                    {(memory as any)?.expires_at && (
                      <div className="flex items-center gap-1 bg-zinc-700 px-3 py-1 rounded-lg">
                        <span className="text-sm text-zinc-400">Expires:</span>
                        <p className="text-sm text-zinc-100 font-semibold">
                          {new Date((memory as any).expires_at).toLocaleDateString()}
                        </p>
                      </div>
                    )}
                    {memory?.created_by && (
                      <div className="flex items-center gap-1 bg-zinc-700 px-3 py-1 rounded-lg">
                        <span className="text-sm text-zinc-400">User:</span>
                        <p className="text-sm text-zinc-100 font-semibold">{memory.created_by}</p>
                      </div>
                    )}
                    <div className="flex items-center gap-1 bg-zinc-700 px-3 py-1 rounded-lg">
                      <span className="text-sm text-zinc-400">App:</span>
                      <div className="w-4 h-4 rounded-full bg-zinc-700 flex items-center justify-center overflow-hidden">
                        <Image
                          src={
                            constants[
                              memory?.app_name as keyof typeof constants
                            ]?.iconImage || ""
                          }
                          alt="App"
                          width={24}
                          height={24}
                        />
                      </div>
                      <p className="text-sm text-zinc-100 font-semibold">
                        {
                          constants[
                            memory?.app_name as keyof typeof constants
                          ]?.name
                        }
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="w-full lg:w-1/3 flex flex-col gap-4">
          <AccessLog memoryId={memory?.id || ""} />
          <RelatedMemories memoryId={memory?.id || ""} />
        </div>
      </div>
    </div>
  );
}
