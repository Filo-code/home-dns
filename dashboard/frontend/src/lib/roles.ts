import type { Role } from "../api/types";

export function isAdmin(role: Role | null): boolean {
  return role === "admin";
}
