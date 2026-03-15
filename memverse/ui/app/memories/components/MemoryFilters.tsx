"use client";
import { useState } from "react";
import { Archive, Pause, Play, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { FiTrash2 } from "react-icons/fi";
import { useSelector, useDispatch } from "react-redux";
import { RootState } from "@/store/store";
import { clearSelection } from "@/store/memoriesSlice";
import { useMemoriesApi } from "@/hooks/useMemoriesApi";
import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useRouter, useSearchParams } from "next/navigation";
import { debounce } from "lodash";
import { useEffect, useRef } from "react";
import FilterComponent from "./FilterComponent";
import { clearFilters } from "@/store/filtersSlice";

export function MemoryFilters() {
  const dispatch = useDispatch();
  const selectedMemoryIds = useSelector(
    (state: RootState) => state.memories.selectedMemoryIds
  );
  const { deleteMemories, updateMemoryState } = useMemoriesApi();
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeFilters = useSelector((state: RootState) => state.filters.apps);
  const [actionLoading, setActionLoading] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);

  const handleDeleteSelected = async () => {
    setActionLoading(true);
    try {
      await deleteMemories(selectedMemoryIds);
      toast.success(`${selectedMemoryIds.length} memory(s) deleted`);
      dispatch(clearSelection());
    } catch {
      toast.error("Failed to delete memories");
    } finally {
      setActionLoading(false);
    }
  };

  const handleArchiveSelected = async () => {
    setActionLoading(true);
    try {
      await updateMemoryState(selectedMemoryIds, "archived");
      toast.success(`${selectedMemoryIds.length} memory(s) archived`);
    } catch {
      toast.error("Failed to archive memories");
    } finally {
      setActionLoading(false);
    }
  };

  const handlePauseSelected = async () => {
    setActionLoading(true);
    try {
      await updateMemoryState(selectedMemoryIds, "paused");
      toast.success(`${selectedMemoryIds.length} memory(s) paused`);
    } catch {
      toast.error("Failed to pause memories");
    } finally {
      setActionLoading(false);
    }
  };

  const handleResumeSelected = async () => {
    setActionLoading(true);
    try {
      await updateMemoryState(selectedMemoryIds, "active");
      toast.success(`${selectedMemoryIds.length} memory(s) resumed`);
    } catch {
      toast.error("Failed to resume memories");
    } finally {
      setActionLoading(false);
    }
  };

  // add debounce
  const handleSearch = debounce(async (query: string) => {
    router.push(`/memories?search=${query}`);
  }, 500);

  useEffect(() => {
    if (searchParams.get("search")) {
      if (inputRef.current) {
        inputRef.current.value = searchParams.get("search") || "";
        inputRef.current.focus();
      }
    }
  }, []);

  const handleClearAllFilters = () => {
    dispatch(clearFilters());
    const params = new URLSearchParams(searchParams.toString());
    params.set("page", "1");
    router.push(`?${params.toString()}`);
  };

  const hasActiveFilters =
    activeFilters.selectedApps.length > 0 ||
    activeFilters.selectedCategories.length > 0 ||
    activeFilters.selectedDomains.length > 0;

  return (
    <div className="flex flex-col md:flex-row gap-4 mb-4">
      <div className="relative flex-1">
        <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
        <Input
          ref={inputRef}
          placeholder="Search memories..."
          className="pl-8 bg-zinc-950 border-zinc-800 max-w-[500px]"
          onChange={(e) => handleSearch(e.target.value)}
        />
      </div>
      <div className="flex gap-2">
        <FilterComponent />
        {hasActiveFilters && (
          <Button
            variant="outline"
            className="bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
            onClick={handleClearAllFilters}
          >
            Clear Filters
          </Button>
        )}
        {selectedMemoryIds.length > 0 && (
          <>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  className="border-zinc-700/50 bg-zinc-900 hover:bg-zinc-800"
                  disabled={actionLoading}
                >
                  {actionLoading ? "Processing..." : "Actions"}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                className="bg-zinc-900 border-zinc-800"
              >
                <DropdownMenuItem onClick={handleArchiveSelected}>
                  <Archive className="mr-2 h-4 w-4" />
                  Archive Selected
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handlePauseSelected}>
                  <Pause className="mr-2 h-4 w-4" />
                  Pause Selected
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleResumeSelected}>
                  <Play className="mr-2 h-4 w-4" />
                  Resume Selected
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={handleDeleteSelected}
                  className="text-red-500"
                >
                  <FiTrash2 className="mr-2 h-4 w-4" />
                  Delete Selected
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        )}
      </div>
    </div>
  );
}
