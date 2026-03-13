export type Category = "personal" | "work" | "health" | "finance" | "travel" | "education" | "preferences" | "relationships"
export type Client = "chrome" | "chatgpt" | "cursor" | "windsurf" | "terminal" | "api"
export type MemoryType = "fact" | "preference" | "session" | "episodic"

export interface Memory {
  id: string
  memory: string
  metadata: any
  client: Client
  categories: Category[]
  created_at: number
  app_name: string
  created_by: string | null
  domain: string
  state: "active" | "paused" | "archived" | "deleted"
  memory_type?: MemoryType | null
  agent_id?: string | null
  run_id?: string | null
  expires_at?: string | null
}