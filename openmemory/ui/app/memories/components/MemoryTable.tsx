import {
  Edit,
  MoreHorizontal,
  Trash2,
  Pause,
  Archive,
  Play,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import { useMemoriesApi } from "@/hooks/useMemoriesApi";
import { useDispatch, useSelector } from "react-redux";
import { RootState } from "@/store/store";
import {
  selectMemory,
  deselectMemory,
  selectAllMemories,
  clearSelection,
} from "@/store/memoriesSlice";
import SourceApp from "@/components/shared/source-app";
import { HiMiniRectangleStack } from "react-icons/hi2";
import { PiSwatches } from "react-icons/pi";
import { GoPackage } from "react-icons/go";
import { CiCalendar } from "react-icons/ci";
import { TbWorldSearch } from "react-icons/tb";
import { FiUser } from "react-icons/fi";
import { LuBrainCircuit, LuBot } from "react-icons/lu";
import { useRouter } from "next/navigation";
import Categories from "@/components/shared/categories";
import { useUI } from "@/hooks/useUI";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatDate } from "@/lib/helpers";

export function MemoryTable() {
  const router = useRouter();
  const dispatch = useDispatch();
  const selectedMemoryIds = useSelector(
    (state: RootState) => state.memories.selectedMemoryIds
  );
  const memories = useSelector((state: RootState) => state.memories.memories);

  const { deleteMemories, updateMemoryState, isLoading } = useMemoriesApi();

  const handleDeleteMemory = async (id: string) => {
    try {
      await deleteMemories([id]);
      toast.success("Memory deleted");
    } catch {
      toast.error("Failed to delete memory");
    }
  };

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      dispatch(selectAllMemories());
    } else {
      dispatch(clearSelection());
    }
  };

  const handleSelectMemory = (id: string, checked: boolean) => {
    if (checked) {
      dispatch(selectMemory(id));
    } else {
      dispatch(deselectMemory(id));
    }
  };
  const { handleOpenUpdateMemoryDialog } = useUI();

  const handleEditMemory = (memory_id: string, memory_content: string) => {
    handleOpenUpdateMemoryDialog(memory_id, memory_content);
  };

  const handleUpdateMemoryState = async (id: string, newState: string) => {
    try {
      await updateMemoryState([id], newState);
      toast.success(`Memory ${newState}`);
    } catch {
      toast.error("Failed to update memory state");
    }
  };

  const isAllSelected =
    memories.length > 0 && selectedMemoryIds.length === memories.length;
  const isPartiallySelected =
    selectedMemoryIds.length > 0 && selectedMemoryIds.length < memories.length;

  const handleMemoryClick = (id: string) => {
    router.push(`/memory/${id}`);
  };

  return (
    <div className="rounded-md border">
      <Table className="">
        <TableHeader>
          <TableRow className="bg-zinc-800 hover:bg-zinc-800">
            <TableHead className="w-[50px] pl-4">
              <Checkbox
                className="data-[state=checked]:border-primary border-zinc-500/50"
                checked={isAllSelected}
                data-state={
                  isPartiallySelected
                    ? "indeterminate"
                    : isAllSelected
                    ? "checked"
                    : "unchecked"
                }
                onCheckedChange={handleSelectAll}
              />
            </TableHead>
            <TableHead className="border-zinc-700">
              <div className="flex items-center min-w-[300px]">
                <HiMiniRectangleStack className="mr-1" />
                Memory
              </div>
            </TableHead>
            <TableHead className="border-zinc-700">
              <div className="flex items-center whitespace-nowrap">
                <PiSwatches className="mr-1" size={15} />
                Categories
              </div>
            </TableHead>
            <TableHead className="border-zinc-700">
              <div className="flex items-center whitespace-nowrap">
                <TbWorldSearch className="mr-1" size={15} />
                Domain
              </div>
            </TableHead>
            <TableHead className="border-zinc-700">
              <div className="flex items-center whitespace-nowrap">
                <LuBrainCircuit className="mr-1" size={14} />
                Type
              </div>
            </TableHead>
            <TableHead className="border-zinc-700">
              <div className="flex items-center whitespace-nowrap">
                <LuBot className="mr-1" size={14} />
                Agent
              </div>
            </TableHead>
            <TableHead className="border-zinc-700">
              <div className="flex items-center whitespace-nowrap">
                <FiUser className="mr-1" size={14} />
                Created By
              </div>
            </TableHead>
            <TableHead className="border-zinc-700">
              <div className="flex items-center whitespace-nowrap">
                <GoPackage className="mr-1" />
                Source App
              </div>
            </TableHead>
            <TableHead className="border-zinc-700">
              <div className="flex items-center whitespace-nowrap">
                <CiCalendar className="mr-1" size={16} />
                Created On
              </div>
            </TableHead>
            <TableHead className="text-right border-zinc-700 flex justify-center">
              <div className="flex items-center justify-end">
                <MoreHorizontal className="h-4 w-4 mr-2" />
              </div>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {memories.map((memory) => (
            <TableRow
              key={memory.id}
              className={`hover:bg-zinc-900/50 ${
                memory.state === "paused" || memory.state === "archived"
                  ? "text-zinc-400"
                  : ""
              } ${isLoading ? "animate-pulse opacity-50" : ""}`}
            >
              <TableCell className="pl-4">
                <Checkbox
                  className="data-[state=checked]:border-primary border-zinc-500/50"
                  checked={selectedMemoryIds.includes(memory.id)}
                  onCheckedChange={(checked) =>
                    handleSelectMemory(memory.id, checked as boolean)
                  }
                />
              </TableCell>
              <TableCell className="">
                {memory.state === "paused" || memory.state === "archived" ? (
                  <TooltipProvider>
                    <Tooltip delayDuration={0}>
                      <TooltipTrigger asChild>
                        <div
                          onClick={() => handleMemoryClick(memory.id)}
                          className={`font-medium ${
                            memory.state === "paused" ||
                            memory.state === "archived"
                              ? "text-zinc-400"
                              : "text-white"
                          } cursor-pointer`}
                        >
                          {memory.memory}
                        </div>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>
                          This memory is{" "}
                          <span className="font-bold">
                            {memory.state === "paused" ? "paused" : "archived"}
                          </span>{" "}
                          and <span className="font-bold">disabled</span>.
                        </p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                ) : (
                  <div
                    onClick={() => handleMemoryClick(memory.id)}
                    className={`font-medium text-white cursor-pointer`}
                  >
                    {memory.memory}
                  </div>
                )}
              </TableCell>
              <TableCell className="">
                <div className="flex flex-wrap gap-1">
                  <Categories
                    categories={memory.categories}
                    isPaused={
                      memory.state === "paused" || memory.state === "archived"
                    }
                    concat={true}
                  />
                </div>
              </TableCell>
              <TableCell className="text-center whitespace-nowrap">
                <span className={`text-xs px-2 py-0.5 rounded-full border ${
                  memory.state === "paused" || memory.state === "archived"
                    ? "border-zinc-700 text-zinc-500"
                    : "border-zinc-600 text-zinc-300"
                }`}>
                  {memory.domain}
                </span>
              </TableCell>
              <TableCell className="text-center whitespace-nowrap">
                {memory.memory_type ? (
                  <span className={`text-xs px-2 py-0.5 rounded-full border ${
                    {
                      fact: "border-blue-600/50 text-blue-400 bg-blue-950/30",
                      preference: "border-purple-600/50 text-purple-400 bg-purple-950/30",
                      session: "border-yellow-600/50 text-yellow-400 bg-yellow-950/30",
                      episodic: "border-green-600/50 text-green-400 bg-green-950/30",
                    }[memory.memory_type] || "border-zinc-600 text-zinc-400"
                  }`}>
                    {memory.memory_type}
                  </span>
                ) : (
                  <span className="text-xs text-zinc-600">—</span>
                )}
              </TableCell>
              <TableCell className="text-center whitespace-nowrap">
                {memory.agent_id ? (
                  <span className="text-xs px-2 py-0.5 rounded-full border border-zinc-600 text-zinc-300 bg-zinc-800/50">
                    {memory.agent_id}
                  </span>
                ) : (
                  <span className="text-xs text-zinc-600">—</span>
                )}
              </TableCell>
              <TableCell className="whitespace-nowrap">
                <span className="text-sm text-zinc-300">
                  {memory.created_by || "-"}
                </span>
              </TableCell>
              <TableCell className="text-center whitespace-nowrap">
                <SourceApp source={memory.app_name} />
              </TableCell>
              <TableCell className="text-center whitespace-nowrap">
                {formatDate(memory.created_at)}
              </TableCell>
              <TableCell className="text-right flex justify-center">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-8 w-8">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="end"
                    className="bg-zinc-900 border-zinc-800"
                  >
                    <DropdownMenuItem
                      className="cursor-pointer"
                      onClick={() => {
                        const newState =
                          memory.state === "active" ? "paused" : "active";
                        handleUpdateMemoryState(memory.id, newState);
                      }}
                    >
                      {memory?.state === "active" ? (
                        <>
                          <Pause className="mr-2 h-4 w-4" />
                          Pause
                        </>
                      ) : (
                        <>
                          <Play className="mr-2 h-4 w-4" />
                          Resume
                        </>
                      )}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      className="cursor-pointer"
                      onClick={() => {
                        const newState =
                          memory.state === "active" ? "archived" : "active";
                        handleUpdateMemoryState(memory.id, newState);
                      }}
                    >
                      <Archive className="mr-2 h-4 w-4" />
                      {memory?.state !== "archived" ? (
                        <>Archive</>
                      ) : (
                        <>Unarchive</>
                      )}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      className="cursor-pointer"
                      onClick={() => handleEditMemory(memory.id, memory.memory)}
                    >
                      <Edit className="mr-2 h-4 w-4" />
                      Edit
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="cursor-pointer text-red-500 focus:text-red-500"
                      onClick={() => handleDeleteMemory(memory.id)}
                    >
                      <Trash2 className="mr-2 h-4 w-4" />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
