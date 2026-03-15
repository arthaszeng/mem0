import { useState, useEffect, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Category, Client } from "@/components/types";
import { MemoryTable } from "./MemoryTable";
import { MemoryPagination } from "./MemoryPagination";
import { CreateMemoryDialog } from "./CreateMemoryDialog";
import { PageSizeSelector } from "./PageSizeSelector";
import { useMemoriesApi } from "@/hooks/useMemoriesApi";
import { useRouter, useSearchParams } from "next/navigation";
import { MemoryTableSkeleton } from "@/skeleton/MemoryTableSkeleton";
import { useSelector, useDispatch } from "react-redux";
import { RootState } from "@/store/store";
import { clearSelection } from "@/store/memoriesSlice";
import { Archive, Pause, Trash2 } from "lucide-react";
import { toast } from "sonner";

export function MemoriesSection() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const dispatch = useDispatch();
  const { fetchMemories, deleteMemories, updateMemoryState } = useMemoriesApi();
  const selectedMemoryIds = useSelector((state: RootState) => state.memories.selectedMemoryIds);
  const [memories, setMemories] = useState<any[]>([]);
  const [totalItems, setTotalItems] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [isLoading, setIsLoading] = useState(true);

  const currentPage = Number(searchParams.get("page")) || 1;
  const itemsPerPage = Number(searchParams.get("size")) || 10;
  const [selectedCategory, setSelectedCategory] = useState<Category | "all">(
    "all"
  );
  const [selectedClient, setSelectedClient] = useState<Client | "all">("all");

  const filters = useSelector((state: RootState) => state.filters.apps);
  const categoryItems = useSelector((state: RootState) => state.filters.categories.items);
  const filterKey = useMemo(() => JSON.stringify(filters), [filters]);

  useEffect(() => {
    const loadMemories = async () => {
      setIsLoading(true);
      try {
        const searchQuery = searchParams.get("search") || "";

        const categoryIds = categoryItems
          .filter(cat => filters.selectedCategories.includes(cat.name))
          .map(cat => cat.id);

        const result = await fetchMemories(
          searchQuery,
          currentPage,
          itemsPerPage,
          {
            apps: filters.selectedApps.length > 0 ? filters.selectedApps : undefined,
            categories: categoryIds.length > 0 ? categoryIds : undefined,
            domains: filters.selectedDomains.length > 0 ? filters.selectedDomains : undefined,
            sortColumn: filters.sortColumn,
            sortDirection: filters.sortDirection,
            showArchived: filters.showArchived,
          }
        );
        setMemories(result.memories);
        setTotalItems(result.total);
        setTotalPages(result.pages);
      } catch (error) {
        console.error("Failed to fetch memories:", error);
      }
      setIsLoading(false);
    };

    loadMemories();
  }, [currentPage, itemsPerPage, fetchMemories, searchParams, filterKey]);

  const setCurrentPage = (page: number) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("page", page.toString());
    params.set("size", itemsPerPage.toString());
    router.push(`?${params.toString()}`);
  };

  const handlePageSizeChange = (size: number) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("page", "1"); // Reset to page 1 when changing page size
    params.set("size", size.toString());
    router.push(`?${params.toString()}`);
  };

  const refreshMemories = async () => {
    try {
      const searchQuery = searchParams.get("search") || "";
      const categoryIds = categoryItems
        .filter(cat => filters.selectedCategories.includes(cat.name))
        .map(cat => cat.id);
      const result = await fetchMemories(
        searchQuery,
        currentPage,
        itemsPerPage,
        {
          apps: filters.selectedApps.length > 0 ? filters.selectedApps : undefined,
          categories: categoryIds.length > 0 ? categoryIds : undefined,
          domains: filters.selectedDomains.length > 0 ? filters.selectedDomains : undefined,
          sortColumn: filters.sortColumn,
          sortDirection: filters.sortDirection,
          showArchived: filters.showArchived,
        }
      );
      setMemories(result.memories);
      setTotalItems(result.total);
      setTotalPages(result.pages);
    } catch (error) {
      console.error("Failed to fetch memories:", error);
    }
  };

  const handleBulkArchive = async () => {
    try {
      await updateMemoryState(selectedMemoryIds, "archived");
      toast.success(`${selectedMemoryIds.length} memory(s) archived`);
      dispatch(clearSelection());
      await refreshMemories();
    } catch {
      toast.error("Failed to archive memories");
    }
  };

  const handleBulkPause = async () => {
    try {
      await updateMemoryState(selectedMemoryIds, "paused");
      toast.success(`${selectedMemoryIds.length} memory(s) paused`);
      dispatch(clearSelection());
      await refreshMemories();
    } catch {
      toast.error("Failed to pause memories");
    }
  };

  const handleBulkDelete = async () => {
    try {
      await deleteMemories(selectedMemoryIds);
      toast.success(`${selectedMemoryIds.length} memory(s) deleted`);
      dispatch(clearSelection());
      await refreshMemories();
    } catch {
      toast.error("Failed to delete memories");
    }
  };

  const handleClearSelection = () => {
    dispatch(clearSelection());
  };

  if (isLoading) {
    return (
      <div className="w-full bg-transparent">
        <MemoryTableSkeleton />
        <div className="flex items-center justify-between mt-4">
          <div className="h-8 w-32 bg-zinc-800 rounded animate-pulse" />
          <div className="h-8 w-48 bg-zinc-800 rounded animate-pulse" />
          <div className="h-8 w-32 bg-zinc-800 rounded animate-pulse" />
        </div>
      </div>
    );
  }

  return (
    <div className="w-full bg-transparent">
      <div>
        {memories.length > 0 ? (
          <>
            {selectedMemoryIds.length > 0 && (
              <div className="flex items-center gap-3 bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 mb-3 animate-fade-slide-down">
                <span className="text-sm text-zinc-300">{selectedMemoryIds.length} selected</span>
                <div className="h-4 w-px bg-zinc-600" />
                <Button variant="ghost" size="sm" onClick={handleBulkArchive}>
                  <Archive className="h-4 w-4 mr-1" /> Archive
                </Button>
                <Button variant="ghost" size="sm" onClick={handleBulkPause}>
                  <Pause className="h-4 w-4 mr-1" /> Pause
                </Button>
                <Button variant="ghost" size="sm" className="text-red-400 hover:text-red-300" onClick={handleBulkDelete}>
                  <Trash2 className="h-4 w-4 mr-1" /> Delete
                </Button>
                <div className="flex-1" />
                <Button variant="ghost" size="sm" onClick={handleClearSelection}>
                  Clear
                </Button>
              </div>
            )}
            <MemoryTable />
            <div className="flex flex-col sm:flex-row items-center justify-between mt-4 gap-3">
              <PageSizeSelector
                pageSize={itemsPerPage}
                onPageSizeChange={handlePageSizeChange}
              />
              <div className="text-sm text-zinc-500 whitespace-nowrap">
                Showing {(currentPage - 1) * itemsPerPage + 1} to{" "}
                {Math.min(currentPage * itemsPerPage, totalItems)} of{" "}
                {totalItems} memories
              </div>
              <MemoryPagination
                currentPage={currentPage}
                totalPages={totalPages}
                setCurrentPage={setCurrentPage}
              />
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="rounded-full bg-zinc-800 p-3 mb-4">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="h-6 w-6 text-zinc-400"
              >
                <path d="M21 9v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7"></path>
                <path d="M16 2v6h6"></path>
                <path d="M12 18v-6"></path>
                <path d="M9 15h6"></path>
              </svg>
            </div>
            <h3 className="text-lg font-medium">No memories found</h3>
            <p className="text-zinc-400 mt-1 mb-4">
              {selectedCategory !== "all" || selectedClient !== "all"
                ? "Try adjusting your filters"
                : "Create your first memory to see it here"}
            </p>
            {selectedCategory !== "all" || selectedClient !== "all" ? (
              <Button
                variant="outline"
                onClick={() => {
                  setSelectedCategory("all");
                  setSelectedClient("all");
                }}
              >
                Clear Filters
              </Button>
            ) : (
              <CreateMemoryDialog />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
