import { usePathname } from "next/navigation";

const GLOBAL_ROUTES = ["/login", "/change-password", "/settings", "/invite", "/admin", "/api-keys"];

export function useProjectSlug(): string {
  const pathname = usePathname();
  if (GLOBAL_ROUTES.some((r) => pathname === r || pathname.startsWith(r + "/"))) return "";
  const seg = pathname.split("/").filter(Boolean);
  return seg.length > 0 ? seg[0] : "";
}
